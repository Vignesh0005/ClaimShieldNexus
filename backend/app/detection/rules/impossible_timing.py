from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import TYPICAL_MINUTES
from app.utils.geo import haversine_km


def billed_minutes(claim: ClaimData) -> int:
    return sum(TYPICAL_MINUTES.get(l.cpt_code or "", 0) * max(l.units or 1, 1) for l in claim.lines)


class ImpossibleTiming(Rule):
    name = "impossible_timing"
    description = "More service time billed in one day than a day contains, or one member billed at two distant places on the same day."
    max_minutes = 16 * 60  # flag well before a literal 24 hours: 16 hours of face-to-face time is already implausible
    min_km = 300

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        claim = ctx.claim
        if claim.service_date is None:
            return None
        same_day = [c for c in ctx.provider_history if c.service_date == claim.service_date]
        minutes = billed_minutes(claim) + sum(billed_minutes(c) for c in same_day)
        if minutes > self.max_minutes:
            hours = minutes / 60
            return self.signal(
                0.90 + 0.08 * min(1.0, (hours - 16) / 8),
                {"billed_hours_on_date": round(hours, 1), "claims_on_date": len(same_day) + 1, "service_date": str(claim.service_date), "basis": "typical minutes per procedure code"},
                ["provider_id", "service_date", "lines.cpt_code", "lines.units"],
            )

        here = ctx.facility_locations.get(claim.facility_id or "")
        if here:
            for other in ctx.member_history:
                there = ctx.facility_locations.get(other.facility_id or "")
                if other.service_date != claim.service_date or not there or other.facility_id == claim.facility_id:
                    continue
                km = haversine_km(here[0], here[1], there[0], there[1])
                if km >= self.min_km:
                    return self.signal(
                        0.90 + 0.08 * min(1.0, km / 2000),
                        {"pattern": "impossible_geography", "distance_km": round(km), "locations": [here[2], there[2]], "other_claim_id": other.claim_id, "service_date": str(claim.service_date)},
                        ["member_id", "facility_id", "service_date"],
                    )
        return None
