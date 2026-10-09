import hashlib
import json

from app.schemas.claim import ClaimIn

HASH_KEY = "_content_hash"


def content_hash(claim: ClaimIn) -> str:
    """Stable hash of the claim's content. The same claim delivered twice (a retried request, an
    SQS redelivery) produces the same hash and is acknowledged without being processed again."""
    payload = claim.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
