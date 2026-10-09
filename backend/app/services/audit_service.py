import csv
import io
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AuditLog


def to_dict(e: AuditLog) -> dict:
    return {
        "id": str(e.id), "timestamp": e.timestamp, "actor": e.actor_label, "actor_type": e.actor_type, "action": e.action,
        "resource_type": e.resource_type, "resource_id": e.resource_id, "details": e.details, "ip_address": e.ip_address,
    }


async def query(
    db: AsyncSession, tenant_id: uuid.UUID, *, resource_type: str | None = None, resource_id: str | None = None, actor: str | None = None,
    action: str | None = None, since: datetime | None = None, until: datetime | None = None, limit: int = 200, offset: int = 0,
) -> tuple[list[AuditLog], int]:
    # AuditLog has a nullable tenant_id, so it is not covered by the automatic tenant filter.
    where = [AuditLog.tenant_id == tenant_id]
    if resource_type:
        where.append(AuditLog.resource_type == resource_type)
    if resource_id:
        where.append(AuditLog.resource_id == resource_id)
    if actor:
        where.append(AuditLog.actor_label == actor)
    if action:
        where.append(AuditLog.action.like(f"{action}%"))
    if since:
        where.append(AuditLog.timestamp >= since)
    if until:
        where.append(AuditLog.timestamp <= until)
    total = (await db.execute(select(func.count()).select_from(AuditLog).where(*where))).scalar_one()
    rows = (await db.execute(select(AuditLog).where(*where).order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset))).scalars().all()
    return list(rows), total


def to_csv(entries: list[AuditLog]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp_utc", "actor", "actor_type", "action", "resource_type", "resource_id", "details", "ip_address"])
    for e in entries:
        writer.writerow([e.timestamp.isoformat() if e.timestamp else "", e.actor_label, e.actor_type, e.action, e.resource_type, e.resource_id, e.details, e.ip_address])
    return buf.getvalue()


def retention_policy() -> dict:
    days = get_settings().audit_retention_days
    return {
        "audit_log_retention_days": days,
        "audit_log": "Append-only. Entries cannot be edited or deleted through the application; PostgreSQL enforces this with a trigger.",
        "claims": "Retained for the tenant's contract period; removed by the cleanup job after the tenant's configured retention window.",
        "briefs_and_counterfactuals": "Regenerated on demand; stored copies follow the claims retention window.",
        "model_feedback": "Retained while any model trained on it is deployed.",
    }
