from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from app.config import get_settings
from app.core.exceptions import ClaimShieldException, ValidationFailed
from app.deps import Ctx, require
from app.ingestion.adapters.csv_adapter import CSVAdapter
from app.ingestion.adapters.fhir_adapter import FHIRAdapter
from app.ingestion.adapters.webhook_adapter import WebhookAdapter
from app.ingestion.validator import validate_claim
from app.schemas.claim import BatchIn, ClaimAccepted, CsvIngestIn
from app.services import claim_service

router = APIRouter(prefix="/claims", tags=["claims"])


def _accepted(claim, duplicate: bool) -> ClaimAccepted:
    return ClaimAccepted(claim_id=claim.claim_id, status=claim.processing_status, job_id=claim.job_id, estimated_completion_seconds=0 if duplicate else 5, duplicate=duplicate)


async def _ingest_many(ctx: Ctx, background: BackgroundTasks, records: list[dict], source: str, mapping: dict | None) -> dict:
    """Stores each valid record and reports each invalid one. One bad claim does not reject the
    batch; the caller gets a per-claim reason and can resend only those."""
    limit = get_settings().batch_max_claims
    if len(records) > limit:
        raise ValidationFailed(f"A batch can contain at most {limit} claims; this one has {len(records)}. Split it and resend.")
    accepted, rejected, stored = [], [], []
    for index, record in enumerate(records):
        try:
            claim_in = validate_claim(record, mapping)
            async with ctx.db.begin_nested():
                claim, duplicate = await claim_service.store(ctx.db, ctx.tenant, claim_in, source, ctx.principal)
            accepted.append(_accepted(claim, duplicate).model_dump())
            if not duplicate:
                stored.append(claim)
        except ClaimShieldException as exc:
            rejected.append({"index": index, "claim_id": record.get("claim_id") if isinstance(record, dict) else None, "code": exc.error_code, "message": exc.message, "details": exc.details})
    await ctx.db.commit()
    for claim in stored:
        claim_service.dispatch(background, claim)
    return {"accepted": len(accepted), "rejected": len(rejected), "claims": accepted, "errors": rejected}


@router.post("", status_code=202, response_model=ClaimAccepted, summary="Ingest a single claim")
@router.post("/ingest", status_code=202, response_model=ClaimAccepted, include_in_schema=False)
async def ingest_claim(record: dict, background: BackgroundTasks, ctx: Ctx = Depends(require("claims:write"))):
    claim, duplicate = await claim_service.store(ctx.db, ctx.tenant, validate_claim(record, ctx.tenant.field_mapping), "api", ctx.principal)
    await ctx.db.commit()
    if not duplicate:
        claim_service.dispatch(background, claim)
    return _accepted(claim, duplicate)


@router.post("/batch", status_code=202, summary="Ingest up to 1,000 claims")
async def ingest_batch(body: BatchIn, background: BackgroundTasks, ctx: Ctx = Depends(require("claims:write"))):
    return await _ingest_many(ctx, background, body.claims, "api-batch", ctx.tenant.field_mapping)


@router.post("/ingest/csv", status_code=202, summary="Ingest a CSV extract (one row per service line)")
async def ingest_csv(body: CsvIngestIn, background: BackgroundTasks, ctx: Ctx = Depends(require("claims:write"))):
    mapping = ctx.tenant.field_mapping if body.use_field_mapping else None
    # The adapter applies the mapping while grouping rows, so it is not applied a second time.
    return await _ingest_many(ctx, background, CSVAdapter(body.csv_text, mapping).parse(), "csv", None)


@router.post("/ingest/fhir", status_code=202, summary="Ingest a FHIR R4 Claim resource or Bundle")
async def ingest_fhir(payload: dict, background: BackgroundTasks, ctx: Ctx = Depends(require("claims:write"))):
    records = FHIRAdapter(payload).parse()
    if not records:
        raise ValidationFailed("No FHIR Claim resource was found in the request body.")
    return await _ingest_many(ctx, background, records, "fhir", None)


@router.post("/webhook", status_code=202, summary="Webhook receiver (optionally HMAC-signed)")
async def ingest_webhook(request: Request, background: BackgroundTasks, ctx: Ctx = Depends(require("claims:write"))):
    secret = (ctx.tenant.config or {}).get("webhook_secret")
    adapter = WebhookAdapter(await request.body(), request.headers.get("x-claimshield-signature"), secret)
    records = [r async for r in adapter.records()]
    return await _ingest_many(ctx, background, records, "webhook", ctx.tenant.field_mapping)


@router.get("", summary="List claims")
async def list_claims(
    ctx: Ctx = Depends(require("claims:read")),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    provider_id: str | None = None,
    member_id: str | None = None,
    min_risk: float | None = Query(None, ge=0, le=1),
    status: str | None = None,
):
    rows, total = await claim_service.list_claims(ctx.db, ctx.tenant.id, limit=limit, offset=offset, provider_id=provider_id, member_id=member_id, min_risk=min_risk, status=status)
    return {"items": [claim_service.claim_summary(c) for c in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/{claim_id}", summary="Claim detail with line items")
async def get_claim(claim_id: str, ctx: Ctx = Depends(require("claims:read"))):
    return claim_service.claim_detail(await claim_service.get(ctx.db, ctx.tenant.id, claim_id))


@router.get("/{claim_id}/flags", summary="Detection signals for a claim")
async def claim_flags(claim_id: str, ctx: Ctx = Depends(require("claims:read"))):
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    return {"claim_id": claim_id, "flags": [claim_service.signal_dict(s) for s in await claim_service.signals(ctx.db, ctx.tenant.id, claim)]}


@router.get("/{claim_id}/status", summary="Processing status")
async def claim_status(claim_id: str, ctx: Ctx = Depends(require("claims:read"))):
    c = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    return {"claim_id": c.claim_id, "status": c.processing_status, "job_id": c.job_id, "error": c.processing_error, "coverage_status": c.coverage_status, "risk_score": c.risk_score, "processed_at": c.processed_at, "processing_time_ms": c.processing_time_ms}


@router.post("/{claim_id}/reprocess", status_code=202, summary="Re-run detection")
async def reprocess(claim_id: str, background: BackgroundTasks, ctx: Ctx = Depends(require("detection:run"))):
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    claim.processing_status = "processing"
    await ctx.audit.log("claim.reprocess_requested", "claim", claim_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    claim_service.dispatch(background, claim)
    return _accepted(claim, False)
