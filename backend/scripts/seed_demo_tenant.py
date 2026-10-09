"""Seed only the Mock Insurer integration tenant; no claims, model training or schema changes.

From the project root: python backend/scripts/seed_demo_tenant.py
From backend/: python -m scripts.seed_demo_tenant
"""
import asyncio
import os
import sys
from pathlib import Path

# Support the requested direct-file command and resolve SQLite/artifacts relative to backend/.
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.config import get_settings  # noqa: E402
from app.core.security import hash_api_key  # noqa: E402
from app.db.seed.seed_demo_tenant import seed_tenant  # noqa: E402
from app.db.session import create_all, dispose_engine, session_scope  # noqa: E402
from app.integrations.webhooks import REGISTRY_KEY, SUPPORTED_EVENTS, validate_destination  # noqa: E402


async def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise RuntimeError("Fixed demo credentials cannot be seeded in production.")
    key = settings.demo_api_key
    url = validate_destination(settings.demo_webhook_url)
    secret = settings.demo_webhook_secret
    if len(secret) < 16:
        raise ValueError("DEMO_WEBHOOK_SECRET must be at least 16 characters.")
    # Local convenience only; production databases must use migrations.
    if settings.database_url.startswith("sqlite"):
        await create_all()
    try:
        async with session_scope() as db:
            tenant, _generated_key = await seed_tenant(db, "Mock Insurer Demo", "demo_tenant")
            if not tenant.is_demo:
                raise RuntimeError("Refusing to replace credentials on an existing non-demo tenant.")
            tenant.api_key_hash, tenant.api_key_last4 = hash_api_key(key), key[-4:]
            cfg = dict(tenant.config or {})
            cfg["thresholds"] = {**cfg.get("thresholds", {}), "routing": 0.70}
            cfg["case_opening"] = {**cfg.get("case_opening", {}), "tier1_composite_threshold": 0.70, "tier2_enabled": True, "tier2_rule_threshold": 0.90}
            cfg["integration_read_access"] = True
            registry = dict(cfg.get(REGISTRY_KEY) or {})
            registry["mock-insurer"] = {"id": "mock-insurer", "url": url, "events": sorted(SUPPORTED_EVENTS), "secret": secret, "enabled": True}
            cfg[REGISTRY_KEY] = registry
            tenant.config = cfg
            tenant_uuid = str(tenant.id)
        print("Demo integration tenant ready (safe to re-run).")
        print(f"Tenant UUID: {tenant_uuid}")
        print(f"Webhook: {url}")
        print("Mock backend environment:")
        print("CLAIMSHIELD_API_URL=http://localhost:8000")
        print(f"CLAIMSHIELD_API_KEY={key}")
        print("CLAIMSHIELD_TENANT_ID=demo_tenant")
        print(f"CLAIMSHIELD_WEBHOOK_SECRET={secret}")
        print("MOCK_BACKEND_PORT=3002")
        print("MOCK_FRONTEND_PORT=3001")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
