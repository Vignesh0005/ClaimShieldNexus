from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.exceptions import NotFound
from app.core.security import Principal
from app.explainability import brief_generator
from app.explainability import counterfactuals as cf
from app.explainability.copilot import InvestigationCopilot
from app.models import Brief, Case, Provider, Tenant
from app.services import case_service


async def build_content(db: AsyncSession, tenant: Tenant, case: Case) -> dict:
    signals = await case_service.signals_of(db, case)
    provider = (await db.execute(select(Provider.name).where(Provider.tenant_id == tenant.id, Provider.provider_id == case.provider_id))).scalar_one_or_none()
    case_dict = {**case_service.summary(case), "provider_name": provider}
    events = [{"date": e["date"], "title": e["title"]} for e in await case_service.timeline(db, tenant, case)]
    return brief_generator.build_content(
        case=case_dict, signals=signals, timeline=events,
        limitations=await case_service.case_limitations(db, tenant, case, signals),
        model_version=(case.summary or {}).get("model_version"),
    )


def template_type(brief_type: str) -> str:
    """Stored type names: technical_template, plain_template, technical_llm, plain_llm."""
    return brief_type if brief_type.endswith(("_template", "_llm")) else f"{brief_type}_template"


async def generate(db: AsyncSession, tenant: Tenant, case: Case, brief_type: str, principal: Principal | None = None, request=None) -> Brief:
    """The default brief: rendered from templates over stored evidence, so every line is traceable."""
    content = await build_content(db, tenant, case)
    kind = "plain" if brief_type.startswith("plain") else "technical"
    brief = Brief(tenant_id=tenant.id, case_id=case.id, brief_type=template_type(kind), content=content, content_markdown=brief_generator.render(content, kind), model_version=content["model_version"])
    db.add(brief)
    await AuditLogger(db).log("brief.generated", "case", case.case_id, principal=principal, tenant_id=tenant.id, details={"type": brief.brief_type}, request=request)
    await db.flush()
    return brief


async def latest(db: AsyncSession, tenant: Tenant, case: Case, brief_type: str = "technical") -> Brief:
    brief = (
        await db.execute(select(Brief).where(Brief.tenant_id == tenant.id, Brief.case_id == case.id, Brief.brief_type.in_({brief_type, template_type(brief_type)})).order_by(Brief.generated_at.desc()).limit(1))
    ).scalar_one_or_none()
    if brief is None:
        raise NotFound(f"No {brief_type} brief has been generated for case '{case.case_id}'. Generate one first.")
    return brief


def to_dict(brief: Brief, case_id: str) -> dict:
    return {"case_id": case_id, "brief_type": brief.brief_type, "content": brief.content, "markdown": brief.content_markdown, "model_version": brief.model_version, "generated_at": brief.generated_at}


async def enhance(db: AsyncSession, tenant: Tenant, case: Case, brief_type: str, principal: Principal, request=None) -> dict:
    """Template brief plus an optional LLM layer. The template is always generated and stored; the
    enhanced version is stored as <type>_llm only when it really came from the LLM."""
    from app.explainability.copilot import FALLBACK_MODEL, enhance_brief, render_enhancement

    kind = "plain" if brief_type.startswith("plain") else "technical"
    template = await generate(db, tenant, case, kind, principal, request)
    what_if = await case_service.counterfactual(db, tenant, case, persist=False)
    enhancement = await enhance_brief(template.content, cf.as_sentences(what_if))
    markdown = (template.content_markdown or "") + render_enhancement(enhancement)
    stored_as = None
    if enhancement["model"] != FALLBACK_MODEL:
        stored_as = f"{kind}_llm"
        db.add(Brief(tenant_id=tenant.id, case_id=case.id, brief_type=stored_as, content={**template.content, "enhancement": enhancement}, content_markdown=markdown, model_version=enhancement["model"]))
    await AuditLogger(db).log("brief.enhanced", "case", case.case_id, principal=principal, tenant_id=tenant.id, details={"type": kind, "model": enhancement["model"], "stored_as": stored_as}, request=request)
    await db.flush()
    return {**to_dict(template, case.case_id), "markdown": markdown, "enhancement": enhancement, "template_stored_as": template.brief_type, "enhanced_stored_as": stored_as}


async def copilot_inputs(db: AsyncSession, tenant: Tenant, case: Case) -> tuple[dict, list[str]]:
    content = await build_content(db, tenant, case)
    what_if = await case_service.counterfactual(db, tenant, case, persist=False)
    return content, cf.as_sentences(what_if)


async def investigate(db: AsyncSession, tenant: Tenant, case: Case, include_counterfactuals: bool, include_plain_language: bool, principal: Principal, request=None) -> dict:
    content, sentences = await copilot_inputs(db, tenant, case)
    out = await InvestigationCopilot().investigate(content, sentences, include_counterfactuals, include_plain_language)
    await AuditLogger(db).log("copilot.investigate", "case", case.case_id, principal=principal, details={"model": out["model"]}, request=request)
    return out


async def ask(db: AsyncSession, tenant: Tenant, case: Case, question: str, principal: Principal, request=None) -> dict:
    content, sentences = await copilot_inputs(db, tenant, case)
    out = await InvestigationCopilot().ask(content, sentences, question)
    await AuditLogger(db).log("copilot.ask", "case", case.case_id, principal=principal, details={"model": out["model"], "question": question[:200]}, request=request)
    return out
