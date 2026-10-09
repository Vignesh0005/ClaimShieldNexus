"""Section 1: types of health insurance plans."""
from app.detection.coverage.registry import PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check


@coverage_check("plan_type_recognised")
def plan_type_recognised(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if not inp.plan_type:
        return Outcome(REVIEW, "Plan type was not supplied; confirm the policy the claim falls under.")
    if rule.valid_values and inp.plan_type not in rule.valid_values:
        return Outcome(REVIEW, f"Plan type '{inp.plan_type}' is not a recognised product type; confirm against the policy schedule.")
    return Outcome(PASS)
