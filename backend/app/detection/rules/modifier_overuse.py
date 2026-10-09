from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.base import Rule
from app.detection.rules.peer_outlier import MIN_PEERS, comparable_peers
from app.utils.codes import NCCI_BYPASS_MODIFIERS


def bypass_lines(claims: list[ClaimData]) -> tuple[int, int]:
    """(lines carrying a bypass modifier, all lines)."""
    lines = [l for c in claims for l in c.lines if l.cpt_code]
    return sum(1 for l in lines if set(l.modifiers) & NCCI_BYPASS_MODIFIERS), len(lines)


class ModifierOveruse(Rule):
    name = "modifier_overuse"
    description = "A distinct-service modifier (25, 59, XE, XS, XP, XU) on a far higher share of lines than specialty peers."
    min_lines = 30
    min_peer_lines = 200
    min_rate = 0.30

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        if not bypass_lines([ctx.claim])[0]:
            return None  # only raised on a claim that itself uses one of the modifiers
        peers = comparable_peers(ctx)
        used, lines = bypass_lines(ctx.provider_window(90) + [ctx.claim])
        peer_lines = sum(p.lines for p in peers)
        if len(peers) < MIN_PEERS or lines < self.min_lines or peer_lines < self.min_peer_lines:
            return None
        rate, peer_rate = used / lines, sum(p.bypass_lines for p in peers) / peer_lines
        threshold = max(self.min_rate, 3 * peer_rate)
        if rate < threshold or threshold >= 1:
            return None
        # 0.55 at the threshold, rising to 0.95 when every line carries a bypass modifier.
        confidence = 0.55 + 0.40 * (rate - threshold) / (1 - threshold)
        return self.signal(
            confidence,
            {
                "provider_rate": round(rate, 2), "peer_rate": round(peer_rate, 2), "lines_counted": lines, "lines_with_modifier": used, "peer_lines_counted": peer_lines, "peers_compared": len(peers),
                "threshold_rate": round(threshold, 2), "modifiers": sorted(NCCI_BYPASS_MODIFIERS), "specialty": ctx.provider.specialty, "window_days": 90,
            },
            ["provider_id", "lines.modifiers"],
        )
