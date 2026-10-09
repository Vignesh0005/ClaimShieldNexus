from datetime import date

from app.detection.coverage.engine import CoverageRulesEngine
from app.detection.coverage.registry import CoverageInput


def evaluate(**kw):
    base = dict(claim_id="C1", plan_type="family_floater", member_age=40, policy_start_date=date(2020, 1, 1), service_date=date(2025, 1, 8), procedure_codes=["99213"], diagnosis_codes=["M54.5"], service_location="IN", claim_type="professional")
    return CoverageRulesEngine().evaluate(CoverageInput(**{**base, **kw}))


def status_of(result, rule_id):
    return next(r.status for r in result.rule_results if r.rule_id == rule_id)


def test_clean_claim_is_coverable():
    r = evaluate()
    assert r.overall_status == "COVERABLE"
    assert not r.review_required and r.not_fraud and r.not_denial


def test_spec_example_senior_with_chronic_condition():
    r = evaluate(member_age=72, policy_start_date=date(2024, 6, 1), procedure_codes=["99215"], diagnosis_codes=["I25.10"], documents_provided=["claim_form", "discharge_summary"])
    assert r.overall_status == "COVERABLE_WITH_CONDITIONS"
    assert r.conditions[0]["condition"] == "co_payment" and r.conditions[0]["value"] == 0.10
    assert status_of(r, "COV_WAITING_PED_001") == "REVIEW_REQUIRED"
    assert status_of(r, "COV_ELIGIBILITY_AGE_001") == "PASS"
    assert r.review_required and not r.blocks_detection  # advisory review does not hold back FWA detection


def test_age_alone_never_fails():
    assert status_of(evaluate(member_age=97), "COV_ELIGIBILITY_AGE_001") == "PASS"


def test_service_before_policy_start_is_not_coverable_but_not_fraud_or_denial():
    r = evaluate(policy_start_date=date(2025, 6, 1))
    assert r.overall_status == "NOT_COVERABLE" and r.blocks_detection
    out = r.to_dict()
    assert out["not_fraud"] is True and out["not_denial"] is True and "Not a fraud determination" in out["disclaimer"]


def test_initial_waiting_period_exempts_accidents():
    assert evaluate(policy_start_date=date(2024, 12, 25)).overall_status == "NOT_COVERABLE"
    assert status_of(evaluate(policy_start_date=date(2024, 12, 25), attributes={"accident": True}), "COV_WAITING_INITIAL_001") == "PASS"


def test_ped_waiting_passes_after_36_months_and_with_portability_credit():
    assert status_of(evaluate(diagnosis_codes=["E11.9"], policy_start_date=date(2021, 1, 1)), "COV_WAITING_PED_001") == "PASS"
    recent = dict(diagnosis_codes=["E11.9"], policy_start_date=date(2024, 1, 1))
    assert status_of(evaluate(**recent), "COV_WAITING_PED_001") == "REVIEW_REQUIRED"
    assert status_of(evaluate(**recent, attributes={"portability_credit_months": 30}), "COV_WAITING_PED_001") == "PASS"


def test_cosmetic_exclusion_and_accident_exception():
    assert evaluate(procedure_codes=["15780"]).overall_status == "NOT_COVERABLE"
    r = evaluate(procedure_codes=["15780"], attributes={"accident": True})
    assert r.overall_status == "COVERAGE_REVIEW_REQUIRED"


def test_unknown_plan_type_needs_review_not_failure():
    r = evaluate(plan_type="mystery_plan")
    assert r.overall_status == "COVERAGE_REVIEW_REQUIRED"


def test_sum_insured_cap_is_a_condition():
    r = evaluate(total_billed=500_000, attributes={"sum_insured": 300_000})
    assert r.overall_status == "COVERABLE_WITH_CONDITIONS"
    assert any(c["condition"] == "sum_insured_cap" for c in r.conditions)


def test_planned_inpatient_without_preauth_flags_review_only():
    r = evaluate(claim_type="inpatient", attributes={"hospitalisation_hours": 48})
    assert status_of(r, "COV_PROCESS_PREAUTH_001") == "REVIEW_REQUIRED"
    assert r.overall_status == "COVERABLE_WITH_CONDITIONS"


def test_every_rule_has_a_source_section():
    for rule in CoverageRulesEngine().rules:
        assert rule.source_section.startswith("Section "), rule.rule_id
        assert rule.not_fraud and rule.not_denial
