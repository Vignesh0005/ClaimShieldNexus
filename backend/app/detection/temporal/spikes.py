from datetime import timedelta

from app.detection.context import DetectionContext, Signal, severity_for
from app.detection.temporal.baseline import provider_baseline, weekly_series
from app.detection.temporal.zscore import latest_zscore


def billing_spike(ctx: DetectionContext) -> Signal | None:
    """Flags a provider whose recent billing departs sharply from its own history."""
    claim = ctx.claim
    if claim.service_date is None:
        return None
    history = ctx.provider_history + [claim]
    series = weekly_series(history, claim.service_date, weeks=13)
    z = latest_zscore(series)
    recent_start = claim.service_date - timedelta(days=30)
    recent = sum(c.total_billed for c in history if c.service_date and c.service_date > recent_start)
    earlier = sum(c.total_billed for c in history if c.service_date and c.service_date <= recent_start) / 2  # 60 days -> per 30
    if z is None or earlier <= 0:
        return None
    change = (recent - earlier) / earlier
    if z < 2.5 or change < 1.0:
        return None
    score = round(min(0.95, 0.5 + z / 12 + min(change, 4) / 20), 2)
    base = provider_baseline(series)
    return Signal(
        "temporal",
        "billing_spike",
        score,
        severity=severity_for(score),
        evidence={
            "change_30d_pct": round(change * 100),
            "billed_last_30d": round(recent, 2),
            "billed_prior_per_30d": round(earlier, 2),
            "latest_week_zscore": round(z, 1),
            "weekly_baseline": round(base["mean"], 2),
        },
        source_fields=["provider_id", "service_date", "total_billed"],
    )
