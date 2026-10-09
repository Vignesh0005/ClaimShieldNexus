"""Every injected test scheme must reach a reviewer, and the new read endpoints must work."""
import pytest

from app.services.inject_service import SCHEMES

pytestmark = pytest.mark.asyncio


async def test_all_eight_schemes_open_a_case(client, tenants):
    inv = tenants["alpha"]["investigator"]
    rows = []
    for scheme in list(SCHEMES)[:8]:  # the original eight; schemes for the newer rules are covered in test_new_rules.py
        out = (await client.post("/api/v1/inject", headers=inv, json={"scheme": scheme})).json()
        rows.append((scheme, out["composite_risk"], out["max_rule_confidence"], out["routed"], out["case_opening_reason"]))
    print("\nscheme | composite_risk | max_rule_conf | opened | reason")
    for r in rows:
        print(" | ".join(str(x) for x in r))
    assert len(rows) == 8
    assert all(opened for *_, opened, _ in rows), [r for r in rows if not r[3]]
    assert all(reason for *_, reason in rows)
    cases = (await client.get("/api/v1/cases?limit=100", headers=inv)).json()
    assert cases["total"] >= 8 and all(c["opened_reason"] for c in cases["items"])


async def test_tier2_can_be_disabled_per_tenant(client, tenants):
    t = tenants["alpha"]
    cfg = {"config": {"thresholds": {"routing": 0.95}, "case_opening": {"tier2_enabled": False, "tier3_enabled": False}}}
    assert (await client.post("/api/v1/tenants/me/config", headers=t["admin"], json=cfg)).status_code == 200
    out = (await client.post("/api/v1/inject", headers=t["investigator"], json={"scheme": "duplicate_billing"})).json()
    assert out["caught"] is True and out["routed"] is False and out["case_id"] is None
    cfg = {"config": {"case_opening": {"tier2_enabled": True, "tier2_rule_threshold": 0.9, "tier3_enabled": False}}}
    await client.post("/api/v1/tenants/me/config", headers=t["admin"], json=cfg)
    out = (await client.post("/api/v1/inject", headers=t["investigator"], json={"scheme": "duplicate_billing"})).json()
    assert out["routed"] is True and out["case_opening_reason"] == "tier2_rule_confidence"


async def test_ui_support_endpoints(client, tenants):
    t = tenants["alpha"]
    inv = t["investigator"]
    out = (await client.post("/api/v1/inject", headers=inv, json={"scheme": "identity_misuse"})).json()
    case_id = out["case_id"]

    dash = (await client.get("/api/v1/dashboard", headers=inv)).json()
    assert dash["funnel"]["stages"][0]["value"] == 2 and dash["periods"]["current"]["claims"] == 2 and dash["top_providers"]
    assert any(a["action"] == "case.created" for a in dash["activity"])

    geo = (await client.get("/api/v1/network/geo-conflicts", headers=inv)).json()
    assert geo["total"] == 1 and {geo["events"][0]["a"]["city"], geo["events"][0]["b"]["city"]} == {"Mumbai", "Delhi"} and geo["events"][0]["case_id"] == case_id

    analytics = (await client.get("/api/v1/admin/analytics", headers=inv)).json()
    assert analytics["dollars_recovered"] is None and analytics["decisions"]["reviewer_confirmed_rate"] is None and analytics["by_flag"]

    assert (await client.post(f"/api/v1/cases/{case_id}/status?status=in_review", headers=inv)).json()["status"] == "in_review"
    assert (await client.post(f"/api/v1/cases/{case_id}/status?status=confirmed", headers=inv)).status_code == 422  # outcomes need a decision
    assert (await client.post(f"/api/v1/cases/{case_id}/status?status=in_review", headers=t["viewer"])).status_code == 403

    assert (await client.post("/api/v1/audit/events", headers=inv, json={"action": "export.queue_csv", "detail": "12 cases"})).status_code == 200
    assert (await client.post("/api/v1/audit/events", headers=inv, json={"action": "case.decision"})).status_code == 422  # cannot forge server events
    trail = (await client.get("/api/v1/audit", headers=inv)).json()["events"]
    assert any(e["action"] == "client.export.queue_csv" and e["details"]["client_reported"] for e in trail)
    assert any(e["action"] == "case.status_changed" for e in trail)

    assert (await client.get("/api/v1/admin/logs", headers=t["admin"])).status_code == 403
    assert "logs" in (await client.get("/api/v1/admin/logs", headers=t["platform"])).json()
