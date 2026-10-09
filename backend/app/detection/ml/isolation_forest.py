from pathlib import Path

import joblib
import numpy as np

ANOMALY_THRESHOLD = 0.8
SCORE_CEILING = 0.99


def calibrated_score(raw, *, low: float, high: float, method: str = "linear"):
    """Anomaly index, not fraud probability. Legacy artifacts retain their old mapping."""
    values = np.asarray(raw, dtype=float)
    if method == "heldout_log_logistic_v1":
        # low/high are log1p(raw) median/97th percentile of held-out normal claims.
        # Anchors: median -> .30; 97th percentile -> .80. Log compresses LOF's long tail.
        lo_logit = np.log(0.30 / (SCORE_CEILING - 0.30))
        hi_logit = np.log(ANOMALY_THRESHOLD / (SCORE_CEILING - ANOMALY_THRESHOLD))
        z = lo_logit + (np.log1p(np.maximum(values, 0)) - low) * (hi_logit - lo_logit) / max(high - low, 1e-6)
        # logaddexp keeps the smooth sigmoid numerically stable for extreme raw scores.
        return SCORE_CEILING * np.exp(-np.logaddexp(0, -z))
    if method != "linear":
        raise ValueError(f"Unknown anomaly calibration method: {method}")
    return np.clip((values - low) / max(high - low, 1e-9), 0.0, 1.0)


class OutlierModel:
    """Unsupervised detector with versioned calibration fitted on held-out normals."""

    def __init__(self, path: Path, low: float, high: float, method: str = "linear"):
        bundle = joblib.load(path)
        self.scaler = bundle["scaler"]
        self.model = bundle["model"]
        self.low, self.high, self.method = low, high, method

    def score(self, row: list[float]) -> float:
        raw = -float(self.model.score_samples(self.scaler.transform(np.array([row], dtype=float)))[0])
        return float(calibrated_score(raw, low=self.low, high=self.high, method=self.method))


IsolationForestModel = OutlierModel
