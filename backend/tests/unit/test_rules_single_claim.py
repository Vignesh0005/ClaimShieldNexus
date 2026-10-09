from app.detection.context import AmountStats
from app.detection.rules.amount_outlier import MIN_HISTORY_LINES, AmountOutlier
from app.detection.rules.registry import RuleEngine
from app.detection.rules.units_cap import UnitsCap
from app.explainability.brief_generator import _detail
from app.explainability.plain_language import SIGNAL_TEXT
from app.utils.codes import MAX_UNITS_PER_DAY, REFERENCE_DATA, TYPICAL_AMOUNTS
from tests.conftest import make_claim, make_ctx


def test_units_cap_fires_on_fifty_units_of_a_timed_code():
    s = UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("97112",), units=50, billed=2100)))
    assert s and s.name == "units_cap" and s.confidence == 0.95
    assert s.evidence["cpt_code"] == "97112" and s.evidence["units_billed"] == 50 and s.evidence["max_units"] == MAX_UNITS_PER_DAY["97112"]


def test_units_cap_is_silent_at_the_limit_and_for_codes_without_a_limit():
    assert UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("97112",), units=MAX_UNITS_PER_DAY["97112"], billed=168))) is None
    assert UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("12345",), units=50))) is None


def test_units_cap_confidence_grows_with_the_size_of_the_breach():
    marginal = UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("97110",), units=7, billed=280)))
    extreme = UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("97110",), units=40, billed=1600)))
    assert marginal and extreme and marginal.confidence < 0.7 < extreme.confidence


def test_units_cap_adds_up_lines_for_the_same_code_and_day():
    claim = make_claim("C1", codes=("97112", "97112"), billed=126)
    for line in claim.lines:
        line.units = 3
    s = UnitsCap().evaluate(make_ctx(claim))
    assert s and s.evidence["units_billed"] == 6


def test_amount_outlier_fires_on_an_office_visit_billed_far_above_the_usual_amount():
    s = AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("99213",), billed=156_789)))
    assert s and s.name == "amount_outlier" and s.confidence == 0.95
    e = s.evidence
    assert e["cpt_code"] == "99213" and e["billed_amount"] == 156_789 and e["typical_amount"] == TYPICAL_AMOUNTS["99213"] and e["ratio"] > 1000


def test_amount_outlier_is_silent_for_an_ordinary_amount_and_for_unknown_codes():
    assert AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("99213",), billed=300))) is None  # 2.5 times
    assert AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("12345",), billed=90_000))) is None  # nothing to compare with


def test_amount_outlier_confidence_grows_with_the_ratio_and_uses_the_amount_per_unit():
    marginal = AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("99213",), billed=400)))
    extreme = AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("99213",), billed=5000)))
    assert marginal and extreme and marginal.confidence < 0.65 < extreme.confidence
    assert AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("97110",), units=4, billed=170))) is None  # 42.50 per unit


def test_amount_outlier_prefers_tenant_history_when_there_is_enough_of_it():
    claim = make_claim("C1", codes=("99213",), billed=400)
    enough = {"99213": AmountStats(typical=350.0, lines=MIN_HISTORY_LINES)}
    assert AmountOutlier().evaluate(make_ctx(claim, typical_amounts=enough)) is None  # normal for this tenant
    too_few = {"99213": AmountStats(typical=350.0, lines=MIN_HISTORY_LINES - 1)}
    s = AmountOutlier().evaluate(make_ctx(claim, typical_amounts=too_few))
    assert s and "sample" in s.evidence["basis"].lower()  # falls back to the sample table
    unknown = make_claim("C2", codes=("12345",), billed=900)
    assert AmountOutlier().evaluate(make_ctx(unknown, typical_amounts={"12345": AmountStats(100.0, MIN_HISTORY_LINES - 1)})) is None
    s = AmountOutlier().evaluate(make_ctx(unknown, typical_amounts={"12345": AmountStats(100.0, MIN_HISTORY_LINES)}))
    assert s and s.evidence["typical_amount"] == 100.0 and "this tenant" in s.evidence["basis"]


def test_new_rules_are_registered_described_and_documented():
    names = {r["name"] for r in RuleEngine().catalogue()}
    for name in ("units_cap", "amount_outlier"):
        assert name in names
        assert SIGNAL_TEXT[name]["label"] and SIGNAL_TEXT[name]["plain"] and SIGNAL_TEXT[name]["clears"]
    used = " ".join(d["used_by"] for d in REFERENCE_DATA)
    assert "units_cap" in used and "amount_outlier" in used
    assert "50 units of 97112" in _detail("units_cap", UnitsCap().evaluate(make_ctx(make_claim("C1", codes=("97112",), units=50))).evidence)
    assert "99213" in _detail("amount_outlier", AmountOutlier().evaluate(make_ctx(make_claim("C1", codes=("99213",), billed=156_789))).evidence)
