"""Rolling record of detection latency for this process. Feeds GET /api/v1/health/performance.
In-memory and per process: with several workers each reports its own figures."""
import time
from collections import deque

_samples: deque[tuple[float, float]] = deque(maxlen=5000)  # (unix time, milliseconds)


def record(ms: float) -> None:
    _samples.append((time.time(), float(ms)))


def reset() -> None:
    _samples.clear()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def percentiles(values: list[float]) -> dict:
    return {"p50": round(_percentile(values, 50), 1), "p95": round(_percentile(values, 95), 1), "p99": round(_percentile(values, 99), 1), "mean": round(sum(values) / len(values), 1) if values else 0.0}


def summary() -> dict:
    now = time.time()
    samples = list(_samples)
    values = [ms for _, ms in samples]
    last_minute = sum(1 for t, _ in samples if now - t <= 60)
    last_five = sum(1 for t, _ in samples if now - t <= 300)
    by_minute: dict[int, list[float]] = {}
    for t, ms in samples:
        if now - t <= 1800:
            by_minute.setdefault(int(t // 60), []).append(ms)
    series = [{"minute": time.strftime("%H:%M", time.localtime(m * 60)), "claims": len(v), "p50_ms": round(_percentile(v, 50), 1), "p95_ms": round(_percentile(v, 95), 1)} for m, v in sorted(by_minute.items())]
    return {
        "samples": len(values),
        "latency_ms": percentiles(values) if values else None,
        "throughput": {"claims_last_minute": last_minute, "claims_per_minute_5m": round(last_five / 5, 1)},
        "series": series,
    }
