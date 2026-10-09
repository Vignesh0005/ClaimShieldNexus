"""Section 5: common exclusions."""
from app.detection.coverage.registry import FAIL, PASS, REVIEW, CoverageInput, Outcome, RuleDef, coverage_check
from app.utils.codes import COSMETIC_CPT_RANGES, COSMETIC_DX, DENTAL_DX_PREFIXES, INFERTILITY_DX_PREFIXES, has_prefix, in_ranges


@coverage_check("exclusion_cosmetic")
def exclusion_cosmetic(inp: CoverageInput, rule: RuleDef) -> Outcome:
    cosmetic = [c for c in inp.procedure_codes if in_ranges(c, COSMETIC_CPT_RANGES)] + [d for d in inp.diagnosis_codes if d in COSMETIC_DX]
    if not cosmetic:
        return Outcome(PASS)
    if inp.attributes.get("accident") or inp.attributes.get("medically_necessary"):
        return Outcome(REVIEW, f"Cosmetic-range codes {', '.join(cosmetic)} recorded as reconstructive or accident-related; confirm medical necessity.")
    return Outcome(FAIL, f"Codes {', '.join(cosmetic)} fall under the cosmetic treatment exclusion.")


@coverage_check("exclusion_dental")
def exclusion_dental(inp: CoverageInput, rule: RuleDef) -> Outcome:
    dental = has_prefix(inp.diagnosis_codes, DENTAL_DX_PREFIXES)
    if not dental:
        return Outcome(PASS)
    if inp.attributes.get("accident"):
        return Outcome(REVIEW, "Dental treatment recorded as arising from an accident; confirm before applying the exclusion.")
    return Outcome(FAIL, f"Diagnosis {', '.join(dental)} falls under the dental treatment exclusion.")


@coverage_check("exclusion_infertility")
def exclusion_infertility(inp: CoverageInput, rule: RuleDef) -> Outcome:
    found = has_prefix(inp.diagnosis_codes, INFERTILITY_DX_PREFIXES)
    if not found:
        return Outcome(PASS)
    return Outcome(FAIL, f"Diagnosis {', '.join(found)} falls under the infertility and assisted reproduction exclusion.")
