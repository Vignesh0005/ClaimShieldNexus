"""Section 3: what the policy covers."""
from app.detection.coverage.registry import PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check
from app.utils.codes import DAYCARE_CPT


@coverage_check("hospitalisation_duration")
def hospitalisation_duration(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.claim_type not in ("inpatient", "institutional"):
        return Outcome(PASS, "Not an inpatient claim.")
    hours = inp.attributes.get("hospitalisation_hours")
    if hours is None:
        return Outcome(PASS, "Length of stay not supplied.")
    minimum = rule.conditions.get("min_hours", 24)
    if float(hours) >= minimum or set(inp.procedure_codes) & DAYCARE_CPT:
        return Outcome(PASS)
    return Outcome(REVIEW, f"Stay of {hours} hours is under {minimum} hours and no listed day-care procedure was billed.")


@coverage_check("service_territory")
def service_territory(inp: CoverageInput, rule: RuleDef) -> Outcome:
    allowed = rule.conditions.get("territories", ["IN"])
    if not inp.service_location or inp.service_location.upper() in allowed:
        return Outcome(PASS)
    if inp.attributes.get("worldwide_cover"):
        return Outcome(PASS, "Treatment outside India; policy carries worldwide cover.")
    return Outcome(REVIEW, f"Treatment location '{inp.service_location}' is outside the policy territory; confirm whether worldwide cover applies.")
