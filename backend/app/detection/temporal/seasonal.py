from collections import defaultdict
from datetime import date


def month_of_year_index(monthly_totals: dict[date, float]) -> dict[int, float]:
    """Ratio of each calendar month's average billing to the overall monthly average. With less
    than a full year of data every month returns 1.0 (no seasonal adjustment)."""
    if len(monthly_totals) < 12:
        return {m: 1.0 for m in range(1, 13)}
    by_month: dict[int, list[float]] = defaultdict(list)
    for d, total in monthly_totals.items():
        by_month[d.month].append(total)
    overall = sum(monthly_totals.values()) / len(monthly_totals) or 1.0
    return {m: (sum(v) / len(v)) / overall if (v := by_month.get(m)) else 1.0 for m in range(1, 13)}


def deseasonalise(value: float, month: int, index: dict[int, float]) -> float:
    return value / max(index.get(month, 1.0), 0.1)
