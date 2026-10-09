import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.events import event_bus
from app.core.security import Principal
from app.core.tenancy import get_current_tenant
from app.models.audit_log import AuditLog


class AuditLogger:
    """Append-only audit trail. Entries are added to the caller's transaction so an action and its
    audit record commit or roll back together."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        *,
        principal: Principal | None = None,
        actor_label: str | None = None,
        actor_type: str = "system",
        tenant_id: uuid.UUID | None = None,
        details: dict | None = None,
        request: Request | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=tenant_id or (principal.tenant_id if principal else None) or get_current_tenant(),
            actor_id=principal.user_id if principal else None,
            actor_label=actor_label or (principal.subject if principal else "system"),
            actor_type=principal.actor_type if principal else actor_type,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
        self.db.add(entry)
        await self.db.flush()
        await event_bus.publish(
            "audit.logged",
            {"tenant_id": str(entry.tenant_id) if entry.tenant_id else None, "action": action, "resource_type": resource_type, "resource_id": resource_id},
        )
        return entry
