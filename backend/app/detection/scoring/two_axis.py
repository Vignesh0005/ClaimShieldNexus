THRESHOLD = 0.7


def quadrant(suspicion: float, evidence: float, threshold: float = THRESHOLD) -> str:
    """siu: high suspicion, strong evidence. investigate: high suspicion, evidence still thin.
    review: well-evidenced but lower suspicion. dismiss: neither (no action, kept for audit)."""
    if suspicion >= threshold and evidence >= threshold:
        return "siu"
    if suspicion >= threshold:
        return "investigate"
    if evidence >= threshold:
        return "review"
    return "dismiss"
