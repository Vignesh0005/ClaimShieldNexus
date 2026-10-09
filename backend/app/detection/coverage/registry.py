from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

PASS = "PASS"
CONDITIONAL = "CONDITIONAL"
REVIEW = "REVIEW_REQUIRED"
FAIL = "FAIL"


@dataclass
class CoverageInput:
    claim_id: str
    plan_type: str | None = None
    member_age: int | None = None
    policy_start_date: date | None = None
    service_date: date | None = None
    procedure_codes: list[str] = field(default_factory=list)
    diagnosis_codes: list[str] = field(default_factory=list)
    service_location: str | None = None
    pre_auth_number: str | None = None
    documents_provided: list[str] | None = None
    claim_type: str | None = None
    total_billed: float | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class RuleDef:
    rule_id: str
    category: str
    rule_name: str
    check: str
    description: str = ""
    source_section: str = ""
    source_document: str = ""
    inputs: list[str] = field(default_factory=list)
    valid_values: list | None = None
    conditions: dict = field(default_factory=dict)
    on_pass: str = "CONTINUE"
    on_fail: str = "NOT_COVERABLE"
    on_uncertain: str = "COVERAGE_REVIEW_REQUIRED"
    not_fraud: bool = True
    not_denial: bool = True
    enabled: bool = True
    authoritative: bool = False
    needs_compliance_review: bool = True
    disclaimer: str = ""


@dataclass
class Outcome:
    status: str
    note: str | None = None
    condition: dict | None = None


Check = Callable[[CoverageInput, RuleDef], Outcome]
_CHECKS: dict[str, Check] = {}


def coverage_check(name: str) -> Callable[[Check], Check]:
    def register(fn: Check) -> Check:
        _CHECKS[name] = fn
        return fn

    return register


def get_check(name: str) -> Check | None:
    from app.detection.coverage import rules  # noqa: F401  (imports register the checks)

    return _CHECKS.get(name)
