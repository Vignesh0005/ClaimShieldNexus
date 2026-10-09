"""End-to-end through the HTTP API on an in-memory database: ingest, detection, case, evidence,
decision, feedback, audit. No model artifacts are present, so this also covers rules-only fallback."""
import pytest
from sqlalchemy import select

from app.core.exceptions import ImmutableRecord
from app.db import session as db_session
from app.models import AuditLog
from tests.conftest import api_claim, ingest

pytestmark = pytest.mark.asyncio


async def test_health_endpoints_need_no_auth(client, db_ready):
    for path in ("/health", "/health/ready", "/health/db", "/health/redis", "/health/ml-server", "/health/ollama", "/metrics"):
        assert (await client.get(path)).status_code == 200, path
    ml = (await client.get("/health/ml-server")).json()
    assert ml["mode"] == "rules_only" and ml["degraded"] is True


async def test_auth_is_required_and_errors_have_one_shape(client, tenants):
    r = await client.get("/api/v1/cases")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
    assert (await client.get("/api/v1/cases", headers={"Authorization": "Bearer nonsense"})).status_code == 401
    assert (await client.get("/api/v1/cases", headers={"X-API-Key": "csn_wrong"})).status_code == 401


async def test_ingest_is_idempotent_and_never_overwrites(client, tenants):
    key = tenants["alpha"]["key"]
    first = await ingest(client, key, api_claim())
    assert first["status"] == "processing" and first["job_id"].startswith("job_") and not first["duplicate"]
    again = await ingest(client, key, api_claim())
    assert again["duplicate"] is True and again["job_id"] == first["job_id"]
    r = await client.post("/api/v1/claims", headers=key, json=api_claim(billed=999))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    listed = (await client.get("/api/v1/claims", headers=tenants["alpha"]["viewer"])).json()
    assert listed["total"] == 1


async def test_clean_claim_is_processed_with_low_risk_and_no_case(client, tenants):
    t = tenants["alpha"]
    await ingest(client, t["key"], api_claim())
    status = (await client.get("/api/v1/claims/CLM-1/status", headers=t["key"])).json()
    assert status["status"] == "processed" and status["coverage_status"] == "COVERABLE" and status["risk_score"] < 0.2
    assert (await client.get("/api/v1/cases", headers=t["investigator"])).json()["total"] == 0
    funnel = (await client.get("/api/v1/funnel", headers=t["investigator"])).json()
    assert [s["value"] for s in funnel["stages"]] == [1, 0, 0, 0]


async def test_coverage_failure_is_not_scored_as_fraud(client, tenants):
    t = tenants["alpha"]
    await ingest(client, t["key"], api_claim("CLM-COS", code="15780"))
    claim = (await client.get("/api/v1/claims/CLM-COS", headers=t["investigator"])).json()
    assert claim["coverage_status"] == "NOT_COVERABLE" and claim["risk_score"] is None and claim["severity"] is None
    assert claim["coverage_details"]["not_fraud"] is True and claim["coverage_details"]["not_denial"] is True
    assert (await client.get("/api/v1/claims/CLM-COS/flags", headers=t["investigator"])).json()["flags"] == []
    run = (await client.post("/api/v1/detection/run/CLM-COS", headers=t["investigator"])).json()
    assert run["fwa_signals"] == [] and run["risk_score"] is None and run["not_fraud"] is True and run["not_denial"] is True


async def test_duplicate_becomes_a_case_and_can_be_reviewed(client, tenants):
    t = tenants["alpha"]
    inv = t["investigator"]
    await ingest(client, t["key"], api_claim("CLM-A", code="99215", billed=400))
    await ingest(client, t["key"], api_claim("CLM-B", code="99215", billed=400))

    flags = (await client.get("/api/v1/claims/CLM-B/flags", headers=inv)).json()["flags"]
    dup = next(f for f in flags if f.get("rule_name") == "duplicate_billing")
    assert dup["confidence"] == 0.98 and dup["evidence"]["matched_claim_id"] == "CLM-A" and dup["source_fields"]
    claim = (await client.get("/api/v1/claims/CLM-B", headers=inv)).json()
    assert claim["model_version"] == "fallback_rules_only"  # no model present: degraded, not failed

    cases = (await client.get("/api/v1/cases?status=open", headers=inv)).json()
    assert cases["total"] == 1
    case_id = cases["items"][0]["case_id"]
    assert case_id.startswith("CS-") and cases["items"][0]["status"] == "pending_review"

    detail = (await client.get(f"/api/v1/cases/{case_id}", headers=inv)).json()
    assert detail["flags"][0]["name"] == "duplicate_billing" and detail["primary_claim"]["claim_id"] == "CLM-B"

    evidence = (await client.get(f"/api/v1/cases/{case_id}/evidence", headers=inv)).json()
    assert evidence["items"][0]["source"]["claim_id"] == "CLM-B"
    assert any("No prior investigation outcome" in l for l in evidence["limitations"])
    assert any("ML models were unavailable" in l for l in evidence["limitations"])

    what_if = (await client.post(f"/api/v1/cases/{case_id}/counterfactual", headers=inv)).json()
    removed = next(s for s in what_if["scenarios"] if s["removes"] == "duplicate_billing")
    assert removed["counterfactual_risk"] < what_if["baseline_risk"] and removed["would_still_route"] is False

    brief = (await client.post(f"/api/v1/briefs/{case_id}/generate", headers=inv)).json()
    assert "Not a fraud determination" in brief["markdown"] and "Matches CLM-A" in brief["markdown"] and "Limitations" in brief["markdown"]
    plain = (await client.post(f"/api/v1/briefs/{case_id}/plain", headers=inv)).json()
    assert "not a conclusion about anyone" in plain["markdown"]
    pdf = await client.get(f"/api/v1/briefs/{case_id}/pdf", headers=inv)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    copilot = (await client.post("/api/v1/copilot/investigate", headers=inv, json={"case_id": case_id})).json()
    assert copilot["model"] == "template_fallback" and copilot["disclaimer"] and copilot["limitations"] and copilot["suggested_next_action"]

    queue = (await client.get("/api/v1/queue", headers=inv)).json()
    assert queue["total"] == 1 and queue["cases"][0]["in_capacity"] is True

    # Roles: a viewer and an analyst can read but not decide.
    body = {"decision": "confirm_fraud", "notes": "Duplicate confirmed against the original claim.", "line_decisions": [{"line_id": "CLM-B-L1", "decision": "confirm"}], "next_action": "escalate_tier2"}
    for role in ("viewer", "analyst"):
        assert (await client.post(f"/api/v1/cases/{case_id}/decision", headers=t[role], json=body)).status_code == 403
    short = await client.post(f"/api/v1/cases/{case_id}/decision", headers=inv, json={**body, "notes": "ok"})
    assert short.status_code == 422  # a decision needs reasoning

    decision = (await client.post(f"/api/v1/cases/{case_id}/decision", headers=inv, json=body)).json()
    assert decision["final_label"] == 1 and decision["decided_by"] == "AUD-007" and decision["status"] == "escalated"
    assert decision["training_queued"] is True and decision["audit_logged"] is True

    trail = (await client.get(f"/api/v1/audit/{case_id}", headers=inv)).json()["events"]
    actions = [e["action"] for e in trail]
    for expected in ("case.created", "case.viewed", "case.evidence_viewed", "brief.generated", "case.line_decision", "case.decision"):
        assert expected in actions, expected
    assert next(e for e in trail if e["action"] == "case.decision")["actor"] == "AUD-007"

    training = (await client.get("/api/v1/feedback/queue", headers=inv)).json()
    assert training["training_queue_size"] == 1 and training["confirmed"] == 1 and not training["ready_to_retrain"]
    assert (await client.get("/api/v1/queue", headers=inv)).json()["total"] == 0  # decided cases leave the open queue


async def test_referral_ring_is_caught_by_the_graph_detector(client, tenants):
    t = tenants["alpha"]
    ring = ["PRV-A", "PRV-B", "PRV-C", "PRV-D"]
    n = 0
    for _ in range(3):
        for i, provider in enumerate(ring):
            n += 1
            await ingest(client, t["key"], api_claim(f"CLM-R{n}", provider=provider, member=f"MBR-{n % 5}", code="99214", billed=180, referring_provider_id=ring[i - 1]))
    flags = (await client.get(f"/api/v1/claims/CLM-R{n}/flags", headers=t["investigator"])).json()["flags"]
    loop = next(f for f in flags if f.get("pattern") == "referral_loop")
    assert sorted(loop["evidence"]["loop_members"]) == ring and loop["evidence"]["members_affected"] == 5
    loops = (await client.get("/api/v1/network/referral-loops", headers=t["investigator"])).json()
    assert loops["total"] == 1 and loops["loops"][0]["size"] == 4
    graph = (await client.get("/api/v1/network", headers=t["investigator"])).json()
    assert sum(1 for node in graph["nodes"] if node["in_loop"]) == 4


async def test_batch_reports_each_rejected_claim(client, tenants):
    r = await client.post("/api/v1/claims/batch", headers=tenants["alpha"]["key"], json={"claims": [api_claim("B1"), {"claim_id": "B2"}, api_claim("B1")]})
    out = r.json()
    assert r.status_code == 202 and out["accepted"] == 2 and out["rejected"] == 1
    assert out["errors"][0]["index"] == 1 and out["errors"][0]["code"] == "VALIDATION_FAILED" and out["claims"][1]["duplicate"] is True
    too_many = await client.post("/api/v1/claims/batch", headers=tenants["alpha"]["key"], json={"claims": [{}] * 1001})
    assert too_many.status_code == 422 and "at most 1000" in too_many.json()["error"]["message"]


async def test_coverage_evaluate_matches_documented_example(client, tenants):
    body = {"claim_id": "CLM-2025-00421", "plan_type": "family_floater", "member_age": 72, "policy_start_date": "2024-06-01", "service_date": "2025-01-08", "procedure_code": "99215", "diagnosis_codes": ["I25.10"], "service_location": "IN", "pre_auth_number": None, "documents_provided": ["claim_form", "discharge_summary"]}
    out = (await client.post("/api/v1/coverage/evaluate", headers=tenants["alpha"]["viewer"], json=body)).json()
    assert out["overall_status"] == "COVERABLE_WITH_CONDITIONS" and out["review_required"] and out["not_fraud"] and out["not_denial"]
    assert out["conditions"][0] == {"condition": "co_payment", "value": 0.1, "source": "Section 6 — Limits and Cost-Sharing Rules", "note": "Senior citizen plan typically has 10-20% co-pay"}
    assert {"rule_id": "COV_PLAN_TYPE_001", "category": "plan_type", "status": "PASS", "source": "Section 1 — Types of Health Insurance Plans"} in out["rule_results"]


async def test_inject_is_limited_to_demo_tenants_and_own_tenant(client, tenants):
    inv = tenants["alpha"]["investigator"]
    out = (await client.post("/api/v1/inject", headers=inv, json={"scheme": "duplicate_billing"})).json()
    assert out["caught"] is True and "rule" in out["caught_by"] and out["case_id"] and out["latency_ms"] >= 0
    assert (await client.post("/api/v1/inject", headers=inv, json={"scheme": "duplicate_billing", "tenant_id": "beta"})).status_code == 403
    assert (await client.post("/api/v1/inject", headers=inv, json={"scheme": "nonsense"})).status_code == 422
    assert (await client.post("/api/v1/inject", headers=tenants["alpha"]["viewer"], json={"scheme": "upcoding"})).status_code == 403


async def test_audit_log_is_append_only(client, tenants):
    await ingest(client, tenants["alpha"]["key"], api_claim())
    async with db_session.get_sessionmaker()() as db:
        entry = (await db.execute(select(AuditLog).limit(1))).scalar_one()
        entry.action = "tampered"
        with pytest.raises(ImmutableRecord):
            await db.flush()
        await db.rollback()
        entry = (await db.execute(select(AuditLog).limit(1))).scalar_one()
        await db.delete(entry)
        with pytest.raises(ImmutableRecord):
            await db.flush()


async def test_every_write_request_is_audited(client, tenants):
    t = tenants["alpha"]
    await client.post("/api/v1/tenants/me/config", headers=t["admin"], json={"config": {"capacity": {"num_investigators": 5, "hours_per_investigator": 10}}})
    events = (await client.get("/api/v1/audit", headers=t["admin"])).json()["events"]
    actions = {e["action"] for e in events}
    assert "tenant.config_updated" in actions and "http.post" in actions
    bad = await client.post("/api/v1/tenants/me/config", headers=t["admin"], json={"config": {"thresholds": {"high": 0.9, "critical": 0.8}}})
    assert bad.status_code == 422
