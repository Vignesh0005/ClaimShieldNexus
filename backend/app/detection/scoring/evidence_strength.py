from app.detection.context import Signal
from app.utils.validators import clamp


def evidence_strength(signals: list[Signal]) -> float:
    """How well-supported the suspicion is, separate from how high it is.

    Suspicion asks "how unusual does this look"; evidence asks "how much can a reviewer verify".
    It rises with independent detectors agreeing, with rule findings that cite concrete records,
    and falls when the only support is an unexplained model score."""
    if not signals:
        return 0.0
    signals = [s for s in signals if s.detector != "similarity"]  # context for the reviewer, not evidence
    if not signals:
        return 0.0
    detectors = {s.detector for s in signals}
    best_rule = max((s.confidence or s.score for s in signals if s.detector == "rule" and s.name != "coding_validity"), default=0.0)
    citable = sum(1 for s in signals if s.evidence and s.detector in ("rule", "graph", "temporal"))
    score = 0.2 + 0.15 * (len(detectors) - 1) + 0.35 * best_rule + 0.05 * min(citable, 4)
    if detectors == {"ml"}:
        score = min(score, 0.35)  # a model score with nothing a person can check is weak evidence
    return round(clamp(score), 2)
