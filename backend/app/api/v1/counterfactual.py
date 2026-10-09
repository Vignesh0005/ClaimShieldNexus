from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.schemas.case import CounterfactualIn
from app.services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/{case_id}/counterfactual", summary="Generate what-if scenarios by re-scoring")
async def generate(case_id: str, body: CounterfactualIn | None = None, ctx: Ctx = Depends(require("cases:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.counterfactual(ctx.db, ctx.tenant, case, only=body.remove_signals if body else None)
    await ctx.db.commit()
    return out


@router.get("/{case_id}/counterfactual", summary="What-if scenarios (not stored)")
async def view(case_id: str, ctx: Ctx = Depends(require("cases:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    return await case_service.counterfactual(ctx.db, ctx.tenant, case, persist=False)
