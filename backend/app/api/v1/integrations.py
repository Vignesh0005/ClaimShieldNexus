"""Additive machine integration routes; existing user routes and permissions stay intact."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, SecretStr

from app.api.v1.tenants import _own_tenant
from app.core.exceptions import Forbidden, ValidationFailed
from app.core.security import Role
from app.deps import Ctx, context
from app.integrations.webhooks import REGISTRY_KEY, SUPPORTED_EVENTS, registrations, result_payload, validate_destination
from app.services import case_service, claim_service

router = APIRouter(tags=["integrations"])


class WebhookIn(BaseModel):
    id: str = Field(default="mock-insurer", min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    url: str = Field(max_length=2048)
    events: list[str] = Field(default_factory=lambda: sorted(SUPPORTED_EVENTS), min_length=1, max_length=5)
    secret: SecretStr = Field(min_length=16, max_length=512)
    enabled: bool = True


def public_registration(entry: dict) -> dict:
    return {key: entry.get(key) for key in ("id", "url", "events", "enabled")}


@router.post("/tenants/{tenant_id}/webhooks", status_code=201, summary="Register or replace an outbound webhook (tenant admin)")
async def register_webhook(tenant_id: str, body: WebhookIn, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id, write=True)
    try:
        validate_destination(body.url)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    unsupported = set(body.events) - SUPPORTED_EVENTS
    if unsupported:
        raise ValidationFailed("Unsupported webhook event.", supported=sorted(SUPPORTED_EVENTS))
    entry = {"id": body.id, "url": body.url, "events": sorted(set(body.events)), "secret": body.secret.get_secret_value(), "enabled": body.enabled}
    registry = {**((tenant.config or {}).get(REGISTRY_KEY) or {}), body.id: entry}
    tenant.config = {**(tenant.config or {}), REGISTRY_KEY: registry}
    await ctx.audit.log("tenant.webhook_registered", "tenant", tenant.slug, principal=ctx.principal, tenant_id=tenant.id, details={"webhook_id": body.id, "events": entry["events"], "enabled": body.enabled}, request=ctx.request)
    await ctx.db.commit()
    return {"webhook": public_registration(entry)}


@router.get("/tenants/{tenant_id}/webhooks", summary="List outbound webhooks without secrets (tenant admin)")
async def list_webhooks(tenant_id: str, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id, write=True)
    return {"webhooks": [public_registration(entry) for entry in registrations(tenant)]}


async def integration_reader(ctx: Ctx = Depends(context)) -> Ctx:
    requested = ctx.request.headers.get("x-tenant-id")
    if requested and requested not in {ctx.tenant.slug, str(ctx.tenant.id)}:
        raise Forbidden("The API key does not belong to the requested tenant.")
    if ctx.principal.role == Role.API:
        if not (ctx.tenant.config or {}).get("integration_read_access", False):
            raise Forbidden("This tenant has not enabled machine integration reads.")
    else:
        ctx.principal.require("cases:read")
    return ctx


@router.get("/integrations/claims/{claim_id}/result", summary="Latest integration result (opt-in tenant API key)")
async def get_result(claim_id: str, ctx: Ctx = Depends(integration_reader)):
    claim = await claim_service.get(ctx.db, ctx.tenant.id, claim_id)
    topic = "claim.failed" if claim.processing_status == "failed" else "case.updated" if claim.case_ref else "claim.processed"
    out = await result_payload(ctx.db, ctx.tenant, claim, topic)
    if claim.case_ref:
        from sqlalchemy import select
        from app.models import CaseDecision

        decision = (await ctx.db.execute(select(CaseDecision).where(CaseDecision.tenant_id == ctx.tenant.id, CaseDecision.case_id == claim.case_ref).order_by(CaseDecision.decided_at.desc()).limit(1))).scalar_one_or_none()
        if decision:
            out = await result_payload(ctx.db, ctx.tenant, claim, "case.decided", decision=decision)
    await ctx.audit.log("integration.result_viewed", "claim", claim_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out


@router.get("/integrations/cases/{case_id}", summary="Case result for an opt-in machine integration")
async def get_case(case_id: str, ctx: Ctx = Depends(integration_reader)):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.detail(ctx.db, ctx.tenant, case)
    await ctx.audit.log("integration.case_viewed", "case", case_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out


@router.get("/integrations/cases/{case_id}/evidence", summary="Evidence, graph and timeline for an opt-in machine integration")
async def get_evidence(case_id: str, ctx: Ctx = Depends(integration_reader)):
    case = await case_service.get(ctx.db, ctx.tenant.id, case_id)
    out = await case_service.evidence(ctx.db, ctx.tenant, case)
    out["network"] = await case_service.network(ctx.db, ctx.tenant, case)
    out["timeline"] = await case_service.timeline(ctx.db, ctx.tenant, case)
    await ctx.audit.log("integration.evidence_viewed", "case", case_id, principal=ctx.principal, request=ctx.request)
    await ctx.db.commit()
    return out
