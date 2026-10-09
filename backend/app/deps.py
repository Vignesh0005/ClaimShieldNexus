from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware.auth import authenticate
from app.api.middleware.rate_limit import enforce_rate_limit
from app.api.middleware.tenant import apply_tenant_scope
from app.core.audit import AuditLogger
from app.core.exceptions import Forbidden
from app.core.security import Principal
from app.db.session import get_session
from app.models import Tenant


@dataclass
class Ctx:
    """Everything a route needs about the caller, already authenticated and tenant-scoped."""

    request: Request
    db: AsyncSession
    principal: Principal
    tenant: Tenant

    @property
    def audit(self) -> AuditLogger:
        return AuditLogger(self.db)


async def context(request: Request, db: AsyncSession = Depends(get_session)) -> Ctx:
    principal, tenant = await authenticate(request, db)
    apply_tenant_scope(request, db, principal, tenant)
    await enforce_rate_limit(principal)
    return Ctx(request, db, principal, tenant)


def require(permission: str) -> Callable:
    async def dependency(ctx: Ctx = Depends(context)) -> Ctx:
        ctx.principal.require(permission)
        return ctx

    return dependency


async def platform_admin(ctx: Ctx = Depends(context)) -> Ctx:
    if not ctx.principal.platform_admin:
        raise Forbidden("This action is limited to platform administrators.")
    return ctx
