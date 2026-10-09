import uuid

from app.core.logging import logger
from app.db.session import session_scope
from app.services import model_service
from app.workers.celery_app import celery_app, run_async


async def retrain_inline(tenant_id: uuid.UUID | None, actor: str = "system") -> dict | None:
    """Trains a candidate model. Used directly as a background task when no broker is configured."""
    try:
        async with session_scope() as db:
            return await model_service.retrain(db, tenant_id, actor)
    except Exception as exc:  # noqa: BLE001
        logger.error("retrain_failed", error=str(exc))
        return None


@celery_app.task(name="app.workers.tasks.retrain_task.train_candidate_model")
def train_candidate_model(tenant_id: str | None = None, actor: str = "system"):
    """The candidate is registered but never deployed here; deployment is a human decision."""
    return run_async(retrain_inline(uuid.UUID(tenant_id) if tenant_id else None, actor))
