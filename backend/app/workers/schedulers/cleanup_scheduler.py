from datetime import timedelta

from sqlalchemy import delete, select

from app.core.logging import logger
from app.db.base import utcnow
from app.db.session import session_scope
from app.models import Brief, Counterfactual, GraphSnapshot, Tenant
from app.workers.celery_app import celery_app, run_async

DERIVED_RETENTION_DAYS = 180


async def _cleanup() -> dict:
    """Removes derived artefacts that can be regenerated (old briefs, what-if results, graph
    snapshots). Claims, decisions and the audit log are never touched by this job."""
    cutoff = utcnow() - timedelta(days=DERIVED_RETENTION_DAYS)
    removed = {"briefs": 0, "counterfactuals": 0, "graph_snapshots": 0}
    async with session_scope() as db:
        tenant_ids = (await db.execute(select(Tenant.id))).scalars().all()
        for tenant_id in tenant_ids:
            days = int(((await db.get(Tenant, tenant_id)).config or {}).get("derived_retention_days", DERIVED_RETENTION_DAYS))
            limit = utcnow() - timedelta(days=days) if days != DERIVED_RETENTION_DAYS else cutoff
            removed["briefs"] += (await db.execute(delete(Brief).where(Brief.tenant_id == tenant_id, Brief.generated_at < limit))).rowcount or 0
            removed["counterfactuals"] += (await db.execute(delete(Counterfactual).where(Counterfactual.tenant_id == tenant_id, Counterfactual.generated_at < limit))).rowcount or 0
            removed["graph_snapshots"] += (await db.execute(delete(GraphSnapshot).where(GraphSnapshot.tenant_id == tenant_id, GraphSnapshot.created_at < limit))).rowcount or 0
    logger.info("cleanup_done", **removed)
    return removed


@celery_app.task(name="app.workers.schedulers.cleanup_scheduler.cleanup")
def cleanup():
    return run_async(_cleanup())
