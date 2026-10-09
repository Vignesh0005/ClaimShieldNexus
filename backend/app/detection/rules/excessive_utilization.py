from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule


class ExcessiveUtilization(Rule):
    name = "excessive_utilization"
    description = "One member seen by the same provider far more often in 30 days than specialty peers."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        if not ctx.claim.member_id:
            return None
        visits = 1 + sum(1 for c in ctx.provider_window(30) if c.member_id == ctx.claim.member_id)
        peer = max(ctx.peers.visits_per_member, 1.0)
        threshold = max(6.0, 3 * peer)
        if visits < threshold:
            return None
        confidence = 0.6 + 0.3 * min(1.0, (visits - threshold) / threshold)
        return self.signal(
            confidence,
            {"visits_in_30_days": visits, "peer_visits_per_member": round(peer, 1), "threshold": threshold},
            ["member_id", "provider_id", "service_date"],
        )
