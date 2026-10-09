import uuid

from app.db.session import session_scope
from app.workers.celery_app import celery_app, run_async


async def _forecast(tenant_id: uuid.UUID) -> int:
    from app.api.v1.admin import compute_forecasts

    async with session_scope(tenant_id) as db:
        return await compute_forecasts(db, tenant_id)


@celery_app.task(name="app.workers.tasks.forecast_task.forecast_tenant")
def forecast_tenant(tenant_id: str):
    return {"forecasts_written": run_async(_forecast(uuid.UUID(tenant_id)))}
