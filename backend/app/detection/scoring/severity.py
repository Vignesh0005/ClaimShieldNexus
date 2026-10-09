DEFAULT_THRESHOLDS = {"critical": 0.8, "high": 0.6, "medium": 0.4}


def severity(risk: float, thresholds: dict | None = None) -> str:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if risk >= t["critical"]:
        return "critical"
    if risk >= t["high"]:
        return "high"
    if risk >= t["medium"]:
        return "medium"
    return "low"


def priority_tier(risk: float, member_harm: float) -> str:
    if risk >= 0.8 or (risk >= 0.7 and member_harm >= 0.7):
        return "tier_1"
    if risk >= 0.6:
        return "tier_2"
    return "tier_3"
