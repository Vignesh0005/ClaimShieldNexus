from pydantic import ValidationError

from app.core.exceptions import ValidationFailed
from app.ingestion.field_mapping import apply_mapping
from app.ingestion.normalizer import normalize_claim
from app.schemas.claim import ClaimIn


def validate_claim(record: dict, mapping: dict[str, str] | None = None) -> ClaimIn:
    """Maps, normalises and validates one inbound record. Raises ValidationFailed with a list of
    {field, message} so the sender can correct and resend."""
    normalized = normalize_claim(apply_mapping(record, mapping))
    try:
        claim = ClaimIn.model_validate(normalized)
    except ValidationError as exc:
        errors = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationFailed("The claim did not pass validation.", claim_id=record.get("claim_id"), errors=errors) from exc
    for line in claim.lines:
        if line.service_date is None:
            line.service_date = claim.service_date
    return claim
