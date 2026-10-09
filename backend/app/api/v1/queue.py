from fastapi import APIRouter, Depends, Query

from app.deps import Ctx, require
from app.schemas.case import AssignIn, OptimizeIn
from app.services import case_service, queue_service

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("", summary="Ranked SIU queue with capacity markers")
async def get_queue(
    ctx: Ctx = Depends(require("queue:read")),
    num_investigators: int | None = Query(None, ge=1, le=500),
    hours_per_investigator: float | None = Query(None, gt=0, le=80),
):
    params = None
    if num_investigators or hours_per_investigator:
        default = queue_service.default_capacity(ctx.tenant)
        params = OptimizeIn(num_investigators=num_investigators or default.num_investigators, hours_per_investigator=hours_per_investigator or default.hours_per_investigator)
    return await queue_service.ranked(ctx.db, ctx.tenant, params)


@router.post("/optimize", summary="Capacity-aware case selection")
async def optimize(body: OptimizeIn, ctx: Ctx = Depends(require("queue:optimize"))):
    return await queue_service.optimize(ctx.db, ctx.tenant, body)


@router.get("/stats", summary="Queue statistics")
async def stats(ctx: Ctx = Depends(require("queue:read"))):
    return await queue_service.stats(ctx.db, ctx.tenant)


@router.post("/assign", summary="Assign a case to an investigator")
async def assign(body: AssignIn, ctx: Ctx = Depends(require("cases:assign"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, body.case_id)
    await case_service.assign(ctx.db, ctx.tenant, case, body.assignee, ctx.principal, ctx.request)
    await ctx.db.commit()
    return {"case_id": case.case_id, "assigned_to": body.assignee, "status": case.status}


@router.get("/funnel", summary="Alert-to-case funnel")
async def funnel(ctx: Ctx = Depends(require("queue:read"))):
    return await queue_service.funnel(ctx.db, ctx.tenant)
