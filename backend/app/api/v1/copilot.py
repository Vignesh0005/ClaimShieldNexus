from fastapi import APIRouter, Depends

from app.deps import Ctx, require
from app.schemas.feedback import CopilotAskIn, CopilotInvestigateIn
from app.services import brief_service, case_service

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/investigate", summary="Explain a case's evidence (LLM, with a deterministic fallback)")
async def investigate(body: CopilotInvestigateIn, ctx: Ctx = Depends(require("copilot:use"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, body.case_id)
    out = await brief_service.investigate(ctx.db, ctx.tenant, case, body.include_counterfactuals, body.include_plain_language, ctx.principal, ctx.request)
    await ctx.db.commit()
    return out


@router.post("/ask", summary="Ask a question about a case's evidence")
async def ask(body: CopilotAskIn, ctx: Ctx = Depends(require("copilot:use"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, body.case_id)
    out = await brief_service.ask(ctx.db, ctx.tenant, case, body.question, ctx.principal, ctx.request)
    await ctx.db.commit()
    return out
