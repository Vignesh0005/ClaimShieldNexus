import math
from dataclasses import dataclass, field

from app.detection.context import DetectionContext, Signal
from app.detection.scoring.evidence_strength import evidence_strength
from app.detection.scoring.member_harm import member_harm_score
from app.detection.scoring.severity import priority_tier, severity
from app.detection.scoring.two_axis import quadrant
from app.utils.validators import clamp

WEIGHTS = {"rule": 0.30, "ml": 0.25, "graph": 0.20, "dollar": 0.15, "harm": 0.10}
# Low-weight data-quality signals do not drive the rule score.
EXCLUDED_FROM_RULE_SCORE = {"coding_validity"}


# A single near-certain rule finding sets a floor under the composite score, so a clear-cut,
# verifiable finding cannot be averaged away by detectors that had nothing to say.
MAX_RULE_FLOOR = 0.85


@dataclass
class RiskResult:
    risk_score: float
    suspicion_score: float
    evidence_strength: float
    member_harm_score: float
    two_axis_quadrant: str
    severity: str
    priority_tier: str
    components: dict = field(default_factory=dict)
    harm_factors: list[str] = field(default_factory=list)
    composite_risk: float = 0.0
    max_rule_confidence: float = 0.0


def aggregate(signals: list[Signal], detector: str) -> float:
    """Strongest signal from a detector, nudged up when several agree (noisy-or on the rest)."""
    scores = sorted((s.score for s in signals if s.detector == detector and s.name not in EXCLUDED_FROM_RULE_SCORE), reverse=True)
    if not scores:
        return 0.0
    rest = 1.0
    for s in scores[1:]:
        rest *= 1 - 0.25 * s
    return clamp(scores[0] + (1 - scores[0]) * (1 - rest))


def dollar_impact(total_billed: float | None) -> float:
    """0 at about 100, 1 at about 100,000 on a log scale."""
    return clamp((math.log10(max(total_billed or 0.0, 1.0)) - 2) / 3)


def max_rule_confidence(signals: list[Signal]) -> float:
    return max((s.confidence or s.score for s in signals if s.detector == "rule" and s.name not in EXCLUDED_FROM_RULE_SCORE), default=0.0)


def combine_risk(signals: list[Signal], dollar: float, harm: float, weights: dict | None = None) -> tuple[float, float, float]:
    """Returns (risk_score, composite, max_rule_confidence).

        composite  = 0.30*rule + 0.25*ml + 0.20*graph + 0.15*dollar + 0.10*harm
        risk_score = max(composite, max_rule_confidence * 0.85)
    """
    w = {**WEIGHTS, **(weights or {})}
    # Temporal findings describe provider behaviour in the same way graph findings do, so they
    # share the network-and-behaviour component rather than diluting the published weights.
    graph = max(aggregate(signals, "graph"), aggregate(signals, "temporal"))
    composite = w["rule"] * aggregate(signals, "rule") + w["ml"] * aggregate(signals, "ml") + w["graph"] * graph + w["dollar"] * dollar + w["harm"] * harm
    scored = [s for s in signals if s.detector in ("rule", "ml", "graph", "temporal")]
    if not scored:
        composite = min(composite, 0.2)  # amount and member profile alone never make a claim look suspicious
    top_rule = max_rule_confidence(signals)
    return round(clamp(max(composite, top_rule * MAX_RULE_FLOOR)), 4), round(clamp(composite), 4), round(top_rule, 4)


class RiskFusion:
    """Combines detector output into a composite risk score, the two-axis position and member harm."""

    def __init__(self, thresholds: dict | None = None, weights: dict | None = None):
        self.thresholds = thresholds
        self.weights = {**WEIGHTS, **(weights or {})}

    def fuse(self, ctx: DetectionContext, signals: list[Signal]) -> RiskResult:
        rule = aggregate(signals, "rule")
        ml = aggregate(signals, "ml")
        graph = max(aggregate(signals, "graph"), aggregate(signals, "temporal"))
        temporal = aggregate(signals, "temporal")
        harm, factors = member_harm_score(ctx)
        dollar = dollar_impact(ctx.claim.total_billed)

        risk, composite, top_rule = combine_risk(signals, dollar, harm, self.weights)
        suspicion = round(clamp(0.4 * rule + 0.35 * ml + 0.25 * graph), 4)
        evidence = evidence_strength(signals)
        return RiskResult(
            risk_score=risk,
            suspicion_score=suspicion,
            evidence_strength=evidence,
            member_harm_score=harm,
            two_axis_quadrant=quadrant(suspicion, evidence),
            severity=severity(risk, self.thresholds),
            priority_tier=priority_tier(risk, harm),
            composite_risk=composite,
            max_rule_confidence=top_rule,
            components={"composite": composite, "max_rule_confidence": top_rule, "rule": round(rule, 4), "ml": round(ml, 4), "graph": round(graph, 4), "temporal": round(temporal, 4), "dollar_impact": round(dollar, 4), "member_harm": harm},
            harm_factors=factors,
        )
