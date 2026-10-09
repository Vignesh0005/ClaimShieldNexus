import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import AuditLogger
from app.core.exceptions import ValidationFailed
from app.core.security import Principal
from app.db.base import utcnow
from app.models import Case, DetectionSignal, ModelFeedback, Tenant
from app.schemas.feedback import FeedbackIn
from app.services import case_service

LABELS = {"confirmed_fraud": 1, "false_positive": 0, "needs_info": None}


def retrain_threshold(tenant: Tenant) -> int:
    return int((tenant.config or {}).get("retrain_threshold", get_settings().retrain_threshold))


async def queue_size(db: AsyncSession, tenant_id: uuid.UUID) -> int:
    return (await db.execute(select(func.count()).select_from(ModelFeedback).where(ModelFeedback.tenant_id == tenant_id, ModelFeedback.used_in_training.is_(False), ModelFeedback.final_label.isnot(None)))).scalar_one()


def reward(final_label: int | None, risk_score: float | None) -> float:
    """+1 when the model's routing agreed with the reviewer, -1 when it did not, 0 when the
    reviewer has not reached a conclusion."""
    if final_label is None or risk_score is None:
        return 0.0
    return 1.0 if (risk_score >= 0.5) == bool(final_label) else -1.0


async def submit(db: AsyncSession, tenant: Tenant, body: FeedbackIn, principal: Principal, request=None) -> dict:
    case = await case_service.get(db, tenant.id, body.case_id)
    claims = await case_service.claims_of(db, case)
    if not claims:
        raise ValidationFailed("This case has no claims to attach feedback to.")
    top = claims[0]
    label = body.final_label if body.final_label is not None else LABELS[body.decision]
    if body.final_label is not None and LABELS[body.decision] is not None and body.final_label != LABELS[body.decision]:
        raise ValidationFailed("final_label does not match the decision.", decision=body.decision, final_label=body.final_label)
    xgb = (await db.execute(select(DetectionSignal.score).where(DetectionSignal.tenant_id == tenant.id, DetectionSignal.claim_id == top.id, DetectionSignal.model_name == "xgboost"))).scalar_one_or_none()
    count = (await db.execute(select(func.count()).select_from(ModelFeedback).where(ModelFeedback.tenant_id == tenant.id))).scalar_one()
    entry = ModelFeedback(
        tenant_id=tenant.id, feedback_id=f"FB-{utcnow().year}-{count + 1:05d}", claim_id=top.id, case_id=case.id, model_version=top.model_version,
        fraud_probability=xgb, risk_score=top.risk_score, human_decision=body.decision, final_label=label,
        reviewer_id=principal.user_id, reviewer_label=principal.subject, notes=body.notes, time_spent_seconds=body.time_spent_seconds,
        features=(top.attributes or {}).get("_features"),
    )
    db.add(entry)
    await AuditLogger(db).log("feedback.submitted", "case", case.case_id, principal=principal, details={"decision": body.decision, "final_label": label, "feedback_id": entry.feedback_id}, request=request)
    await db.flush()

    size, threshold = await queue_size(db, tenant.id), retrain_threshold(tenant)
    triggered = size >= threshold
    remaining = max(threshold - size, 0)
    return {
        "feedback_id": entry.feedback_id, "case_id": case.case_id, "reward": reward(label, top.risk_score),
        "training_queue_size": size, "retrain_threshold": threshold, "retrain_triggered": triggered,
        "message": "Feedback logged. Enough decisions have accumulated; a candidate model will be trained for review." if triggered else f"Feedback logged. {remaining} more decisions needed to trigger retraining.",
    }


async def queue_status(db: AsyncSession, tenant: Tenant) -> dict:
    size, threshold = await queue_size(db, tenant.id), retrain_threshold(tenant)
    labels = dict((await db.execute(select(ModelFeedback.final_label, func.count()).where(ModelFeedback.tenant_id == tenant.id, ModelFeedback.used_in_training.is_(False)).group_by(ModelFeedback.final_label))).all())
    return {
        "training_queue_size": size, "retrain_threshold": threshold, "ready_to_retrain": size >= threshold,
        "confirmed": labels.get(1, 0), "false_positive": labels.get(0, 0), "undecided": labels.get(None, 0),
    }


async def list_feedback(db: AsyncSession, tenant_id: uuid.UUID, limit: int = 100) -> list[dict]:
    rows = (await db.execute(select(ModelFeedback, Case.case_id).outerjoin(Case, Case.id == ModelFeedback.case_id).where(ModelFeedback.tenant_id == tenant_id).order_by(ModelFeedback.reviewed_at.desc()).limit(limit))).all()
    return [
        {"feedback_id": f.feedback_id, "case_id": case_id, "decision": f.human_decision, "final_label": f.final_label, "reviewer": f.reviewer_label, "risk_score": f.risk_score, "model_version": f.model_version, "notes": f.notes, "reviewed_at": f.reviewed_at, "used_in_training": f.used_in_training}
        for f, case_id in rows
    ]
