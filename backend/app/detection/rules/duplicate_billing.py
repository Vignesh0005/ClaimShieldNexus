from app.detection.context import ClaimData, DetectionContext, Signal
from app.detection.rules.base import Rule

FIELDS = ["member_id", "provider_id", "service_date", "cpt_code", "billed_amount"]


def match_fields(a: ClaimData, b: ClaimData) -> list[str]:
    matched = []
    if a.member_id and a.member_id == b.member_id:
        matched.append("member_id")
    if a.provider_id and a.provider_id == b.provider_id:
        matched.append("provider_id")
    if a.service_date and a.service_date == b.service_date:
        matched.append("service_date")
    if set(a.cpt_codes) & set(b.cpt_codes):
        matched.append("cpt_code")
    if a.total_billed and abs(a.total_billed - b.total_billed) <= 0.01 * max(a.total_billed, 1):
        matched.append("billed_amount")
    return matched


def best_match(ctx: DetectionContext) -> tuple[ClaimData | None, list[str]]:
    best: tuple[ClaimData | None, list[str]] = (None, [])
    seen: set[str] = set()
    for other in ctx.provider_history + ctx.member_history:
        if other.claim_id in seen or other.claim_id == ctx.claim.claim_id:
            continue
        seen.add(other.claim_id)
        fields = match_fields(ctx.claim, other)
        if len(fields) > len(best[1]):
            best = (other, fields)
    return best


class DuplicateBilling(Rule):
    name = "duplicate_billing"
    description = "Same member, provider, service date and procedure as an earlier claim."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        other, fields = best_match(ctx)
        core = {"member_id", "provider_id", "service_date", "cpt_code"}
        if other is None or not core.issubset(fields):
            return None
        # Four identifying fields match; an identical billed amount as well makes it near-certain.
        confidence = 0.98 if "billed_amount" in fields else 0.88
        return self.signal(
            confidence,
            {"matched_claim_id": other.claim_id, "match_percentage": confidence, "matching_fields": fields},
            ["claim_id", "member_id", "provider_id", "service_date", "lines.cpt_code"],
        )
