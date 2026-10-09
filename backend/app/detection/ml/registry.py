import json
from pathlib import Path

from app.config import get_settings
from app.core.exceptions import MLServerUnavailable
from app.core.logging import logger
from app.detection.context import DetectionContext, Signal, severity_for
from app.detection.ml.feature_engineering import build_features, to_row
from app.detection.ml.isolation_forest import ANOMALY_THRESHOLD, OutlierModel
from app.detection.ml.remote_client import MLPrediction, RemoteMLClient
from app.detection.ml.shap_explainer import top_features
from app.detection.ml.xgboost_model import XGBoostModel

FALLBACK_VERSION = "fallback_rules_only"
SIGNAL_THRESHOLD = 0.5
# Outlier detectors fire only on the most unusual claims; a lower bar floods reviewers with noise.


class ModelRegistry:
    """Loads the deployed model version from the artifacts directory (written by training)."""

    def __init__(self, artifacts_dir: str | None = None):
        self.dir = Path(artifacts_dir or get_settings().artifacts_dir)
        self.version: str | None = None
        self.meta: dict = {}
        self.xgb: XGBoostModel | None = None
        self.iforest: OutlierModel | None = None
        self.lof: OutlierModel | None = None

    def current_version(self) -> str | None:
        pointer = self.dir / "CURRENT"
        return pointer.read_text(encoding="utf-8").strip() if pointer.exists() else None

    def load(self, version: str | None = None) -> bool:
        version = version or self.current_version()
        if not version or not (self.dir / version / "meta.json").exists():
            self.version = None
            return False
        if version == self.version:
            return True
        path = self.dir / version
        try:
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            self.xgb = XGBoostModel(path / "xgboost.json", meta["features"])
            cal = meta["calibration"]
            self.iforest = OutlierModel(path / "isolation_forest.joblib", **cal["isolation_forest"])
            self.lof = OutlierModel(path / "lof.joblib", **cal["lof"])
            self.meta, self.version = meta, version
            logger.info("model_loaded", version=version)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("model_load_failed", version=version, error=str(exc))
            self.version = None
            return False

    def predict(self, features: dict[str, float]) -> MLPrediction:
        if not self.load():
            return MLPrediction(fraud_probability=None, degraded=True)
        assert self.xgb and self.iforest and self.lof
        row = to_row(features, self.meta["features"])
        return MLPrediction(
            fraud_probability=round(self.xgb.predict_proba(row), 4),
            anomaly_score=round(self.iforest.score(row), 4),
            lof_score=round(self.lof.score(row), 4),
            top_features=top_features(self.xgb.explain(row), features),
            model_version=f"xgb_{self.version}",
        )


registry = ModelRegistry()
_remote: RemoteMLClient | None = None


def remote_client() -> RemoteMLClient | None:
    global _remote
    settings = get_settings()
    if not settings.ml_server_url:
        return None
    if _remote is None or _remote.base_url != settings.ml_server_url.rstrip("/"):
        _remote = RemoteMLClient(settings.ml_server_url, settings.ml_server_timeout)
    return _remote


class MLEngine:
    """Scores a claim. Order of preference: remote model server, local artifacts, rules only.
    Degrading never fails the claim: it is processed with the detectors that are available and the
    result records that ML was not used."""

    async def predict(self, features: dict[str, float]) -> MLPrediction:
        client = remote_client()
        if client is not None:
            try:
                return await client.predict(features)
            except MLServerUnavailable:
                if not get_settings().ml_fallback_enabled:
                    raise
                logger.warning("ml_unavailable_falling_back", to="local artifacts or rules only")
        prediction = registry.predict(features)
        if client is not None:
            prediction.degraded = True
        return prediction

    async def run_all(self, ctx: DetectionContext) -> tuple[list[Signal], dict[str, float], MLPrediction]:
        features = build_features(ctx)
        prediction = await self.predict(features)
        signals: list[Signal] = []
        if prediction.fraud_probability is not None and prediction.fraud_probability >= SIGNAL_THRESHOLD:
            signals.append(
                Signal(
                    "ml", "xgboost", prediction.fraud_probability, severity=severity_for(prediction.fraud_probability),
                    evidence={"model": prediction.model_version, "top_features": prediction.top_features},
                    source_fields=[f["feature"] for f in prediction.top_features],
                )
            )
        for name, score in (("isolation_forest", prediction.anomaly_score), ("lof", prediction.lof_score)):
            if score is not None and score >= ANOMALY_THRESHOLD:
                signals.append(
                    Signal("ml", name, score, severity="medium", evidence={"model": name, "meaning": "Anomaly index calibrated against held-out normal claims. Unusualness is not fraud probability; anomaly-only severity is capped at medium."})
                )
        return signals, features, prediction
