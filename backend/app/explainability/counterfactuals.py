from app.detection.context import Signal
from app.detection.scoring.fusion import combine_risk
from app.explainability.plain_language import clears, label


def rescore(signals: list[Signal], dollar: float, harm: float, weights: dict | None = None) -> float:
    """Same formula as RiskFusion.fuse, applied to a modified set of signals."""
    return combine_risk(signals, dollar, harm, weights)[0]


def generate(signals: list[Signal], dollar: float, harm: float, threshold: float, weights: dict | None = None, only: list[str] | None = None) -> dict:
    """What-if scenarios computed by actually re-scoring with one finding removed. Each answers
    "what would have to be true for this case not to be here?"."""
    baseline = rescore(signals, dollar, harm, weights)
    names = list(dict.fromkeys(s.name for s in signals))
    scenarios = []
    for name in only or names:
        if name not in names:
            continue
        remaining = [s for s in signals if s.name != name]
        risk = rescore(remaining, dollar, harm, weights)
        scenarios.append(
            {
                "scenario": f"If {clears(name)}",
                "removes": name,
                "label": label(name),
                "original_risk": baseline,
                "counterfactual_risk": risk,
                "change": round(risk - baseline, 4),
                "would_still_route": risk >= threshold,
            }
        )
    if len(names) > 1 and not only:
        risk = rescore([], dollar, harm, weights)
        scenarios.append({"scenario": "If every finding above were explained", "removes": "all", "label": "All findings", "original_risk": baseline, "counterfactual_risk": risk, "change": round(risk - baseline, 4), "would_still_route": risk >= threshold})
    scenarios.sort(key=lambda s: s["counterfactual_risk"])
    return {"baseline_risk": baseline, "routing_threshold": threshold, "scenarios": scenarios}


def as_sentences(result: dict) -> list[str]:
    return [f"{s['scenario']} -> risk drops to {s['counterfactual_risk']:.0%}" for s in result["scenarios"] if s["removes"] != "all"]
