from datetime import timedelta

from app.detection.context import MemberInfo, ProviderVolume
from app.detection.rules.demographic_mismatch import DemographicMismatch
from app.detection.rules.diagnosis_procedure_mismatch import DiagnosisProcedureMismatch
from app.detection.rules.modifier_overuse import ModifierOveruse
from app.detection.rules.new_provider_burst import NewProviderBurst
from app.detection.rules.peer_outlier import PeerOutlier
from app.detection.rules.provider_shopping import ProviderShopping
from app.detection.rules.registry import ALL_RULES, RuleEngine
from app.detection.rules.split_billing import SplitBilling
from app.explainability.brief_generator import _detail
from app.explainability.plain_language import SIGNAL_TEXT, find_banned
from app.utils.codes import REFERENCE_DATA
from tests.conftest import TODAY, make_claim, make_ctx

NEW_RULES = ["units_cap", "amount_outlier", "diagnosis_procedure_mismatch", "demographic_mismatch", "peer_outlier", "split_billing", "modifier_overuse", "new_provider_burst", "provider_shopping"]


def peers(n=6, **kw):
    values = {"claims": 20, "members": 15, "billed": 3000.0, "lines": 100, "bypass_lines": 5, **kw}
    return [ProviderVolume(f"PEER-{i}", **values) for i in range(n)]


# ---------- diagnosis_procedure_mismatch ----------

def test_knee_arthroscopy_with_only_an_eye_diagnosis():
    s = DiagnosisProcedureMismatch().evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=["H25.9"], billed=4200)))
    assert s and s.confidence == 0.75
    assert s.evidence["cpt_code"] == "29881" and s.evidence["diagnosis_codes"] == ["H25.9"] and s.evidence["expected_diagnosis_groups"] == ["musculoskeletal", "injury"]


def test_diagnosis_mismatch_is_silent_when_any_diagnosis_fits_or_the_code_is_not_in_the_table():
    rule = DiagnosisProcedureMismatch()
    assert rule.evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=["M23.20"]))) is None
    assert rule.evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=["H25.9", "S83.201A"]))) is None  # one fitting diagnosis is enough
    assert rule.evaluate(make_ctx(make_claim("C1", codes=("99213",), dx=["H25.9"]))) is None
    assert rule.evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=[]))) is None  # left to coding_validity


def test_diagnosis_mismatch_is_weaker_when_the_diagnosis_is_merely_unclassified():
    unclassified = DiagnosisProcedureMismatch().evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=["Z00.00"])))
    several = DiagnosisProcedureMismatch().evaluate(make_ctx(make_claim("C1", codes=("29881", "66984", "45378"), dx=["F32.9"])))
    assert unclassified.confidence == 0.55 and several.confidence == 0.85


# ---------- demographic_mismatch ----------

def test_maternity_service_for_a_male_member():
    s = DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",), attributes={"member_gender": "M"}, member_age=30)))
    assert s and s.confidence == 0.90 and s.evidence["member_gender"] == "M" and s.evidence["constraint"] == "female members only"


def test_demographic_mismatch_is_silent_when_the_member_fits():
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",), attributes={"gender": "female"}, member_age=30))) is None
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("99213",), attributes={"member_gender": "M"}))) is None


def test_demographic_mismatch_never_guesses_a_missing_age_or_gender():
    nobody = MemberInfo("MBR-1", True, None)
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",)), member=nobody)) is None  # neither supplied
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",), member_age=30), member=nobody)) is None  # age fits, gender unknown
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",), attributes={"member_gender": "unknown"}), member=nobody)) is None
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("99387",), attributes={"member_gender": "F"}), member=nobody)) is None  # age limit, age unknown


def test_demographic_age_confidence_grows_with_distance_from_the_range():
    near = DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("99383",), member_age=12)))
    far = DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("99387",), member_age=30)))
    assert near.confidence == 0.63 and near.evidence["constraint"] == "age 5 to 11" and far.confidence == 0.90
    assert DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("99460",), member_age=0))) is None  # a newborn is age 0


# ---------- peer_outlier ----------

def busy_history(n=24, members=5, billed=500.0):
    return [make_claim(f"H{i}", member=f"M{i % members}", day=TODAY - timedelta(days=1 + i), billed=billed) for i in range(n)]


def test_peer_outlier_fires_when_billing_per_member_is_far_above_peers():
    s = PeerOutlier().evaluate(make_ctx(make_claim("C1", member="M0", billed=500), provider_history=busy_history(), specialty_peers=peers()))
    assert s and s.confidence == 0.90
    assert s.evidence["metric"] == "billed_per_member" and s.evidence["provider_value"] == 2500 and s.evidence["peer_median"] == 200 and s.evidence["peers_compared"] == 6


def test_peer_outlier_is_silent_for_a_provider_in_line_with_peers():
    history = [make_claim(f"H{i}", member=f"M{i}", day=TODAY - timedelta(days=1 + i), billed=200) for i in range(24)]
    assert PeerOutlier().evaluate(make_ctx(make_claim("C1", member="M0", billed=200), provider_history=history, specialty_peers=peers())) is None


def test_peer_outlier_needs_enough_peers_and_enough_claims():
    claim = make_claim("C1", member="M0", billed=500)
    assert PeerOutlier().evaluate(make_ctx(claim, provider_history=busy_history())) is None  # no peers at all
    assert PeerOutlier().evaluate(make_ctx(claim, provider_history=busy_history(), specialty_peers=peers(4))) is None
    assert PeerOutlier().evaluate(make_ctx(claim, provider_history=busy_history(), specialty_peers=peers(claims=9))) is None  # peers too small to compare with
    assert PeerOutlier().evaluate(make_ctx(claim, provider_history=busy_history(9), specialty_peers=peers())) is None  # ten claims


# ---------- split_billing ----------

def test_split_billing_links_parts_on_consecutive_days():
    earlier = [make_claim("C0", day=TODAY - timedelta(days=1), billed=60), make_claim("B9", day=TODAY - timedelta(days=2), billed=10)]
    s = SplitBilling().evaluate(make_ctx(make_claim("C1", billed=60), member_history=earlier))
    assert s and s.evidence["cpt_code"] == "99213" and s.evidence["total_billed"] == 130 and s.evidence["typical_amount"] == 120
    assert [c["claim_id"] for c in s.evidence["linked_claims"]] == ["B9", "C0", "C1"]
    exact = SplitBilling().evaluate(make_ctx(make_claim("C1", billed=60), member_history=earlier[:1]))
    assert exact.confidence == 0.90 > s.confidence


def test_split_billing_is_silent_for_full_services_gaps_and_other_providers():
    rule = SplitBilling()
    assert rule.evaluate(make_ctx(make_claim("C1"), member_history=[make_claim("C0", day=TODAY - timedelta(days=1))])) is None  # two full visits
    assert rule.evaluate(make_ctx(make_claim("C1", billed=60), member_history=[make_claim("C0", day=TODAY - timedelta(days=3), billed=60)])) is None
    assert rule.evaluate(make_ctx(make_claim("C1", billed=60), member_history=[make_claim("C0", provider="PRV-2", day=TODAY - timedelta(days=1), billed=60)])) is None
    assert rule.evaluate(make_ctx(make_claim("C1", billed=60))) is None  # no history


def test_split_billing_needs_a_known_usual_amount():
    earlier = [make_claim("C0", codes=("12345",), day=TODAY - timedelta(days=1), billed=60)]
    assert SplitBilling().evaluate(make_ctx(make_claim("C1", codes=("12345",), billed=60), member_history=earlier)) is None


# ---------- modifier_overuse ----------

def with_modifier(claim, modifier="59"):
    for line in claim.lines:
        line.modifiers = [modifier]
    return claim


def test_modifier_overuse_fires_when_almost_every_line_carries_a_bypass_modifier():
    history = [with_modifier(make_claim(f"H{i}", member=f"M{i}", day=TODAY - timedelta(days=1 + i))) for i in range(30)]
    s = ModifierOveruse().evaluate(make_ctx(with_modifier(make_claim("C1"), "XU"), provider_history=history, specialty_peers=peers()))
    assert s and s.confidence == 0.95
    assert s.evidence["provider_rate"] == 1.0 and s.evidence["peer_rate"] == 0.05 and s.evidence["lines_counted"] == 31


def test_modifier_overuse_is_silent_at_an_ordinary_rate_or_on_a_claim_without_the_modifier():
    plain = [make_claim(f"H{i}", member=f"M{i}", day=TODAY - timedelta(days=1 + i)) for i in range(30)]
    assert ModifierOveruse().evaluate(make_ctx(with_modifier(make_claim("C1")), provider_history=plain, specialty_peers=peers())) is None  # 1 line in 31
    heavy = [with_modifier(c) for c in plain]
    assert ModifierOveruse().evaluate(make_ctx(make_claim("C1"), provider_history=heavy, specialty_peers=peers())) is None  # this claim has none
    assert ModifierOveruse().evaluate(make_ctx(with_modifier(make_claim("C1"), "26"), provider_history=heavy, specialty_peers=peers())) is None  # not a bypass modifier


def test_modifier_overuse_needs_enough_lines_and_peers():
    history = [with_modifier(make_claim(f"H{i}", day=TODAY - timedelta(days=1 + i))) for i in range(30)]
    claim = with_modifier(make_claim("C1"))
    assert ModifierOveruse().evaluate(make_ctx(claim, provider_history=history[:9], specialty_peers=peers())) is None  # ten lines
    assert ModifierOveruse().evaluate(make_ctx(claim, provider_history=history)) is None  # no peers
    assert ModifierOveruse().evaluate(make_ctx(claim, provider_history=history, specialty_peers=peers(lines=20))) is None  # too few peer lines


# ---------- new_provider_burst ----------

def burst(n=29, days=10):
    return [make_claim(f"H{i}", member=f"M{i}", day=TODAY - timedelta(days=i % days)) for i in range(n)]


def test_new_provider_burst_fires_for_a_new_provider_with_high_volume():
    ctx = make_ctx(make_claim("C1"), provider_history=burst(), specialty_peers=peers(claims=30), provider_first_seen=TODAY - timedelta(days=10), tenant_first_seen=TODAY - timedelta(days=200))
    s = NewProviderBurst().evaluate(ctx)
    assert s and s.confidence == 0.75
    assert s.evidence["first_seen"] == str(TODAY - timedelta(days=10)) and s.evidence["claims_in_window"] == 30 and s.evidence["usual_claims_in_window"] == 4.7


def test_new_provider_burst_is_silent_for_an_established_provider_or_modest_volume():
    old = make_ctx(make_claim("C1"), provider_history=burst(), specialty_peers=peers(claims=30), provider_first_seen=TODAY - timedelta(days=120), tenant_first_seen=TODAY - timedelta(days=200))
    assert NewProviderBurst().evaluate(old) is None
    modest = make_ctx(make_claim("C1"), provider_history=burst(9), specialty_peers=peers(claims=30), provider_first_seen=TODAY - timedelta(days=10), tenant_first_seen=TODAY - timedelta(days=200))
    assert NewProviderBurst().evaluate(modest) is None


def test_new_provider_burst_is_silent_for_a_new_tenant_or_without_peers():
    kw = {"provider_history": burst(), "provider_first_seen": TODAY - timedelta(days=10)}
    assert NewProviderBurst().evaluate(make_ctx(make_claim("C1"), specialty_peers=peers(claims=30), tenant_first_seen=TODAY - timedelta(days=20), **kw)) is None  # everyone is new
    assert NewProviderBurst().evaluate(make_ctx(make_claim("C1"), tenant_first_seen=TODAY - timedelta(days=200), **kw)) is None  # no peers
    assert NewProviderBurst().evaluate(make_ctx(make_claim("C1"), specialty_peers=peers(claims=30), **kw)) is None  # first-seen dates not loaded


# ---------- provider_shopping ----------

def visits(n, **kw):
    return [make_claim(f"V{i}", provider=f"PRV-{i + 2}", codes=("99214",), day=TODAY - timedelta(days=2 * i + 1), **kw) for i in range(n)]


def test_provider_shopping_fires_for_one_member_and_many_providers():
    s = ProviderShopping().evaluate(make_ctx(make_claim("C1"), member_history=visits(4)))
    assert s and s.confidence == 0.60
    assert s.evidence["member_id"] == "MBR-1" and s.evidence["service_group"] == "office_visit" and s.evidence["distinct_providers"] == 5 and len(s.evidence["claim_ids"]) == 5
    assert ProviderShopping().evaluate(make_ctx(make_claim("C1"), member_history=visits(9))).confidence == 0.90


def test_provider_shopping_is_silent_for_few_providers_repeat_visits_or_other_services():
    rule = ProviderShopping()
    assert rule.evaluate(make_ctx(make_claim("C1"), member_history=visits(3))) is None
    same = [make_claim(f"V{i}", provider="PRV-2", day=TODAY - timedelta(days=i + 1)) for i in range(8)]
    assert rule.evaluate(make_ctx(make_claim("C1"), member_history=same)) is None  # many visits, two providers
    labs = [make_claim(f"V{i}", provider=f"PRV-{i + 2}", codes=("80053",), day=TODAY - timedelta(days=i + 1)) for i in range(6)]
    assert rule.evaluate(make_ctx(make_claim("C1"), member_history=labs)) is None  # a different kind of service
    old = [make_claim(f"V{i}", provider=f"PRV-{i + 2}", day=TODAY - timedelta(days=40 + i)) for i in range(6)]
    assert rule.evaluate(make_ctx(make_claim("C1"), member_history=old)) is None  # outside 30 days
    assert rule.evaluate(make_ctx(make_claim("C1"))) is None  # no history


# ---------- all nine ----------

def test_all_nine_are_registered_after_the_existing_rules_with_wording_and_reference_data():
    names = [r.name for r in ALL_RULES]
    assert names[:11] == ["duplicate_billing", "upcoding", "unbundling", "ncci_edit", "phantom_services", "excessive_utilization", "impossible_timing", "referral_loop", "coding_validity", "provider_validity", "member_eligibility"]
    assert names[11:] == NEW_RULES
    for name in NEW_RULES:
        text = SIGNAL_TEXT[name]
        assert text["label"] and text["plain"] and text["clears"] and not find_banned(text["label"] + text["plain"])
    used = " ".join(d["used_by"] for d in REFERENCE_DATA)
    for name in ("units_cap", "amount_outlier", "split_billing", "diagnosis_procedure_mismatch", "demographic_mismatch", "provider_shopping"):
        assert name in used


def test_history_rules_stay_silent_for_a_tenant_with_ten_claims():
    history = [make_claim(f"H{i}", member=f"M{i % 3}", day=TODAY - timedelta(days=i)) for i in range(9)]
    ctx = make_ctx(make_claim("C1"), provider_history=history, member_history=history[:3], specialty_peers=[ProviderVolume("PEER-0", 3, 2, 400.0, 3, 0)], provider_first_seen=TODAY - timedelta(days=9), tenant_first_seen=TODAY - timedelta(days=9))
    assert not {s.name for s in RuleEngine().run_all(ctx)} & {"peer_outlier", "split_billing", "modifier_overuse", "new_provider_burst", "provider_shopping"}


def test_every_new_signal_has_a_one_line_detail_for_the_brief():
    signals = [
        DiagnosisProcedureMismatch().evaluate(make_ctx(make_claim("C1", codes=("29881",), dx=["H25.9"]))),
        DemographicMismatch().evaluate(make_ctx(make_claim("C1", codes=("59400",), attributes={"member_gender": "M"}))),
        PeerOutlier().evaluate(make_ctx(make_claim("C1", member="M0", billed=500), provider_history=busy_history(), specialty_peers=peers())),
        SplitBilling().evaluate(make_ctx(make_claim("C1", billed=60), member_history=[make_claim("C0", day=TODAY - timedelta(days=1), billed=60)])),
        ProviderShopping().evaluate(make_ctx(make_claim("C1"), member_history=visits(4))),
    ]
    for s in signals:
        assert s and len(_detail(s.name, s.evidence)) > 20
