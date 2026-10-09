from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import MAX_UNITS_PER_DAY


class UnitsCap(Rule):
    name = "units_cap"
    description = "More units of a procedure code billed for one day than the daily maximum for that code."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        billed: dict[tuple[str, str], int] = {}
        for line in claim.lines:
            if line.cpt_code in MAX_UNITS_PER_DAY:
                key = (line.cpt_code, str(line.service_date or claim.service_date))
                billed[key] = billed.get(key, 0) + max(line.units or 1, 1)
        breaches = [
            {"cpt_code": code, "service_date": day, "units_billed": units, "max_units": MAX_UNITS_PER_DAY[code]}
            for (code, day), units in billed.items()
            if units > MAX_UNITS_PER_DAY[code]
        ]
        if not breaches:
            return None
        worst = max(breaches, key=lambda b: b["units_billed"] / b["max_units"])
        # One unit over the limit is 0.60 plus a little; three times the limit or more is 0.95.
        excess = (worst["units_billed"] - worst["max_units"]) / (2 * worst["max_units"])
        confidence = 0.60 + 0.35 * min(1.0, excess)
        return self.signal(
            confidence,
            {**worst, "breaches": breaches, "limit_source": "Illustrative sample of daily unit limits"},
            ["lines.cpt_code", "lines.units", "lines.service_date"],
        )
