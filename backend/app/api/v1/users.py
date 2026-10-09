from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.security import PERMISSIONS, Role, create_access_token
from app.db.session import get_session
from app.deps import Ctx, context, require
from app.models import User
from app.schemas.tenant import DevTokenIn, UserCreate, UserOut, UserUpdate
from app.services import tenant_service

router = APIRouter(tags=["users"])


@router.get("/users/me", summary="The current caller, role and permissions")
async def me(ctx: Ctx = Depends(context)):
    granted = PERMISSIONS.get(ctx.principal.role, set())
    return {
        "subject": ctx.principal.subject, "role": ctx.principal.role.value, "tenant": {"id": str(ctx.tenant.id), "slug": ctx.tenant.slug, "name": ctx.tenant.name, "is_demo": ctx.tenant.is_demo},
        "permissions": sorted(granted), "platform_admin": ctx.principal.platform_admin,
    }


@router.get("/users", summary="Users in the tenant")
async def list_users(ctx: Ctx = Depends(require("users:manage"))):
    rows = (await ctx.db.execute(select(User).where(User.tenant_id == ctx.tenant.id).order_by(User.external_id))).scalars().all()
    return {"users": [UserOut.model_validate(u).model_dump() for u in rows]}


@router.post("/users", status_code=201, summary="Add a user")
async def create_user(body: UserCreate, ctx: Ctx = Depends(require("users:manage"))):
    if await tenant_service.get_user(ctx.db, ctx.tenant.id, body.external_id):
        raise Conflict(f"User '{body.external_id}' already exists in this tenant.")
    user = User(tenant_id=ctx.tenant.id, **body.model_dump())
    ctx.db.add(user)
    await ctx.audit.log("user.created", "user", body.external_id, principal=ctx.principal, details={"role": body.role}, request=ctx.request)
    await ctx.db.commit()
    return UserOut.model_validate(user).model_dump()


@router.post("/users/{external_id}", summary="Change a user's role or deactivate them")
async def update_user(external_id: str, body: UserUpdate, ctx: Ctx = Depends(require("users:manage"))):
    user = await tenant_service.get_user(ctx.db, ctx.tenant.id, external_id)
    if user is None:
        raise NotFound(f"User '{external_id}' not found.")
    if external_id == ctx.principal.subject and (body.active is False or (body.role and body.role != "admin")):
        raise ValidationFailed("You cannot remove your own admin access. Ask another admin to do it.")
    before = {"role": user.role, "active": user.active}
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
    await ctx.audit.log("user.updated", "user", external_id, principal=ctx.principal, details={"before": before, "after": {"role": user.role, "active": user.active}}, request=ctx.request)
    await ctx.db.commit()
    return UserOut.model_validate(user).model_dump()


@router.post("/auth/dev-token", summary="Mint a token for local development (disabled in production)")
async def dev_token(body: DevTokenIn, db: AsyncSession = Depends(get_session)):
    """Lets a developer or the demo frontend sign in without an identity provider. It issues
    tokens to anyone who asks, so it does not exist when ENV=production."""
    if get_settings().is_production:
        raise NotFound("Not found.")
    tenant = await tenant_service.get_by_slug(db, body.tenant)
    user = await tenant_service.ensure_user(db, tenant.id, body.user, Role(body.role))
    user.role = body.role
    await db.commit()
    token = create_access_token(subject=body.user, tenant_id=tenant.id, role=body.role, platform_admin=body.platform_admin)
    return {"access_token": token, "token_type": "bearer", "tenant": tenant.slug, "role": body.role, "expires_in_minutes": 480}
