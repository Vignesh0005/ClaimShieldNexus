from app.detection.context import Signal
from app.detection.scoring.capacity_optimizer import CapacityOptimizer, QueueCase
from app.detection.scoring.evidence_strength import evidence_strength
from app.detection.scoring.fusion import RiskFusion, aggregate, dollar_impact
from app.detection.scoring.severity import priority_tier, severity
from app.detection.scoring.two_axis import quadrant
from app.explainability import counterfactuals
from app.explainability.plain_language import SIGNAL_TEXT, find_banned
from app.explainability.uncertainty import limitations
from tests.conftest import make_claim, make_ctx


def rule(name="duplicate_billing", score=0.98):
    return Signal("rule", name, score, score, evidence={"x": 1})


def test_no_signals_means_low_risk_whatever_the_amount_or_member():
    ctx = make_ctx(make_claim("C1", billed=90_000, member_age=88))
    r = RiskFusion().fuse(ctx, [])
    assert r.risk_score <= 0.2 and r.severity == "low" and r.two_axis_quadrant == "dismiss"


def test_fusion_weights_and_bounds():
    ctx = make_ctx(make_claim("C1", billed=1000))
    signals = [rule(), Signal("ml", "xgboost", 0.9), Signal("graph", "referral_loop", 0.85, evidence={"loop_members": ["a", "b", "c"]})]
    r = RiskFusion().fuse(ctx, signals)
    composite = 0.30 * 0.98 + 0.25 * 0.9 + 0.20 * 0.85 + 0.15 * dollar_impact(1000) + 0.10 * r.member_harm_score
    assert abs(r.composite_risk - round(composite, 4)) < 1e-6
    assert r.max_rule_confidence == 0.98 and r.risk_score == round(max(composite, 0.98 * 0.85), 4)
    assert 0 <= r.risk_score <= 1 and r.two_axis_quadrant == "siu" and r.severity in ("high", "critical")


def test_coding_errors_do_not_drive_the_rule_score():
    assert aggregate([Signal("rule", "coding_validity", 0.5, 0.5)], "rule") == 0.0


def test_agreement_between_rules_raises_the_score_but_never_above_one():
    one = aggregate([rule(score=0.8)], "rule")
    two = aggregate([rule(score=0.8), rule("upcoding", 0.8)], "rule")
    assert one == 0.8 and one < two <= 1.0


def test_model_score_alone_is_weak_evidence():
    assert evidence_strength([Signal("ml", "xgboost", 0.99)]) <= 0.35
    assert evidence_strength([rule(), Signal("ml", "xgboost", 0.9)]) >= 0.6
    assert evidence_strength([]) == 0.0


def test_quadrants_severity_and_tiers():
    assert [quadrant(0.8, 0.8), quadrant(0.8, 0.3), quadrant(0.3, 0.8), quadrant(0.3, 0.3)] == ["siu", "investigate", "review", "dismiss"]
    assert [severity(0.85), severity(0.65), severity(0.45), severity(0.1)] == ["critical", "high", "medium", "low"]
    assert severity(0.65, {"critical": 0.6}) == "critical"  # tenant thresholds apply
    assert priority_tier(0.72, 0.8) == "tier_1" and priority_tier(0.72, 0.2) == "tier_2" and priority_tier(0.3, 0.9) == "tier_3"


def cases():
    return [
        QueueCase("A", "P1", 0.9, 90_000, 0.8, 10, 0.9),
        QueueCase("B", "P2", 0.8, 60_000, 0.5, 6, 0.8),
        QueueCase("C", "P3", 0.7, 55_000, 0.5, 6, 0.8),
        QueueCase("D", "P4", 0.95, 500_000, 0.9, 4, 0.2),  # high value, weak evidence
    ]


def test_optimizer_respects_capacity_and_evidence_floor():
    r = CapacityOptimizer().optimize(cases(), num_investigators=1, hours_per_investigator=12)
    assert r.total_hours <= 12 and r.skipped_low_evidence == 1
    assert "D" not in [c.case_id for c in r.selected_cases]
    # B + C together (12h, weighted value 86,250) beat A alone (10h, 81,000): a greedy pick of the largest case would miss this.
    assert sorted(c.case_id for c in r.selected_cases) == ["B", "C"]
    assert r.optimization_method == "integer_linear_programming"


def test_optimizer_max_cases_and_empty_queue():
    assert len(CapacityOptimizer().optimize(cases(), 5, 20, max_cases=1).selected_cases) == 1
    empty = CapacityOptimizer().optimize([], 3, 20)
    assert empty.selected_cases == [] and empty.total_expected_recovery == 0


def test_greedy_fallback_gives_a_feasible_answer():
    chosen = CapacityOptimizer._solve_greedy(cases()[:3], 12, None)
    assert sum(c.estimated_hours for c in chosen) <= 12 and chosen


def test_counterfactuals_are_recomputed_not_invented():
    signals = [rule(), Signal("ml", "xgboost", 0.9), Signal("graph", "referral_loop", 0.85)]
    out = counterfactuals.generate(signals, dollar=0.3, harm=0.4, threshold=0.7)
    by = {s["removes"]: s for s in out["scenarios"]}
    composite = 0.30 * 0.98 + 0.25 * 0.9 + 0.20 * 0.85 + 0.15 * 0.3 + 0.10 * 0.4
    assert out["baseline_risk"] == round(max(composite, 0.98 * 0.85), 4)
    # With the rule finding gone there is no floor: the score is the remaining composite.
    assert abs(by["duplicate_billing"]["counterfactual_risk"] - (composite - 0.30 * 0.98)) < 1e-3
    assert by["all"]["counterfactual_risk"] <= 0.2 and by["all"]["would_still_route"] is False
    assert all(s["counterfactual_risk"] <= out["baseline_risk"] for s in out["scenarios"])


def test_limitations_always_state_what_is_unknown():
    out = limitations({"referral_loop", "xgboost"}, provider_id="PRV-1", ml_degraded=True, claim_count=1, has_prior_outcome=False, provider_known=False)
    text = " ".join(out)
    assert "No prior investigation outcome for PRV-1" in text and "legitimacy unverified" in text and "unavailable" in text and "single claim" in text


def test_wording_never_accuses():
    for name, text in SIGNAL_TEXT.items():
        assert not find_banned(" ".join(text.values())), name
    assert find_banned("The provider committed fraud.") == ["committed fraud"]


def test_max_rule_floor_lifts_a_single_near_certain_rule():
    from app.detection.scoring.fusion import combine_risk

    risk, composite, top = combine_risk([rule(score=0.95)], dollar=0.1, harm=0.2)
    assert composite < 0.70 and top == 0.95 and risk == round(0.95 * 0.85, 4) and risk >= 0.80
    # Low-confidence rules and data-quality findings get no lift.
    assert combine_risk([rule(score=0.5)], 0.1, 0.2)[0] == max(combine_risk([rule(score=0.5)], 0.1, 0.2)[1], 0.425)
    assert combine_risk([Signal("rule", "coding_validity", 0.55, 0.55)], 0.1, 0.2)[2] == 0.0
    # A model score alone never triggers the floor.
    assert combine_risk([Signal("ml", "xgboost", 0.99)], 0.1, 0.2)[2] == 0.0


def test_three_tier_case_opening_and_tenant_config():
    from types import SimpleNamespace

    from app.detection.pipeline import DetectionPipeline
    from app.detection.scoring.fusion import RiskResult

    def pipeline(config):
        return DetectionPipeline(None, SimpleNamespace(id="t", config=config))

    def result(risk, top_rule, quadrant="investigate"):
        return SimpleNamespace(risk=RiskResult(risk, 0.5, 0.5, 0.3, quadrant, "medium", "tier_3", max_rule_confidence=top_rule))

    default = pipeline({})
    assert default.case_opening_reason(result(0.75, 0.0)) == "tier1_risk_score"
    assert default.case_opening_reason(result(0.50, 0.92)) == "tier2_rule_confidence"
    assert default.case_opening_reason(result(0.50, 0.50, "siu")) == "tier3_siu_quadrant"
    assert default.case_opening_reason(result(0.50, 0.50)) is None
    assert default.case_opening_reason(SimpleNamespace(risk=None)) is None  # coverage hold: never a case

    strict = pipeline({"case_opening": {"tier2_enabled": False, "tier3_enabled": False}})
    assert strict.case_opening_reason(result(0.50, 0.99, "siu")) is None
    raised = pipeline({"case_opening": {"tier2_rule_threshold": 0.95}})
    assert raised.case_opening_reason(result(0.50, 0.92)) is None and raised.case_opening_reason(result(0.50, 0.96)) == "tier2_rule_confidence"
