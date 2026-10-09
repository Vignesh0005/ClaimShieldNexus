import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.exceptions import Forbidden, TenantNotFound, ValidationFailed
from app.db.session import bind_tenant
from app.deps import Ctx, context, platform_admin
from app.ingestion.field_mapping import validate_mapping
from app.models import Tenant
from app.schemas.tenant import ConfigIn, FieldMappingIn, TenantCreate, TenantOut
from app.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


async def _own_tenant(ctx: Ctx, tenant_id: str, write: bool = False) -> Tenant:
    """Resolves the path tenant. Tenant admins may only reach their own; platform administrators
    may reach any. Other roles can read their own tenant's non-secret settings only."""
    if tenant_id in ("me", ctx.tenant.slug, str(ctx.tenant.id)):
        tenant = ctx.tenant
    elif ctx.principal.platform_admin:
        bind_tenant(ctx.db, None)
        try:
            tenant = await ctx.db.get(Tenant, uuid.UUID(tenant_id))
        except ValueError:
            tenant = (await ctx.db.execute(select(Tenant).where(Tenant.slug == tenant_id))).scalar_one_or_none()
        if tenant is None:
            raise TenantNotFound("Tenant not found.")
    else:
        # Same response whether or not the tenant exists, so tenant identifiers cannot be probed.
        raise Forbidden("You do not have access to that tenant.")
    if write and not (ctx.principal.platform_admin or ctx.principal.can("*")):
        raise Forbidden("Only an admin can change tenant settings.")
    return tenant


@router.post("", status_code=201, summary="Create a tenant (platform admin)")
async def create_tenant(body: TenantCreate, ctx: Ctx = Depends(platform_admin)):
    bind_tenant(ctx.db, None)
    tenant, api_key = await tenant_service.create(ctx.db, body.name, body.slug, body.is_demo, body.config)
    await ctx.audit.log("tenant.created", "tenant", tenant.slug, principal=ctx.principal, tenant_id=tenant.id, request=ctx.request)
    await ctx.db.commit()
    return {**TenantOut.model_validate(tenant).model_dump(), "api_key": api_key, "api_key_note": "Store this key now. It is not shown again."}


@router.get("", summary="List tenants (platform admin sees all; others see their own)")
async def list_tenants(ctx: Ctx = Depends(context)):
    if not ctx.principal.platform_admin:
        return {"tenants": [TenantOut.model_validate(ctx.tenant).model_dump()]}
    bind_tenant(ctx.db, None)
    rows = (await ctx.db.execute(select(Tenant).order_by(Tenant.created_at))).scalars().all()
    return {"tenants": [TenantOut.model_validate(t).model_dump() for t in rows]}


@router.get("/{tenant_id}", summary="Tenant detail")
async def get_tenant(tenant_id: str, ctx: Ctx = Depends(context)):
    return TenantOut.model_validate(await _own_tenant(ctx, tenant_id)).model_dump()


@router.post("/{tenant_id}/api-keys", status_code=201, summary="Generate a new API key (replaces the current one)")
async def rotate_key(tenant_id: str, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id, write=True)
    api_key = await tenant_service.rotate_api_key(ctx.db, tenant)
    await ctx.audit.log("tenant.api_key_rotated", "tenant", tenant.slug, principal=ctx.principal, tenant_id=tenant.id, details={"last4": api_key[-4:]}, request=ctx.request)
    await ctx.db.commit()
    return {"api_key": api_key, "last4": api_key[-4:], "api_key_note": "Store this key now. It is not shown again. The previous key no longer works."}


@router.post("/{tenant_id}/field-mapping", summary="Save field mapping")
async def save_mapping(tenant_id: str, body: FieldMappingIn, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id, write=True)
    missing = validate_mapping(body.mapping)
    if missing:
        raise ValidationFailed(f"The mapping does not cover required fields: {', '.join(missing)}.", missing=missing)
    tenant.field_mapping = body.mapping
    await ctx.audit.log("tenant.field_mapping_updated", "tenant", tenant.slug, principal=ctx.principal, tenant_id=tenant.id, details={"fields": len(body.mapping)}, request=ctx.request)
    await ctx.db.commit()
    return {"field_mapping": tenant.field_mapping}


@router.get("/{tenant_id}/config", summary="Tenant configuration")
async def get_config(tenant_id: str, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id)
    config = {k: v for k, v in (tenant.config or {}).items() if "secret" not in k}
    return {"config": config, "field_mapping": tenant.field_mapping, "api_key_last4": tenant.api_key_last4}


@router.post("/{tenant_id}/config", summary="Update tenant configuration")
async def update_config(tenant_id: str, body: ConfigIn, ctx: Ctx = Depends(context)):
    tenant = await _own_tenant(ctx, tenant_id, write=True)
    thresholds = {**(tenant.config or {}).get("thresholds", {}), **body.config.get("thresholds", {})}
    if thresholds and not (0 < thresholds.get("medium", 0.4) < thresholds.get("high", 0.6) < thresholds.get("critical", 0.8) <= 1):
        raise ValidationFailed("Thresholds must satisfy 0 < medium < high < critical <= 1.", thresholds=thresholds)
    before = dict(tenant.config or {})
    tenant.config = {**before, **body.config, "thresholds": thresholds}
    changed = sorted(k for k in tenant.config if tenant.config.get(k) != before.get(k))
    await ctx.audit.log("tenant.config_updated", "tenant", tenant.slug, principal=ctx.principal, tenant_id=tenant.id, details={"changed": changed}, request=ctx.request)
    await ctx.db.commit()
    return {"config": {k: v for k, v in tenant.config.items() if "secret" not in k}}
