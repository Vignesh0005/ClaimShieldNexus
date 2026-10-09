"""Per-prediction feature attributions.

XGBoost computes exact TreeSHAP values natively (`pred_contribs=True`), so the `shap` package is
not required at scoring time. Values are in log-odds units: positive pushes the score up."""
import numpy as np


def tree_shap(booster, row: list[float], feature_names: list[str]) -> dict[str, float]:
    import xgboost as xgb

    contribs = booster.predict(xgb.DMatrix(np.array([row], dtype=float), feature_names=feature_names), pred_contribs=True)[0]
    return {name: float(v) for name, v in zip(feature_names, contribs[:-1])}  # last column is the bias term


def top_features(shap_values: dict[str, float], features: dict[str, float], k: int = 5) -> list[dict]:
    ranked = sorted(shap_values.items(), key=lambda kv: kv[1], reverse=True)
    return [{"feature": name, "shap": round(value, 3), "value": features.get(name)} for name, value in ranked[:k] if value > 0]
