from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import is_valid_icd10, is_valid_procedure_code


class CodingValidity(Rule):
    name = "coding_validity"
    description = "Procedure or diagnosis codes are malformed, or a line points at a diagnosis that is not on the claim."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        problems: list[str] = []
        for line in claim.lines:
            if not is_valid_procedure_code(line.cpt_code):
                problems.append(f"Line {line.line_id}: procedure code '{line.cpt_code}' is not a valid format")
            for pointer in line.diagnosis_pointer:
                if pointer < 1 or pointer > len(claim.diagnosis_codes):
                    problems.append(f"Line {line.line_id}: diagnosis pointer {pointer} has no matching diagnosis")
            if (line.units or 0) < 1:
                problems.append(f"Line {line.line_id}: units must be at least 1")
        for dx in claim.diagnosis_codes:
            if not is_valid_icd10(dx):
                problems.append(f"Diagnosis code '{dx}' is not a valid ICD-10 format")
        if claim.lines and not claim.diagnosis_codes:
            problems.append("No diagnosis code on the claim")
        line_total = sum(l.billed_amount for l in claim.lines)
        if claim.lines and claim.total_billed and line_total > claim.total_billed * 1.01:
            problems.append(f"Line amounts ({line_total:,.2f}) exceed the claim total ({claim.total_billed:,.2f})")
        if not problems:
            return None
        # A data-quality signal: low weight, routed for correction rather than investigation.
        return self.signal(min(0.55, 0.3 + 0.08 * len(problems)), {"problems": problems}, ["lines.cpt_code", "diagnosis_codes", "lines.diagnosis_pointer"], severity="low")
