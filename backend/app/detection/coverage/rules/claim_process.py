"""Section 7: claim process."""
from app.detection.coverage.registry import PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check


@coverage_check("pre_authorisation")
def pre_authorisation(inp: CoverageInput, rule: RuleDef) -> Outcome:
    planned_inpatient = inp.claim_type in ("inpatient", "institutional") and not inp.attributes.get("emergency")
    if not planned_inpatient or inp.attributes.get("claim_mode") == "reimbursement":
        return Outcome(PASS, "Pre-authorisation applies to planned cashless admissions.")
    if inp.pre_auth_number:
        return Outcome(PASS)
    return Outcome(REVIEW, "Planned cashless admission without a pre-authorisation number on the claim.")


@coverage_check("required_documents")
def required_documents(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.documents_provided is None:
        return Outcome(PASS, "Document list not supplied with the claim.")
    key = "inpatient" if inp.claim_type in ("inpatient", "institutional") else "default"
    required = rule.conditions.get(key, rule.conditions.get("default", ["claim_form"]))
    missing = [d for d in required if d not in inp.documents_provided]
    if not missing:
        return Outcome(PASS)
    return Outcome(REVIEW, f"Documents not yet received: {', '.join(missing)}.")


@coverage_check("timely_submission")
def timely_submission(inp: CoverageInput, rule: RuleDef) -> Outcome:
    submitted = inp.attributes.get("days_from_discharge_to_submission")
    limit = rule.conditions.get("days", 30)
    if submitted is None or int(submitted) <= limit:
        return Outcome(PASS)
    return Outcome(REVIEW, f"Claim submitted {submitted} days after discharge (policy window {limit} days). Delay alone is not a ground for rejection where there is a reasonable cause.")
