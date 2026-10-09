import hashlib
import hmac
import json
from collections.abc import AsyncIterator

from app.core.exceptions import Unauthorized, ValidationFailed
from app.ingestion.adapters.base import IngestionAdapter


def verify_signature(body: bytes, signature: str | None, secret: str) -> None:
    """HMAC-SHA256 of the raw body, hex encoded, sent as `X-ClaimShield-Signature: sha256=<hex>`."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    supplied = (signature or "").removeprefix("sha256=")
    if not hmac.compare_digest(expected, supplied):
        raise Unauthorized("Webhook signature did not match.")


class WebhookAdapter(IngestionAdapter):
    """Claims pushed by the tenant's system: a claim object, a list, or {"claims": [...]}."""

    name = "webhook"

    def __init__(self, body: bytes, signature: str | None = None, secret: str | None = None):
        if secret:
            verify_signature(body, signature, secret)
        try:
            self.payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValidationFailed("Webhook body is not valid JSON.") from exc

    async def records(self) -> AsyncIterator[dict]:
        payload = self.payload
        items = payload if isinstance(payload, list) else payload.get("claims", [payload]) if isinstance(payload, dict) else []
        for item in items:
            yield item
