from datetime import date

from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.services import case_service, network_service

router = APIRouter(tags=["network"])


@router.get("/network", summary="Global network graph")
async def global_graph(as_of: date | None = None, ctx: Ctx = Depends(require("network:read"))):
    return await network_service.global_graph(ctx.db, ctx.tenant.id, as_of)


@router.get("/network/clusters", summary="Community clusters, central providers and shared addresses")
async def clusters(ctx: Ctx = Depends(require("network:read"))):
    return await network_service.clusters(ctx.db, ctx.tenant.id)


@router.get("/network/time-travel", summary="Network as of a date, with month-by-month loop counts")
async def time_travel(as_of: date | None = None, provider_id: str | None = None, ctx: Ctx = Depends(require("network:read"))):
    return await network_service.time_travel(ctx.db, ctx.tenant.id, as_of, provider_id)


@router.get("/network/referral-loops", summary="All referral loops")
async def referral_loops(ctx: Ctx = Depends(require("network:read"))):
    return await network_service.referral_loops(ctx.db, ctx.tenant.id)


@router.get("/network/geo-conflicts", summary="Members billed at two distant facilities on the same day")
async def geo_conflicts(ctx: Ctx = Depends(require("network:read"))):
    events = await network_service.geo_conflicts(ctx.db, ctx.tenant.id)
    return {"events": events, "total": len(events), "note": "Claims carry service dates, not times. Telehealth, billing-address errors and shared identifiers can produce the same pattern."}


@router.get("/network/provider/{provider_id}", summary="A provider and its direct connections")
async def provider_network(provider_id: str, as_of: date | None = None, ctx: Ctx = Depends(require("network:read"))):
    return await network_service.node_network(ctx.db, ctx.tenant.id, provider_id, as_of)


@router.get("/network/member/{member_id}", summary="A member and its direct connections")
async def member_network(member_id: str, as_of: date | None = None, ctx: Ctx = Depends(require("network:read"))):
    return await network_service.node_network(ctx.db, ctx.tenant.id, member_id, as_of)


@router.get("/cases/{case_id}/network", tags=["cases"], summary="Network graph for a case")
async def case_network(case_id: str, as_of: date | None = None, ctx: Ctx = Depends(require("network:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.network(ctx.db, ctx.tenant, case, as_of)
    await ctx.audit.log("case.network_viewed", "case", case_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out
