import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.security import Principal
from app.core.tenancy import set_current_tenant
from app.db.session import bind_tenant
from app.models import Tenant


def apply_tenant_scope(request: Request, db: AsyncSession, principal: Principal, tenant: Tenant) -> None:
    """Scopes the request to one tenant: the database session (automatic tenant filter on every
    ORM read), the context variable used by the audit logger, and the log context."""
    bind_tenant(db, tenant.id)
    set_current_tenant(tenant.id)
    request.state.principal = principal
    request.state.tenant = tenant
    structlog.contextvars.bind_contextvars(tenant=tenant.slug, actor=principal.subject)
