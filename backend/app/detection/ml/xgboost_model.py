from pathlib import Path

import numpy as np

from app.detection.ml.shap_explainer import tree_shap


class XGBoostModel:
    """Primary classifier. Trained on reviewer labels (1 = confirmed for referral)."""

    def __init__(self, path: Path, feature_names: list[str]):
        import xgboost as xgb

        self.feature_names = feature_names
        self.booster = xgb.Booster()
        self.booster.load_model(str(path))

    def predict_proba(self, row: list[float]) -> float:
        import xgboost as xgb

        return float(self.booster.predict(xgb.DMatrix(np.array([row], dtype=float), feature_names=self.feature_names))[0])

    def explain(self, row: list[float]) -> dict[str, float]:
        return tree_shap(self.booster, row, self.feature_names)
