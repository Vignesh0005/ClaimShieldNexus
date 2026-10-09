from statistics import median

from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.detection.rules.peer_outlier import MIN_PEERS, comparable_peers


class NewProviderBurst(Rule):
    name = "new_provider_burst"
    description = "A provider first seen in the last 30 days submitting far more claims than established peers do."
    new_within_days = 30
    window_days = 14
    min_tenant_history_days = 60  # a tenant that has only just started sending claims makes every provider look new
    min_claims = 20

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        day, first, tenant_first = ctx.claim.service_date, ctx.provider_first_seen, ctx.tenant_first_seen
        if day is None or first is None or tenant_first is None:
            return None
        if (day - tenant_first).days < self.min_tenant_history_days or (day - first).days > self.new_within_days:
            return None
        peers = comparable_peers(ctx)
        if len(peers) < MIN_PEERS:
            return None
        # No tenant has enough genuinely new providers to measure their usual volume directly, so the
        # yardstick is what an established provider in the same specialty submits in the same span.
        usual = median(p.claims for p in peers) * self.window_days / 90
        claims = len(ctx.provider_window(self.window_days)) + 1
        threshold = max(float(self.min_claims), 3 * usual)
        if claims < threshold:
            return None
        # 0.60 at the threshold, rising to 0.90 at twice the threshold.
        confidence = 0.60 + 0.30 * min(1.0, (claims - threshold) / threshold)
        return self.signal(
            confidence,
            {
                "first_seen": str(first), "days_since_first_seen": (day - first).days, "claims_in_window": claims, "window_days": self.window_days,
                "usual_claims_in_window": round(usual, 1), "usual_basis": f"Median of {len(peers)} established providers in the same specialty", "threshold": round(threshold, 1), "specialty": ctx.provider.specialty,
            },
            ["provider_id", "service_date"],
        )
