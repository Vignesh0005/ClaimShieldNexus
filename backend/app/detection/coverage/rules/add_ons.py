"""Section 9: add-ons and riders."""
from app.detection.coverage.registry import PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check
from app.utils.codes import MATERNITY_DX_PREFIXES, has_prefix


def _riders(inp: CoverageInput) -> list[str]:
    return list(inp.attributes.get("riders") or [])


@coverage_check("maternity_rider")
def maternity_rider(inp: CoverageInput, rule: RuleDef) -> Outcome:
    maternity = has_prefix(inp.diagnosis_codes, MATERNITY_DX_PREFIXES)
    if not maternity or "maternity" in _riders(inp):
        return Outcome(PASS)
    if "riders" not in inp.attributes:
        return Outcome(REVIEW, f"Maternity diagnosis {', '.join(maternity)}; rider information was not supplied.")
    return Outcome(REVIEW, f"Maternity diagnosis {', '.join(maternity)} and no maternity rider is recorded on the policy.")


@coverage_check("outpatient_rider")
def outpatient_rider(inp: CoverageInput, rule: RuleDef) -> Outcome:
    if inp.claim_type != "outpatient" or "opd" in _riders(inp) or "riders" not in inp.attributes:
        return Outcome(PASS)
    return Outcome(REVIEW, "Outpatient claim and no OPD rider is recorded on the policy.")
