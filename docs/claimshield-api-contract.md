# ClaimShield API contract for the mock insurer

Mock system. Synthetic data only.

This document describes the ClaimShield integration points. The mock team owns its existing
claim rows, receiver, status UI, evidence modal and live updates. Existing ClaimShield
endpoints, detection rules, database schemas and SIU screens are preserved.

## Addresses and authentication

| Service | Local address |
| --- | --- |
| ClaimShield API | http://localhost:8000 |
| ClaimShield SIU | http://localhost:3000 |
| Mock backend | http://localhost:3002 |
| Mock frontend | http://localhost:3001 |

The demo tenant identifier is the existing tenant **slug**, `demo_tenant`. Its primary key
remains a generated UUID, printed by the seed script. No UUID schema is converted to text.

Mock **server-side** requests use:

```http
X-API-Key: demo_api_key_12345
X-Tenant-ID: demo_tenant
Content-Type: application/json
```

Keep the API key and webhook secret out of browser code and NEXT_PUBLIC variables. An API
key selects exactly one tenant. A tenant header cannot grant access to another tenant.
Reviewer decisions require an authenticated investigator/admin user.

## Endpoints

| Method | Path | Authentication | Purpose |
| --- | --- | --- | --- |
| GET | /health | None | Liveness |
| GET | /health/ready | None | Readiness |
| POST | /api/v1/claims | API key | Accept claim, return 202 |
| GET | /api/v1/claims/{claim_id} | API key | Existing claim detail |
| GET | /api/v1/claims/{claim_id}/status | API key | Processing state |
| GET | /api/v1/claims/{claim_id}/flags | API key | Detector findings |
| GET | /api/v1/integrations/claims/{claim_id}/result | API key + tenant opt-in | Complete result, case link and latest decision; polling/recovery |
| GET | /api/v1/integrations/cases/{case_id} | API key + tenant opt-in | Case details |
| GET | /api/v1/integrations/cases/{case_id}/evidence | API key + tenant opt-in | Evidence, graph and timeline |
| POST | /api/v1/tenants/{tenant_id}/webhooks | Admin bearer | Register/replace callback |
| GET | /api/v1/tenants/{tenant_id}/webhooks | Admin bearer | Inspect registry without secrets |
| GET | /api/v1/cases/{case_id} | User bearer | Existing SIU detail |
| GET | /api/v1/cases/{case_id}/evidence | User bearer | Existing SIU evidence |
| POST | /api/v1/cases/{case_id}/decision | Investigator/admin bearer | Existing human decision |

**Required mock-side adjustment:** the existing /cases/{id}/evidence endpoint rejects API
keys. Proxy evidence through the added **/integrations/cases/{id}/evidence** endpoint.
This leaves existing permissions intact and grants machines no decision capability.
Machine reads require config.integration_read_access=true, enabled by the demo seed.
Other tenants must be explicitly opted in by an admin using the existing config endpoint.

## Submit a claim

Send from the mock backend using async httpx with a ten-second timeout:

```json
{
  "claim_id": "MOCK-CLAIM-001",
  "member_id": "MOCK-MEMBER-001",
  "provider_id": "MOCK-PROVIDER-001",
  "facility_id": "MOCK-FACILITY-001",
  "service_date": "2026-10-08",
  "claim_type": "professional",
  "total_billed": 120,
  "total_paid": 108,
  "diagnosis_codes": ["M54.5"],
  "plan_type": "family_floater",
  "policy_start_date": "2020-01-01",
  "service_location": "IN",
  "pre_auth_number": null,
  "lines": [{
    "line_id": "MOCK-CLAIM-001-L1",
    "cpt_code": "99213",
    "modifiers": [],
    "units": 1,
    "billed_amount": 120,
    "paid_amount": 108,
    "service_date": "2026-10-08",
    "diagnosis_pointer": [1]
  }]
}
```

Required fields: claim_id, member_id, provider_id, service_date, total_billed. Dates use
YYYY-MM-DD; amounts are nonnegative. Line code field is **cpt_code**, not procedure_code.
The example's policy/location values match the existing illustrative India coverage rules.
Optional inputs include member_age, documents_provided and attributes. Consult current
OpenAPI and app/schemas/claim.py for complete validation rules.

HTTP 202 response:

```json
{
  "claim_id": "MOCK-CLAIM-001",
  "status": "processing",
  "job_id": "job_example123",
  "estimated_completion_seconds": 5,
  "duplicate": false
}
```

Store the job ID on the same mock row and show processing. Acceptance is not the final
result. Identical resubmissions return the same job with duplicate=true and do not rerun
detection or produce another webhook. An ID reused with changed content returns 409.

For a deterministic strong-rule demonstration, submit two distinct claim IDs with the same
member, provider, service date and CPT service; give each a unique line ID. The second can
trigger the existing duplicate-billing rule and tier-2 routing even below composite risk 0.70.
Ordinary claims are not guaranteed to flag or finish within two seconds.

## Register a webhook

POST /api/v1/tenants/demo_tenant/webhooks with an authenticated admin bearer:

```json
{
  "id": "mock-insurer",
  "url": "http://localhost:3002/api/webhooks/claimshield",
  "events": ["case.opened", "case.updated", "case.decided", "claim.processed", "claim.failed"],
  "secret": "demo_webhook_secret",
  "enabled": true
}
```

Repeated registration ID replaces that entry, allowing URL/secret rotation or disabled
delivery. ID defaults to mock-insurer; events default to all five. Secrets must have at least
16 characters. Only HTTP(S) destinations without credentials/fragments are accepted;
production requires HTTPS. Restrict destinations through trusted network egress policies.

Registrations are stored in existing tenants.config under **outbound_webhook_secrets**,
keyed by ID. Existing config readers redact that top-level key; registry responses omit
secrets. This is separate from the existing inbound-ingestion webhook_secret setting.
No table or column was added. Registry management is admin-only.

## Callback events and payload

| Event | Trigger | Mock handling |
| --- | --- | --- |
| case.opened | Completed detection opens a case | Flagged risk card and review link |
| case.updated | A processed claim joins a case; case status/assignment changes | Refresh the corresponding claim |
| case.decided | Human decision recorded | Use outcome and decision_final |
| claim.processed | Completed detection with no case | Cleared or coverage_review |
| claim.failed | Detection failed | Show error and stop processing |

Subscribe to all five events. Without claim.processed/claim.failed, ordinary or failed claims
can remain stuck in processing. Coverage failure means **coverage_review**, not fraud or
clearance. Render a review banner or map it to the mock's pending-review state with
review_required=true; risk is null.

Illustrative callback (actual scores come from persisted detection results):

```json
{
  "event": "case.opened",
  "event_id": "94808a8c-c611-4c4b-b53b-360a46f5d154",
  "schema_version": "1.0",
  "tenant_id": "demo_tenant",
  "tenant_uuid": "6c6419d7-8299-4a57-8d4e-cab8cff33b5d",
  "occurred_at": "2026-10-08T12:00:00+00:00",
  "claim_id": "MOCK-CLAIM-002",
  "job_id": "job_example456",
  "case_id": "CS-2026-0001",
  "risk_score": 0.45,
  "severity": "medium",
  "evidence_strength": 0.6,
  "member_harm_score": 0.1,
  "two_axis_quadrant": "siu",
  "fraud_flagged": true,
  "claimshield_status": "flagged",
  "processing_status": "processed",
  "coverage_status": "COVERABLE",
  "review_required": false,
  "top_reasons": [{"rule": "duplicate_billing", "confidence": 0.98, "detector": "rule"}],
  "review_url": "http://localhost:3000/cases/CS-2026-0001",
  "case_status": "pending_review",
  "outcome": null,
  "decision_id": null,
  "notes": null,
  "decided_by": null,
  "decision_final": false,
  "error": null,
  "disclaimer": "Mock system. Synthetic data only. A flag is a prompt for human review, not a fraud determination."
}
```

Scores, severity, quadrant, case_id and review_url may be null. Do not format null scores
with toFixed. Severity uses low/medium/high/critical. A strong-rule flag does not imply a
critical composite score. fraud_flagged means human investigation, never automatic denial.

For case.decided:
- outcome is confirm_fraud, false_positive, needs_info or reassign.
- confirm_fraud/false_positive have decision_final=true and claimshield_status=decided.
- needs_info/reassign remain flagged for continued review.
- A false-positive decision sets fraud_flagged=false and retains original scores.
- One callback is emitted for **every linked claim** in a provider case.
- Do not map every decision to flagged/cleared based only on fraud_flagged.

## HMAC and receiver requirements

```http
Content-Type: application/json
X-ClaimShield-Signature: <lowercase hexadecimal HMAC-SHA256>
X-ClaimShield-Event-Id: <body event_id>
```

Verify the exact raw body before parsing JSON:

```python
import hashlib
import hmac
import json

raw_body = await request.body()
expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
provided = request.headers.get("X-ClaimShield-Signature", "")
if not hmac.compare_digest(provided, expected):
    raise HTTPException(status_code=401, detail="Invalid webhook signature")
payload = json.loads(raw_body)
```

There is no sha256= prefix. Do not reserialize before verification. Signed compact UTF-8
bytes are sent unchanged; retry attempts keep identical body, signature and event ID.
Deduplicate event_id, verify tenant_id and match the existing row by tenant/claim ID.
Persist the receipt and row update together before returning 2xx and broadcasting live UI
updates. Unknown claim IDs should be logged and return a failure rather than silently
discarding the event. Return 401 for invalid signatures.

Store scores, severity, case_id, top_reasons, review_url, evidence_strength, member_harm_score,
quadrant and outcome as supported by the mock schema. Do not insert another claim row.
Use occurred_at/current state to prevent older concurrent callbacks overwriting a final
decision. Production replay protection/durable delivery require additional design.

Delivery starts **after database commit**. httpx timeout is ten seconds per attempt; three
attempts use 0.5s and 1s backoff. Non-2xx responses, timeouts and connection errors retry;
redirects are not followed. Logs include event/claim identifiers, attempt and response
status without secrets or raw claim bodies. Failed delivery never rolls back detection or
a committed reviewer decision. There is no durable outbox: reconcile missed results.

## Evidence modal and SIU link

Mock backend proxies:
GET /api/v1/integrations/cases/{case_id}/evidence using the tenant API key.

Response preserves the existing evidence structure and adds network and timeline:

```json
{
  "case_id": "CS-2026-0001",
  "model_warning": null,
  "items": [{
    "signal_id": "SIG-001",
    "detector": "rule",
    "name": "duplicate_billing",
    "title": "Duplicate billing",
    "summary": "Verify against the original record.",
    "score_label": "confidence",
    "score": 0.98,
    "severity": "high",
    "evidence": {"matched_claim_id": "MOCK-CLAIM-001"},
    "source": {"claim_id": "MOCK-CLAIM-002", "fields": ["member_id", "provider_id", "service_date"]},
    "occurrences": 1
  }],
  "limitations": [],
  "network": {"nodes": [], "edges": []},
  "timeline": []
}
```

Render actual evidence/source fields, graph, timeline, model warning and limitations in the
existing mock modal. Reads are tenant-scoped and audited.

Open the provided review_url in a new tab. The existing SIU route is **/cases/{case_id}**,
not /siu/cases/{case_id}. Complete normal login, then select **Mock Insurer Demo** in the
existing tenant switcher before opening the case; demo admins can switch tenants.
No auto-login, automatic tenant selection or SIU screen changes were added. Case IDs are
tenant-scoped and may repeat in different tenants.

## Errors and reconciliation

Typical failures keep the existing API error structure:

```json
{"error":{"code":"FORBIDDEN","message":"Access is not allowed.","details":{}}}
```

401: credentials; 403: permissions/tenant/opt-in; 404: tenant-scoped resource not found;
409: ID/content conflict; 422: validation; 429: rate limit. The mock should preserve HTTP
status and show friendly messages, without logging keys, tokens, secrets or raw claims.

Poll GET /api/v1/integrations/claims/{claim_id}/result every two seconds while processing
if callbacks are unavailable, with a finite timeout/backoff. It supplies case_id, scores,
claimshield_status, review_url and latest decision using the callback shape. Reading does
not emit another webhook. Its event_id is a fresh result snapshot ID, not a replay ID.
The existing /claims/{claim_id}/status reports processed, not flagged/cleared, and has no
case link. Identical resubmissions should recover via this result endpoint.

## Reviewer notes and identity sharing

`case.decided` callbacks and the claim result snapshot include `notes` and
`decided_by`. Existing fields retain their meanings. Both new fields are null
without a decision, or while sharing is disabled.

Internal SIU notes are free text. Confirm that these notes and reviewer identity
are acceptable to share with this tenant before enabling sharing. An admin can
then POST `/api/v1/tenants/{tenant_id}/config` with:

```json
{"config":{"integration_share_decision_details":true}}
```

This tenant setting defaults to disabled and requires the literal JSON boolean
true. Set it to false to disable future sharing. With approval enabled, `notes`
is the recorded decision notes and `decided_by` is the recorded reviewer login
ID (for example `ADM-002`), falling back to the stored user UUID if no login ID
is recorded. Missing recorded values remain null. The latest recorded decision
is used for polling, including non-final `needs_info` and `reassign` decisions.
Enabling sharing also exposes existing decisions through polling; it does not
replay past callbacks. Disabling does not retract information already delivered.
The existing admin-only configuration endpoint audits the setting change.
