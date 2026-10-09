"""Security tests: one tenant must never be able to read, change or infer another tenant's data."""
import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.models import Case, Claim, DetectionSignal
from tests.conftest import api_claim, ingest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def seeded(client, tenants):
    """The same claim IDs in both tenants, with a duplicate (and so a case) in each."""
    for slug in ("alpha", "beta"):
        for claim_id in ("CLM-A", "CLM-B"):
            await ingest(client, tenants[slug]["key"], api_claim(claim_id, provider=f"PRV-{slug}", code="99215", billed=400))
    return tenants


async def test_same_claim_id_can_exist_in_two_tenants(client, seeded):
    a = (await client.get("/api/v1/claims/CLM-B", headers=seeded["alpha"]["investigator"])).json()
    b = (await client.get("/api/v1/claims/CLM-B", headers=seeded["beta"]["investigator"])).json()
    assert a["provider_id"] == "PRV-alpha" and b["provider_id"] == "PRV-beta"


async def test_lists_only_contain_own_tenant(client, seeded):
    for slug in ("alpha", "beta"):
        h = seeded[slug]["investigator"]
        claims = (await client.get("/api/v1/claims", headers=h)).json()
        assert claims["total"] == 2 and {c["provider_id"] for c in claims["items"]} == {f"PRV-{slug}"}
        cases = (await client.get("/api/v1/cases", headers=h)).json()
        assert cases["total"] == 1 and cases["items"][0]["provider_id"] == f"PRV-{slug}"
        graph = (await client.get("/api/v1/network", headers=h)).json()
        assert all(n["id"] != f"PRV-{'beta' if slug == 'alpha' else 'alpha'}" for n in graph["nodes"])
        audit = (await client.get("/api/v1/audit", headers=seeded[slug]["admin"])).json()
        assert audit["total"] > 0


async def test_detection_history_does_not_cross_tenants(client, tenants):
    """A claim in beta identical to one in alpha is not a duplicate: history is per tenant."""
    await ingest(client, tenants["alpha"]["key"], api_claim("CLM-X", code="99215", billed=400))
    await ingest(client, tenants["beta"]["key"], api_claim("CLM-Y", code="99215", billed=400))
    flags = (await client.get("/api/v1/claims/CLM-Y/flags", headers=tenants["beta"]["investigator"])).json()["flags"]
    assert flags == []
    assert (await client.get("/api/v1/cases", headers=tenants["beta"]["investigator"])).json()["total"] == 0


async def test_other_tenants_records_are_not_found(client, tenants):
    await ingest(client, tenants["alpha"]["key"], api_claim("CLM-ONLY-ALPHA"))
    beta = tenants["beta"]["investigator"]
    for path in ("/claims/CLM-ONLY-ALPHA", "/claims/CLM-ONLY-ALPHA/flags", "/claims/CLM-ONLY-ALPHA/status", "/detection/signals/CLM-ONLY-ALPHA"):
        assert (await client.get("/api/v1" + path, headers=beta)).status_code == 404, path
    assert (await client.post("/api/v1/detection/run/CLM-ONLY-ALPHA", headers=beta)).status_code == 404
    assert (await client.post("/api/v1/claims/CLM-ONLY-ALPHA/reprocess", headers=beta)).status_code == 404


async def test_tenant_header_cannot_be_spoofed(client, seeded):
    beta = seeded["beta"]["admin"]  # a tenant admin, not a platform admin
    r = await client.get("/api/v1/cases", headers={**beta, "X-Tenant-Id": "alpha"})
    assert r.status_code == 403
    for path in ("/tenants/alpha", "/tenants/alpha/config", f"/tenants/{seeded['alpha']['id']}"):
        assert (await client.get("/api/v1" + path, headers=beta)).status_code == 403
    assert (await client.post("/api/v1/tenants/alpha/api-keys", headers=beta)).status_code == 403
    assert (await client.get("/api/v1/tenants/does-not-exist", headers=beta)).status_code == 403  # no existence oracle
    assert len((await client.get("/api/v1/tenants", headers=beta)).json()["tenants"]) == 1


async def test_platform_admin_can_switch_tenant_explicitly(client, seeded):
    platform = seeded["beta"]["platform"]
    own = (await client.get("/api/v1/cases", headers=platform)).json()
    switched = (await client.get("/api/v1/cases", headers={**platform, "X-Tenant-Id": "alpha"})).json()
    assert own["items"][0]["provider_id"] == "PRV-beta" and switched["items"][0]["provider_id"] == "PRV-alpha"
    assert len((await client.get("/api/v1/tenants", headers=platform)).json()["tenants"]) == 2


async def test_api_key_is_limited_to_ingestion_and_rotation_revokes_it(client, tenants):
    t = tenants["alpha"]
    for path in ("/cases", "/queue", "/audit", "/network", "/models", "/users"):
        assert (await client.get("/api/v1" + path, headers=t["key"])).status_code == 403, path
    new = (await client.post("/api/v1/tenants/me/api-keys", headers=t["admin"])).json()["api_key"]
    assert (await client.post("/api/v1/claims", headers=t["key"], json=api_claim("CLM-OLD"))).status_code == 401
    assert (await client.post("/api/v1/claims", headers={"X-API-Key": new}, json=api_claim("CLM-NEW"))).status_code == 202
    assert (await client.post("/api/v1/tenants/me/api-keys", headers=t["investigator"])).status_code == 403


async def test_role_changes_and_deactivation_take_effect_immediately(client, tenants):
    t = tenants["alpha"]
    assert (await client.get("/api/v1/audit", headers=t["viewer"])).status_code == 403
    r = await client.post("/api/v1/users/VWR-021", headers=t["admin"], json={"role": "siu_investigator"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/audit", headers=t["viewer"])).status_code == 200  # same token, stored role wins
    await client.post("/api/v1/users/VWR-021", headers=t["admin"], json={"active": False})
    assert (await client.get("/api/v1/cases", headers=t["viewer"])).status_code == 403
    assert (await client.post("/api/v1/users/ADM-002", headers=t["admin"], json={"role": "viewer"})).status_code == 422  # no self-lockout
    assert (await client.post("/api/v1/users/VWR-021", headers=tenants["beta"]["admin"], json={"active": True})).status_code in (200, 404)
    assert (await client.get("/api/v1/cases", headers=t["viewer"])).status_code == 403  # beta's admin could not reactivate alpha's user


async def test_session_level_filter_blocks_unfiltered_queries(seeded):
    """Defence in depth: even a query that forgets its tenant predicate returns one tenant's rows."""
    async with db_session.session_scope(seeded["alpha"]["id"]) as db:
        claims = (await db.execute(select(Claim))).scalars().all()
        assert len(claims) == 2 and {c.tenant_id for c in claims} == {seeded["alpha"]["id"]}
        assert all(len(c.lines) == 1 and c.lines[0].tenant_id == seeded["alpha"]["id"] for c in claims)  # relationship loads too
        assert {c.tenant_id for c in (await db.execute(select(Case))).scalars()} == {seeded["alpha"]["id"]}
        joined = (await db.execute(select(DetectionSignal, Claim).join(Claim, Claim.id == DetectionSignal.claim_id))).all()
        assert joined and all(s.tenant_id == seeded["alpha"]["id"] for s, _ in joined)
    async with db_session.session_scope() as db:
        assert len((await db.execute(select(Claim))).scalars().all()) == 4  # unscoped platform session sees all
