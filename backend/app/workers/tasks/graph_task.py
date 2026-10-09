from sqlalchemy import select

from app.db.session import session_scope
from app.models import Tenant
from app.services import network_service
from app.workers.celery_app import celery_app, run_async


async def _snapshot_all() -> int:
    async with session_scope() as db:
        tenant_ids = (await db.execute(select(Tenant.id).where(Tenant.active.is_(True)))).scalars().all()
    for tenant_id in tenant_ids:
        async with session_scope(tenant_id) as db:
            await network_service.time_travel(db, tenant_id, None, store=True)
    return len(tenant_ids)


@celery_app.task(name="app.workers.tasks.graph_task.snapshot_all_tenants")
def snapshot_all_tenants():
    """Stores today's network for each tenant so past states can be replayed exactly."""
    return {"tenants": run_async(_snapshot_all())}
