import uuid
from datetime import datetime
from pathlib import Path

import anyio
import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import metrics
from app.core.audit import AuditLogger
from app.core.exceptions import NotFound, ValidationFailed
from app.core.security import Principal
from app.detection.ml.feature_engineering import FEATURES, to_row
from app.detection.ml.registry import registry
from app.detection.ml.training import SYNTHETIC_WARNING, set_current, train_models
from app.models import ModelFeedback, ModelVersion

INTENDED_USE = (
    "Ranks healthcare claims and provider clusters for human review by a Special Investigations Unit. "
    "A score indicates how closely a claim resembles patterns reviewers have referred before. It is not a finding of fraud, waste or abuse."
)
OUT_OF_SCOPE = [
    "Automatically denying, pending or recouping claims",
    "Decisions about a member's eligibility or care",
    "Use without review by a qualified investigator",
]
LIMITATIONS = [
    "Trained on synthetic claims with planted patterns; performance on production claims is unverified.",
    "Reported metrics are high because the planted patterns are easy to separate. They are not a forecast of real-world accuracy.",
    "The model relies heavily on provider volume features, so it partly recognises busy providers instead of billing behaviour. See the provider-split figures.",
    "Peer comparison uses specialty only and does not adjust for case mix or practice size.",
    "Labels come from planted patterns and reviewer decisions, which can carry reviewer bias.",
    "No bias audit across provider or member groups has been run on real data.",
]


async def register(db: AsyncSession, meta: dict, artifact_path: str, deployed: bool = False, notes: str | None = None) -> ModelVersion:
    row = (await db.execute(select(ModelVersion).where(ModelVersion.version == meta["version"]))).scalar_one_or_none()
    if row is None:
        row = ModelVersion(version=meta["version"])
        db.add(row)
    m = meta["metrics"]
    row.model_type, row.trained_at, row.training_samples = meta["model_type"], datetime.fromisoformat(meta["trained_at"]), meta["training_samples"]
    row.precision, row.recall, row.f1, row.roc_auc, row.pr_auc = m["precision"], m["recall"], m["f1"], m["roc_auc"], m["pr_auc"]
    row.false_positive_rate, row.false_negative_rate = m["false_positive_rate"], m["false_negative_rate"]
    row.confusion_matrix, row.hyperparameters, row.feature_importance = meta["confusion_matrix"], meta["hyperparameters"], meta["feature_importance"]
    row.evaluation = {**(meta.get("evaluation") or {}), "bias_analysis": meta.get("bias_analysis", []), "training_data_kind": meta.get("training_data_kind", "synthetic"), "anomaly_evaluation": meta.get("anomaly_evaluation", {})}
    row.artifact_path, row.notes = artifact_path, notes or row.notes
    if deployed:
        await db.execute(update(ModelVersion).values(is_deployed=False))
        row.is_deployed = True
    await db.flush()
    return row


async def list_versions(db: AsyncSession) -> list[ModelVersion]:
    return list((await db.execute(select(ModelVersion).order_by(ModelVersion.trained_at.desc()))).scalars().all())


async def get(db: AsyncSession, version: str) -> ModelVersion:
    row = (await db.execute(select(ModelVersion).where(ModelVersion.version == version))).scalar_one_or_none()
    if row is None:
        raise NotFound(f"Model version '{version}' not found.")
    return row


def summary(m: ModelVersion) -> dict:
    return {"version": m.version, "model_type": m.model_type, "trained_at": m.trained_at, "training_samples": m.training_samples, "f1": m.f1, "precision": m.precision, "recall": m.recall, "roc_auc": m.roc_auc, "pr_auc": m.pr_auc, "is_deployed": m.is_deployed, "notes": m.notes}


def model_warning(model_version: str | None) -> str | None:
    """Label attached to every prediction from a model trained on synthetic data. Every model this
    codebase can train starts from the synthetic base set, so every real model version carries it."""
    if not model_version or model_version.startswith("fallback"):
        return None
    return SYNTHETIC_WARNING


def card(m: ModelVersion) -> dict:
    evaluation = dict(m.evaluation or {})
    bias = evaluation.pop("bias_analysis", [])
    evaluation.pop("training_data_kind", None)
    return {
        **summary(m),
        "model_name": "ClaimShield FWA classifier",
        "warning": SYNTHETIC_WARNING,
        "evaluation": evaluation or {"random_split": {"precision": m.precision, "recall": m.recall, "f1": m.f1, "roc_auc": m.roc_auc, "pr_auc": m.pr_auc}, "provider_split": None, "note": "Provider-split evaluation was not run for this version."},
        "bias_analysis": bias,
        "fairness": "Not yet measured. No analysis of score or false-positive differences across provider groups (rural or urban, solo or group practice) or member groups (age, income area) has been run.",
        "false_positive_rate": m.false_positive_rate, "false_negative_rate": m.false_negative_rate, "confusion_matrix": m.confusion_matrix,
        "hyperparameters": m.hyperparameters, "feature_importance": m.feature_importance, "features": list(FEATURES),
        "intended_use": INTENDED_USE, "out_of_scope": OUT_OF_SCOPE, "limitations": LIMITATIONS,
        "training_data": "Synthetic claims with planted billing patterns, plus reviewer decisions recorded in this system. No real claims or protected health information.",
        "explainability": "Per-claim feature attributions from TreeSHAP; companion isolation forest and local outlier factor anomaly scores.",
    }


async def deploy(db: AsyncSession, version: str, principal: Principal, request=None) -> ModelVersion:
    """Promotes a version to live scoring. Always a deliberate human action; retraining only ever
    produces a candidate."""
    row = await get(db, version)
    directory = Path(get_settings().artifacts_dir)
    if not (directory / version / "meta.json").exists():
        raise ValidationFailed(f"Artifacts for model version '{version}' are not on this server.")
    await db.execute(update(ModelVersion).values(is_deployed=False))
    row.is_deployed = True
    set_current(directory, version)
    registry.load(version)
    if row.f1 is not None:
        metrics.model_f1.labels(version).set(row.f1)
    await AuditLogger(db).log("model.deployed", "model", version, principal=principal, details={"f1": row.f1, "roc_auc": row.roc_auc}, request=request)
    await db.flush()
    return row


async def retrain(db: AsyncSession, tenant_id: uuid.UUID | None = None, actor: str = "system") -> dict:
    """Trains a candidate from the synthetic base set plus reviewer feedback not yet used. The
    candidate is registered but not deployed."""
    from app.db.seed.synthetic import training_matrix_with_groups

    where = [ModelFeedback.used_in_training.is_(False), ModelFeedback.final_label.isnot(None), ModelFeedback.features.isnot(None)]
    if tenant_id:
        where.append(ModelFeedback.tenant_id == tenant_id)
    rows = list((await db.execute(select(ModelFeedback).where(*where))).scalars().all())
    X, y, groups = await anyio.to_thread.run_sync(training_matrix_with_groups)
    usable = [f for f in rows if f.features]
    if usable:
        # Reviewer decisions are scarcer and more trustworthy than planted labels: weight them up.
        fx = np.array([to_row(f.features, FEATURES) for f in usable] * 5, dtype=float)
        fy = np.array([f.final_label for f in usable] * 5, dtype=int)
        X, y = np.vstack([X, fx]), np.concatenate([y, fy])
        groups = np.concatenate([groups, np.array(["reviewer-feedback"] * len(fy))])
    existing = await list_versions(db)
    version = f"v1.{len(existing)}.{len(usable)}"
    directory = Path(get_settings().artifacts_dir)
    meta = await anyio.to_thread.run_sync(lambda: train_models(X, y, version, directory, groups=groups))
    await register(db, meta, str(directory / version), deployed=False, notes=f"Candidate trained with {len(usable)} reviewer decisions. Awaiting review before deployment.")
    batch = uuid.uuid4()
    for f in usable:
        f.used_in_training, f.training_batch_id = True, batch
    await AuditLogger(db).log("model.retrained", "model", version, tenant_id=tenant_id, actor_label=actor, details={"feedback_used": len(usable), **meta["metrics"]})
    await db.flush()
    return {"version": version, "feedback_used": len(usable), "training_samples": meta["training_samples"], "metrics": meta["metrics"], "evaluation": meta["evaluation"], "warning": SYNTHETIC_WARNING, "deployed": False}
