from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import PROCEDURE_DEMOGRAPHICS

GENDERS = {"m": "M", "male": "M", "f": "F", "female": "F"}
GENDER_WORD = {"M": "male", "F": "female"}


def member_gender(ctx: DetectionContext) -> str | None:
    """Gender as supplied on the claim (`member_gender` or `gender`). Anything else is unknown."""
    a = ctx.claim.attributes
    value = a.get("member_gender") or a.get("gender")
    return GENDERS.get(str(value).strip().lower()) if value else None


class DemographicMismatch(Rule):
    name = "demographic_mismatch"
    description = "A service that does not fit the member's recorded age or gender."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        age = ctx.claim.member_age if ctx.claim.member_age is not None else ctx.member.age
        gender = member_gender(ctx)
        if age is None and gender is None:
            return None
        failures = []
        for code in dict.fromkeys(ctx.claim.cpt_codes):
            limits = PROCEDURE_DEMOGRAPHICS.get(code)
            if not limits:
                continue
            # A service for the other gender is a matter of record: 0.90.
            if gender and limits.get("gender") and gender != limits["gender"]:
                failures.append({"cpt_code": code, "service": limits["service"], "member_gender": gender, "constraint": f"{GENDER_WORD[limits['gender']]} members only", "confidence": 0.90})
            # Age is graded: one year outside the range is 0.63, ten or more years outside is 0.90.
            lo, hi = limits.get("min_age"), limits.get("max_age")
            if age is not None:
                outside = lo - age if lo is not None and age < lo else age - hi if hi is not None and age > hi else 0
                if outside > 0:
                    span = f"age {lo} to {hi}" if lo is not None and hi is not None else f"age {lo} and over" if lo is not None else f"age {hi} and under"
                    failures.append({"cpt_code": code, "service": limits["service"], "member_age": age, "constraint": span, "years_outside_range": outside, "confidence": round(0.60 + 0.30 * min(1.0, outside / 10), 2)})
        if not failures:
            return None
        worst = max(failures, key=lambda f: f["confidence"])
        return self.signal(
            worst["confidence"],
            {**{k: v for k, v in worst.items() if k != "confidence"}, "failures": [{k: v for k, v in f.items() if k != "confidence"} for f in failures], "limit_source": "Illustrative sample of age and gender limits"},
            ["lines.cpt_code", "member_age", "attributes.member_gender"],
        )
