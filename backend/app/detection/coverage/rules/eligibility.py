"""Section 2: eligibility criteria."""
from app.detection.coverage.registry import FAIL, PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check


@coverage_check("age_not_a_bar")
def age_not_a_bar(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.member_age is None:
        return Outcome(PASS, "Member age not supplied. Age alone is not a ground for rejecting a claim.")
    return Outcome(PASS, "IRDAI removed the upper age cap on entry; a claim cannot be rejected solely on age.")


@coverage_check("policy_in_force")
def policy_in_force(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.policy_start_date is None or inp.service_date is None:
        return Outcome(REVIEW, "Policy start date or service date is missing; confirm the policy was in force on the service date.")
    if inp.service_date < inp.policy_start_date:
        return Outcome(FAIL, f"Service date {inp.service_date} is before the policy start date {inp.policy_start_date}.")
    end = inp.attributes.get("policy_end_date")
    if end and str(inp.service_date) > str(end):
        return Outcome(REVIEW, f"Service date {inp.service_date} is after the recorded policy end date {end}; check renewal and grace period.")
    return Outcome(PASS)
