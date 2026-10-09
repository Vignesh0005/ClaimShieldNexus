"""Exercises real detection -> committed result -> signed webhook -> human decision callbacks."""
import hashlib
import hmac
import json

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import session as db_session
from app.integrations import webhooks
from app.models import Claim
from app.services import claim_service
from tests.conftest import api_claim, ingest

pytestmark = pytest.mark.asyncio
SECRET = "demo_webhook_secret"
URL = "http://mock-insurer/api/webhooks/claimshield"


async def register(client, tenant, events=None):
    r = await client.post("/api/v1/tenants/me/webhooks", headers=tenant["admin"], json={"url": URL, "secret": SECRET, **({"events": events} if events else {})})
    assert r.status_code == 201, r.text
    return r


def receiver(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(webhooks.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(webhooks, "RETRY_DELAYS", (0, 0))


async def test_registry_is_admin_only_and_never_returns_secrets(client, tenants):
    tenant = tenants["alpha"]
    body = {"url": URL, "secret": SECRET}
    for role in ("key", "viewer", "investigator"):
        assert (await client.post("/api/v1/tenants/me/webhooks", headers=tenant[role], json=body)).status_code == 403
    assert (await client.post("/api/v1/tenants/beta/webhooks", headers=tenant["admin"], json=body)).status_code == 403
    for invalid in ({**body, "events": ["unsupported"]}, {**body, "url": "file:///tmp/x"}, {**body, "url": "http://user:pass@mock-insurer/callback"}):
        assert (await client.post("/api/v1/tenants/me/webhooks", headers=tenant["admin"], json=invalid)).status_code == 422
    r = await register(client, tenant)
    assert SECRET not in r.text and "secret" not in r.json()["webhook"]
    listing = await client.get("/api/v1/tenants/me/webhooks", headers=tenant["admin"])
    assert len(listing.json()["webhooks"]) == 1 and SECRET not in listing.text
    assert SECRET not in (await client.get("/api/v1/tenants/me/config", headers=tenant["viewer"])).text
    await register(client, tenant, ["case.opened"])
    assert len((await client.get("/api/v1/tenants/me/webhooks", headers=tenant["admin"])).json()["webhooks"]) == 1


async def test_signed_callbacks_follow_committed_claims_and_decisions(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []

    async def handle(request):
        payload = json.loads(request.content)
        expected = hmac.new(SECRET.encode(), request.content, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(request.headers["X-ClaimShield-Signature"], expected)
        assert request.headers["X-ClaimShield-Event-Id"] == payload["event_id"]
        # A separate connection must already see the completed claim: no pre-commit callbacks.
        async with db_session.get_sessionmaker()() as db:
            row = (await db.execute(select(Claim).where(Claim.tenant_id == tenant["id"], Claim.claim_id == payload["claim_id"]))).scalar_one()
            assert row.processing_status == "processed"
        received.append(payload)
        return httpx.Response(200, json={"received": True})

    receiver(monkeypatch, handle)
    await ingest(client, tenant["key"], api_claim("WEB-A"))
    assert received[-1]["event"] == "claim.processed"
    assert received[-1]["claimshield_status"] == "cleared" and not received[-1]["fraud_flagged"]
    await ingest(client, tenant["key"], api_claim("WEB-B"))
    opened = next(p for p in received if p["claim_id"] == "WEB-B" and p["event"] == "case.opened")
    assert opened["fraud_flagged"] and opened["claimshield_status"] == "flagged"
    assert any(r["rule"] == "duplicate_billing" for r in opened["top_reasons"])
    assert opened["review_url"].endswith("/cases/" + opened["case_id"])
    assert opened["evidence_strength"] is not None and opened["member_harm_score"] is not None
    await ingest(client, tenant["key"], api_claim("WEB-C"))
    assert any(p["claim_id"] == "WEB-C" and p["event"] == "case.updated" for p in received)
    case_id = opened["case_id"]
    r = await client.post(f"/api/v1/cases/{case_id}/status?status=in_review", headers=tenant["investigator"])
    assert r.status_code == 200
    assert any(p["case_status"] == "in_review" and p["event"] == "case.updated" for p in received)
    r = await client.post(f"/api/v1/cases/{case_id}/decision", headers=tenant["investigator"], json={"decision": "false_positive", "notes": "Reviewed matching records; this is a synthetic test outcome."})
    assert r.status_code == 200, r.text
    decided = [p for p in received if p["event"] == "case.decided"]
    assert {p["claim_id"] for p in decided} == {"WEB-B", "WEB-C"}
    assert all(p["outcome"] == "false_positive" and p["claimshield_status"] == "decided" and p["decision_final"] and not p["fraud_flagged"] for p in decided)
    trail = (await client.get(f"/api/v1/cases/{case_id}/audit", headers=tenant["investigator"])).json()
    assert any(e["action"] == "case.decision" for e in trail["events"])


async def test_retry_bytes_and_event_id_stay_identical(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(503 if len(requests) < 3 else 200)

    receiver(monkeypatch, handle)
    delivery = webhooks.Delivery(URL, SECRET, {"event": "case.opened", "event_id": "evt-1", "tenant_id": "alpha", "claim_id": "C1"})
    assert await webhooks.dispatch(delivery)
    assert len(requests) == 3
    assert len({r.content for r in requests}) == 1
    assert all(r.headers["X-ClaimShield-Event-Id"] == "evt-1" for r in requests)
    assert requests[0].headers["X-ClaimShield-Signature"] == webhooks.sign(SECRET, requests[0].content)


async def test_failed_receiver_does_not_fail_claim_processing(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(500)

    receiver(monkeypatch, handle)
    await ingest(client, tenant["key"], api_claim("WEB-FAIL"))
    assert len(attempts) == 3
    assert (await client.get("/api/v1/claims/WEB-FAIL/status", headers=tenant["key"])).json()["status"] == "processed"


async def test_rollback_emits_nothing(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []
    receiver(monkeypatch, lambda request: received.append(request) or httpx.Response(200))
    async with db_session.get_sessionmaker()() as db:
        from app.models import Tenant

        t = await db.get(Tenant, tenant["id"])
        await claim_service.ingest_record(db, t, api_claim("WEB-ROLLBACK"), process=True)
        await db.rollback()
    assert not received
    assert (await client.get("/api/v1/claims/WEB-ROLLBACK", headers=tenant["key"])).status_code == 404


async def test_machine_evidence_is_opt_in_and_tenant_scoped(client, tenants):
    tenant = tenants["alpha"]
    await ingest(client, tenant["key"], api_claim("EVID-A"))
    await ingest(client, tenant["key"], api_claim("EVID-B"))
    case_id = (await client.get("/api/v1/cases", headers=tenant["investigator"])).json()["items"][0]["case_id"]
    path = f"/api/v1/integrations/cases/{case_id}/evidence"
    assert (await client.get(path, headers=tenant["key"])).status_code == 403
    await client.post("/api/v1/tenants/me/config", headers=tenant["admin"], json={"config": {"integration_read_access": True}})
    evidence = await client.get(path, headers=tenant["key"])
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["items"] and evidence.json()["network"] and evidence.json()["timeline"]
    assert (await client.get(path, headers={**tenant["key"], "X-Tenant-ID": "beta"})).status_code == 403
    await client.post("/api/v1/tenants/me/config", headers=tenants["beta"]["admin"], json={"config": {"integration_read_access": True}})
    # Public case IDs may repeat between tenants, but this tenant has no such case.
    assert (await client.get(path, headers=tenants["beta"]["key"])).status_code == 404
    assert (await client.get(f"/api/v1/cases/{case_id}/evidence", headers=tenant["key"])).status_code == 403
    assert (await client.post(f"/api/v1/cases/{case_id}/decision", headers=tenant["key"], json={"decision": "false_positive", "notes": "A machine must never record a reviewer outcome."})).status_code == 403
    result = (await client.get("/api/v1/integrations/claims/EVID-B/result", headers=tenant["key"])).json()
    assert result["case_id"] == case_id and result["claimshield_status"] == "flagged"
    await client.post(f"/api/v1/cases/{case_id}/decision", headers=tenant["investigator"], json={"decision": "confirm_fraud", "notes": "Synthetic duplicate verified for the test."})
    result = (await client.get("/api/v1/integrations/claims/EVID-B/result", headers=tenant["key"])).json()
    assert result["event"] == "case.decided" and result["outcome"] == "confirm_fraud"


async def test_coverage_review_is_not_reported_as_cleared(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []
    receiver(monkeypatch, lambda request: received.append(json.loads(request.content)) or httpx.Response(200))
    await ingest(client, tenant["key"], api_claim("WEB-COV", code="15780"))
    payload = received[-1]
    assert payload["event"] == "claim.processed" and payload["claimshield_status"] == "coverage_review"
    assert payload["risk_score"] is None and payload["review_required"] and not payload["fraud_flagged"]


async def test_model_server_environment_alias(monkeypatch):
    monkeypatch.delenv("ML_SERVER_URL", raising=False)
    monkeypatch.setenv("MODEL_SERVER_URL", "http://model-server:8001")
    assert Settings(_env_file=None).ml_server_url == "http://model-server:8001"
    monkeypatch.setenv("ML_SERVER_URL", "http://preferred-model-server:8001")
    assert Settings(_env_file=None).ml_server_url == "http://preferred-model-server:8001"


async def test_failed_detection_emits_error_result(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []
    receiver(monkeypatch, lambda request: received.append(json.loads(request.content)) or httpx.Response(200))

    async def fail(_pipeline, _claim):
        raise RuntimeError("Synthetic test failure")

    monkeypatch.setattr(claim_service.DetectionPipeline, "run", fail)
    r = await client.post("/api/v1/claims", headers=tenant["key"], json=api_claim("WEB-DETECTION-FAIL"))
    assert r.status_code == 202
    assert len(received) == 1
    payload = received[0]
    assert payload["event"] == "claim.failed" and payload["claimshield_status"] == "error"
    assert payload["processing_status"] == "failed" and payload["error"]
    assert not payload["fraud_flagged"]


async def test_nonfinal_decision_keeps_claim_in_review(client, tenants, monkeypatch):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []
    receiver(monkeypatch, lambda request: received.append(json.loads(request.content)) or httpx.Response(200))
    await ingest(client, tenant["key"], api_claim("WEB-INFO-A"))
    await ingest(client, tenant["key"], api_claim("WEB-INFO-B"))
    case_id = next(p["case_id"] for p in received if p["event"] == "case.opened")
    r = await client.post(f"/api/v1/cases/{case_id}/decision", headers=tenant["investigator"], json={"decision": "needs_info", "notes": "Need the synthetic supporting records to finish review."})
    assert r.status_code == 200
    payload = received[-1]
    assert payload["event"] == "case.decided" and payload["outcome"] == "needs_info"
    assert not payload["decision_final"] and payload["claimshield_status"] == "flagged"
    assert payload["case_status"] == "needs_info"


@pytest.mark.parametrize("share", [False, True, "true"])
@pytest.mark.parametrize("outcome", ["false_positive", "needs_info"])
async def test_decision_details_require_tenant_approval(client, tenants, monkeypatch, share, outcome):
    tenant = tenants["alpha"]
    await register(client, tenant)
    received = []
    receiver(monkeypatch, lambda request: received.append(json.loads(request.content)) or httpx.Response(200))
    r = await client.post("/api/v1/tenants/me/config", headers=tenant["admin"], json={"config": {"integration_read_access": True}})
    assert r.status_code == 200
    await ingest(client, tenant["key"], api_claim("DETAIL-A"))
    await ingest(client, tenant["key"], api_claim("DETAIL-B"))
    opened = next(p for p in received if p["event"] == "case.opened")
    assert opened["notes"] is None and opened["decided_by"] is None
    path = "/api/v1/integrations/claims/DETAIL-B/result"
    initial = (await client.get(path, headers=tenant["key"])).json()
    assert initial["notes"] is None and initial["decided_by"] is None
    notes = "Reviewed supporting records.\nRequest invoice clarification — synthetic test."
    r = await client.post(f"/api/v1/cases/{opened['case_id']}/decision", headers=tenant["investigator"], json={"decision": outcome, "notes": notes})
    assert r.status_code == 200, r.text
    blocked = received[-1]
    assert blocked["event"] == "case.decided"
    assert blocked["notes"] is None and blocked["decided_by"] is None
    before = (await client.get(path, headers=tenant["key"])).json()
    assert before["notes"] is None and before["decided_by"] is None
    r = await client.post("/api/v1/tenants/me/config", headers=tenant["admin"], json={"config": {"integration_share_decision_details": share}})
    assert r.status_code == 200
    # Polling can expose existing decisions only after explicit opt-in.
    approved = (await client.get(path, headers=tenant["key"])).json()
    expected_notes = notes if share is True else None
    expected_reviewer = "AUD-007" if share is True else None
    assert approved["notes"] == expected_notes and approved["decided_by"] == expected_reviewer
    unchanged = set(before) - {"notes", "decided_by", "event_id", "occurred_at"}
    assert {k: before[k] for k in unchanged} == {k: approved[k] for k in unchanged}
    received.clear()
    r = await client.post(f"/api/v1/cases/{opened['case_id']}/decision", headers=tenant["admin"], json={"decision": outcome, "notes": notes})
    assert r.status_code == 200, r.text
    decided = [p for p in received if p["event"] == "case.decided"]
    assert decided
    assert all(p["notes"] == expected_notes and p["decided_by"] == ("ADM-002" if share is True else None) for p in decided)
    latest = (await client.get(path, headers=tenant["key"])).json()
    assert latest["notes"] == expected_notes
    assert latest["decided_by"] == ("ADM-002" if share is True else None)
    await client.post("/api/v1/tenants/me/config", headers=tenant["admin"], json={"config": {"integration_share_decision_details": False}})
    disabled = (await client.get(path, headers=tenant["key"])).json()
    assert disabled["notes"] is None and disabled["decided_by"] is None
