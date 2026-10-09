from datetime import date, timedelta

from app.detection.context import MemberInfo, PeerStats, ProviderInfo
from app.detection.rules.coding_validity import CodingValidity
from app.detection.rules.duplicate_billing import DuplicateBilling
from app.detection.rules.excessive_utilization import ExcessiveUtilization
from app.detection.rules.impossible_timing import ImpossibleTiming
from app.detection.rules.member_eligibility import MemberEligibility
from app.detection.rules.ncci_edits import NCCIEdits
from app.detection.rules.phantom_services import PhantomServices
from app.detection.rules.provider_validity import ProviderValidity
from app.detection.rules.referral_loops import ReciprocalReferrals
from app.detection.rules.registry import RuleEngine
from app.detection.rules.unbundling import Unbundling
from app.detection.rules.upcoding import Upcoding
from tests.conftest import TODAY, make_claim, make_ctx


def test_duplicate_billing_exact_match():
    earlier = make_claim("C0")
    s = DuplicateBilling().evaluate(make_ctx(make_claim("C1"), provider_history=[earlier]))
    assert s and s.confidence == 0.98 and s.evidence["matched_claim_id"] == "C0"
    assert "billed_amount" in s.evidence["matching_fields"]


def test_duplicate_billing_ignores_different_day_or_member():
    assert DuplicateBilling().evaluate(make_ctx(make_claim("C1"), provider_history=[make_claim("C0", day=TODAY - timedelta(days=1))])) is None
    assert DuplicateBilling().evaluate(make_ctx(make_claim("C1"), provider_history=[make_claim("C0", member="MBR-2")])) is None


def test_upcoding_needs_volume_and_a_rate_far_above_peers():
    history = [make_claim(f"H{i}", member=f"M{i}", codes=("99215",), day=TODAY - timedelta(days=i)) for i in range(12)]
    s = Upcoding().evaluate(make_ctx(make_claim("C1", codes=("99215",)), provider_history=history))
    assert s and s.evidence["level5_em_rate"] == 1.0
    assert Upcoding().evaluate(make_ctx(make_claim("C1", codes=("99215",)), provider_history=history[:3])) is None  # too few visits
    mixed = [make_claim(f"H{i}", codes=("99213",), day=TODAY - timedelta(days=i)) for i in range(12)]
    assert Upcoding().evaluate(make_ctx(make_claim("C1", codes=("99215",)), provider_history=mixed)) is None  # one level 5 among many


def test_unbundling_panel_components():
    s = Unbundling().evaluate(make_ctx(make_claim("C1", codes=("82040", "82247", "82310", "82374", "82435"), billed=15)))
    assert s and s.evidence["panel_code"] == "80053"
    assert Unbundling().evaluate(make_ctx(make_claim("C1", codes=("80053", "82040", "82247", "82310", "82374")))) is None  # panel itself billed


def test_ncci_pair_and_modifier_bypass():
    claim = make_claim("C1", codes=("80053", "80048"))
    assert NCCIEdits().evaluate(make_ctx(claim))
    claim.lines[1].modifiers = ["59"]
    assert NCCIEdits().evaluate(make_ctx(claim)) is None


def test_phantom_service_without_encounter():
    assert PhantomServices().evaluate(make_ctx(make_claim("C1", attributes={"encounter_verified": False}))).confidence == 0.9
    assert PhantomServices().evaluate(make_ctx(make_claim("C1"))) is None


def test_dme_without_prior_visit():
    assert PhantomServices().evaluate(make_ctx(make_claim("C1", codes=("E0601",), billed=900)))
    prior = make_claim("C0", provider="PRV-9", day=TODAY - timedelta(days=10))
    assert PhantomServices().evaluate(make_ctx(make_claim("C1", codes=("E0601",), billed=900), member_history=[prior])) is None


def test_excessive_utilization():
    history = [make_claim(f"H{i}", day=TODAY - timedelta(days=i * 3)) for i in range(1, 8)]
    s = ExcessiveUtilization().evaluate(make_ctx(make_claim("C1"), provider_history=history, peers=PeerStats(visits_per_member=2)))
    assert s and s.evidence["visits_in_30_days"] == 8
    assert ExcessiveUtilization().evaluate(make_ctx(make_claim("C1"), provider_history=history[:2])) is None


def test_impossible_day():
    history = [make_claim(f"H{i}", member=f"M{i}", codes=("90837",)) for i in range(17)]
    s = ImpossibleTiming().evaluate(make_ctx(make_claim("C1", codes=("90837",)), provider_history=history))
    assert s and s.evidence["billed_hours_on_date"] == 18.0
    assert ImpossibleTiming().evaluate(make_ctx(make_claim("C1", codes=("90837",)), provider_history=history[:5])) is None


def test_impossible_geography():
    here, there = make_claim("C1", facility_id="F1"), make_claim("C0", provider="PRV-2", facility_id="F2")
    locations = {"F1": (19.076, 72.8777, "Mumbai"), "F2": (28.6139, 77.209, "Delhi")}
    s = ImpossibleTiming().evaluate(make_ctx(here, member_history=[there], facility_locations=locations))
    assert s and s.evidence["pattern"] == "impossible_geography" and s.evidence["distance_km"] > 1000


def test_reciprocal_referrals():
    claim = make_claim("C1", referring_provider_id="PRV-2")
    edges = [("PRV-2", "PRV-1")] * 2 + [("PRV-1", "PRV-2")] * 3
    assert ReciprocalReferrals().evaluate(make_ctx(claim, referral_edges=edges))
    assert ReciprocalReferrals().evaluate(make_ctx(claim, referral_edges=[("PRV-2", "PRV-1")] * 5)) is None  # one direction only


def test_coding_validity_is_low_severity():
    claim = make_claim("C1", codes=("9921",), dx=["NOTACODE"])
    s = CodingValidity().evaluate(make_ctx(claim))
    assert s and s.severity == "low" and len(s.evidence["problems"]) == 2
    assert CodingValidity().evaluate(make_ctx(make_claim("C1"))) is None


def test_provider_and_member_checks_are_silent_without_master_files():
    ctx = make_ctx(make_claim("C1"), provider=ProviderInfo("PRV-1"), member=MemberInfo("MBR-1"))
    assert ProviderValidity().evaluate(ctx) is None and MemberEligibility().evaluate(ctx) is None
    ctx.provider_master_loaded = ctx.member_master_loaded = True
    assert ProviderValidity().evaluate(ctx).confidence == 0.6
    assert MemberEligibility().evaluate(ctx).confidence == 0.6


def test_revoked_licence_and_lapsed_eligibility():
    ctx = make_ctx(make_claim("C1"), provider=ProviderInfo("PRV-1", True, license_status="revoked"), member=MemberInfo("MBR-1", True, eligibility_end=date(2024, 12, 31)), provider_master_loaded=True, member_master_loaded=True)
    assert ProviderValidity().evaluate(ctx).confidence == 0.9
    assert MemberEligibility().evaluate(ctx).confidence == 0.85


def test_engine_clean_claim_has_no_signals_and_disabled_rules_are_skipped():
    assert RuleEngine().run_all(make_ctx(make_claim("C1"))) == []
    ctx = make_ctx(make_claim("C1"), provider_history=[make_claim("C0")])
    assert [s.name for s in RuleEngine().run_all(ctx)] == ["duplicate_billing"]
    assert RuleEngine(disabled={"duplicate_billing"}).run_all(ctx) == []
