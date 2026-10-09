from collections import defaultdict
from datetime import date, timedelta

from app.detection.context import ClaimData
from app.utils.dates import week_start


def weekly_series(claims: list[ClaimData], end: date, weeks: int = 13) -> list[float]:
    """Billed amount per week for the `weeks` weeks ending in the week of `end`, oldest first.
    Weeks with no claims are zero, so a quiet provider is not mistaken for a missing one."""
    totals: dict[date, float] = defaultdict(float)
    for c in claims:
        if c.service_date:
            totals[week_start(c.service_date)] += c.total_billed or 0.0
    last = week_start(end)
    return [totals.get(last - timedelta(weeks=i), 0.0) for i in range(weeks - 1, -1, -1)]


def provider_baseline(series: list[float]) -> dict:
    """Mean and spread of the weeks before the most recent one."""
    prior = series[:-1]
    if not prior:
        return {"mean": 0.0, "std": 0.0, "weeks": 0}
    mean = sum(prior) / len(prior)
    var = sum((x - mean) ** 2 for x in prior) / len(prior)
    return {"mean": mean, "std": var**0.5, "weeks": len(prior)}
