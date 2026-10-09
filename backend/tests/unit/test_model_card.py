import pytest

from app.db.seed.synthetic import generate, training_matrix_with_groups
from app.detection.ml.training import SYNTHETIC_WARNING, train_models
from app.services import model_service


@pytest.fixture(scope="module")
def meta(tmp_path_factory):
    data = generate(seed=3, n_providers=24, n_members=150, days=70)
    X, y, groups = training_matrix_with_groups(data)
    assert len(set(groups)) >= 20 and len(X) == len(y) == len(groups)
    return train_models(X, y, "vtest", tmp_path_factory.mktemp("artifacts"), groups=groups)


def test_provider_split_is_reported_separately(meta):
    ev = meta["evaluation"]
    random_split, provider_split = ev["random_split"], ev["provider_split"]
    assert provider_split is not None and provider_split["folds"] == 5 and "GroupKFold by provider" in provider_split["method"]
    assert provider_split["test_claims"] == meta["training_samples"]  # every claim scored by a model that never saw its provider
    for key in ("f1", "precision", "recall"):
        assert 0.0 <= provider_split[key] <= 1.0 and 0.0 <= random_split[key] <= 1.0
    assert "synthetic" in ev["note"].lower()


def test_meta_carries_warning_and_bias_analysis(meta):
    assert meta["warning"] == SYNTHETIC_WARNING == "Synthetic-trained model. Not validated for production use."
    assert meta["training_data_kind"] == "synthetic" and len(meta["bias_analysis"]) >= 3
    assert abs(sum(meta["feature_importance"].values()) - 1.0) < 0.01


def test_model_card_document_has_required_sections(meta):
    from scripts.train_xgboost import render_model_card

    text = render_model_card(meta)
    for heading in ("## Model name and version", "## Training data", "## Metrics", "## IMPORTANT LIMITATIONS", "## Intended use", "## Bias analysis (which features dominate)", "## Fairness considerations"):
        assert heading in text, heading
    assert "Provider split" in text and "Not yet measured" in text and SYNTHETIC_WARNING in text


def test_warning_applies_to_real_models_only():
    assert model_service.model_warning("xgb_v1.0.0") == SYNTHETIC_WARNING
    assert model_service.model_warning("fallback_rules_only") is None and model_service.model_warning(None) is None


@pytest.mark.asyncio
async def test_card_endpoint(client, tenants, meta):
    from app.db import session as db_session

    async with db_session.session_scope() as db:
        await model_service.register(db, meta, "unused", deployed=True)
    card = (await client.get("/api/v1/models/vtest/card", headers=tenants["alpha"]["viewer"])).json()
    assert card["warning"] == SYNTHETIC_WARNING and card["fairness"].startswith("Not yet measured")
    assert card["evaluation"]["provider_split"]["f1"] == meta["evaluation"]["provider_split"]["f1"]
    assert card["evaluation"]["random_split"]["f1"] == meta["evaluation"]["random_split"]["f1"]
    assert card["bias_analysis"] and any("synthetic" in l.lower() for l in card["limitations"])
    assert (await client.get("/api/v1/models/nope/card", headers=tenants["alpha"]["viewer"])).status_code == 404
