from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.services import queue_service

router = APIRouter(tags=["queue"])


@router.get("/dashboard", summary="Overview: funnel, period-over-period counts, top providers, recent activity")
async def dashboard(ctx: Ctx = Depends(require("queue:read"))):
    return await queue_service.dashboard(ctx.db, ctx.tenant)


@router.get("/funnel", summary="Alert-to-case funnel (same data as /queue/funnel)")
async def funnel(ctx: Ctx = Depends(require("queue:read"))):
    return await queue_service.funnel(ctx.db, ctx.tenant)
