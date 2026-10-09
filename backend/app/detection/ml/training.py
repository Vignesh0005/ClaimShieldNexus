"""Model training, shared by scripts/train_xgboost.py and the retraining worker task."""
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from app.detection.ml.feature_engineering import FEATURES
from app.detection.ml.isolation_forest import ANOMALY_THRESHOLD, calibrated_score

HYPERPARAMETERS = {"n_estimators": 220, "max_depth": 4, "learning_rate": 0.08, "subsample": 0.9, "colsample_bytree": 0.9, "eval_metric": "aucpr"}


VOLUME_FEATURES = {"provider_members_30d", "provider_claims_30d", "provider_avg_claim", "provider_peer_ratio"}
SYNTHETIC_WARNING = "Synthetic-trained model. Not validated for production use."


def _metrics(y_true: np.ndarray, proba: np.ndarray) -> dict:
    from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    both = len(set(y_true.tolist())) > 1
    return {
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y_true, proba)), 4) if both else None,
        "false_positive_rate": round(float(fp / max(fp + tn, 1)), 4),
        "false_negative_rate": round(float(fn / max(fn + tp, 1)), 4),
        "test_claims": int(len(y_true)),
        "test_positives": int(y_true.sum()),
    }


def provider_split_evaluation(X: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int = 7, folds: int = 5) -> dict | None:
    """Out-of-fold predictions where every claim is scored by a model that never saw its
    provider (each fold holds out about 20% of providers). This is the honest generalisation
    figure: a random split lets the model recognise providers it trained on."""
    import xgboost as xgb
    from sklearn.model_selection import GroupKFold

    providers = np.unique(groups)
    positive_providers = np.unique(groups[y == 1])
    if len(providers) < folds or len(positive_providers) < 2:
        return None
    proba = np.zeros(len(y), dtype=float)
    used = 0
    for train_idx, test_idx in GroupKFold(n_splits=folds).split(X, y, groups):
        if y[train_idx].sum() == 0:
            continue
        positives = max(int(y[train_idx].sum()), 1)
        clf = xgb.XGBClassifier(**HYPERPARAMETERS, random_state=seed, scale_pos_weight=(len(train_idx) - positives) / positives)
        clf.fit(X[train_idx], y[train_idx])
        proba[test_idx] = clf.predict_proba(X[test_idx])[:, 1]
        used += 1
    return {**_metrics(y, proba), "folds": used, "providers": int(len(providers)), "providers_with_planted_patterns": int(len(positive_providers)), "method": f"GroupKFold by provider, {folds} folds, pooled out-of-fold predictions"}


def train_models(X: np.ndarray, y: np.ndarray, version: str, out_dir: Path, seed: int = 7, groups: np.ndarray | None = None) -> dict:
    """Trains the classifier and both outlier detectors, writes artifacts to out_dir/version and
    returns the metadata: metrics on a random 25% split and, when providers are supplied, on
    providers held out of training."""
    import xgboost as xgb
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=seed, stratify=y)
    positives = max(int(y_train.sum()), 1)
    clf = xgb.XGBClassifier(**HYPERPARAMETERS, random_state=seed, scale_pos_weight=(len(y_train) - positives) / positives)
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()

    target = out_dir / version
    target.mkdir(parents=True, exist_ok=True)
    clf.get_booster().feature_names = list(FEATURES)
    clf.get_booster().save_model(str(target / "xgboost.json"))

    scaler = StandardScaler().fit(X_train)
    normal = scaler.transform(X_train[y_train == 0])
    # Both partitions are disjoint from detector/scaler fitting and from each other.
    calibration_rows, validation_rows = train_test_split(X_test[y_test == 0], test_size=0.5, random_state=seed)
    calibration = {}
    anomaly_evaluation = {}
    for name, model in (
        ("isolation_forest", IsolationForest(n_estimators=64, contamination="auto", random_state=seed)),
        ("lof", LocalOutlierFactor(n_neighbors=25, novelty=True)),
    ):
        model.fit(normal)
        raw = -model.score_samples(scaler.transform(calibration_rows))
        log_raw = np.log1p(np.maximum(raw, 0))
        calibration[name] = {"method": "heldout_log_logistic_v1", "low": float(np.percentile(log_raw, 50)), "high": float(np.percentile(log_raw, 97))}
        validation_raw = -model.score_samples(scaler.transform(validation_rows))
        scores = calibrated_score(validation_raw, **calibration[name])
        anomaly_evaluation[name] = {
            "fit_normal_rows": int(len(normal)), "calibration_normal_rows": int(len(calibration_rows)),
            "validation_normal_rows": int(len(validation_rows)), "threshold": ANOMALY_THRESHOLD,
            "above_threshold_share": float(np.mean(scores >= ANOMALY_THRESHOLD)),
            "exact_one_share": float(np.mean(scores == 1.0)),
            "percentiles": {str(q): float(np.percentile(scores, q)) for q in (50, 90, 99)},
            "method": "Disjoint held-out normal calibration and validation halves; log-logistic anchors median=.30, p97=.80; ceiling=.99.",
        }
        joblib.dump({"scaler": scaler, "model": model}, target / f"{name}.joblib")

    importance = clf.get_booster().get_score(importance_type="gain")
    total_gain = sum(importance.values()) or 1.0
    shares = {k: v / total_gain for k, v in sorted(importance.items(), key=lambda kv: -kv[1])}
    random_split = _metrics(y_test, proba)
    provider_split = provider_split_evaluation(X, y, groups, seed) if groups is not None else None
    top = list(shares.items())[:3]
    volume_share = sum(v for k, v in shares.items() if k in VOLUME_FEATURES)
    bias_analysis = [
        "The three most influential features are " + ", ".join(f"{k} ({v:.0%})" for k, v in top) + ".",
        f"Provider volume and billing-level features ({', '.join(sorted(VOLUME_FEATURES & set(shares)))}) account for {volume_share:.0%} of total gain. A model that leans on them tends to score busy providers higher whatever they bill.",
        "Member age is a model input. Its effect on scores for older or younger members has not been measured.",
    ]
    if provider_split:
        gap = random_split["f1"] - provider_split["f1"]
        bias_analysis.append(f"F1 falls from {random_split['f1']:.2f} on a random split to {provider_split['f1']:.2f} on providers the model never saw (a gap of {gap:.2f}), which shows how much it relies on recognising providers.")
    meta = {
        "version": version,
        "model_type": "xgboost",
        "features": list(FEATURES),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_samples": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "metrics": {
            "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
            "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
            "false_positive_rate": round(float(fp / max(fp + tn, 1)), 4),
            "false_negative_rate": round(float(fn / max(fn + tp, 1)), 4),
        },
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "hyperparameters": HYPERPARAMETERS,
        "feature_importance": {k: round(v, 4) for k, v in shares.items()},
        "calibration": calibration,
        "anomaly_evaluation": anomaly_evaluation,
        "training_data_kind": "synthetic",
        "warning": SYNTHETIC_WARNING,
        "bias_analysis": bias_analysis,
        "evaluation": {
            "random_split": random_split,
            "provider_split": provider_split,
            "note": "Both figures come from synthetic claims with planted patterns. Neither says how the model would perform on real claims."
            if provider_split
            else "Provider-split evaluation was not run for this version. The random-split figure is from synthetic claims and overstates real-world performance.",
        },
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def set_current(out_dir: Path, version: str) -> None:
    """Points the scoring service at a version. Deployment is a deliberate, separate step."""
    (out_dir / "CURRENT").write_text(version, encoding="utf-8")
