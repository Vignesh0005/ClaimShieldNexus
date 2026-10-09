from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import EM_CODES, EM_HIGH_LEVEL


def level5_rate(claims: list[ClaimData]) -> tuple[float, int]:
    em = [code for c in claims for code in c.cpt_codes if code in EM_CODES]
    if not em:
        return 0.0, 0
    return sum(1 for code in em if code in EM_HIGH_LEVEL) / len(em), len(em)


class Upcoding(Rule):
    name = "upcoding"
    description = "Highest-level evaluation codes billed far more often than specialty peers."
    min_visits = 10

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        if not set(ctx.claim.cpt_codes) & EM_HIGH_LEVEL:
            return None
        rate, n = level5_rate(ctx.provider_history + [ctx.claim])
        peer = max(ctx.peers.level5_rate, 0.01)
        if n < self.min_visits or rate < max(0.4, 3 * peer):
            return None
        confidence = 0.55 + 0.4 * min(1.0, (rate - 0.4) / 0.5)
        return self.signal(
            confidence,
            {"level5_em_rate": round(rate, 2), "peer_level5_em_rate": round(peer, 2), "em_visits_in_window": n, "window_days": 90},
            ["provider_id", "lines.cpt_code"],
        )
