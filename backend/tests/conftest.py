import os
import tempfile

# A file database rather than :memory: so background detection tasks get their own connection.
_DB = os.path.join(tempfile.mkdtemp(prefix="claimshield-test-"), "test.db").replace(os.sep, "/")

# Must be set before any app module reads settings.
os.environ.update(
    ENV="test",
    DATABASE_URL=f"sqlite+aiosqlite:///{_DB}",
    LOG_LEVEL="ERROR",
    RATE_LIMIT_PER_MINUTE="0",
    ARTIFACTS_DIR="tests/.artifacts-none",  # no model: exercises the rules-only fallback
    OLLAMA_API_KEY="",
    REDIS_URL="",
    ML_SERVER_URL="",
)

from datetime import date, timedelta  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.core.cache import cache  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.seed.seed_demo_tenant import seed_tenant  # noqa: E402
from app.detection.context import ClaimData, DetectionContext, LineData, MemberInfo, ProviderInfo  # noqa: E402


@pytest_asyncio.fixture
async def db_ready():
    """Empty database per test."""
    configure_logging()
    await db_session.dispose_engine()
    cache.clear_memory()
    import app.models  # noqa: F401

    async with db_session.get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db_session.dispose_engine()


@pytest_asyncio.fixture
async def tenants(db_ready):
    """Two tenants with users, and bearer headers for each role."""
    out = {}
    async with db_session.session_scope() as db:
        for slug in ("alpha", "beta"):
            tenant, api_key = await seed_tenant(db, f"{slug.title()} Health", slug)
            out[slug] = {"id": tenant.id, "api_key": api_key, "key": {"X-API-Key": api_key}}
    for slug, t in out.items():
        for name, user, role in (("admin", "ADM-002", "admin"), ("investigator", "AUD-007", "siu_investigator"), ("analyst", "ANL-014", "analyst"), ("viewer", "VWR-021", "viewer")):
            t[name] = {"Authorization": "Bearer " + create_access_token(subject=user, tenant_id=t["id"], role=role)}
        t["platform"] = {"Authorization": "Bearer " + create_access_token(subject="ADM-002", tenant_id=t["id"], role="admin", platform_admin=True)}
    return out


@pytest_asyncio.fixture
async def client(db_ready):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


TODAY = date(2025, 1, 8)


def make_claim(claim_id="C1", provider="PRV-1", member="MBR-1", codes=("99213",), day=TODAY, billed=120.0, **kw) -> ClaimData:
    lines = [LineData(f"{claim_id}-L{i + 1}", code, [], kw.pop("units", 1), billed, billed * 0.9, day, [1]) for i, code in enumerate(codes)]
    return ClaimData(claim_id=claim_id, member_id=member, provider_id=provider, service_date=day, total_billed=billed * len(codes), diagnosis_codes=kw.pop("dx", ["M54.5"]), lines=lines, **kw)


def make_ctx(claim: ClaimData, provider_history=(), member_history=(), **kw) -> DetectionContext:
    return DetectionContext(
        claim=claim, provider=kw.pop("provider", ProviderInfo(claim.provider_id, True, "Family medicine")), member=kw.pop("member", MemberInfo(claim.member_id, True, 40)),
        provider_history=list(provider_history), member_history=list(member_history), **kw,
    )


def api_claim(claim_id="CLM-1", provider="PRV-1", member="MBR-1", code="99213", day="2025-01-08", billed=120.0, **extra) -> dict:
    return {
        "claim_id": claim_id, "member_id": member, "provider_id": provider, "service_date": day, "total_billed": billed, "diagnosis_codes": ["M54.5"],
        "plan_type": "family_floater", "policy_start_date": "2020-01-01", "service_location": "IN",
        "lines": [{"line_id": f"{claim_id}-L1", "cpt_code": code, "units": 1, "billed_amount": billed, "paid_amount": billed * 0.9, "diagnosis_pointer": [1]}],
        **extra,
    }


async def ingest(client, headers, claim, wait=True) -> dict:
    """Posts a claim and, by default, waits for background detection to finish."""
    import asyncio

    r = await client.post("/api/v1/claims", headers=headers, json=claim)
    assert r.status_code == 202, r.text
    for _ in range(200):
        if not wait:
            break
        status = (await client.get(f"/api/v1/claims/{claim['claim_id']}/status", headers=headers)).json()
        if status["status"] != "processing":
            assert status["status"] == "processed", status
            break
        await asyncio.sleep(0.05)
    return r.json()


@pytest.fixture
def days_ago():
    return lambda n: TODAY - timedelta(days=n)
