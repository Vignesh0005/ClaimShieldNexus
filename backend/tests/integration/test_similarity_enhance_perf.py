"""Similar-case search (P5), optional LLM brief enhancement (P6) and performance metrics (P7)."""
import pytest

from app.core import perf
from app.detection.ml.tfidf_index import TfidfIndex
from app.explainability import copilot
from app.explainability.copilot import FALLBACK_MODEL, enhance_brief, enhancement_packet, template_enhancement, validate_enhancement

# ---------- similarity ----------


def test_tfidf_index_ranks_shared_codes_first_and_needs_no_torch():
    import sys

    index = TfidfIndex().build(
        ["A", "B", "C"],
        ["procedures 99215 93000 diagnoses I25.10 signals upcoding duplicate_billing", "procedures 82040 82247 82310 diagnoses M54.5 signals unbundling", "procedures 99213 diagnoses J06.9 signals"],
        [{"case_id": "CS-1"}, {"case_id": "CS-2"}, {"case_id": "CS-3"}],
    )
    hits = index.search("procedures 99215 diagnoses I25.10 signals upcoding", k=2)
    assert hits[0]["claim_id"] == "A" and hits[0]["case_id"] == "CS-1" and hits[0]["similarity"] > 0.5
    assert all(h["claim_id"] != "A" for h in index.search("procedures 99215 signals upcoding", exclude={"A"}))
    assert TfidfIndex().build([], []).search("anything") == [] and index.search("   ") == []
    assert "torch" not in sys.modules and "faiss" not in sys.modules


@pytest.mark.asyncio
async def test_new_claim_retrieves_the_planted_historical_claims(client, tenants):
    inv = tenants["alpha"]["investigator"]
    first = (await client.post("/api/v1/inject", headers=inv, json={"scheme": "upcoding"})).json()
    planted_tag = first["claim_id"].split("-")[2]
    second = (await client.post("/api/v1/inject", headers=inv, json={"scheme": "upcoding"})).json()
    assert second["claim_id"].split("-")[2] != planted_tag

    # The second scheme's claim was scored after the first scheme's claims were on file.
    similar = second["similar_cases"]
    assert similar and all(s["claim_id"].startswith(f"CLM-INJ-{planted_tag}") for s in similar)
    assert similar[0]["similarity"] >= 0.35 and similar[0]["case_id"] == first["case_id"] and similar[0]["outcome"] == "not yet reviewed"
    assert "similarity" not in second["caught_by"]  # context, not a detector that flagged it

    # Stored as a signal, shown in the evidence trail and the brief, and absent from the score.
    flags = (await client.get(f"/api/v1/claims/{second['claim_id']}/flags", headers=inv)).json()["flags"]
    sim = next(f for f in flags if f["detector"] == "similarity")
    assert sim["pattern"] == "similar_cases" and "Not used in the risk score" in sim["evidence"]["note"]
    evidence = (await client.get(f"/api/v1/cases/{second['case_id']}/evidence", headers=inv)).json()
    assert any(i["detector"] == "similarity" for i in evidence["items"])
    detail = (await client.get(f"/api/v1/cases/{second['case_id']}", headers=inv)).json()
    assert detail["similar_cases"] and all(s["case_id"] == first["case_id"] for s in detail["similar_cases"])
    brief = (await client.post(f"/api/v1/briefs/{second['case_id']}/generate", headers=inv)).json()
    assert "Most similar earlier claims" in brief["markdown"]
    what_if = (await client.get(f"/api/v1/cases/{second['case_id']}/counterfactual", headers=inv)).json()
    assert all(s["removes"] != "similar_cases" for s in what_if["scenarios"])

    # POST /similar by text and by claim
    by_text = (await client.post("/api/v1/similar", headers=inv, json={"claim_text": "procedures 99215 signals upcoding", "k": 3})).json()
    assert by_text["method"] == "tfidf_cosine" and len(by_text["similar_cases"]) == 3 and by_text["corpus_size"] >= 2
    by_claim = (await client.post("/api/v1/similar", headers=inv, json={"claim_id": second["claim_id"], "k": 5})).json()
    assert by_claim["similar_cases"] and all(s["claim_id"] != second["claim_id"] for s in by_claim["similar_cases"])
    assert (await client.post("/api/v1/similar", headers=inv, json={})).status_code == 422
    # Another tenant's corpus is empty: nothing leaks across tenants.
    other = (await client.post("/api/v1/similar", headers=tenants["beta"]["investigator"], json={"claim_text": "procedures 99215 signals upcoding"})).json()
    assert other["similar_cases"] == [] and other["corpus_size"] == 0


@pytest.mark.asyncio
async def test_confirmed_only_corpus_is_empty_until_a_reviewer_confirms(client, tenants):
    t = tenants["alpha"]
    await client.post("/api/v1/tenants/me/config", headers=t["admin"], json={"config": {"similarity": {"corpus": "confirmed_only"}}})
    first = (await client.post("/api/v1/inject", headers=t["investigator"], json={"scheme": "duplicate_billing"})).json()
    empty = (await client.post("/api/v1/similar", headers=t["investigator"], json={"claim_text": "procedures 99215 signals duplicate_billing"})).json()
    assert empty["corpus"] == "confirmed_only" and empty["similar_cases"] == []
    body = {"decision": "confirm_fraud", "notes": "Duplicate confirmed against the original claim.", "next_action": "escalate_tier2"}
    await client.post(f"/api/v1/cases/{first['case_id']}/decision", headers=t["investigator"], json=body)
    second = (await client.post("/api/v1/inject", headers=t["investigator"], json={"scheme": "duplicate_billing"})).json()
    assert second["similar_cases"] and second["similar_cases"][0]["outcome"] == "confirmed by a reviewer"


# ---------- LLM enhancement ----------

BRIEF = {
    "case_id": "CS-1", "provider": "Dr. X (PRV-1)", "risk_score": 0.83, "severity": "critical", "evidence_strength": 0.74, "member_harm_score": 0.4,
    "potential_dollars": 800.0, "members_affected": 1, "suggested_next_action": "escalate_tier2", "model_version": "x",
    "evidence": [{"detector": "rule", "name": "duplicate_billing", "label": "Duplicate billing", "score": 0.98, "score_label": "confidence", "detail": "Matches CLM-A on member_id, provider_id", "plain": "A claim looks the same as one already submitted.", "source": "claim CLM-B, signal SIG-001"}],
    "timeline": [{"date": "2025-01-08", "title": "Duplicate billing first detected"}],
    "network": {"text": "No referral loop detected.", "providers": 1, "members": 1},
    "limitations": ["No prior investigation outcome for PRV-1"],
    "clears": ["If the second claim is a corrected resubmission."],
}
WHAT_IF = ["If the second claim is shown to be a corrected resubmission -> risk drops to 0.11"]


class FakeLLM:
    configured, model = True, "gpt-oss:120b"

    def __init__(self, response):
        self.response = response
        self.prompt = None

    async def generate(self, prompt):
        self.prompt = prompt
        return self.response


def good():
    return {
        "narrative": [{"text": "A duplicate billing finding with confidence 0.98 may indicate a repeated submission and requires review.", "sources": ["signal.duplicate_billing"]}, {"text": "The risk score is 0.83.", "sources": ["case.risk_score"]}],
        "counterfactuals": [{"text": "If the second claim is a corrected resubmission, risk drops to 0.11.", "sources": ["counterfactual.0"]}],
        "plain_language": [{"text": "One claim looks the same as an earlier one. Someone should check why.", "sources": ["signal.duplicate_billing"]}],
        "limitations": ["ignored: limitations always come from the evidence"],
    }


@pytest.mark.asyncio
async def test_valid_llm_output_is_accepted_and_every_line_cites_a_source():
    llm = FakeLLM(good())
    out = await enhance_brief(BRIEF, WHAT_IF, client=llm)
    assert out["model"] == "gpt-oss:120b" and out["fallback_reason"] is None
    allowed = set(enhancement_packet(BRIEF, WHAT_IF)["sources"])
    for section in ("narrative", "counterfactuals", "plain_language"):
        assert out[section] and all(line["sources"] and set(line["sources"]) <= allowed for line in out[section])
    assert out["limitations"] == BRIEF["limitations"]  # the model cannot drop or rewrite limitations
    for rule in ("Use ONLY the facts", "NEVER say or imply that anyone committed fraud", "limitations", "Counterfactuals", "plain-language", "requires review"):
        assert rule in llm.prompt, rule
    assert "CLM-B" not in llm.prompt or "MBR-" not in llm.prompt  # no member identifiers are sent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda d: d["narrative"].append({"text": "The provider also billed 47 further duplicates worth 12,400.", "sources": ["signal.duplicate_billing"]}), "number that is not in the evidence"),
        (lambda d: d["narrative"].__setitem__(0, {"text": "A finding requires review.", "sources": []}), "cited no source"),
        (lambda d: d["plain_language"].__setitem__(0, {"text": "Something requires review.", "sources": ["signal.made_up"]}), "unknown source"),
        (lambda d: d["narrative"].__setitem__(0, {"text": "The provider committed fraud.", "sources": ["signal.duplicate_billing"]}), "accusatory wording"),
        (lambda d: d.pop("counterfactuals"), "missing or empty"),
    ],
)
async def test_llm_output_that_adds_facts_or_lacks_citations_is_discarded(mutate, reason):
    data = good()
    mutate(data)
    assert reason in validate_enhancement(data, enhancement_packet(BRIEF, WHAT_IF))
    out = await enhance_brief(BRIEF, WHAT_IF, client=FakeLLM(data))
    assert out["model"] == FALLBACK_MODEL and reason in out["fallback_reason"]


def test_template_fallback_also_cites_every_line():
    out = template_enhancement(BRIEF, WHAT_IF, "test")
    allowed = set(enhancement_packet(BRIEF, WHAT_IF)["sources"])
    assert all(line["sources"] and set(line["sources"]) <= allowed for s in ("narrative", "counterfactuals", "plain_language") for line in out[s])
    assert validate_enhancement(out, enhancement_packet(BRIEF, WHAT_IF)) is None and not copilot.find_banned(str(out))


@pytest.mark.asyncio
async def test_enhance_endpoint_keeps_the_template_and_stores_typed_briefs(client, tenants, monkeypatch):
    t = tenants["alpha"]
    inv = t["investigator"]
    case_id = (await client.post("/api/v1/inject", headers=inv, json={"scheme": "duplicate_billing"})).json()["case_id"]

    template = (await client.post(f"/api/v1/briefs/{case_id}/generate", headers=inv)).json()
    assert template["brief_type"] == "technical_template" and "enhancement" not in template

    # No API key configured: the template is still returned, with a cited fallback layer.
    out = (await client.post(f"/api/v1/briefs/{case_id}/enhance", headers=inv, json={"brief_type": "technical"})).json()
    assert out["enhancement"]["model"] == FALLBACK_MODEL and "not configured" in out["enhancement"]["fallback_reason"]
    assert out["template_stored_as"] == "technical_template" and out["enhanced_stored_as"] is None
    assert out["content"]["evidence"] == template["content"]["evidence"] and all(l["sources"] for l in out["enhancement"]["narrative"])
    assert (await client.get(f"/api/v1/briefs/{case_id}?type=technical_llm", headers=inv)).status_code == 404

    # With an LLM whose output passes validation, the enhanced brief is stored as technical_llm.
    async def fake_enhance(brief, sentences, client=None):
        packet = enhancement_packet(brief, sentences)
        cite = [f"signal.{brief['evidence'][0]['name']}"]
        return {"model": "gpt-oss:120b", "fallback_reason": None, "narrative": [{"text": "A finding requires review.", "sources": cite}], "counterfactuals": [{"text": sentences[0], "sources": ["counterfactual.0"]}], "plain_language": [{"text": "Someone should check this.", "sources": cite}], "limitations": packet["limitations"]}

    monkeypatch.setattr(copilot, "enhance_brief", fake_enhance)
    out = (await client.post(f"/api/v1/briefs/{case_id}/enhance", headers=inv, json={"brief_type": "plain"})).json()
    assert out["enhancement"]["model"] == "gpt-oss:120b" and out["enhanced_stored_as"] == "plain_llm" and "# Enhancement (gpt-oss:120b)" in out["markdown"]
    stored = (await client.get(f"/api/v1/briefs/{case_id}?type=plain_llm", headers=inv)).json()
    assert stored["brief_type"] == "plain_llm" and stored["content"]["enhancement"]["narrative"][0]["sources"]
    assert (await client.get(f"/api/v1/briefs/{case_id}?type=plain", headers=inv)).json()["brief_type"] == "plain_template"

    trail = [e["action"] for e in (await client.get(f"/api/v1/audit/{case_id}", headers=inv)).json()["events"]]
    assert trail.count("brief.enhanced") == 2
    assert (await client.post(f"/api/v1/briefs/{case_id}/enhance", headers=t["viewer"])).status_code == 403


# ---------- performance ----------


def test_percentiles():
    assert perf.percentiles([float(i) for i in range(1, 101)]) == {"p50": 50.5, "p95": 95.0, "p99": 99.0, "mean": 50.5}
    assert perf.percentiles([]) == {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0}


@pytest.mark.asyncio
async def test_performance_endpoint_reports_only_what_was_measured(client, tenants):
    perf.reset()
    h = tenants["alpha"]["viewer"]
    before = (await client.get("/api/v1/health/performance", headers=h)).json()
    assert before["samples"] == 0 and before["latency_ms"] is None and before["throughput"]["claims_last_minute"] == 0
    assert "in-process" in before["mode"] and "sqlite" in before["mode"]
    await client.post("/api/v1/inject", headers=tenants["alpha"]["investigator"], json={"scheme": "impossible_day"})
    after = (await client.get("/api/v1/health/performance", headers=h)).json()
    assert after["samples"] == 18 and after["throughput"]["claims_last_minute"] == 18
    assert 0 < after["latency_ms"]["p50"] <= after["latency_ms"]["p95"] <= after["latency_ms"]["p99"]
    assert after["series"] and after["series"][-1]["claims"] == 18 and after["backlog"] == 0
    assert (await client.get("/api/v1/health/performance")).status_code == 401
