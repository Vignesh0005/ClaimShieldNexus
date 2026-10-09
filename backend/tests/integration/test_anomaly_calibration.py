import numpy as np
import pytest
from sklearn.model_selection import train_test_split

from app.db.seed.synthetic import generate, training_matrix_with_groups
from app.detection.context import Signal
from app.detection.ml.feature_engineering import build_features, to_row
from app.detection.ml.isolation_forest import ANOMALY_THRESHOLD, calibrated_score
from app.detection.ml.registry import MLEngine, ModelRegistry
from app.detection.ml.remote_client import MLPrediction
from app.detection.ml.training import set_current, train_models
from tests.conftest import api_claim, ingest, make_claim, make_ctx


@pytest.fixture(scope="module")
def calibrated_models(tmp_path_factory):
    X, y, _ = training_matrix_with_groups(generate(seed=7))
    path = tmp_path_factory.mktemp("calibrated-anomalies")
    meta = train_models(X, y, "calibration-test", path)
    set_current(path, "calibration-test")
    models = ModelRegistry(str(path))
    assert models.load()
    _, heldout, _, labels = train_test_split(X, y, test_size=.25, random_state=7, stratify=y)
    _, validation = train_test_split(heldout[labels == 0], test_size=.5, random_state=7)
    return models, meta, validation


def test_normal_scores_do_not_saturate_and_false_positive_rate_is_small(calibrated_models):
    models, meta, validation = calibrated_models
    for name, detector in [("lof", models.lof), ("isolation_forest", models.iforest)]:
        scores = np.array([detector.score(row.tolist()) for row in validation])
        # This fails for the previous hard-clip calibration on out-of-distribution normals.
        assert np.mean(scores == 1.0) <= .01
        assert np.mean(scores >= ANOMALY_THRESHOLD) <= .05
        p50, p90, p99 = np.percentile(scores, [50,90,99])
        assert .1 < p50 < .5 < p90 < p99 < 1
        assert meta["anomaly_evaluation"][name]["validation_normal_rows"] == len(validation)
        # Huge finite raw values must stay finite and below 1, even after API rounding.
        extreme = calibrated_score([10, 100, 1000, 1e100], **meta["calibration"][name])
        assert np.all(np.isfinite(extreme)) and np.all(np.round(extreme,4) < 1)
        assert np.all(np.diff(extreme) >= 0)


def test_timed_therapy_extreme_still_scores_high(calibrated_models):
    models, _, _ = calibrated_models
    claim = make_claim(codes=("97110",), units=100, billed=4000)
    features = build_features(make_ctx(claim))
    assert models.lof.score(to_row(features)) >= ANOMALY_THRESHOLD
    assert models.lof.score(to_row(features)) < 1


@pytest.mark.asyncio
async def test_remote_anomalies_can_never_be_critical(monkeypatch):
    async def prediction(_self, _features):
        return MLPrediction(fraud_probability=0, anomaly_score=1, lof_score=1, model_version="test")
    monkeypatch.setattr(MLEngine, "predict", prediction)
    signals, _, _ = await MLEngine().run_all(make_ctx(make_claim()))
    assert {s.name for s in signals} == {"lof", "isolation_forest"}
    assert all(s.severity == "medium" for s in signals)


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme,rule", [("duplicate_billing","duplicate_billing"), ("unbundling","unbundling"), ("impossible_day","impossible_timing"), ("phantom_billing","phantom_services"), ("ncci_edit","ncci_edit")])
async def test_rule_cases_still_open_with_calibrated_models(client, tenants, monkeypatch, calibrated_models, scheme, rule):
    models, _, _ = calibrated_models
    async def prediction(_self, features):
        return models.predict(features)
    monkeypatch.setattr(MLEngine, "predict", prediction)
    tenant = tenants["alpha"]
    if scheme == "ncci_edit":
        claim = api_claim("NCCI-CAL", code="93000")
        claim["lines"].append({"line_id":"NCCI-L2", "cpt_code":"93005", "units":1, "billed_amount":120, "diagnosis_pointer":[1]})
        claim["total_billed"] = 240
        await ingest(client, tenant["key"], claim)
        flags = (await client.get("/api/v1/claims/NCCI-CAL/flags", headers=tenant["investigator"])).json()["flags"]
        assert any(f.get("rule_name") == rule for f in flags)
        cases = (await client.get("/api/v1/cases", headers=tenant["investigator"])).json()
        assert cases["total"] >= 1
    else:
        response = await client.post("/api/v1/inject", headers=tenant["investigator"], json={"scheme":scheme})
        assert response.status_code == 200, response.text
        result = response.json()
        assert any(f.get("rule_name") == rule for f in result["flags"]), result
        assert result["case_id"] is not None, result
