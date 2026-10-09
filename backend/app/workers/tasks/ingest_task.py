import uuid

from app.core.exceptions import ClaimShieldException
from app.core.logging import logger
from app.db.session import session_scope
from app.models import Tenant
from app.services import claim_service
from app.workers.celery_app import celery_app, run_async


async def _ingest(tenant_id: uuid.UUID, records: list[dict], source: str) -> dict:
    accepted = rejected = 0
    async with session_scope(tenant_id) as db:
        tenant = await db.get(Tenant, tenant_id)
        for record in records:
            try:
                async with db.begin_nested():
                    await claim_service.ingest_record(db, tenant, record, source=source, process=True)
                accepted += 1
            except ClaimShieldException as exc:
                rejected += 1
                logger.warning("ingest_rejected", claim_id=record.get("claim_id"), code=exc.error_code)
    return {"accepted": accepted, "rejected": rejected}


@celery_app.task(bind=True, max_retries=3, name="app.workers.tasks.ingest_task.ingest_records")
def ingest_records(self, tenant_id: str, records: list[dict], source: str = "worker"):
    """Validates, stores and scores a list of claim records (large files, REST pulls)."""
    try:
        return run_async(_ingest(uuid.UUID(tenant_id), records, source))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=60)
