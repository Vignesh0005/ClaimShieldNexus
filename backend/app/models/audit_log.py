import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.core.exceptions import ImmutableRecord
from app.db.base import Base, JSONType, UUIDMixin, utcnow


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_resource", "resource_type", "resource_id"),)

    # Nullable: platform-level actions (creating a tenant) have no tenant. Tenant-scoped reads
    # always filter on this column explicitly.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    actor_label: Mapped[str | None] = mapped_column(String(100), index=True)
    actor_type: Mapped[str] = mapped_column(String(50), default="system")  # user | system | api
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# Append-only at the ORM layer. The initial migration adds the same guarantee as a PostgreSQL
# trigger, which also covers writes that bypass the ORM.
@event.listens_for(AuditLog, "before_update")
def _no_update(*_):
    raise ImmutableRecord("Audit log entries cannot be changed.")


@event.listens_for(AuditLog, "before_delete")
def _no_delete(*_):
    raise ImmutableRecord("Audit log entries cannot be deleted.")
