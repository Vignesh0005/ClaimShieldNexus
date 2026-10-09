from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.core.cache import cache
from app.core.logging import configure_logging, logger
from app.db.session import create_all, dispose_engine
from app.detection.ml.registry import registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging()
    settings.validate_for_startup()
    if settings.sentry_dsn:
        import sentry_sdk

        # Request bodies contain claim data; never send them to an external service.
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, send_default_pii=False, max_request_body_size="never", traces_sample_rate=0.05)
    await cache.connect()
    if settings.database_url.startswith("sqlite"):
        # Development convenience. PostgreSQL schemas are managed with Alembic migrations.
        await create_all()
    model_loaded = registry.load()
    logger.info(
        "startup", env=settings.env, database=settings.database_url.split("://")[0], cache=cache.backend,
        processing="inline" if settings.process_inline else "celery", model=registry.version if model_loaded else "none (rules only)",
        ml_server=bool(settings.ml_server_url), copilot=bool(settings.ollama_api_key and settings.enable_copilot),
    )
    yield
    await cache.close()
    await dispose_engine()
