"""Section 4: waiting periods."""
from datetime import timedelta

from app.detection.coverage.registry import FAIL, PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check
from app.utils.codes import CHRONIC_DX_PREFIXES, SPECIFIC_WAITING_DX_PREFIXES, has_prefix
from app.utils.dates import months_between


def _months_on_policy(inp: CoverageInput) -> int | None:
    if inp.policy_start_date is None or inp.service_date is None:
        return None
    # Continuous cover carried over from a previous insurer counts towards waiting periods.
    return months_between(inp.policy_start_date, inp.service_date) + int(inp.attributes.get("portability_credit_months", 0))


@coverage_check("initial_waiting_period")
def initial_waiting_period(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.policy_start_date is None or inp.service_date is None:
        return Outcome(PASS, "Dates not supplied.")
    days = rule.conditions.get("days", 30)
    if inp.service_date >= inp.policy_start_date + timedelta(days=days):
        return Outcome(PASS)
    if inp.attributes.get("accident") or inp.attributes.get("portability_credit_months"):
        return Outcome(PASS, "Within the initial waiting period, which does not apply to accidents or continuous renewed cover.")
    return Outcome(FAIL, f"Service falls within the first {days} days of the policy and is not recorded as accident-related.")


@coverage_check("specific_disease_waiting")
def specific_disease_waiting(inp: CoverageInput, rule: RuleDef) -> Outcome:
    listed = has_prefix(inp.diagnosis_codes, SPECIFIC_WAITING_DX_PREFIXES)
    months = _months_on_policy(inp)
    if not listed or months is None:
        return Outcome(PASS)
    limit = rule.conditions.get("months", 24)
    if months >= limit:
        return Outcome(PASS)
    return Outcome(REVIEW, f"Diagnosis {', '.join(listed)} is on the specific-disease list and the policy is {months} months old (waiting period up to {limit} months; check the policy wording).")


@coverage_check("pre_existing_disease_waiting")
def pre_existing_disease_waiting(inp: CoverageInput, rule: RuleDef) -> Outcome:
    chronic = has_prefix(inp.diagnosis_codes, CHRONIC_DX_PREFIXES)
    months = _months_on_policy(inp)
    if not chronic or months is None:
        return Outcome(PASS)
    limit = rule.conditions.get("months", 36)
    if months >= limit:
        return Outcome(PASS)
    if inp.attributes.get("ped_declared") is False:
        return Outcome(PASS, "Condition recorded as first diagnosed after the policy started.")
    return Outcome(REVIEW, f"PED waiting up to {limit // 12} years; check diagnosis date for {', '.join(chronic)} against the policy start ({months} months on policy).")
