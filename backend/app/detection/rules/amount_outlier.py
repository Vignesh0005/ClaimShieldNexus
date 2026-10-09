import math

from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import TYPICAL_AMOUNTS

MIN_HISTORY_LINES = 30  # below this the tenant's own median is too noisy to compare against


def typical_amount(ctx: DetectionContext, code: str | None) -> tuple[float, str] | None:
    """Typical billed amount for one unit of a code and where it came from: the tenant's own
    history when there is enough of it, otherwise the sample table, otherwise nothing."""
    stats = ctx.typical_amounts.get(code or "")
    if stats and stats.lines >= MIN_HISTORY_LINES and stats.typical > 0:
        return stats.typical, f"Median of {stats.lines} lines billed by this tenant in the prior 90 days"
    if code in TYPICAL_AMOUNTS:
        return float(TYPICAL_AMOUNTS[code]), "Illustrative sample of typical amounts"
    return None


class AmountOutlier(Rule):
    name = "amount_outlier"
    description = "A line billed at several times the usual amount for its procedure code."
    min_ratio = 3.0

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        outliers = []
        for line in ctx.claim.lines:
            usual = typical_amount(ctx, line.cpt_code)
            if usual is None or not line.billed_amount:
                continue
            typical, basis = usual
            per_unit = line.billed_amount / max(line.units or 1, 1)
            ratio = per_unit / typical
            if ratio >= self.min_ratio:
                outliers.append({"line_id": line.line_id, "cpt_code": line.cpt_code, "units": max(line.units or 1, 1), "billed_amount": round(line.billed_amount, 2), "typical_amount": round(typical, 2), "ratio": round(ratio, 1), "basis": basis})
        if not outliers:
            return None
        worst = max(outliers, key=lambda o: o["ratio"])
        # Log scale: three times the usual amount is 0.55, thirty times or more is 0.95.
        confidence = 0.55 + 0.40 * min(1.0, math.log10(worst["ratio"] / self.min_ratio))
        return self.signal(
            confidence,
            {**{k: worst[k] for k in ("cpt_code", "billed_amount", "typical_amount", "ratio", "units", "basis")}, "threshold_ratio": self.min_ratio, "lines": outliers},
            ["lines.cpt_code", "lines.billed_amount", "lines.units"],
        )
