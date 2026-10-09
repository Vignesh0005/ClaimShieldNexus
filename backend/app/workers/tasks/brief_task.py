import uuid

from app.db.session import session_scope
from app.models import Tenant
from app.services import brief_service, case_service
from app.workers.celery_app import celery_app, run_async


async def _generate(tenant_id: uuid.UUID, case_id: str) -> None:
    async with session_scope(tenant_id) as db:
        tenant = await db.get(Tenant, tenant_id)
        case = await case_service.get(db, tenant_id, case_id)
        for brief_type in ("technical", "plain"):
            await brief_service.generate(db, tenant, case, brief_type)


@celery_app.task(name="app.workers.tasks.brief_task.generate_briefs")
def generate_briefs(tenant_id: str, case_id: str):
    """Pre-generates both briefs for a case so they are ready when a reviewer opens it."""
    run_async(_generate(uuid.UUID(tenant_id), case_id))
    return {"status": "success", "case_id": case_id}
