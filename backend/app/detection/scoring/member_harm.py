from app.detection.context import DetectionContext
from app.utils.codes import CHRONIC_DX_PREFIXES, has_prefix
from app.utils.validators import clamp


def member_harm_score(ctx: DetectionContext) -> tuple[float, list[str]]:
    """How much the pattern, if real, would hurt the member rather than only the plan: exhausted
    benefits, unnecessary procedures, a false medical history. Returns the score and the factors
    behind it so a reviewer can see why a case was moved up the queue."""
    claim = ctx.claim
    score, factors = 0.15, []
    age = claim.member_age if claim.member_age is not None else ctx.member.age
    if age is not None and age >= 65:
        score += 0.25
        factors.append(f"Member is {age} years old")
    elif age is not None and age < 18:
        score += 0.15
        factors.append("Member is a minor")
    if ctx.member.low_income_area:
        score += 0.15
        factors.append("Member lives in a low-income area")
    repeat = 1 + sum(1 for c in ctx.provider_window(30) if c.member_id == claim.member_id)
    if repeat >= 3:
        score += min(0.25, 0.05 * repeat)
        factors.append(f"Repeat exposure ({repeat} claims for this member from this provider in 30 days)")
    if has_prefix(claim.diagnosis_codes, CHRONIC_DX_PREFIXES):
        score += 0.1
        factors.append("Long-term condition on the claim; an inaccurate record affects future care and cover")
    sum_insured = claim.attributes.get("sum_insured")
    if sum_insured and claim.total_billed and claim.total_billed / float(sum_insured) >= 0.25:
        score += 0.15
        factors.append("Claim uses a quarter or more of the member's sum insured")
    return round(clamp(score), 2), factors
