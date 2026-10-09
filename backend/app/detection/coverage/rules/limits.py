"""Section 6: limits and cost-sharing."""
from app.detection.coverage.registry import CONDITIONAL, PASS, CoverageInput, Outcome, RuleDef, coverage_check


@coverage_check("senior_co_payment")
def senior_co_payment(inp: CoverageInput, rule: RuleDef) -> Outcome:
    age = rule.conditions.get("age_from", 61)
    rate = inp.attributes.get("co_pay_rate", rule.conditions.get("default_rate", 0.10))
    if inp.plan_type == "senior_citizen" or (inp.member_age is not None and inp.member_age >= age):
        return Outcome(
            CONDITIONAL,
            "Senior citizen plan typically has 10-20% co-pay",
            {"condition": "co_payment", "value": rate, "source": rule.source_section, "note": "Senior citizen plan typically has 10-20% co-pay"},
        )
    return Outcome(PASS)


@coverage_check("sum_insured_limit")
def sum_insured_limit(inp: CoverageInput, rule: RuleDef) -> Outcome:
    sum_insured = inp.attributes.get("sum_insured_remaining", inp.attributes.get("sum_insured"))
    if sum_insured is None or inp.total_billed is None:
        return Outcome(PASS, "Sum insured not supplied.")
    if inp.total_billed <= float(sum_insured):
        return Outcome(PASS)
    note = f"Billed amount {inp.total_billed:,.0f} exceeds the available sum insured {float(sum_insured):,.0f}; payable amount is capped."
    return Outcome(CONDITIONAL, note, {"condition": "sum_insured_cap", "value": float(sum_insured), "source": rule.source_section, "note": note})


@coverage_check("room_rent_limit")
def room_rent_limit(inp: CoverageInput, rule: RuleDef) -> Outcome:
    rent = inp.attributes.get("room_rent_per_day")
    cap = inp.attributes.get("room_rent_cap_per_day")
    if rent is None or cap is None or float(rent) <= float(cap):
        return Outcome(PASS)
    note = f"Room rent {float(rent):,.0f} per day is above the policy cap {float(cap):,.0f}; proportionate deduction may apply."
    return Outcome(CONDITIONAL, note, {"condition": "room_rent_proportionate_deduction", "value": round(float(cap) / float(rent), 2), "source": rule.source_section, "note": note})
