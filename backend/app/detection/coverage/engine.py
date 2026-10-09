from dataclasses import dataclass, field

from app.core.logging import logger
from app.detection.context import ClaimData
from app.detection.coverage.loader import CoverageRuleLoader
from app.detection.coverage.registry import CONDITIONAL, FAIL, PASS, REVIEW, CoverageInput, RuleDef, get_check

COVERAGE_DISCLAIMER = "Coverage outcome only. Not a fraud determination. Subject to insurer's normal human claims decision."
COMPLIANCE_NOTICE = "Coverage rules marked 'illustrative' require compliance review before production use."
BLOCKING = ("NOT_COVERABLE", "COVERAGE_REVIEW_REQUIRED")


@dataclass
class RuleResult:
    rule_id: str
    category: str
    status: str
    source: str
    note: str | None = None
    condition: dict | None = None
    blocking: bool = False

    def to_dict(self) -> dict:
        out = {"rule_id": self.rule_id, "category": self.category, "status": self.status, "source": self.source}
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class CoverageResult:
    claim_id: str
    overall_status: str
    rule_results: list[RuleResult] = field(default_factory=list)
    conditions: list[dict] = field(default_factory=list)
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    not_fraud: bool = True
    not_denial: bool = True
    illustrative_rules_applied: int = 0

    @property
    def blocks_detection(self) -> bool:
        return self.overall_status in BLOCKING

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "overall_status": self.overall_status,
            "conditions": self.conditions,
            "rule_results": [r.to_dict() for r in self.rule_results],
            "review_required": self.review_required,
            "review_reasons": self.review_reasons,
            "not_fraud": True,
            "not_denial": True,
            "disclaimer": COVERAGE_DISCLAIMER,
            "illustrative_rules_applied": self.illustrative_rules_applied,
            "compliance_notice": COMPLIANCE_NOTICE if self.illustrative_rules_applied else None,
        }


def input_from_claim(claim: ClaimData) -> CoverageInput:
    a = claim.attributes or {}
    return CoverageInput(
        claim_id=claim.claim_id,
        plan_type=claim.plan_type,
        member_age=claim.member_age,
        policy_start_date=claim.policy_start_date,
        service_date=claim.service_date,
        procedure_codes=claim.cpt_codes,
        diagnosis_codes=claim.diagnosis_codes,
        service_location=a.get("service_location"),
        pre_auth_number=claim.pre_auth_number,
        documents_provided=a.get("documents_provided"),
        claim_type=claim.claim_type,
        total_billed=claim.total_billed,
        attributes=a,
    )


class CoverageRulesEngine:
    """Evaluates a claim against coverage rules.

    A coverage finding is never a fraud signal and never a denial. A failed rule produces
    NOT_COVERABLE, which means "a person in claims must look at this", and nothing else happens
    automatically. Rules whose on_uncertain is FLAG_FOR_REVIEW raise a review reason without
    holding the claim back from FWA detection."""

    def __init__(self, rules: list[RuleDef] | None = None):
        self.rules = rules if rules is not None else CoverageRuleLoader().load_all()

    def evaluate(self, inp: CoverageInput) -> CoverageResult:
        results: list[RuleResult] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if rule.check == "reference_only":
                continue  # recorded for reference; not evaluated automatically, so it yields no result
            check = get_check(rule.check)
            if check is None:
                logger.warning("coverage_check_missing", rule_id=rule.rule_id, check=rule.check)
                continue
            try:
                outcome = check(inp, rule)
            except Exception as exc:  # noqa: BLE001  A broken rule asks for review; it never passes silently.
                logger.error("coverage_rule_error", rule_id=rule.rule_id, error=str(exc))
                results.append(RuleResult(rule.rule_id, rule.category, REVIEW, rule.source_section, "Rule could not be evaluated; review manually.", blocking=True))
                continue
            results.append(
                RuleResult(
                    rule.rule_id, rule.category, outcome.status, rule.source_section, outcome.note, outcome.condition,
                    blocking=outcome.status == FAIL or (outcome.status == REVIEW and rule.on_uncertain == "COVERAGE_REVIEW_REQUIRED"),
                )
            )

        if any(r.status == FAIL for r in results):
            overall = "NOT_COVERABLE"
        elif any(r.status == REVIEW and r.blocking for r in results):
            overall = "COVERAGE_REVIEW_REQUIRED"
        elif any(r.status in (CONDITIONAL, REVIEW) for r in results):
            overall = "COVERABLE_WITH_CONDITIONS"
        else:
            overall = "COVERABLE"

        illustrative = sum(1 for rule in self.rules if rule.enabled and not rule.authoritative)
        reasons = [r.note or f"{r.rule_id} needs review" for r in results if r.status in (FAIL, REVIEW)]
        return CoverageResult(
            claim_id=inp.claim_id,
            overall_status=overall,
            rule_results=results,
            conditions=[r.condition for r in results if r.status == CONDITIONAL and r.condition],
            review_required=bool(reasons),
            review_reasons=reasons,
            illustrative_rules_applied=illustrative,
        )


__all__ = ["CoverageRulesEngine", "CoverageResult", "RuleResult", "input_from_claim", "PASS", "COVERAGE_DISCLAIMER"]
