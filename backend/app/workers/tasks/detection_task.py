import uuid

from app.services import claim_service
from app.workers.celery_app import celery_app, run_async


@celery_app.task(bind=True, max_retries=3, name="app.workers.tasks.detection_task.run_detection")
def run_detection(self, claim_uuid: str, tenant_id: str):
    """Runs the detection pipeline for one stored claim. Safe to retry: the pipeline replaces a
    claim's signals and recomputes its case rather than adding to them."""
    try:
        run_async(claim_service.process_claim(uuid.UUID(tenant_id), uuid.UUID(claim_uuid)))
        return {"status": "success", "claim": claim_uuid}
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
