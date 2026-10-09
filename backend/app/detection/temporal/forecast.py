import math

HORIZONS = (30, 60, 90)
MODEL_VERSION = "linear_trend_v1"


def linear_trend(series: list[float]) -> tuple[float, float]:
    """Least-squares slope and intercept of a weekly series."""
    n = len(series)
    if n < 2:
        return 0.0, series[0] if series else 0.0
    mean_x, mean_y = (n - 1) / 2, sum(series) / n
    denom = sum((i - mean_x) ** 2 for i in range(n))
    slope = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(series)) / denom
    return slope, mean_y - slope * mean_x


def forecast_provider(weekly: list[float], current_risk: float | None) -> list[dict]:
    """Projects billed dollars over the next 30, 60 and 90 days from the weekly trend, and a
    probability that the provider is routed for review in that window. This is a planning aid for
    SIU staffing, deliberately simple and labelled with its method."""
    slope, intercept = linear_trend(weekly)
    n = len(weekly)
    mean = sum(weekly) / n if n else 0.0
    growth = slope / mean if mean > 0 else 0.0  # weekly growth as a share of average billing
    out = []
    for days in HORIZONS:
        weeks = days / 7
        projected = sum(max(0.0, intercept + slope * (n + w)) for w in range(math.ceil(weeks)))
        logit = -2.0 + 4.0 * (current_risk or 0.0) + 6.0 * growth * (days / 30)
        out.append({"horizon_days": days, "predicted_dollars": round(projected, 2), "risk_probability": round(1 / (1 + math.exp(-logit)), 4)})
    return out
