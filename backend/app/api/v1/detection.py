from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.detection.pipeline import DetectionPipeline
from app.services import claim_service

router = APIRouter(prefix="/detection", tags=["detection"])


@router.post("/run/{claim_id}", summary="Run the full detection pipeline and store the result")
async def run_full(claim_id: str, ctx: Ctx = Depends(require("detection:run"))):
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    result = await claim_service.run_pipeline(ctx.db, ctx.tenant, claim)
    await ctx.audit.log("detection.run", "claim", claim_id, principal=ctx.principal, details={"risk_score": claim.risk_score}, request=ctx.request)
    await ctx.db.commit()
    return result.to_dict()


async def _partial(claim_id: str, ctx: Ctx, stage: str) -> dict:
    """Runs one detector family without storing anything. Useful for seeing what each contributes."""
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    result = await DetectionPipeline(ctx.db, ctx.tenant).evaluate(claim, stages=frozenset({stage}))
    out = result.to_dict()
    out["stage"], out["stored"] = stage, False
    return out


@router.post("/rules/{claim_id}", summary="Run FWA rules only (not stored)")
async def run_rules(claim_id: str, ctx: Ctx = Depends(require("detection:run"))):
    return await _partial(claim_id, ctx, "rules")


@router.post("/ml/{claim_id}", summary="Run ML models only (not stored)")
async def run_ml(claim_id: str, ctx: Ctx = Depends(require("detection:run"))):
    return await _partial(claim_id, ctx, "ml")


@router.post("/graph/{claim_id}", summary="Run graph analytics only (not stored)")
async def run_graph(claim_id: str, ctx: Ctx = Depends(require("detection:run"))):
    return await _partial(claim_id, ctx, "graph")


@router.post("/temporal/{claim_id}", summary="Run temporal analytics only (not stored)")
async def run_temporal(claim_id: str, ctx: Ctx = Depends(require("detection:run"))):
    return await _partial(claim_id, ctx, "temporal")


@router.get("/signals/{claim_id}", summary="Stored detection signals for a claim")
async def get_signals(claim_id: str, ctx: Ctx = Depends(require("claims:read"))):
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    return {"claim_id": claim_id, "coverage_status": claim.coverage_status, "risk_score": claim.risk_score, "fwa_signals": [claim_service.signal_dict(s) for s in await claim_service.signals(ctx.db, ctx.tenant.id, claim)]}
