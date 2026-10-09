from dataclasses import dataclass, field

from app.detection.context import Signal, severity_for
from app.detection.graph.builder import ReferralEdge, build_referral_graph
from app.detection.graph.ownership import common_owner
from app.detection.graph.referral_loops import loop_referral_count, loops_for_provider
from app.detection.graph.shared_address import shared_address_count


@dataclass
class LoopStats:
    """Claim totals for the providers in a loop, supplied by the pipeline from the database."""

    total_claims: int = 0
    total_dollars: float = 0.0
    members: set[str] = field(default_factory=set)


@dataclass
class LoopFinding:
    providers: list[str]
    referrals: int


class GraphEngine:
    def find_loop(self, provider_id: str | None, referrals: list[ReferralEdge]) -> LoopFinding | None:
        """The strongest referral loop this provider belongs to, if any."""
        if not provider_id or not referrals:
            return None
        g = build_referral_graph(referrals)
        loops = loops_for_provider(g, provider_id)
        if not loops:
            return None
        best = max(loops, key=lambda loop: (loop_referral_count(g, loop), -len(loop)))
        return LoopFinding(best, loop_referral_count(g, best))

    def signals(
        self,
        provider_id: str | None,
        loop: LoopFinding | None,
        stats: LoopStats | None,
        addresses: dict[str, str | None],
        owners: dict[str, str | None],
    ) -> list[Signal]:
        out: list[Signal] = []
        if loop is not None:
            score = round(min(0.95, 0.55 + 0.05 * len(loop.providers) + 0.1 * min(1.0, loop.referrals / 40)), 2)
            evidence = {
                "loop_members": loop.providers,
                "referrals_in_loop": loop.referrals,
                "total_claims_in_loop": stats.total_claims if stats else None,
                "total_dollars": round(stats.total_dollars, 2) if stats else None,
                "members_affected": len(stats.members) if stats else None,
                "common_owner": common_owner(owners, loop.providers),
            }
            out.append(Signal("graph", "referral_loop", score, severity=severity_for(score), evidence=evidence, source_fields=["provider_id", "referring_provider_id"]))
        if provider_id:
            shared = shared_address_count(addresses, provider_id)
            if shared >= 2:
                score = round(min(0.8, 0.45 + 0.08 * shared), 2)
                out.append(
                    Signal("graph", "shared_address", score, severity=severity_for(score), evidence={"providers_at_same_address": shared, "address": addresses.get(provider_id)}, source_fields=["provider_id"])
                )
        return out
