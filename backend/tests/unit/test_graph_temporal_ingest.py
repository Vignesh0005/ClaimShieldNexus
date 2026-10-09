import hashlib
import hmac
from datetime import date, timedelta

import pytest

from app.core.exceptions import Unauthorized, ValidationFailed
from app.detection.graph.builder import ClaimEdge, ReferralEdge, build_bipartite_graph, build_referral_graph
from app.detection.graph.engine import GraphEngine
from app.detection.graph.referral_loops import find_loops
from app.detection.graph.shared_address import shared_address_groups
from app.detection.graph.time_travel import replay
from app.detection.ml.remote_client import CircuitBreaker
from app.detection.temporal.forecast import forecast_provider, linear_trend
from app.detection.temporal.spikes import billing_spike
from app.ingestion.adapters.csv_adapter import CSVAdapter
from app.ingestion.adapters.fhir_adapter import FHIRAdapter
from app.ingestion.adapters.webhook_adapter import WebhookAdapter
from app.ingestion.field_mapping import apply_mapping, validate_mapping
from app.ingestion.idempotency import content_hash
from app.ingestion.normalizer import normalize_icd
from app.ingestion.validator import validate_claim
from tests.conftest import TODAY, api_claim, make_claim, make_ctx

D = date(2025, 1, 1)


def ring(n=4, repeats=3, start=D):
    names = [f"P{i}" for i in range(n)]
    return [ReferralEdge(names[i], names[(i + 1) % n], start + timedelta(days=r)) for r in range(repeats) for i in range(n)]


def test_loop_found_once_and_one_off_referrals_ignored():
    assert find_loops(build_referral_graph(ring())) == [["P0", "P1", "P2", "P3"]]
    assert find_loops(build_referral_graph(ring(repeats=1))) == []  # single referrals around a circle are ordinary
    assert find_loops(build_referral_graph([ReferralEdge("A", "B", D)] * 5 + [ReferralEdge("B", "A", D)] * 5)) == []  # pairs are the rule's job


def test_graph_engine_signal_carries_loop_evidence():
    engine = GraphEngine()
    loop = engine.find_loop("P1", ring(n=5, repeats=4))
    assert loop and len(loop.providers) == 5 and loop.referrals == 20
    signal = engine.signals("P1", loop, None, {}, {p: "OWN-1" for p in loop.providers})[0]
    assert signal.detector == "graph" and signal.evidence["common_owner"] == "OWN-1" and 0.8 <= signal.score <= 0.95
    assert engine.find_loop("ZZ", ring()) is None


def test_time_travel_shows_when_the_loop_closed():
    edges = [ReferralEdge("A", "B", date(2025, 1, 5)), ReferralEdge("A", "B", date(2025, 1, 6)), ReferralEdge("B", "C", date(2025, 2, 5)), ReferralEdge("B", "C", date(2025, 2, 6)), ReferralEdge("C", "A", date(2025, 3, 5)), ReferralEdge("C", "A", date(2025, 3, 6))]
    frames = replay([], edges, date(2025, 1, 1), date(2025, 3, 31))
    assert [f["referral_loops"] for f in frames] == [0, 0, 1]


def test_bipartite_graph_and_shared_addresses():
    g = build_bipartite_graph([ClaimEdge("P1", "M1", "F1", D, 100), ClaimEdge("P1", "M1", "F1", D, 50)], [ReferralEdge("P1", "P2", D)])
    assert g.nodes["P1"]["amount"] == 150 and g["M1"]["P1"]["weight"] == 2 and g["P1"]["P2"]["type"] == "referral"
    groups = shared_address_groups({"A": "12 Harbour Road, Suite 4", "B": "12 harbour rd ste 4", "C": "12 Harbour Rd., Ste 4", "D": "9 Other St"})
    assert groups and groups[0]["providers"] == ["A", "B", "C"]


def test_billing_spike_needs_history_and_a_real_jump():
    steady = [make_claim(f"H{i}", member=f"M{i}", day=TODAY - timedelta(days=35 + i), billed=100) for i in range(50)]
    burst = [make_claim(f"B{i}", member=f"M{i}", day=TODAY - timedelta(days=i % 6), billed=400) for i in range(40)]
    s = billing_spike(make_ctx(make_claim("C1"), provider_history=steady + burst))
    assert s and s.detector == "temporal" and s.evidence["change_30d_pct"] > 100
    assert billing_spike(make_ctx(make_claim("C1"), provider_history=steady)) is None
    assert billing_spike(make_ctx(make_claim("C1"), provider_history=burst)) is None  # a new provider has no baseline


def test_forecast_follows_trend():
    assert linear_trend([1, 2, 3, 4])[0] == pytest.approx(1.0)
    rising = forecast_provider([100 * i for i in range(1, 14)], current_risk=0.8)
    flat = forecast_provider([500.0] * 13, current_risk=0.1)
    assert [f["horizon_days"] for f in rising] == [30, 60, 90]
    assert rising[0]["risk_probability"] > flat[0]["risk_probability"] and rising[2]["predicted_dollars"] > rising[0]["predicted_dollars"]


def test_circuit_breaker_opens_and_recovers():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
    cb.record_failure()
    assert not cb.is_open()
    cb.record_failure()
    assert cb.opened_at is not None and not cb.is_open()  # zero timeout: straight to a trial call
    cb.recovery_timeout = 60
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open() and cb.failures == 0


# ---------- ingestion ----------

MAPPING = {"clm_id": "claim_id", "mbr_no": "member_id", "prv_id": "provider_id", "svc_dt": "service_date", "cpt_cd": "procedure_code", "icd_cd": "diagnosis_code", "billed_amt": "billed_amount"}


def test_field_mapping_and_required_fields():
    assert apply_mapping({"clm_id": "C1", "cpt_cd": "99213", "other": 1}, MAPPING) == {"claim_id": "C1", "cpt_code": "99213", "other": 1}
    assert validate_mapping(MAPPING) == []
    assert validate_mapping({"clm_id": "claim_id"}) == ["billed_amount", "cpt_code", "member_id", "provider_id", "service_date"]


def test_csv_rows_group_into_claims():
    text = "clm_id;mbr_no;prv_id;svc_dt;cpt_cd;icd_cd;billed_amt\nC1;M1;P1;01/08/2025;99213;J069;$120.00\nC1;M1;P1;01/08/2025;85025;J069;30\nC2;M2;P1;2025-01-09;99214;I2510;180\n"
    claims = [validate_claim(c) for c in CSVAdapter(text, MAPPING).parse()]
    assert [c.claim_id for c in claims] == ["C1", "C2"]
    assert len(claims[0].lines) == 2 and claims[0].total_billed == 150 and claims[0].diagnosis_codes == ["J06.9"]
    assert str(claims[0].service_date) == "2025-01-08" and claims[1].diagnosis_codes == ["I25.10"]


def test_icd_normalisation_leaves_dotted_codes_alone():
    assert normalize_icd("i2510") == "I25.10" and normalize_icd("E11.9") == "E11.9" and normalize_icd("I10") == "I10"


def test_validation_reports_fields():
    with pytest.raises(ValidationFailed) as e:
        validate_claim({"claim_id": "C1", "provider_id": "P1", "total_billed": -5})
    fields = {x["field"] for x in e.value.details["errors"]}
    assert {"member_id", "service_date", "total_billed"} <= fields


def test_unknown_fields_are_kept_as_attributes():
    claim = validate_claim({**api_claim(), "sum_insured": 500000, "riders": ["opd"]})
    assert claim.attributes["sum_insured"] == 500000 and claim.attributes["riders"] == ["opd"]


def test_content_hash_is_stable_and_sensitive():
    a, b = validate_claim(api_claim()), validate_claim(dict(reversed(list(api_claim().items()))))
    assert content_hash(a) == content_hash(b)
    assert content_hash(a) != content_hash(validate_claim(api_claim(billed=121)))


def test_fhir_claim_mapping():
    resource = {
        "resourceType": "Bundle",
        "entry": [{"resource": {"resourceType": "Claim", "id": "F1", "patient": {"reference": "Patient/M1"}, "provider": {"reference": "Practitioner/P1"}, "billablePeriod": {"start": "2025-01-08"}, "total": {"value": 120},
                                "diagnosis": [{"diagnosisCodeableConcept": {"coding": [{"code": "M54.5"}]}}], "item": [{"sequence": 1, "productOrService": {"coding": [{"code": "99213"}]}, "net": {"value": 120}}]}}, {"resource": {"resourceType": "Patient"}}],
    }
    claims = FHIRAdapter(resource).parse()
    assert len(claims) == 1
    claim = validate_claim(claims[0])
    assert (claim.claim_id, claim.member_id, claim.provider_id, claim.lines[0].cpt_code, claim.total_billed) == ("F1", "M1", "P1", "99213", 120)


def test_webhook_signature():
    body = b'{"claims": [{"claim_id": "C1"}]}'
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    WebhookAdapter(body, good, "secret")
    with pytest.raises(Unauthorized):
        WebhookAdapter(body, "sha256=deadbeef", "secret")
    with pytest.raises(Unauthorized):
        WebhookAdapter(body, None, "secret")
