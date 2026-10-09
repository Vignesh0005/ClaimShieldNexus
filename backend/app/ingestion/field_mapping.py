"""Maps a tenant's field names onto ClaimShield's. The mapping is saved per tenant during
onboarding as {"their_field": "our_field"}; fields with no mapping pass through unchanged."""

# Names the onboarding screen offers that differ from the canonical schema.
ALIASES = {
    "procedure_code": "cpt_code",
    "diagnosis_code": "diagnosis_codes",
    "billed_amount": "billed_amount",
    "paid_amount": "paid_amount",
    "place_of_service": "service_location",
    "modifier": "modifiers",
}

CLAIM_FIELDS = {
    "claim_id", "member_id", "provider_id", "facility_id", "referring_provider_id", "service_date", "claim_type",
    "total_billed", "total_paid", "diagnosis_codes", "plan_type", "policy_start_date", "pre_auth_number",
    "member_age", "service_location", "documents_provided", "lines", "attributes",
}
LINE_FIELDS = {"line_id", "cpt_code", "modifiers", "units", "billed_amount", "paid_amount", "diagnosis_pointer"}


def apply_mapping(record: dict, mapping: dict[str, str] | None) -> dict:
    out: dict = {}
    for key, value in record.items():
        target = (mapping or {}).get(key, key)
        target = ALIASES.get(target, target)
        if isinstance(value, list) and target == "lines":
            value = [apply_mapping(line, mapping) if isinstance(line, dict) else line for line in value]
        out[target] = value
    return out


def validate_mapping(mapping: dict[str, str]) -> list[str]:
    """Returns the required canonical fields the mapping does not cover."""
    targets = {ALIASES.get(t, t) for t in mapping.values()}
    required = {"claim_id", "member_id", "provider_id", "service_date", "cpt_code", "billed_amount"}
    return sorted(required - targets)
