from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("/{case_id}/evidence", summary="Evidence trail with source citations and limitations")
async def evidence(case_id: str, ctx: Ctx = Depends(require("cases:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.evidence(ctx.db, ctx.tenant, case)
    await ctx.audit.log("case.evidence_viewed", "case", case_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out


@router.get("/{case_id}/timeline", summary="Timeline of events for a case")
async def timeline(case_id: str, ctx: Ctx = Depends(require("cases:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    return {"case_id": case_id, "events": await case_service.timeline(ctx.db, ctx.tenant, case)}
