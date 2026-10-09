from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.config import get_settings
from app.core.cache import cache
from app.db.session import get_sessionmaker
from app.detection.ml.registry import registry, remote_client
from app.explainability.copilot import OllamaClient

# Mounted at the root (not under /api/v1) and unauthenticated: used by load balancers and probes.
# Responses carry status only, never data.
router = APIRouter(tags=["health"])


async def _db_ok() -> bool:
    try:
        async with get_sessionmaker()() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


def _result(ok: bool, **extra) -> JSONResponse:
    return JSONResponse({"status": "ok" if ok else "unavailable", **extra}, status_code=200 if ok else 503)


@router.get("/health", summary="Liveness")
async def liveness():
    return {"status": "ok"}


@router.get("/health/ready", summary="Readiness: database and cache reachable")
async def readiness():
    db, redis = await _db_ok(), await cache.ping()
    return _result(db and redis, database=db, cache=redis, cache_backend=cache.backend)


@router.get("/health/db", summary="Database health")
async def db_health():
    return _result(await _db_ok())


@router.get("/health/redis", summary="Redis health")
async def redis_health():
    return _result(await cache.ping(), backend=cache.backend, note=None if cache.backend == "redis" else "REDIS_URL is not set; using the in-process cache.")


@router.get("/health/ml-server", summary="ML scoring health")
async def ml_health():
    client = remote_client()
    local = registry.load()
    if client is None:
        return _result(True, mode="local" if local else "rules_only", model_version=registry.version, degraded=not local)
    remote = await client.health()
    return _result(remote or local or get_settings().ml_fallback_enabled, mode="remote" if remote else ("local_fallback" if local else "rules_only"), remote_reachable=remote, model_version=registry.version, degraded=not remote)


@router.get("/health/ollama", summary="Copilot model health")
async def ollama_health():
    client = OllamaClient()
    if not client.configured:
        return _result(True, mode="template_fallback", note="No OLLAMA_API_KEY set or copilot disabled; explanations use the deterministic template.")
    ok = await client.health()
    return _result(ok, mode="llm" if ok else "template_fallback", model=client.model)


@router.get("/metrics", summary="Prometheus metrics")
async def prometheus():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
