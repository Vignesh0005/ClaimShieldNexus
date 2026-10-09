from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import PROCEDURE_DX_GROUPS, dx_groups


class DiagnosisProcedureMismatch(Rule):
    name = "diagnosis_procedure_mismatch"
    description = "A procedure billed with no diagnosis on the claim that it would normally be performed for."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        diagnoses = [d for d in claim.diagnosis_codes if d]
        if not diagnoses:
            return None  # a claim with no diagnosis at all is a coding_validity finding, not a mismatch
        found = {d: dx_groups(d) for d in diagnoses}
        on_claim = {g for groups in found.values() for g in groups}
        mismatches = []
        for code in dict.fromkeys(claim.cpt_codes):
            if code not in PROCEDURE_DX_GROUPS:
                continue
            service, expected = PROCEDURE_DX_GROUPS[code]
            if not on_claim & set(expected):
                mismatches.append({"cpt_code": code, "service": service, "expected_diagnosis_groups": list(expected)})
        if not mismatches:
            return None
        # 0.55 when the claim's diagnoses are simply not in the sample groupings, rising to 0.75 when
        # every one of them belongs to a different body system. Each further mismatched procedure
        # adds 0.05, up to 0.10.
        elsewhere = sum(1 for groups in found.values() if groups) / len(diagnoses)
        confidence = 0.55 + 0.20 * elsewhere + 0.05 * min(len(mismatches) - 1, 2)
        return self.signal(
            confidence,
            {**mismatches[0], "diagnosis_codes": diagnoses, "diagnosis_groups_on_claim": sorted(on_claim), "procedures": mismatches, "grouping_source": "Illustrative sample of procedure and diagnosis groups"},
            ["lines.cpt_code", "diagnosis_codes"],
        )
