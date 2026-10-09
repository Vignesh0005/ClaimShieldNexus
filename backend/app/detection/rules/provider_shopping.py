from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import SERVICE_GROUPS


def service_groups(claim: ClaimData) -> set[str]:
    return {SERVICE_GROUPS[c] for c in claim.cpt_codes if c in SERVICE_GROUPS}


class ProviderShopping(Rule):
    name = "provider_shopping"
    description = "One member receiving the same kind of service from many different providers within 30 days."
    window_days = 30
    min_providers = 5

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        if not claim.member_id or not claim.provider_id:
            return None
        recent = ctx.member_window(self.window_days) + [claim]
        best: tuple[int, str, list[ClaimData]] | None = None
        for group in sorted(service_groups(claim)):
            matching = [c for c in recent if c.provider_id and group in service_groups(c)]
            providers = len({c.provider_id for c in matching})
            if providers >= self.min_providers and (best is None or providers > best[0]):
                best = (providers, group, matching)
        if best is None:
            return None
        providers, group, matching = best
        # Five providers is 0.60; ten or more is 0.90.
        confidence = 0.60 + 0.30 * min(1.0, (providers - self.min_providers) / self.min_providers)
        return self.signal(
            confidence,
            {
                "member_id": claim.member_id, "service_group": group, "distinct_providers": providers, "provider_ids": sorted({c.provider_id for c in matching}),
                "claim_ids": [c.claim_id for c in sorted(matching, key=lambda c: (c.service_date, c.claim_id))], "window_days": self.window_days, "threshold": self.min_providers,
                "grouping_source": "Illustrative sample of service groups",
            },
            ["member_id", "provider_id", "service_date", "lines.cpt_code"],
        )
