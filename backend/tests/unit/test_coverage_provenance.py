import json

import pytest

from app.detection.coverage import loader
from app.detection.coverage.engine import CoverageRulesEngine
from app.detection.coverage.loader import SECTION_RE, CoverageRuleLoader, validate_authoritative
from app.detection.coverage.registry import CoverageInput
from app.utils.codes import REFERENCE_DATA

GOOD = {"rule_id": "IRDAI_S4_001", "category": "waiting_period", "rule_name": "Transcribed rule", "description": "Text from the document.", "source_section": "Section 4 \u2014 Waiting Periods", "check": "reference_only"}


def test_every_rule_cites_a_source_section_and_document():
    for rule in CoverageRuleLoader().load_all():
        assert SECTION_RE.match(rule.source_section), rule.rule_id
        assert rule.source_document


def test_bundled_rules_are_flagged_illustrative_not_authoritative():
    rules = CoverageRuleLoader().load_all()
    assert rules and all(not r.authoritative and r.needs_compliance_review and "compliance review" in r.disclaimer for r in rules)


def test_sample_code_tables_are_flagged():
    assert all(not d["authoritative"] and d["needs_compliance_review"] and "Not for production use" in d["disclaimer"] for d in REFERENCE_DATA)
    assert REFERENCE_DATA[0]["disclaimer"] == "Sample code pairs. Not for production use."


def test_importer_validation_rejects_uncited_or_unknown_rules():
    assert validate_authoritative(GOOD) == []
    assert "source_section must look like" in " ".join(validate_authoritative({**GOOD, "source_section": "Waiting periods"}))
    assert "missing source_section" in validate_authoritative({**GOOD, "source_section": ""})
    assert "no evaluator named" in " ".join(validate_authoritative({**GOOD, "check": "made_up_check"}))
    assert validate_authoritative({**GOOD, "check": "initial_waiting_period"}) == []


def test_authoritative_file_is_loaded_and_marked(tmp_path, monkeypatch):
    path = tmp_path / "irdai.json"
    path.write_text(json.dumps({"rules": [GOOD]}), encoding="utf-8")
    monkeypatch.setattr(loader, "AUTHORITATIVE_FILE", path)
    rules = CoverageRuleLoader().load_all()
    imported = [r for r in rules if r.authoritative]
    assert len(imported) == 1 and imported[0].needs_compliance_review is False
    assert imported[0].source_document == "Health_Insurance_Coverage_Criteria_and_Rules.pdf"
    # A reference-only rule is listed but never produces an automated result.
    result = CoverageRulesEngine(rules).evaluate(CoverageInput(claim_id="C1", plan_type="individual"))
    assert all(r.rule_id != "IRDAI_S4_001" for r in result.rule_results)
    assert result.illustrative_rules_applied == len(rules) - 1 and result.to_dict()["compliance_notice"]


@pytest.mark.asyncio
async def test_rules_filter_and_compliance_report(client, tenants):
    h = tenants["alpha"]["viewer"]
    everything = (await client.get("/api/v1/coverage/rules", headers=h)).json()
    illustrative = (await client.get("/api/v1/coverage/rules?authoritative=false", headers=h)).json()
    authoritative = (await client.get("/api/v1/coverage/rules?authoritative=true", headers=h)).json()
    assert everything["total"] == illustrative["total"] == 22 and authoritative["total"] == 0
    assert "require compliance review" in everything["notice"] and authoritative["notice"] is None
    assert all(r["authoritative"] is False and r["needs_compliance_review"] and r["disclaimer"] and r["source_section"] for r in everything["rules"])

    report = (await client.get("/api/v1/coverage/compliance-report", headers=h)).json()
    assert report["coverage_rules"] == {"total": 22, "authoritative": 0, "illustrative": 22, "needs_compliance_review": 22}
    assert report["authoritative_source"]["status"] == "not_loaded" and report["authoritative_source"]["expected_rules"] == 78
    assert len(report["rules_needing_review"]) == 22 and len(report["reference_data"]) == len(REFERENCE_DATA)
    assert sum(c["illustrative"] for c in report["by_category"]) == 22
