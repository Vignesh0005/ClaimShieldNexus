from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.exceptions import NotFound
from app.deps import Ctx, require
from app.explainability import brief_generator
from app.schemas.common import Schema
from app.services import brief_service, case_service

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.post("/{case_id}/generate", summary="Generate the technical brief")
async def generate(case_id: str, ctx: Ctx = Depends(require("briefs:generate"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    brief = await brief_service.generate(ctx.db, ctx.tenant, case, "technical", ctx.principal, ctx.request)
    await ctx.db.commit()
    return brief_service.to_dict(brief, case_id)


@router.post("/{case_id}/plain", summary="Generate the plain-language brief")
async def generate_plain(case_id: str, ctx: Ctx = Depends(require("briefs:generate"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    brief = await brief_service.generate(ctx.db, ctx.tenant, case, "plain", ctx.principal, ctx.request)
    await ctx.db.commit()
    return brief_service.to_dict(brief, case_id)


class EnhanceIn(Schema):
    brief_type: Literal["technical", "plain"] = "technical"


@router.post("/{case_id}/enhance", summary="Template brief plus an optional LLM narrative layer (opt-in)")
async def enhance(case_id: str, body: EnhanceIn | None = None, ctx: Ctx = Depends(require("briefs:generate"))):
    """Returns the template brief with an added narrative, counterfactuals and plain-language
    version. Every added line cites the evidence entries it is based on. When the LLM is not
    configured or its output fails validation, the same sections are built from the template and
    `enhancement.model` is `template_fallback` with the reason."""
    ctx.principal.require("copilot:use")
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await brief_service.enhance(ctx.db, ctx.tenant, case, (body or EnhanceIn()).brief_type, ctx.principal, ctx.request)
    await ctx.db.commit()
    return out


@router.get("/{case_id}", summary="Latest stored brief")
async def get_brief(case_id: str, type: str = Query("technical", pattern="^(technical|plain)(_template|_llm)?$"), ctx: Ctx = Depends(require("briefs:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    return brief_service.to_dict(await brief_service.latest(ctx.db, ctx.tenant, case, type), case_id)


@router.get("/{case_id}/pdf", summary="Export the brief as PDF")
async def export_pdf(case_id: str, type: str = Query("technical", pattern="^(technical|plain)$"), ctx: Ctx = Depends(require("briefs:read"))):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    try:
        brief = await brief_service.latest(ctx.db, ctx.tenant, case, type)
        markdown = brief.content_markdown or ""
    except NotFound:
        # Nothing stored yet: render from current data without requiring generate permission.
        markdown = brief_generator.render(await brief_service.build_content(ctx.db, ctx.tenant, case), "plain" if type.startswith("plain") else "technical")
    await ctx.audit.log("brief.exported", "case", case_id, principal=ctx.principal, details={"type": type, "format": "pdf"}, request=ctx.request)
    await ctx.db.commit()
    pdf = brief_generator.to_pdf(markdown, f"SIU investigation brief {case_id}")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{case_id}-brief-{type}.pdf"'})
