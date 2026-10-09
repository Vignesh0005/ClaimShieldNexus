import asyncio
from collections.abc import Coroutine

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()
broker = settings.redis_url or "memory://"

celery_app = Celery("claimshield", broker=broker, backend=settings.redis_url or "cache+memory://")
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    task_acks_late=True,  # a task is acknowledged after it finishes, so a crashed worker's task is redelivered
    worker_prefetch_multiplier=1,
    task_always_eager=settings.redis_url is None,  # with no broker, tasks run in the calling process
    timezone="UTC",
    beat_schedule={
        "check-retrain-trigger": {"task": "app.workers.schedulers.retrain_scheduler.check_retrain_trigger", "schedule": crontab(minute=15)},
        "nightly-forecasts": {"task": "app.workers.schedulers.forecast_scheduler.nightly_forecasts", "schedule": crontab(hour=2, minute=0)},
        "nightly-graph-snapshots": {"task": "app.workers.tasks.graph_task.snapshot_all_tenants", "schedule": crontab(hour=2, minute=30)},
        "weekly-cleanup": {"task": "app.workers.schedulers.cleanup_scheduler.cleanup", "schedule": crontab(hour=3, minute=0, day_of_week=0)},
    },
)
celery_app.conf.imports = (
    "app.workers.tasks.ingest_task", "app.workers.tasks.detection_task", "app.workers.tasks.brief_task", "app.workers.tasks.retrain_task",
    "app.workers.tasks.graph_task", "app.workers.tasks.forecast_task", "app.workers.schedulers.retrain_scheduler",
    "app.workers.schedulers.forecast_scheduler", "app.workers.schedulers.cleanup_scheduler",
)


def run_async(coro: Coroutine):
    """Runs a coroutine to completion inside a worker task. Each task gets a fresh event loop and
    database engine, because asyncpg connections cannot be shared across loops."""

    async def wrapper():
        from app.db.session import dispose_engine

        try:
            return await coro
        finally:
            await dispose_engine()

    return asyncio.run(wrapper())
