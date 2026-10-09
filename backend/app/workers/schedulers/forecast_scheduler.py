from sqlalchemy import select

from app.db.session import session_scope
from app.models import Tenant
from app.workers.celery_app import celery_app, run_async
from app.workers.tasks.forecast_task import forecast_tenant


async def _tenant_ids() -> list[str]:
    async with session_scope() as db:
        return [str(t) for t in (await db.execute(select(Tenant.id).where(Tenant.active.is_(True)))).scalars().all()]


@celery_app.task(name="app.workers.schedulers.forecast_scheduler.nightly_forecasts")
def nightly_forecasts():
    ids = run_async(_tenant_ids())
    for tenant_id in ids:
        forecast_tenant.delay(tenant_id)
    return {"tenants": len(ids)}
