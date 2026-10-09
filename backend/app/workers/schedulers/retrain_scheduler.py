from sqlalchemy import func, select

from app.config import get_settings
from app.db.session import session_scope
from app.models import ModelFeedback
from app.workers.celery_app import celery_app, run_async
from app.workers.tasks.retrain_task import train_candidate_model


async def _queue_size() -> int:
    async with session_scope() as db:
        return (await db.execute(select(func.count()).select_from(ModelFeedback).where(ModelFeedback.used_in_training.is_(False), ModelFeedback.final_label.isnot(None)))).scalar_one()


@celery_app.task(name="app.workers.schedulers.retrain_scheduler.check_retrain_trigger")
def check_retrain_trigger():
    """Hourly: trains a candidate once enough reviewer decisions have accumulated."""
    size, threshold = run_async(_queue_size()), get_settings().retrain_threshold
    if size >= threshold:
        train_candidate_model.delay(None, "scheduler")
    return {"queue_size": size, "threshold": threshold, "triggered": size >= threshold}
