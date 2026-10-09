import pytest

from tests.conftest import api_claim, ingest


async def flags(client, tenant, claim_id) -> dict:
    body = (await client.get(f"/api/v1/claims/{claim_id}/flags", headers=tenant["investigator"])).json()
    return {f["rule_name"]: f for f in body["flags"] if f.get("rule_name")}


@pytest.mark.asyncio
async def test_units_cap_and_amount_outlier_reach_the_api_and_the_evidence_trail(client, tenants):
    tenant = tenants["alpha"]
    units = api_claim("CLM-UNITS", code="97112", billed=2100)
    units["lines"][0]["units"] = 50
    await ingest(client, tenant["key"], units)
    found = await flags(client, tenant, "CLM-UNITS")
    assert found["units_cap"]["confidence"] == 0.95 and found["units_cap"]["evidence"]["max_units"] == 4

    await ingest(client, tenant["key"], api_claim("CLM-AMOUNT", provider="PRV-2", member="MBR-2", billed=156_789))
    found = await flags(client, tenant, "CLM-AMOUNT")
    assert found["amount_outlier"]["confidence"] == 0.95 and found["amount_outlier"]["evidence"]["typical_amount"] == 120

    cases = (await client.get("/api/v1/cases", headers=tenant["investigator"])).json()["items"]
    assert {c["provider_id"] for c in cases} == {"PRV-1", "PRV-2"}  # 0.95 is enough to ask a reviewer to look
    case_id = next(c["case_id"] for c in cases if c["provider_id"] == "PRV-2")
    item = next(i for i in (await client.get(f"/api/v1/cases/{case_id}/evidence", headers=tenant["investigator"])).json()["items"] if i["name"] == "amount_outlier")
    assert item["title"] == "Unusually high amount" and "usually billed" in item["summary"]


@pytest.mark.asyncio
async def test_amount_outlier_uses_tenant_history_only_when_there_is_enough(client, tenants):
    tenant = tenants["alpha"]
    # 96372 is not in the sample table, so the only possible yardstick is the tenant's own history.
    for i in range(10):
        await ingest(client, tenant["key"], api_claim(f"CLM-H{i}", provider=f"PRV-{i}", member=f"MBR-{i}", code="96372", billed=50))
    await ingest(client, tenant["key"], api_claim("CLM-EARLY", provider="PRV-X", member="MBR-X", code="96372", billed=5000))
    assert "amount_outlier" not in await flags(client, tenant, "CLM-EARLY")  # ten lines of history: stay silent

    from app.core.cache import cache

    for i in range(10, 31):
        await ingest(client, tenant["key"], api_claim(f"CLM-H{i}", provider=f"PRV-{i}", member=f"MBR-{i}", code="96372", billed=50))
    cache.clear_memory()  # the per-code median is cached for five minutes
    await ingest(client, tenant["key"], api_claim("CLM-LATE", provider="PRV-Y", member="MBR-Y", code="96372", billed=5000))
    found = await flags(client, tenant, "CLM-LATE")
    assert found["amount_outlier"]["evidence"]["typical_amount"] == 50 and "this tenant" in found["amount_outlier"]["evidence"]["basis"]


HISTORY_RULES = {"peer_outlier", "split_billing", "modifier_overuse", "new_provider_burst", "provider_shopping"}


@pytest.mark.asyncio
async def test_history_rules_stay_silent_for_a_tenant_with_ten_claims(client, tenants):
    tenant = tenants["alpha"]
    for i in range(10):
        await ingest(client, tenant["key"], api_claim(f"CLM-T{i}", provider=f"PRV-{i % 2}", member="MBR-1", day=f"2025-01-{i + 1:02d}", billed=60))
        assert not HISTORY_RULES & set(await flags(client, tenant, f"CLM-T{i}"))


@pytest.mark.asyncio
async def test_peer_comparison_runs_through_the_pipeline(client, tenants):
    from sqlalchemy import select

    from app.core.cache import cache
    from app.db import session as db_session
    from app.detection.pipeline import DetectionPipeline
    from app.models import Claim, Provider, Tenant

    tenant = tenants["alpha"]
    async with db_session.session_scope(tenant["id"]) as db:
        for pid in [f"PEER-{p}" for p in range(6)] + ["PRV-BUSY"]:
            db.add(Provider(tenant_id=tenant["id"], provider_id=pid, name=pid, specialty="Cardiology"))
    # Six ordinary peers: ten members seen once each. One of their lines carries a bypass modifier.
    for p in range(6):
        for i in range(10):
            claim = api_claim(f"CLM-P{p}-{i}", provider=f"PEER-{p}", member=f"MBR-{p}-{i}", day="2024-12-20")
            if i == 0:
                claim["lines"][0]["modifiers"] = ["59"]
            await ingest(client, tenant["key"], claim)
    # One provider billing five members four times each at a higher amount.
    for i in range(20):
        await ingest(client, tenant["key"], api_claim(f"CLM-B{i}", provider="PRV-BUSY", member=f"MBR-B{i % 5}", day=f"2025-01-{i + 1:02d}", billed=300))
    cache.clear_memory()  # peer figures are cached for five minutes
    await ingest(client, tenant["key"], api_claim("CLM-B-LAST", provider="PRV-BUSY", member="MBR-B0", day="2025-01-21", billed=300))

    found = await flags(client, tenant, "CLM-B-LAST")
    e = found["peer_outlier"]["evidence"]
    assert e["peers_compared"] == 6 and e["peer_median"] == 120 and e["provider_value"] == 1260 and e["metric"] == "billed_per_member"
    assert found["peer_outlier"]["confidence"] == 0.90
    assert "new_provider_burst" not in found  # the tenant itself has under 60 days of history

    async with db_session.session_scope(tenant["id"]) as db:
        row = (await db.execute(select(Claim).where(Claim.claim_id == "CLM-B-LAST"))).scalar_one()
        ctx = await DetectionPipeline(db, await db.get(Tenant, tenant["id"])).load_context(row)
    peer = next(p for p in ctx.specialty_peers if p.provider_id == "PEER-0")
    assert (peer.claims, peer.members, peer.billed, peer.lines, peer.bypass_lines) == (10, 10, 1200.0, 10, 1)
    assert str(ctx.provider_first_seen) == "2025-01-01" and str(ctx.tenant_first_seen) == "2024-12-20"


NEW_RULES = ["units_cap", "amount_outlier", "diagnosis_procedure_mismatch", "demographic_mismatch", "peer_outlier", "split_billing", "modifier_overuse", "new_provider_burst", "provider_shopping"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["duplicate_billing", "unbundling", "impossible_day", "phantom_billing", "ncci_edit"])
async def test_existing_scenarios_score_and_route_exactly_as_they_did_without_the_new_rules(client, tenants, scheme):
    """Tenant beta has the nine new rules switched off, which is the behaviour before they existed."""
    from app.db import session as db_session
    from app.models import Tenant

    async with db_session.session_scope() as db:
        beta = await db.get(Tenant, tenants["beta"]["id"])
        beta.config = {**(beta.config or {}), "disabled_rules": NEW_RULES}

    outcome = {}
    for slug in ("alpha", "beta"):
        tenant = tenants[slug]
        if scheme == "ncci_edit":
            claim = api_claim("NCCI-1", code="93000")
            claim["lines"].append({"line_id": "NCCI-L2", "cpt_code": "93005", "units": 1, "billed_amount": 120, "diagnosis_pointer": [1]})
            claim["total_billed"] = 240
            await ingest(client, tenant["key"], claim)
            stored = (await client.get("/api/v1/claims/NCCI-1", headers=tenant["investigator"])).json()
            cases = (await client.get("/api/v1/cases", headers=tenant["investigator"])).json()["total"]
            outcome[slug] = (stored["risk_score"], sorted(await flags(client, tenant, "NCCI-1")), cases)
        else:
            r = (await client.post("/api/v1/inject", headers=tenant["investigator"], json={"scheme": scheme})).json()
            outcome[slug] = (r["risk_score"], r["composite_risk"], r["max_rule_confidence"], r["case_opening_reason"], r["case_id"] is not None, sorted(f["rule_name"] for f in r["flags"] if f.get("rule_name")))
    assert outcome["alpha"] == outcome["beta"], outcome
    assert not set(outcome["alpha"][-1] if scheme != "ncci_edit" else outcome["alpha"][1]) & set(NEW_RULES)


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", NEW_RULES)
async def test_each_new_rule_has_an_inject_scheme_that_triggers_it(client, tenants, scheme):
    tenant = tenants["alpha"]
    listed = (await client.get("/api/v1/inject/schemes", headers=tenant["investigator"])).json()["schemes"]
    assert scheme in {s["scheme"] for s in listed}
    response = await client.post("/api/v1/inject", headers=tenant["investigator"], json={"scheme": scheme})
    assert response.status_code == 200, response.text
    result = response.json()
    found = {f["rule_name"]: f["confidence"] for f in result["flags"] if f.get("rule_name")}
    assert scheme in found, result
