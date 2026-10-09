from abc import ABC, abstractmethod

from app.detection.context import DetectionContext, Signal, severity_for


class Rule(ABC):
    """An FWA rule. Returns a Signal when its conditions are met, otherwise None.

    A signal says "this pattern is present and worth a reviewer's time". It is not a conclusion
    about intent, and every signal carries the evidence and source fields it was derived from.

    Confidence is how certain it is that the described pattern is present in the data, never how
    likely it is that anything improper happened. Patterns that are a matter of record (an exact
    duplicate, more hours billed than a day holds, a closed referral loop) start at 0.90.
    Statistical patterns (a rate far above peers) are graded by how far past the line they are."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def evaluate(self, ctx: DetectionContext) -> Signal | None: ...

    def signal(self, confidence: float, evidence: dict, source_fields: list[str], severity: str | None = None) -> Signal:
        confidence = round(max(0.0, min(0.99, confidence)), 2)
        return Signal(
            detector="rule",
            name=self.name,
            score=confidence,
            confidence=confidence,
            severity=severity or severity_for(confidence),
            evidence=evidence,
            source_fields=source_fields,
        )
