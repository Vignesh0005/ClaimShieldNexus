from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule


class MemberEligibility(Rule):
    name = "member_eligibility"
    description = "The member is not on the eligibility file, or cover had ended on the service date."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        m = ctx.member
        if not ctx.member_master_loaded or not ctx.claim.member_id:
            return None
        if not m.known:
            return self.signal(0.6, {"reason": "Member ID is not on the eligibility file", "member_id": m.member_id}, ["member_id"])
        if m.eligibility_end and ctx.claim.service_date and ctx.claim.service_date > m.eligibility_end:
            return self.signal(
                0.85,
                {"reason": "Service date is after the member's cover ended", "eligibility_end": str(m.eligibility_end), "service_date": str(ctx.claim.service_date)},
                ["member_id", "service_date"],
            )
        return None
