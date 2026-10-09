from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.audit import RequestAuditMiddleware
from app.api.middleware.error_handler import register_error_handlers
from app.api.v1 import health
from app.api.v1.router import api_router
from app.config import get_settings
from app.lifespan import lifespan

DESCRIPTION = """
Fraud, waste and abuse detection for healthcare payers.

**How it works:** AI detects and explains, a person verifies, and verified outcomes improve the AI.

- A coverage failure is not fraud and is not a claim denial.
- Nothing is denied, accused or actioned automatically. The strongest thing this API does by
  itself is open a case for a reviewer.
- Every score cites the evidence it came from, and every action is written to an append-only audit log.

Authenticate with `X-API-Key` (claim ingestion) or `Authorization: Bearer <token>` (users).
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ClaimShield Nexus API",
        version="0.1.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(RequestAuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-api-key", "x-tenant-id", "x-request-id", "x-claimshield-signature"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
