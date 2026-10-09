from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.explainability.plain_language import clears, label, plain
from app.schemas.common import DISCLAIMER

TEMPLATES = Path(__file__).parent / "templates"

NEXT_ACTION = {
    "siu": ("escalate_tier2", "Escalate to SIU Tier 2. Request medical records for the flagged dates.", "A senior investigator should review this case and request the medical records."),
    "investigate": ("request_records", "Request supporting records before escalating; suspicion is high but the evidence is not yet strong.", "More records are needed before anyone can judge this case."),
    "review": ("claims_review", "Route to claims review; the findings are well-evidenced but the overall suspicion is moderate.", "The claims team should check this and correct it if needed."),
    "dismiss": ("monitor", "No investigation recommended. Keep on file and monitor.", "Nothing needs to be done now."),
}


def format_inr(value: float) -> str:
    """Use an ASCII currency label for compatibility with the brief PDF font."""
    rounded = round(value)
    digits = str(abs(rounded))
    tail = digits[-3:]
    prefix = digits[:-3]
    groups = []
    while prefix:
        groups.insert(0, prefix[-2:])
        prefix = prefix[:-2]
    grouped = ",".join([*groups, tail])
    return f"{'-' if rounded < 0 else ''}INR {grouped}"


@lru_cache
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined, autoescape=False, trim_blocks=False)
    env.filters["inr"] = format_inr
    return env


def _detail(name: str, evidence: dict) -> str:
    """One factual sentence drawn only from the stored evidence."""
    e = evidence or {}
    if name == "duplicate_billing" and e.get("matched_claim_id"):
        return f"Matches {e['matched_claim_id']} on {', '.join(e.get('matching_fields', []))}"
    if name == "upcoding":
        return f"Level 5 visit rate {e.get('level5_em_rate', 0):.0%} against a peer rate of {e.get('peer_level5_em_rate', 0):.0%} over {e.get('em_visits_in_window', 0)} visits"
    if name == "unbundling":
        return f"{len(e.get('components_billed', []))} components of panel {e.get('panel_code')} billed separately"
    if name == "referral_loop" and e.get("loop_members"):
        return f"Loop of {len(e['loop_members'])} providers ({' > '.join(e['loop_members'])}) with {e.get('referrals_in_loop', 0)} referrals"
    if name == "referral_loop":
        return f"{e.get('referrals_received', 0)} referrals received from and {e.get('referrals_sent_back', 0)} sent back to {e.get('referring_provider_id')}"
    if name == "billing_spike":
        return f"Billing up {e.get('change_30d_pct', 0)}% in 30 days"
    if name == "impossible_timing" and e.get("billed_hours_on_date"):
        return f"{e['billed_hours_on_date']} hours billed on {e.get('service_date')}"
    if name == "impossible_timing":
        return f"Billed in {' and '.join(e.get('locations', []))} on {e.get('service_date')}, {e.get('distance_km')} km apart"
    if name == "excessive_utilization":
        return f"{e.get('visits_in_30_days')} visits by one member in 30 days"
    if name == "units_cap":
        return f"{e.get('units_billed')} units of {e.get('cpt_code')} billed for {e.get('service_date')} against a daily limit of {e.get('max_units')}"
    if name == "amount_outlier":
        return f"{e.get('cpt_code')} billed at {e.get('billed_amount', 0):,.2f} against a typical {e.get('typical_amount', 0):,.2f} per unit ({e.get('ratio')} times)"
    if name == "diagnosis_procedure_mismatch":
        return f"{e.get('service')} ({e.get('cpt_code')}) billed with {', '.join(e.get('diagnosis_codes', []))}; expected a diagnosis in {', '.join(e.get('expected_diagnosis_groups', []))}"
    if name == "demographic_mismatch":
        who = f"age {e['member_age']}" if "member_age" in e else f"gender {e.get('member_gender')}"
        return f"{e.get('service')} ({e.get('cpt_code')}) billed for a member of {who}; limit is {e.get('constraint')}"
    if name == "peer_outlier":
        return f"{str(e.get('metric', '')).replace('_', ' ').capitalize()} of {e.get('provider_value', 0):,.2f} against a peer median of {e.get('peer_median', 0):,.2f} across {e.get('peers_compared')} peers"
    if name == "split_billing":
        return f"{e.get('cpt_code')} billed on {len(e.get('linked_claims', []))} consecutive days ({', '.join(c['claim_id'] for c in e.get('linked_claims', []))}) for a total of {e.get('total_billed', 0):,.2f}"
    if name == "modifier_overuse":
        return f"Distinct-service modifier on {e.get('provider_rate', 0):.0%} of {e.get('lines_counted')} lines against a peer rate of {e.get('peer_rate', 0):.0%}"
    if name == "new_provider_burst":
        return f"First seen {e.get('first_seen')}; {e.get('claims_in_window')} claims in {e.get('window_days')} days against a usual {e.get('usual_claims_in_window')}"
    if name == "provider_shopping":
        return f"Member {e.get('member_id')} received {str(e.get('service_group', '')).replace('_', ' ')} services from {e.get('distinct_providers')} providers in {e.get('window_days')} days"
    if name == "xgboost" and e.get("top_features"):
        return "Leading factors: " + ", ".join(f["feature"] for f in e["top_features"][:3])
    if name == "similar_cases" and e.get("similar_cases"):
        return "Most similar earlier claims: " + ", ".join(f"{m['claim_id']} ({m['similarity']:.2f}, {m.get('outcome', 'not yet reviewed')})" for m in e["similar_cases"][:3]) + ". Context only; not part of the score"
    if e.get("reasons"):
        return "; ".join(e["reasons"])
    if e.get("reason"):
        return e["reason"]
    return ""


def build_content(*, case: dict, signals: list[dict], timeline: list[dict], limitations: list[str], model_version: str | None) -> dict:
    """Assembles the brief from stored case data. Nothing is generated or inferred here: every
    line traces to a signal's evidence, which is what makes the brief citable."""
    quadrant = case.get("two_axis_quadrant") or "investigate"
    action, technical, plain_action = NEXT_ACTION.get(quadrant, NEXT_ACTION["investigate"])
    hours = case.get("estimated_hours")
    evidence = [
        {
            "detector": s["detector"],
            "name": s["name"],
            "label": label(s["name"]),
            "score": s["score"],
            "score_label": "confidence" if s["detector"] == "rule" else "similarity" if s["detector"] == "similarity" else "score",
            "detail": _detail(s["name"], s.get("evidence") or {}),
            "plain": plain(s["name"]),
            "source": f"claim {s['claim_id']}, signal {s['signal_id']}",
        }
        for s in signals
    ]
    loop = next((s["evidence"] for s in signals if s["name"] == "referral_loop" and (s.get("evidence") or {}).get("loop_members")), None)
    network_text = (
        f"{len(loop['loop_members'])} providers and {loop.get('members_affected') or case.get('members_affected')} members connected through referrals and claims."
        if loop
        else f"No referral loop detected. {case.get('members_affected', 0)} members have claims in this case."
    )
    return {
        "case_id": case["case_id"],
        "provider": f"{case.get('provider_name') or 'Provider'} ({case.get('provider_id')})",
        "risk_score": case.get("risk_score") or 0.0,
        "severity": case.get("severity") or "low",
        "potential_dollars": case.get("expected_recovery") or 0.0,
        "members_affected": case.get("members_affected") or 0,
        "member_harm_score": case.get("member_harm_score") or 0.0,
        "evidence_strength": case.get("evidence_strength") or 0.0,
        "quadrant": quadrant,
        "evidence": evidence,
        "timeline": timeline,
        "network": {"text": network_text, "providers": len(loop["loop_members"]) if loop else 1, "members": case.get("members_affected") or 0},
        "limitations": limitations,
        "clears": [f"If {clears(s['name'])}." for s in signals],
        "confidence": case.get("risk_score") or 0.0,
        "suggested_next_action": action,
        "recommended_action": technical + (f" Estimated review time: {hours:g} hours." if hours else ""),
        "recommended_action_plain": plain_action + (f" This should take about {hours:g} hours." if hours else ""),
        "model_version": model_version or "unknown",
        "disclaimer": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def render(content: dict, brief_type: str) -> str:
    template = "brief_plain.jinja2" if brief_type == "plain" else "brief_technical.jinja2"
    return _env().get_template(template).render(b=content)


def to_pdf(markdown: str, title: str) -> bytes:
    """Minimal PDF rendering of the brief text (headings, bullets, paragraphs)."""
    from fpdf import FPDF

    def latin(text: str) -> str:
        for a, b in (("—", "-"), ("–", "-"), ("’", "'"), ("“", '"'), ("”", '"'), ("**", "")):
            text = text.replace(a, b)
        return text.encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title(latin(title))
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for raw in markdown.splitlines():
        line = latin(raw.rstrip())
        pdf.set_x(pdf.l_margin)
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 15)
            pdf.multi_cell(width, 8, line[2:])
        elif line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(width, 7, line[3:])
        elif line.startswith("> "):
            pdf.set_font("Helvetica", "I", 9)
            pdf.multi_cell(width, 6, line[2:])
        elif line:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(width, 5.5, line)
        else:
            pdf.ln(2)
    return bytes(pdf.output())
