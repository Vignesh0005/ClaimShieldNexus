from app.detection.context import DetectionContext
from app.detection.rules.duplicate_billing import best_match
from app.detection.rules.impossible_timing import billed_minutes
from app.detection.rules.upcoding import level5_rate
from app.utils.codes import PANELS

# Order matters: it is the column order of the training matrix and is stored with each model.
FEATURES = [
    "total_billed",
    "n_lines",
    "total_units",
    "n_diagnoses",
    "provider_avg_claim",
    "provider_peer_ratio",
    "billed_vs_provider_avg",
    "provider_claims_30d",
    "provider_members_30d",
    "visits_per_member_30d",
    "level5_em_rate",
    "duplicate_fields",
    "billed_hours_on_date",
    "unbundled_components",
    "has_referrer",
    "member_age",
]


def build_features(ctx: DetectionContext) -> dict[str, float]:
    claim = ctx.claim
    window90 = ctx.provider_window(90)
    window30 = ctx.provider_window(30)
    prior_avg = sum(c.total_billed for c in window90) / len(window90) if window90 else ctx.peers.avg_claim
    provider_avg = (sum(c.total_billed for c in window90) + claim.total_billed) / (len(window90) + 1)
    same_day = [c for c in ctx.provider_history if c.service_date == claim.service_date]
    codes = set(claim.cpt_codes)
    unbundled = max((len(codes & comps) for panel, comps in PANELS.items() if panel not in codes), default=0)
    _, dup_fields = best_match(ctx)
    rate, _ = level5_rate(window90 + [claim])
    age = claim.member_age if claim.member_age is not None else ctx.member.age
    return {
        "total_billed": float(claim.total_billed or 0),
        "n_lines": float(len(claim.lines)),
        "total_units": float(sum(l.units or 1 for l in claim.lines)),
        "n_diagnoses": float(len(claim.diagnosis_codes)),
        "provider_avg_claim": round(provider_avg, 2),
        "provider_peer_ratio": round(provider_avg / max(ctx.peers.avg_claim, 1.0), 3),
        "billed_vs_provider_avg": round((claim.total_billed or 0) / max(prior_avg, 1.0), 3),
        "provider_claims_30d": float(len(window30) + 1),
        "provider_members_30d": float(len({c.member_id for c in window30} | {claim.member_id})),
        "visits_per_member_30d": float(1 + sum(1 for c in window30 if c.member_id == claim.member_id)),
        "level5_em_rate": round(rate, 3),
        "duplicate_fields": float(len(dup_fields)),
        "billed_hours_on_date": round((billed_minutes(claim) + sum(billed_minutes(c) for c in same_day)) / 60, 2),
        "unbundled_components": float(unbundled),
        "has_referrer": 1.0 if claim.referring_provider_id else 0.0,
        "member_age": float(age if age is not None else 45),
    }


def to_row(features: dict[str, float], order: list[str] | None = None) -> list[float]:
    return [float(features.get(name, 0.0)) for name in (order or FEATURES)]
