"""Opt-in, tenant-scoped outbound webhooks, sent only after the transaction commits.

No detection or decision rules are changed. ORM observers collect changed objects;
WebhookSession snapshots their public results before commit and delivers afterwards.
"""
import asyncio
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import logger
from app.db.base import utcnow
from app.models import Case, CaseDecision, Claim, DetectionSignal, Tenant

REGISTRY_KEY = "outbound_webhook_secrets"  # Existing config readers redact keys containing 'secret'.
SUPPORTED_EVENTS = frozenset({"case.opened", "case.updated", "case.decided", "claim.processed", "claim.failed"})
RETRY_DELAYS = (0.5, 1.0)


def validate_destination(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError("Webhook URL must be an absolute HTTP(S) URL without credentials or a fragment.")
    if get_settings().is_production and parts.scheme != "https":
        raise ValueError("Production webhooks require HTTPS.")
    return url


def registrations(tenant: Tenant) -> list[dict]:
    registry = (tenant.config or {}).get(REGISTRY_KEY) or {}
    if not isinstance(registry, dict):
        logger.error("webhook_registry_invalid", tenant_id=str(tenant.id))
        return []
    return [entry for entry in registry.values() if isinstance(entry, dict)]


def sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def encode(payload: dict) -> bytes:
    # The exact bytes signed here are also sent to the receiver: do not use json= afterwards.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Delivery:
    url: str
    secret: str
    payload: dict


async def dispatch(delivery: Delivery) -> bool:
    raw_body = encode(delivery.payload)
    headers = {
        "Content-Type": "application/json",
        "X-ClaimShield-Signature": sign(delivery.secret, raw_body),
        "X-ClaimShield-Event-Id": delivery.payload["event_id"],
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(delivery.url, content=raw_body, headers=headers)
                response.raise_for_status()
                logger.info("webhook_delivered", webhook_event=delivery.payload["event"], event_id=delivery.payload["event_id"], tenant_id=delivery.payload["tenant_id"], claim_id=delivery.payload["claim_id"], attempt=attempt, status=response.status_code)
                return True
            except (httpx.HTTPError, ValueError) as exc:
                # Log identifiers and exception type, never webhook secrets or response bodies.
                logger.warning("webhook_delivery_failed", webhook_event=delivery.payload["event"], event_id=delivery.payload["event_id"], claim_id=delivery.payload["claim_id"], attempt=attempt, error=type(exc).__name__)
                if attempt < 3:
                    await asyncio.sleep(RETRY_DELAYS[attempt - 1])
    logger.error("webhook_delivery_exhausted", event_id=delivery.payload["event_id"], claim_id=delivery.payload["claim_id"])
    return False


async def result_payload(db: AsyncSession, tenant: Tenant, claim: Claim, topic: str, case: Case | None = None, decision: CaseDecision | None = None) -> dict:
    if case is None and claim.case_ref:
        case = (await db.execute(select(Case).where(Case.tenant_id == tenant.id, Case.id == claim.case_ref))).scalar_one_or_none()
    signals = (await db.execute(select(DetectionSignal).where(DetectionSignal.tenant_id == tenant.id, DetectionSignal.claim_id == claim.id).order_by(DetectionSignal.score.desc()))).scalars().all()
    flagged = case is not None and not (decision and decision.final_label == 0) and case.status != "false_positive"
    coverage_review = claim.risk_score is None and claim.processing_status == "processed"
    status = "error" if claim.processing_status == "failed" else "processing" if claim.processing_status == "processing" else "flagged" if flagged else "coverage_review" if coverage_review else "cleared"
    if decision is not None:
        status = "decided" if decision.final_label is not None else "flagged"
    # Internal SIU free text must only leave ClaimShield after tenant-specific approval.
    share_decision_details = (tenant.config or {}).get("integration_share_decision_details") is True
    base_url = get_settings().frontend_url.rstrip("/")
    return {
        "event": topic, "event_id": str(uuid.uuid4()), "schema_version": "1.0",
        "tenant_id": tenant.slug, "tenant_uuid": str(tenant.id), "occurred_at": utcnow().isoformat(),
        "claim_id": claim.claim_id, "job_id": claim.job_id, "case_id": case.case_id if case else None,
        "risk_score": claim.risk_score, "severity": claim.severity,
        "evidence_strength": claim.evidence_strength, "member_harm_score": claim.member_harm_score,
        "two_axis_quadrant": claim.two_axis_quadrant, "fraud_flagged": bool(flagged),
        "claimshield_status": status, "processing_status": claim.processing_status,
        "coverage_status": claim.coverage_status, "review_required": coverage_review,
        "top_reasons": [
            {"rule": s.rule_name or s.pattern_name or s.model_name or "unknown", "confidence": s.confidence if s.confidence is not None else s.score, "detector": s.detector}
            for s in signals if s.detector != "similarity"
        ][:5],
        "review_url": f"{base_url}/cases/{case.case_id}" if case else None,
        "case_status": case.status if case else None,
        "outcome": decision.decision if decision else None,
        "decision_id": decision.decision_id if decision else None,
        "notes": decision.notes if decision and share_decision_details else None,
        "decided_by": (decision.decided_by_label or (str(decision.decided_by) if decision.decided_by else None)) if decision and share_decision_details else None,
        "decision_final": decision.final_label is not None if decision else False,
        "error": "Detection could not complete. Contact the ClaimShield administrator." if claim.processing_status == "failed" else None,
        "disclaimer": "Mock system. Synthetic data only. A flag is a prompt for human review, not a fraud determination.",
    }


class WebhookSyncSession(Session):
    pass


@event.listens_for(WebhookSyncSession, "before_flush")
def _track_changes(session, _context, _instances):
    changes = session.info.setdefault("outbound_changes", {"claims": set(), "created": set(), "cases": set(), "decisions": set()})
    for obj in set(session.new) | set(session.dirty):
        if isinstance(obj, Claim):
            state = inspect(obj)
            if obj.processing_status in {"processed", "failed"} and (obj in session.new or state.attrs.processing_status.history.has_changes() or state.attrs.processed_at.history.has_changes()):
                changes["claims"].add(obj)
        elif isinstance(obj, Case):
            if obj in session.new:
                changes["created"].add(obj)
            elif any(inspect(obj).attrs[key].history.has_changes() for key in ("status", "assigned_to", "claim_count", "risk_score", "evidence_strength", "member_harm_score")):
                changes["cases"].add(obj)
        elif isinstance(obj, CaseDecision) and obj in session.new:
            changes["decisions"].add(obj)


async def prepare_deliveries(db: AsyncSession, changes: dict) -> list[Delivery]:
    deliveries = []
    tenants = {}
    payloads = {}  # One result per claim; a decision takes precedence over a generic case update.
    created_ids = {c.id for c in changes["created"]}

    async def eligible(tenant_id):
        if tenant_id not in tenants:
            tenant = await db.get(Tenant, tenant_id)
            tenants[tenant_id] = tenant if tenant and tenant.active and registrations(tenant) else None
        return tenants[tenant_id]

    for claim in changes["claims"]:
        tenant = await eligible(claim.tenant_id)
        if tenant is None:
            continue
        case = (await db.execute(select(Case).where(Case.tenant_id == tenant.id, Case.id == claim.case_ref))).scalar_one_or_none() if claim.case_ref else None
        topic = "claim.failed" if claim.processing_status == "failed" else "case.opened" if case and case.id in created_ids else "case.updated" if case else "claim.processed"
        payloads[(tenant.id, claim.id)] = await result_payload(db, tenant, claim, topic, case)

    for case in changes["created"] | changes["cases"]:
        tenant = await eligible(case.tenant_id)
        if tenant is None:
            continue
        claims = (await db.execute(select(Claim).where(Claim.tenant_id == tenant.id, Claim.case_ref == case.id))).scalars().all()
        for claim in claims:
            key = (tenant.id, claim.id)
            if key not in payloads:
                payloads[key] = await result_payload(db, tenant, claim, "case.opened" if case.id in created_ids else "case.updated", case)

    # A provider case can contain several claims: send the decision to every corresponding row.
    for decision in sorted(changes["decisions"], key=lambda d: d.decided_at):
        tenant = await eligible(decision.tenant_id)
        if tenant is None:
            continue
        case = (await db.execute(select(Case).where(Case.tenant_id == tenant.id, Case.id == decision.case_id))).scalar_one_or_none()
        if case is None:
            continue
        claims = (await db.execute(select(Claim).where(Claim.tenant_id == tenant.id, Claim.case_ref == case.id))).scalars().all()
        for claim in claims:
            payloads[(tenant.id, claim.id)] = await result_payload(db, tenant, claim, "case.decided", case, decision)

    for (tenant_id, _claim_id), payload in payloads.items():
        for entry in registrations(tenants[tenant_id]):
            if entry.get("enabled", True) and payload["event"] in entry.get("events", []):
                try:
                    url = validate_destination(entry["url"])
                    secret = entry["secret"]
                    if not isinstance(secret, str) or len(secret) < 16:
                        raise ValueError("Invalid secret")
                except (KeyError, ValueError, TypeError):
                    logger.error("webhook_registration_invalid", tenant_id=str(tenant_id), webhook_id=entry.get("id"))
                    continue
                deliveries.append(Delivery(url, secret, payload))
    return deliveries


class WebhookSession(AsyncSession):
    sync_session_class = WebhookSyncSession

    async def commit(self) -> None:
        # Snapshot results while ORM reads are still in this transaction, then COMMIT before HTTP.
        await self.flush()
        changes = self.info.pop("outbound_changes", None)
        deliveries = await prepare_deliveries(self, changes) if changes and any(changes.values()) else []
        await super().commit()
        for delivery in deliveries:
            try:
                await dispatch(delivery)
            except Exception as exc:  # noqa: BLE001
                # An external integration must never turn a committed decision into an API error.
                logger.error("webhook_dispatch_error", event_id=delivery.payload["event_id"], error=type(exc).__name__)

    async def rollback(self) -> None:
        self.info.pop("outbound_changes", None)
        await super().rollback()
