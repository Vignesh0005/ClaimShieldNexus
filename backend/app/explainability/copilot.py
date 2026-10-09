import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import get_settings
from app.core.exceptions import CopilotUnavailable
from app.core.logging import logger
from app.explainability.plain_language import find_banned
from app.schemas.common import DISCLAIMER

PROMPTS = Path(__file__).parent / "prompts"
REQUIRED_KEYS = [
    "investigation_summary", "why_flagged", "evidence_explanation", "important_signals", "limitations",
    "counterfactuals", "missing_information", "investigation_questions", "plain_language_summary", "suggested_next_action",
]
FALLBACK_MODEL = "template_fallback"


class OllamaClient:
    """Chat completion against Ollama (cloud or self-hosted) with JSON-formatted output."""

    def __init__(self) -> None:
        s = get_settings()
        self.url, self.key, self.model, self.timeout = s.ollama_url.rstrip("/"), s.ollama_api_key, s.ollama_model, s.ollama_timeout

    @property
    def configured(self) -> bool:
        return bool(get_settings().enable_copilot and self.key)

    async def generate(self, prompt: str) -> dict:
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json", "options": {"temperature": 0.1, "num_predict": 4000}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.url}/api/chat", json=body, headers=headers)
                response.raise_for_status()
                return json.loads(response.json()["message"]["content"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("copilot_call_failed", error=str(exc)[:200])
            raise CopilotUnavailable("The investigation copilot could not be reached.") from exc

    async def health(self) -> bool:
        if not self.key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.url}/api/tags", headers={"Authorization": f"Bearer {self.key}"})
                return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False


def build_evidence_packet(brief: dict, counterfactual_sentences: list[str]) -> dict:
    """Only structured, already-derived evidence goes to the model: scores, signal findings and
    limitations. Raw claims, member identifiers and free-text notes are never included."""
    return {
        "case_id": brief["case_id"],
        "provider": brief["provider"],
        "risk_score": brief["risk_score"],
        "severity": brief["severity"],
        "evidence_strength": brief["evidence_strength"],
        "member_harm_score": brief["member_harm_score"],
        "potential_dollars": brief["potential_dollars"],
        "members_affected": brief["members_affected"],
        "signals": [{"detector": e["detector"], "finding": e["label"], "score": e["score"], "detail": e["detail"]} for e in brief["evidence"]],
        "timeline": brief["timeline"],
        "network_context": brief["network"]["text"],
        "limitations": brief["limitations"],
        "what_would_clear_it": counterfactual_sentences,
        "suggested_next_action": brief["suggested_next_action"],
    }


def template_response(brief: dict, counterfactual_sentences: list[str], reason: str) -> dict:
    """Deterministic explanation built from the same evidence, used when the LLM is disabled,
    unreachable or returns something unusable."""
    findings = [f"{e['label']} ({e['score_label']} {e['score']:.0%})" for e in brief["evidence"]]
    return {
        "model": FALLBACK_MODEL,
        "fallback_reason": reason,
        "investigation_summary": f"Case {brief['case_id']} concerns {brief['provider']}. It has a risk score of {brief['risk_score']:.0%} ({brief['severity']}) with {len(findings)} findings that require review.",
        "why_flagged": "The case was routed for review because of: " + "; ".join(findings) + "." if findings else "No findings are on record for this case.",
        "evidence_explanation": " ".join(f"{e['label']}: {e['detail']}." for e in brief["evidence"] if e["detail"]),
        "important_signals": findings,
        "limitations": brief["limitations"],
        "counterfactuals": counterfactual_sentences,
        "missing_information": [l for l in brief["limitations"] if "not available" in l or "unknown" in l or "No prior" in l],
        "investigation_questions": [f"Is there documentation showing that {c[3:].rstrip('.')}?" for c in brief["clears"][:5]],
        "plain_language_summary": " ".join(e["plain"] for e in brief["evidence"][:4]) + " These are reasons to look more closely, not conclusions.",
        "suggested_next_action": brief["suggested_next_action"],
    }


class InvestigationCopilot:
    """Explains evidence. Never classifies, never accuses, never decides."""

    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    async def investigate(self, brief: dict, counterfactual_sentences: list[str], include_counterfactuals: bool = True, include_plain_language: bool = True) -> dict:
        packet = build_evidence_packet(brief, counterfactual_sentences)
        out: dict | None = None
        reason = "copilot disabled or no API key configured"
        if self.client.configured:
            prompt = (PROMPTS / "copilot_investigate.txt").read_text(encoding="utf-8").replace("{evidence}", json.dumps(packet, indent=2, default=str))
            try:
                data = await self.client.generate(prompt)
                missing = [k for k in REQUIRED_KEYS if k not in data]
                banned = find_banned(json.dumps(data))
                if missing:
                    reason = f"model response was missing fields: {', '.join(missing)}"
                elif banned:
                    reason = "model response used accusatory wording and was discarded"
                    logger.warning("copilot_output_rejected", banned=banned)
                else:
                    out = {"model": self.client.model, **{k: data[k] for k in REQUIRED_KEYS}}
            except CopilotUnavailable:
                reason = "copilot service unreachable"
        if out is None:
            out = template_response(brief, counterfactual_sentences, reason)
        if not include_counterfactuals:
            out["counterfactuals"] = []
        if not include_plain_language:
            out["plain_language_summary"] = None
        # These are set by the server, never by the model.
        out.update(case_id=brief["case_id"], suggested_next_action=brief["suggested_next_action"], disclaimer=DISCLAIMER, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return out

    async def ask(self, brief: dict, counterfactual_sentences: list[str], question: str) -> dict:
        packet = build_evidence_packet(brief, counterfactual_sentences)
        base = {"case_id": brief["case_id"], "question": question, "disclaimer": DISCLAIMER, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if self.client.configured:
            prompt = (PROMPTS / "copilot_ask.txt").read_text(encoding="utf-8").replace("{evidence}", json.dumps(packet, indent=2, default=str)).replace("{question}", question)
            try:
                data = await self.client.generate(prompt)
                if "answer" in data and not find_banned(json.dumps(data)):
                    return {**base, "model": self.client.model, "answer": data["answer"], "evidence_used": data.get("evidence_used", []), "not_in_evidence": bool(data.get("not_in_evidence", False))}
            except CopilotUnavailable:
                pass
        return {
            **base,
            "model": FALLBACK_MODEL,
            "answer": "The copilot model is not available, so this question cannot be answered in free text. The structured evidence for the case is attached.",
            "evidence_used": [s["finding"] for s in packet["signals"]],
            "not_in_evidence": True,
            "evidence": packet,
        }


# ---------------------------------------------------------------------------
# Optional LLM enhancement of the template brief
# ---------------------------------------------------------------------------
import re  # noqa: E402

ENHANCE_SECTIONS = ("narrative", "counterfactuals", "plain_language")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def enhancement_packet(brief: dict, counterfactual_sentences: list[str]) -> dict:
    """The evidence packet plus an id for every entry the model is allowed to cite."""
    packet = build_evidence_packet(brief, counterfactual_sentences)
    sources = {
        "case.risk_score": f"risk score {brief['risk_score']}",
        "case.severity": f"severity {brief['severity']}",
        "case.potential_dollars": f"potential amount INR {brief['potential_dollars']}",
        "case.members_affected": f"members affected {brief['members_affected']}",
        "case.member_harm_score": f"member harm score {brief['member_harm_score']}",
        "case.evidence_strength": f"evidence strength {brief['evidence_strength']}",
        "network_context": brief["network"]["text"],
        "suggested_next_action": brief["suggested_next_action"],
    }
    for e in brief["evidence"]:
        sources[f"signal.{e['name']}"] = f"{e['label']} ({e['score_label']} {e['score']}): {e['detail']}"
    for i, t in enumerate(brief["timeline"]):
        sources[f"timeline.{i}"] = f"{t['date']}: {t['title']}"
    for i, l in enumerate(brief["limitations"]):
        sources[f"limitation.{i}"] = l
    for i, c in enumerate(counterfactual_sentences):
        sources[f"counterfactual.{i}"] = c
    return {**packet, "sources": sources}


def _numbers(text: str) -> list[float]:
    out = []
    for token in _NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return out


def validate_enhancement(data: dict, packet: dict) -> str | None:
    """Returns None when the model's output may be shown, otherwise the reason it was rejected.

    Checks: the expected structure; every line cites at least one known source id; no accusatory
    wording; and no number that does not appear in the evidence (small counts up to 10 excepted).
    The number check cannot catch an invented claim made in words, so the output is still shown
    beside the template brief it was derived from, never instead of it."""
    if not isinstance(data, dict):
        return "the response was not a JSON object"
    allowed = set(packet["sources"])
    known = _numbers(json.dumps(packet, default=str))
    for section in ENHANCE_SECTIONS:
        lines = data.get(section)
        if not isinstance(lines, list) or not lines:
            return f"the '{section}' section was missing or empty"
        for line in lines:
            if not isinstance(line, dict) or not str(line.get("text", "")).strip():
                return f"a line in '{section}' had no text"
            cited = line.get("sources")
            if not isinstance(cited, list) or not cited:
                return f"a line in '{section}' cited no source"
            unknown = [c for c in cited if c not in allowed]
            if unknown:
                return f"a line in '{section}' cited an unknown source ({unknown[0]})"
            for n in _numbers(line["text"]):
                if n <= 10 and float(n).is_integer():
                    continue
                if not any(abs(n - k) < 0.006 or abs(n - k * 100) < 0.6 for k in known):
                    return f"a line in '{section}' contained a number that is not in the evidence ({n:g})"
    banned = find_banned(json.dumps({s: data[s] for s in ENHANCE_SECTIONS}))
    if banned:
        return "the response used accusatory wording"
    return None


def template_enhancement(brief: dict, counterfactual_sentences: list[str], reason: str) -> dict:
    """The same three sections built directly from the evidence, each line citing its source."""
    narrative = [{"text": f"Case {brief['case_id']} concerns {brief['provider']} and has a risk score of {brief['risk_score']:.0%} ({brief['severity']}), which requires review.", "sources": ["case.risk_score", "case.severity"]}]
    narrative += [{"text": f"{e['label']}: {e['detail'] or 'finding recorded'}. This may indicate a pattern that requires review.", "sources": [f"signal.{e['name']}"]} for e in brief["evidence"]]
    return {
        "model": FALLBACK_MODEL,
        "fallback_reason": reason,
        "narrative": narrative,
        "counterfactuals": [{"text": c, "sources": [f"counterfactual.{i}"]} for i, c in enumerate(counterfactual_sentences)],
        "plain_language": [{"text": e["plain"], "sources": [f"signal.{e['name']}"]} for e in brief["evidence"]],
        "limitations": brief["limitations"],
    }


async def enhance_brief(brief: dict, counterfactual_sentences: list[str], client: OllamaClient | None = None) -> dict:
    """Narrative, counterfactuals and a plain-language version layered on the template brief.
    Uses the LLM when configured and its output passes validation; otherwise the cited template."""
    client = client or OllamaClient()
    packet = enhancement_packet(brief, counterfactual_sentences)
    if not client.configured:
        return template_enhancement(brief, counterfactual_sentences, "LLM enhancement is not configured (no OLLAMA_API_KEY), so this was built from the template")
    prompt = (PROMPTS / "brief_enhance.txt").read_text(encoding="utf-8").replace("{evidence}", json.dumps(packet, indent=2, default=str))
    try:
        data = await client.generate(prompt)
    except CopilotUnavailable:
        return template_enhancement(brief, counterfactual_sentences, "the LLM service could not be reached")
    problem = validate_enhancement(data, packet)
    if problem:
        logger.warning("brief_enhancement_rejected", reason=problem)
        return template_enhancement(brief, counterfactual_sentences, f"the LLM output was discarded because {problem}")
    return {
        "model": client.model,
        "fallback_reason": None,
        **{section: [{"text": str(l["text"]).strip(), "sources": list(l["sources"])} for l in data[section]] for section in ENHANCE_SECTIONS},
        # Limitations always come from the stored evidence, whatever the model returned.
        "limitations": brief["limitations"],
    }


def render_enhancement(enhancement: dict) -> str:
    def block(title: str, lines: list[dict]) -> str:
        return f"## {title}\n" + "\n".join(f"- {l['text']} [{', '.join(l['sources'])}]" for l in lines) + "\n"

    header = f"\n---\n\n# Enhancement ({enhancement['model']})\n\nEach line lists the evidence entries it is based on.\n\n"
    return header + block("Narrative", enhancement["narrative"]) + "\n" + block("What would clear this case", enhancement["counterfactuals"]) + "\n" + block("In plain language", enhancement["plain_language"])
