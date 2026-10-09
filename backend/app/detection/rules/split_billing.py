from datetime import timedelta

from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.amount_outlier import typical_amount
from app.detection.rules.base import Rule


def billed_for(claim: ClaimData, code: str) -> float:
    return sum(l.billed_amount for l in claim.lines if l.cpt_code == code)


class SplitBilling(Rule):
    name = "split_billing"
    description = "The same member, provider and procedure billed on consecutive days in parts that add up to one normal service."
    max_piece = 0.75  # each part must be clearly less than one full service
    total_range = (0.80, 1.30)  # and together they must come to about one

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        if claim.service_date is None or not claim.member_id or not claim.provider_id:
            return None
        earlier = [c for c in ctx.member_history if c.provider_id == claim.provider_id and c.service_date and c.service_date < claim.service_date]
        best: tuple[float, dict] | None = None
        for code in dict.fromkeys(claim.cpt_codes):
            usual = typical_amount(ctx, code)
            if usual is None:
                continue  # with no idea of the usual amount there is nothing for the parts to add up to
            typical, basis = usual
            chain = [claim]
            day = claim.service_date - timedelta(days=1)
            while True:
                previous = [c for c in earlier if c.service_date == day and code in c.cpt_codes]
                if not previous:
                    break
                chain += previous
                day -= timedelta(days=1)
            pieces = [billed_for(c, code) for c in chain]
            total = sum(pieces)
            if len(chain) < 2 or any(p <= 0 or p > self.max_piece * typical for p in pieces) or not self.total_range[0] * typical <= total <= self.total_range[1] * typical:
                continue
            # 0.90 when the parts add up to exactly one usual service, falling to 0.60 as the total
            # drifts 30% away from it.
            confidence = 0.60 + 0.30 * max(0.0, 1 - abs(total / typical - 1) / 0.30)
            evidence = {
                "cpt_code": code, "linked_claims": [{"claim_id": c.claim_id, "service_date": str(c.service_date), "billed_amount": round(p, 2)} for c, p in sorted(zip(chain, pieces), key=lambda x: x[0].service_date)],
                "total_billed": round(total, 2), "typical_amount": round(typical, 2), "consecutive_days": (claim.service_date - day).days, "basis": basis,
            }
            if best is None or confidence > best[0]:
                best = (confidence, evidence)
        if best is None:
            return None
        return self.signal(best[0], best[1], ["member_id", "provider_id", "service_date", "lines.cpt_code", "lines.billed_amount"])
