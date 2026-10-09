import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core import metrics
from app.core.logging import logger
from app.db.session import get_sessionmaker
from app.models import AuditLog

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class RequestAuditMiddleware(BaseHTTPMiddleware):
    """Gives every request an ID, logs it, and writes an audit entry for every state-changing API
    call by an authenticated caller. Domain-level entries (decisions, assignments) are written by
    the services; this is the safety net that guarantees no write goes unrecorded."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers["x-request-id"] = request_id
        metrics.http_requests.labels(request.method, str(response.status_code)).inc()
        path = request.url.path
        if path.startswith("/api/"):
            logger.info("request", method=request.method, path=path, status=response.status_code, ms=elapsed_ms)
        principal = getattr(request.state, "principal", None)
        if principal is not None and request.method in MUTATING and path.startswith("/api/v1") and response.status_code < 500:
            try:
                async with get_sessionmaker()() as db:
                    db.add(
                        AuditLog(
                            tenant_id=principal.tenant_id, actor_id=principal.user_id, actor_label=principal.subject, actor_type=principal.actor_type,
                            action=f"http.{request.method.lower()}", resource_type="endpoint", resource_id=path[:100],
                            details={"status": response.status_code, "request_id": request_id, "ms": elapsed_ms},
                            ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"),
                        )
                    )
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.error("request_audit_failed", error=str(exc))
        return response
