"""Section 11: grievance redressal. Informational: attaches the escalation path to every result."""
from app.detection.coverage.registry import PASS, CoverageInput, Outcome, RuleDef, coverage_check


@coverage_check("grievance_path")
def grievance_path(inp: CoverageInput, rule: RuleDef) -> Outcome:
    return Outcome(PASS, "If the member disputes the outcome: insurer grievance officer, then IRDAI Bima Bharosa, then the Insurance Ombudsman.")
