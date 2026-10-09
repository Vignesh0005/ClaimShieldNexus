from statistics import median

from app.detection.context import DetectionContext, ProviderVolume, Signal
from app.detection.rules.base import Rule

MIN_PEERS = 5
MIN_PEER_CLAIMS = 10  # a peer needs this many claims in the window to count as a comparison point


def comparable_peers(ctx: DetectionContext) -> list[ProviderVolume]:
    return [p for p in ctx.specialty_peers if p.provider_id != ctx.claim.provider_id and p.claims >= MIN_PEER_CLAIMS and p.members > 0]


class PeerOutlier(Rule):
    name = "peer_outlier"
    description = "Billing per member, or claims per member, far above other providers in the same specialty over 90 days."
    min_claims = 20
    min_members = 5
    min_ratio = 3.0

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        peers = comparable_peers(ctx)
        window = ctx.provider_window(90) + [ctx.claim]
        members = len({c.member_id for c in window if c.member_id})
        if len(peers) < MIN_PEERS or len(window) < self.min_claims or members < self.min_members:
            return None
        own = {"billed_per_member": sum(c.total_billed for c in window) / members, "claims_per_member": len(window) / members}
        peer = {"billed_per_member": median(p.billed / p.members for p in peers), "claims_per_member": median(p.claims / p.members for p in peers)}
        ratios = {k: own[k] / peer[k] for k in own if peer[k] > 0}
        if not ratios:
            return None
        metric = max(ratios, key=ratios.get)
        ratio = ratios[metric]
        if ratio < self.min_ratio:
            return None
        # Three times the peer median is 0.55; six times or more is 0.90.
        confidence = 0.55 + 0.35 * min(1.0, (ratio - self.min_ratio) / self.min_ratio)
        return self.signal(
            confidence,
            {
                "metric": metric, "provider_value": round(own[metric], 2), "peer_median": round(peer[metric], 2), "ratio": round(ratio, 1), "peers_compared": len(peers),
                "specialty": ctx.provider.specialty, "provider_claims": len(window), "provider_members": members, "window_days": 90, "threshold_ratio": self.min_ratio,
            },
            ["provider_id", "member_id", "total_billed", "service_date"],
        )
