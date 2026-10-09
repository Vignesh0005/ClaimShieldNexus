from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule


class ReciprocalReferrals(Rule):
    """Fires when the billing provider is part of a closed referral loop (found on the referral
    graph) or, failing that, when it and the referring provider send patients to each other.

    The graph detector reports the same loop with network-level evidence; this rule records the
    loop as a matter-of-record finding on the claim itself."""

    name = "referral_loop"
    description = "This provider is part of a closed referral loop, or exchanges referrals with the referring provider."
    min_each_way = 2

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        if ctx.referral_loop:
            confidence = 0.90 + 0.01 * min(len(ctx.referral_loop), 5) + 0.02 * min(1.0, ctx.referral_loop_count / 40)
            return self.signal(
                confidence,
                {"loop_size": len(ctx.referral_loop), "loop_providers": ctx.referral_loop, "referrals_in_loop": ctx.referral_loop_count},
                ["provider_id", "referring_provider_id"],
            )
        me, ref = ctx.claim.provider_id, ctx.claim.referring_provider_id
        if not me or not ref or me == ref:
            return None
        inbound = sum(1 for a, b in ctx.referral_edges if a == ref and b == me) + 1  # this claim is one
        outbound = sum(1 for a, b in ctx.referral_edges if a == me and b == ref)
        if inbound < self.min_each_way or outbound < self.min_each_way:
            return None
        volume = inbound + outbound
        return self.signal(
            0.6 + 0.3 * min(1.0, volume / 20),
            {"referring_provider_id": ref, "referrals_received": inbound, "referrals_sent_back": outbound},
            ["provider_id", "referring_provider_id"],
        )
