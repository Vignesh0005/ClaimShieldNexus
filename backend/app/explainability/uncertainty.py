def limitations(signal_names: set[str], *, provider_id: str | None, ml_degraded: bool, claim_count: int, has_prior_outcome: bool, provider_known: bool, history_claims: int | None = None) -> list[str]:
    """What the system does not know about a case. Shown beside every explanation so a reviewer
    weighs the evidence with its gaps in view."""
    out: list[str] = []
    if not has_prior_outcome:
        out.append(f"No prior investigation outcome for {provider_id or 'this provider'}")
    if signal_names & {"upcoding", "impossible_timing", "excessive_utilization", "phantom_services"}:
        out.append("EHR visit notes are not available to the system; visit length and content are unverified")
    if "referral_loop" in signal_names:
        out.append("Referral loop legitimacy unverified; integrated care groups produce the same pattern")
    if "shared_address" in signal_names:
        out.append("Shared address may be a medical office building")
    if signal_names & {"xgboost", "isolation_forest", "lof"}:
        out.append("Model scores reflect similarity to past patterns, not proof; the model was trained on synthetic data")
    if ml_degraded:
        out.append("The ML models were unavailable for at least one claim; scores rely on rules, graph and temporal detectors")
    if signal_names & {"upcoding", "excessive_utilization", "xgboost", "peer_outlier", "modifier_overuse", "new_provider_burst"}:
        out.append("Peer comparison uses specialty only and does not adjust for case mix or practice size")
    if signal_names & {"units_cap", "amount_outlier", "diagnosis_procedure_mismatch", "demographic_mismatch", "split_billing", "provider_shopping"}:
        out.append("Unit limits, typical amounts and code groupings are illustrative samples, not a licensed code set or fee schedule")
    if not provider_known:
        out.append("Provider is not on the provider file; specialty and licence status are unknown")
    if history_claims is not None and history_claims < 20:
        out.append(f"Limited history: only {history_claims} claims from this provider in the last 90 days")
    if claim_count == 1:
        out.append("Based on a single claim; a pattern across claims has not been established")
    return out
