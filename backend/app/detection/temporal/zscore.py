from app.detection.temporal.baseline import provider_baseline


def latest_zscore(series: list[float], min_weeks: int = 6) -> float | None:
    """Z-score of the most recent week against the provider's own earlier weeks. Returns None when
    there is too little history to say what is normal for this provider."""
    base = provider_baseline(series)
    active_weeks = sum(1 for x in series[:-1] if x > 0)
    if base["weeks"] < min_weeks or active_weeks < min_weeks // 2:
        return None
    # Floor the spread at 10% of the mean so a perfectly steady biller does not produce huge
    # z-scores from a small change.
    spread = max(base["std"], 0.1 * base["mean"], 1.0)
    return (series[-1] - base["mean"]) / spread


def rolling_zscores(series: list[float], window: int = 8) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(series)):
        out.append(latest_zscore(series[max(0, i - window) : i + 1], min_weeks=min(window, 4)) if i >= 4 else None)
    return out
