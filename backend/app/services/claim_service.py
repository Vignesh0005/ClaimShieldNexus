import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import metrics
from app.core.audit import AuditLogger
from app.core.events import event_bus
from app.core.exceptions import Conflict, NotFound
from app.core.logging import logger
from app.core.security import Principal
from app.core.tenancy import set_current_tenant
from app.db.session import session_scope
from app.detection.ml.training import SYNTHETIC_WARNING
from app.detection.pipeline import DetectionPipeline, DetectionResult
from app.ingestion.idempotency import HASH_KEY, content_hash
from app.ingestion.validator import validate_claim
from app.models import Claim, ClaimLineItem, DetectionSignal, Referral, Tenant
from app.schemas.claim import ClaimIn


async def find(db: AsyncSession, tenant_id: uuid.UUID, claim_id: str) -> Claim | None:
    return (await db.execute(select(Claim).where(Claim.tenant_id == tenant_id, Claim.claim_id == claim_id))).scalar_one_or_none()


async def get(db: AsyncSession, tenant_id: uuid.UUID, claim_id: str) -> Claim:
    claim = await find(db, tenant_id, claim_id)
    if claim is None:
        raise NotFound(f"Claim '{claim_id}' not found.")
    return claim


async def store(db: AsyncSession, tenant: Tenant, claim_in: ClaimIn, source: str = "api", principal: Principal | None = None) -> tuple[Claim, bool]:
    """Stores a validated claim. Returns (claim, duplicate). Re-sending an identical claim is
    acknowledged without storing or processing it again; the same claim ID with different content
    is refused so an earlier submission is never silently overwritten."""
    digest = content_hash(claim_in)
    existing = await find(db, tenant.id, claim_in.claim_id)
    if existing is not None:
        if (existing.attributes or {}).get(HASH_KEY) == digest:
            return existing, True
        raise Conflict(f"Claim '{claim_in.claim_id}' already exists with different content. Send a corrected claim under a new claim ID.", claim_id=claim_in.claim_id)

    attributes = {**claim_in.attributes, HASH_KEY: digest, "_source": source}
    if claim_in.service_location:
        attributes["service_location"] = claim_in.service_location
    if claim_in.documents_provided is not None:
        attributes["documents_provided"] = claim_in.documents_provided
    claim = Claim(
        tenant_id=tenant.id, claim_id=claim_in.claim_id, member_id=claim_in.member_id, provider_id=claim_in.provider_id,
        facility_id=claim_in.facility_id, referring_provider_id=claim_in.referring_provider_id, service_date=claim_in.service_date,
        claim_type=claim_in.claim_type, total_billed=claim_in.total_billed, total_paid=claim_in.total_paid,
        diagnosis_codes=claim_in.diagnosis_codes, plan_type=claim_in.plan_type, policy_start_date=claim_in.policy_start_date,
        pre_auth_number=claim_in.pre_auth_number, member_age=claim_in.member_age, attributes=attributes,
        processing_status="processing", job_id=f"job_{uuid.uuid4().hex[:12]}",
    )
    claim.lines = [
        ClaimLineItem(
            tenant_id=tenant.id, line_id=l.line_id, cpt_code=l.cpt_code, modifiers=l.modifiers, units=l.units,
            billed_amount=l.billed_amount, paid_amount=l.paid_amount, service_date=l.service_date, diagnosis_pointer=l.diagnosis_pointer,
        )
        for l in claim_in.lines
    ]
    db.add(claim)
    if claim_in.referring_provider_id and claim_in.referring_provider_id != claim_in.provider_id:
        db.add(Referral(tenant_id=tenant.id, from_provider_id=claim_in.referring_provider_id, to_provider_id=claim_in.provider_id, member_id=claim_in.member_id, claim_id=claim_in.claim_id, referral_date=claim_in.service_date))
    await db.flush()
    await AuditLogger(db).log("claim.ingested", "claim", claim.claim_id, principal=principal, tenant_id=tenant.id, actor_type="api" if principal is None else principal.actor_type, details={"source": source, "lines": len(claim.lines)})
    metrics.claims_ingested.labels(str(tenant.id)).inc()
    return claim, False


async def ingest_record(db: AsyncSession, tenant: Tenant, record: dict, source: str = "api", process: bool = False, principal: Principal | None = None) -> tuple[Claim, bool, DetectionResult | None]:
    """Validate, store and optionally run detection in the same transaction (seeding, SQS, demo)."""
    claim, duplicate = await store(db, tenant, validate_claim(record, tenant.field_mapping), source, principal)
    result = None
    if process and not duplicate:
        result = await run_pipeline(db, tenant, claim)
    return claim, duplicate, result


async def run_pipeline(db: AsyncSession, tenant: Tenant, claim: Claim) -> DetectionResult:
    result = await DetectionPipeline(db, tenant).run(claim)
    await event_bus.publish("claim.processed", {"tenant_id": str(tenant.id), "claim_id": claim.claim_id, "risk_score": claim.risk_score, "case_id": result.case_id})
    return result


async def process_claim(tenant_id: uuid.UUID, claim_uuid: uuid.UUID) -> None:
    """Background entry point: opens its own session, runs detection and records failure on the
    claim so its status endpoint tells the sender what happened."""
    set_current_tenant(tenant_id)
    try:
        async with session_scope(tenant_id) as db:
            tenant = await db.get(Tenant, tenant_id)
            claim = await db.get(Claim, claim_uuid)
            if tenant is None or claim is None or claim.tenant_id != tenant_id:
                return
            await run_pipeline(db, tenant, claim)
    except Exception as exc:  # noqa: BLE001
        logger.error("claim_processing_failed", claim_uuid=str(claim_uuid), error=str(exc))
        async with session_scope(tenant_id) as db:
            claim = await db.get(Claim, claim_uuid)
            if claim is not None:
                claim.processing_status, claim.processing_error = "failed", str(exc)[:500]
        if not get_settings().process_inline:
            raise  # let the worker retry


def dispatch(background_tasks, claim: Claim) -> None:
    """Queue detection for a stored claim. Call only after the claim has been committed."""
    if get_settings().process_inline:
        background_tasks.add_task(process_claim, claim.tenant_id, claim.id)
    else:
        from app.workers.tasks.detection_task import run_detection

        run_detection.delay(str(claim.id), str(claim.tenant_id))


async def list_claims(db: AsyncSession, tenant_id: uuid.UUID, *, limit: int, offset: int, provider_id: str | None = None, member_id: str | None = None, min_risk: float | None = None, status: str | None = None) -> tuple[list[Claim], int]:
    where = [Claim.tenant_id == tenant_id]
    if provider_id:
        where.append(Claim.provider_id == provider_id)
    if member_id:
        where.append(Claim.member_id == member_id)
    if min_risk is not None:
        where.append(Claim.risk_score >= min_risk)
    if status:
        where.append(Claim.processing_status == status)
    total = (await db.execute(select(func.count()).select_from(Claim).where(*where))).scalar_one()
    rows = (await db.execute(select(Claim).where(*where).order_by(Claim.risk_score.desc().nulls_last(), Claim.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return list(rows), total


async def signals(db: AsyncSession, tenant_id: uuid.UUID, claim: Claim) -> list[DetectionSignal]:
    rows = await db.execute(select(DetectionSignal).where(DetectionSignal.tenant_id == tenant_id, DetectionSignal.claim_id == claim.id).order_by(DetectionSignal.score.desc()))
    return list(rows.scalars().all())


def claim_summary(c: Claim) -> dict:
    return {
        "claim_id": c.claim_id, "member_id": c.member_id, "provider_id": c.provider_id, "facility_id": c.facility_id,
        "service_date": c.service_date, "claim_type": c.claim_type, "total_billed": c.total_billed, "total_paid": c.total_paid,
        "coverage_status": c.coverage_status, "risk_score": c.risk_score, "severity": c.severity, "priority_tier": c.priority_tier,
        "two_axis_quadrant": c.two_axis_quadrant, "status": c.processing_status, "processed_at": c.processed_at,
    }


def claim_detail(c: Claim) -> dict:
    public_attributes = {k: v for k, v in (c.attributes or {}).items() if not k.startswith("_")}
    return {
        **claim_summary(c),
        "referring_provider_id": c.referring_provider_id, "diagnosis_codes": c.diagnosis_codes, "plan_type": c.plan_type,
        "policy_start_date": c.policy_start_date, "pre_auth_number": c.pre_auth_number, "member_age": c.member_age,
        "suspicion_score": c.suspicion_score, "evidence_strength": c.evidence_strength, "member_harm_score": c.member_harm_score,
        "model_version": c.model_version, "model_warning": SYNTHETIC_WARNING if c.model_version and not c.model_version.startswith("fallback") else None, "coverage_details": c.coverage_details, "attributes": public_attributes,
        "processing_time_ms": c.processing_time_ms, "processing_error": c.processing_error,
        "lines": [
            {"line_id": l.line_id, "cpt_code": l.cpt_code, "modifiers": l.modifiers, "units": l.units, "billed_amount": l.billed_amount, "paid_amount": l.paid_amount, "service_date": l.service_date, "diagnosis_pointer": l.diagnosis_pointer}
            for l in c.lines
        ],
    }


def signal_dict(s: DetectionSignal) -> dict:
    out = {"signal_id": s.signal_id, "detector": s.detector, "severity": s.severity, "evidence": s.evidence, "source_fields": s.source_fields}
    if s.detector == "rule":
        out.update(rule_name=s.rule_name, confidence=s.confidence)
    elif s.detector == "ml":
        out.update(model=(s.evidence or {}).get("model", s.model_name), detector_name=s.model_name, score=s.score, top_features=(s.evidence or {}).get("top_features", []))
    else:
        out.update(pattern=s.pattern_name, score=s.score)
    return out
