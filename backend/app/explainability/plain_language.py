"""Plain-language wording for each signal. Wording is neutral on purpose: it describes what was
observed and never states or implies intent."""

SIGNAL_TEXT: dict[str, dict[str, str]] = {
    "duplicate_billing": {"label": "Duplicate billing", "plain": "A claim looks the same as one already submitted for the same patient, provider and day.", "clears": "the second claim is shown to be a corrected resubmission or a separate, documented service"},
    "upcoding": {"label": "Upcoding", "plain": "This provider bills the highest-level visit code much more often than similar providers.", "clears": "visit notes support the time and complexity billed"},
    "unbundling": {"label": "Unbundling", "plain": "Tests that are normally billed together as one panel were billed one by one.", "clears": "the tests were ordered and performed separately for a documented reason"},
    "ncci_edit": {"label": "Code pair edit", "plain": "Two procedure codes were billed together that are normally not paid together.", "clears": "records show the two services were distinct"},
    "phantom_services": {"label": "Service not supported by an encounter", "plain": "A billed service has no matching record of the visit.", "clears": "the encounter record or delivery confirmation is produced"},
    "excessive_utilization": {"label": "Excessive utilisation", "plain": "One patient was seen far more often in a month than is usual for this kind of provider.", "clears": "the treatment plan explains the visit frequency"},
    "impossible_timing": {"label": "Impossible timing", "plain": "More treatment time was billed in one day than is realistic, or a patient was billed in two distant places on the same day.", "clears": "dates or locations turn out to be data-entry errors, or services were delivered by supervised staff"},
    "referral_loop": {"label": "Referral loop", "plain": "A small group of providers keep referring the same patients to each other.", "clears": "the providers are part of a known care network or the referrals are clinically explained"},
    "shared_address": {"label": "Shared address", "plain": "Several providers are registered at the same address.", "clears": "the address is a shared medical office building"},
    "coding_validity": {"label": "Coding errors", "plain": "Some codes on the claim are malformed or do not match.", "clears": "the claim is corrected and resubmitted"},
    "provider_validity": {"label": "Provider record issue", "plain": "The provider is missing from the provider file or is not currently active or licensed.", "clears": "the provider file is updated or the licence is confirmed"},
    "member_eligibility": {"label": "Member eligibility issue", "plain": "The patient is missing from the eligibility file or cover had ended.", "clears": "eligibility on the service date is confirmed"},
    "units_cap": {"label": "Units above daily limit", "plain": "More units of a service were billed for one day than is normally possible for that service.", "clears": "records show the units were delivered, or the unit count is corrected"},
    "amount_outlier": {"label": "Unusually high amount", "plain": "A service was billed at several times the amount usually billed for it.", "clears": "the amount is a keying error that is corrected, or an itemised bill supports it"},
    "diagnosis_procedure_mismatch": {"label": "Procedure does not match diagnosis", "plain": "A procedure was billed, but none of the diagnoses on the claim is one it would normally be performed for.", "clears": "a diagnosis was left off the claim and is added, or records show why the procedure was needed"},
    "demographic_mismatch": {"label": "Service does not fit member's age or gender", "plain": "A service was billed that does not normally apply to a patient of this age or gender.", "clears": "the member's recorded age or gender is corrected, or records support the service"},
    "peer_outlier": {"label": "Billing far above peers", "plain": "This provider bills much more per patient, or sees each patient much more often, than similar providers.", "clears": "the provider's case mix or practice type explains the difference"},
    "split_billing": {"label": "Service split across days", "plain": "One service appears to have been billed in parts on consecutive days.", "clears": "records show separate services were delivered on each day"},
    "modifier_overuse": {"label": "Heavy use of distinct-service modifiers", "plain": "This provider marks services as separate and distinct much more often than similar providers.", "clears": "records support that the services were distinct"},
    "new_provider_burst": {"label": "New provider with high volume", "plain": "A provider with little or no billing history suddenly submitted a large number of claims.", "clears": "the provider took over an existing practice or patient list"},
    "provider_shopping": {"label": "Same service from many providers", "plain": "One patient received the same kind of service from many different providers within a month.", "clears": "referrals or second opinions explain the visits"},
    "xgboost": {"label": "Model score", "plain": "A statistical model trained on past reviewer decisions rates this claim as similar to ones that were referred.", "clears": "the leading factors are explained by the provider's case mix"},
    "isolation_forest": {"label": "Anomaly score", "plain": "The claim is statistically unusual compared with typical claims.", "clears": "the unusual values have an ordinary explanation"},
    "lof": {"label": "Local outlier score", "plain": "The claim differs from the claims most similar to it.", "clears": "the difference has an ordinary explanation"},
    "similar_cases": {"label": "Similar earlier cases", "plain": "Earlier claims that were billed in a similar way and flagged for the same reasons are on file. They are shown for comparison and do not affect the score.", "clears": "the earlier cases turn out to be unrelated"},
    "billing_spike": {"label": "Billing spike", "plain": "The provider's billing rose sharply compared with its own recent history.", "clears": "a practice change such as a new location or added staff explains the increase"},
}

BANNED_PHRASES = ("committed fraud", "is fraudulent", "fraudster", "guilty", "criminal", "stole", "scam", "is a fraud")


def label(name: str) -> str:
    return SIGNAL_TEXT.get(name, {}).get("label", name.replace("_", " ").capitalize())


def plain(name: str) -> str:
    return SIGNAL_TEXT.get(name, {}).get("plain", f"The '{name.replace('_', ' ')}' check was triggered.")


def clears(name: str) -> str:
    return SIGNAL_TEXT.get(name, {}).get("clears", "the pattern is explained by documentation")


def find_banned(text: str) -> list[str]:
    lowered = text.lower()
    return [p for p in BANNED_PHRASES if p in lowered]
