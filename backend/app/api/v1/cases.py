from fastapi import APIRouter, Depends, Query

from app.deps import Ctx, require
from app.schemas.case import DecisionIn
from app.services import audit_service, case_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", summary="List cases")
async def list_cases(
    ctx: Ctx = Depends(require("cases:read")),
    status: str | None = Query(None, description="A status, or 'open' for all statuses awaiting a decision"),
    severity: str | None = None,
    provider_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    items, total = await case_service.list_cases(ctx.db, ctx.tenant.id, status=status, severity=severity, provider_id=provider_id, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{case_id}", summary="Case detail")
async def get_case(case_id: str, ctx: Ctx = Depends(require("cases:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.detail(ctx.db, ctx.tenant, case)
    # Reads of a case are part of its audit trail.
    await ctx.audit.log("case.viewed", "case", case_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out


@router.post("/{case_id}/decision", summary="Record a reviewer's decision")
async def decide(case_id: str, body: DecisionIn, ctx: Ctx = Depends(require("cases:decide"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.decide(ctx.db, ctx.tenant, case, body, ctx.principal, ctx.request)
    await ctx.db.commit()
    return out


@router.post("/{case_id}/status", summary="Move a case between working states (not outcomes)")
async def set_status(case_id: str, status: str = Query(..., description="pending_review, in_review or needs_info"), ctx: Ctx = Depends(require("cases:assign"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    await case_service.set_status(ctx.db, case, status, ctx.principal, ctx.request)
    await ctx.db.commit()
    return {"case_id": case_id, "status": case.status}


@router.get("/{case_id}/audit", summary="Audit trail for a case")
async def case_audit(case_id: str, ctx: Ctx = Depends(require("audit:read")), limit: int = Query(200, ge=1, le=1000)):
    await case_service.get(ctx.db, ctx.tenant.id, case_id)
    rows, total = await audit_service.query(ctx.db, ctx.tenant.id, resource_type="case", resource_id=case_id, limit=limit)
    return {"case_id": case_id, "events": [audit_service.to_dict(e) for e in rows], "total": total}
