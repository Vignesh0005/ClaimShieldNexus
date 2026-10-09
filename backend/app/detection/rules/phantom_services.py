from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import DME_PREFIXES


class PhantomServices(Rule):
    name = "phantom_services"
    description = "A billed service has no supporting encounter, or equipment was billed with no prior visit."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        a = ctx.claim.attributes
        reasons: list[str] = []
        confidence = 0.0
        if a.get("encounter_verified") is False:
            reasons.append("No matching encounter record for the service date")
            confidence = max(confidence, 0.9)
        if a.get("member_deceased_date") and ctx.claim.service_date and str(ctx.claim.service_date) > str(a["member_deceased_date"]):
            reasons.append("Service date is after the member's recorded date of death")
            confidence = max(confidence, 0.97)
        dme = [c for c in ctx.claim.cpt_codes if c.startswith(DME_PREFIXES)]
        if dme and ctx.member.known:
            prior_visits = [c for c in ctx.member_window(90) if c.provider_id != ctx.claim.provider_id or not set(c.cpt_codes) & set(dme)]
            if not prior_visits:
                reasons.append(f"Equipment codes {', '.join(dme)} with no qualifying visit for this member in the prior 90 days")
                confidence = max(confidence, 0.90)
        if not reasons:
            return None
        return self.signal(confidence, {"reasons": reasons, "equipment_codes": dme}, ["member_id", "service_date", "lines.cpt_code"])
