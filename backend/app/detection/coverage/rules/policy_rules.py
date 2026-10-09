"""Section 8: policy rules (moratorium, renewal)."""
from app.detection.coverage.registry import PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check
from app.utils.dates import months_between


@coverage_check("moratorium")
def moratorium(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.policy_start_date is None or inp.service_date is None:
        return Outcome(PASS)
    months = months_between(inp.policy_start_date, inp.service_date) + int(inp.attributes.get("portability_credit_months", 0))
    limit = rule.conditions.get("months", 60)
    if months >= limit:
        return Outcome(PASS, f"Policy has completed the {limit}-month moratorium; the claim cannot be contested on non-disclosure except for established fraud.")
    return Outcome(PASS)


@coverage_check("renewal_continuity")
def renewal_continuity(inp: CoverageInput, rule: RuleDef) -> Outcome:
    lapse_days = inp.attributes.get("renewal_gap_days")
    grace = rule.conditions.get("grace_days", 30)
    if lapse_days is None or int(lapse_days) <= 0:
        return Outcome(PASS)
    if int(lapse_days) <= grace:
        return Outcome(PASS, f"Renewed {lapse_days} days late, inside the {grace}-day grace period; continuity benefits are kept.")
    return Outcome(REVIEW, f"Renewal gap of {lapse_days} days exceeds the {grace}-day grace period; waiting-period credit may be affected.")
