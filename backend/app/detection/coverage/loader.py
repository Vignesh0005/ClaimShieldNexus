import json
import re
from functools import lru_cache
from pathlib import Path

from app.detection.coverage.registry import RuleDef

DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "coverage_rules.json"
# Rules transcribed from the IRDAI framework document go here (see scripts/import_coverage_rules.py).
# The file is absent until someone supplies the document: nothing in this repository invents them.
AUTHORITATIVE_FILE = DATA_DIR / "irdai_authoritative_rules.json"
AUTHORITATIVE_SOURCE = "Health_Insurance_Coverage_Criteria_and_Rules.pdf"
EXPECTED_AUTHORITATIVE_RULES = 78
SECTION_RE = re.compile(r"^Section \d+ \u2014 .+")


@lru_cache
def _raw() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _authoritative() -> list[dict]:
    if not AUTHORITATIVE_FILE.exists():
        return []
    return json.loads(AUTHORITATIVE_FILE.read_text(encoding="utf-8"))["rules"]


class CoverageRuleLoader:
    """Loads rule definitions from the bundled JSON files. `from_rows` builds the same objects from
    the coverage_rules table so rules can be switched on and off per deployment without a release."""

    def load_all(self) -> list[RuleDef]:
        doc = _raw()
        illustrative = [RuleDef(**{"source_document": doc["source_document"], "disclaimer": doc["disclaimer"], **r}) for r in doc["rules"]]
        authoritative = [RuleDef(**{"source_document": AUTHORITATIVE_SOURCE, "authoritative": True, "needs_compliance_review": False, **r}) for r in _authoritative()]
        return authoritative + illustrative

    def plans(self) -> list[dict]:
        return _raw()["plans"]

    @staticmethod
    def from_rows(rows) -> list[RuleDef]:
        return [
            RuleDef(
                rule_id=r.rule_id, category=r.category, rule_name=r.rule_name, check=r.check,
                description=r.description or "", source_section=r.source_section or "",
                source_document=r.source_document or "", inputs=r.inputs or [], valid_values=r.valid_values,
                conditions=r.conditions or {}, on_pass=r.on_pass or "CONTINUE", on_fail=r.on_fail or "NOT_COVERABLE",
                on_uncertain=r.on_uncertain or "COVERAGE_REVIEW_REQUIRED", not_fraud=r.not_fraud,
                not_denial=r.not_denial, enabled=r.enabled, authoritative=bool(r.authoritative),
                needs_compliance_review=bool(r.needs_compliance_review), disclaimer=r.disclaimer or "",
            )
            for r in rows
        ]


def validate_authoritative(rule: dict) -> list[str]:
    """Checks one rule intended for the authoritative set. Returns the problems found."""
    from app.detection.coverage.registry import get_check

    problems = []
    for key in ("rule_id", "category", "rule_name", "check", "source_section", "description"):
        if not rule.get(key):
            problems.append(f"missing {key}")
    if rule.get("source_section") and not SECTION_RE.match(rule["source_section"]):
        problems.append("source_section must look like 'Section N \u2014 name'")
    if rule.get("check") and rule["check"] != "reference_only" and get_check(rule["check"]) is None:
        problems.append(f"no evaluator named '{rule['check']}' (use 'reference_only' for rules that are recorded but not evaluated automatically)")
    return problems
