from fastapi import APIRouter, Depends

from app.core.exceptions import NotFound
from app.deps import Ctx, require
from app.detection.coverage.engine import COMPLIANCE_NOTICE, CoverageRulesEngine
from app.detection.coverage.loader import AUTHORITATIVE_SOURCE, EXPECTED_AUTHORITATIVE_RULES, CoverageRuleLoader
from app.utils.codes import REFERENCE_DATA
from app.detection.coverage.registry import CoverageInput
from app.detection.pipeline import coverage_rules
from app.schemas.coverage import CoverageEvaluateIn

router = APIRouter(prefix="/coverage", tags=["coverage"])


def _rule(r) -> dict:
    return {
        "rule_id": r.rule_id, "category": r.category, "rule_name": r.rule_name, "description": r.description, "source_section": r.source_section,
        "source_document": r.source_document, "inputs": r.inputs, "valid_values": r.valid_values, "conditions": r.conditions,
        "on_pass": r.on_pass, "on_fail": r.on_fail, "on_uncertain": r.on_uncertain, "not_fraud": True, "not_denial": True, "enabled": r.enabled,
        "authoritative": r.authoritative, "needs_compliance_review": r.needs_compliance_review, "disclaimer": r.disclaimer or None,
    }


@router.get("/rules", summary="List coverage rules")
async def list_rules(category: str | None = None, authoritative: bool | None = None, ctx: Ctx = Depends(require("coverage:read"))):
    """`authoritative=true` returns only rules transcribed from the source document;
    `authoritative=false` returns only illustrative rules; omit it for all rules."""
    rules = [r for r in await coverage_rules(ctx.db) if (not category or r.category == category) and (authoritative is None or r.authoritative == authoritative)]
    illustrative = sum(1 for r in rules if not r.authoritative)
    return {"rules": [_rule(r) for r in rules], "total": len(rules), "illustrative": illustrative, "notice": COMPLIANCE_NOTICE if illustrative else None}


@router.get("/compliance-report", summary="Authoritative vs illustrative rules and reference data")
async def compliance_report(ctx: Ctx = Depends(require("coverage:read"))):
    rules = await coverage_rules(ctx.db)
    authoritative = [r for r in rules if r.authoritative]
    illustrative = [r for r in rules if not r.authoritative]
    by_category: dict[str, dict] = {}
    for r in rules:
        entry = by_category.setdefault(r.category, {"category": r.category, "authoritative": 0, "illustrative": 0})
        entry["authoritative" if r.authoritative else "illustrative"] += 1
    loaded = len(authoritative)
    return {
        "coverage_rules": {"total": len(rules), "authoritative": loaded, "illustrative": len(illustrative), "needs_compliance_review": sum(1 for r in rules if r.needs_compliance_review)},
        "authoritative_source": {
            "document": AUTHORITATIVE_SOURCE,
            "expected_rules": EXPECTED_AUTHORITATIVE_RULES,
            "loaded_rules": loaded,
            "status": "complete" if loaded >= EXPECTED_AUTHORITATIVE_RULES else ("partial" if loaded else "not_loaded"),
            "note": None if loaded >= EXPECTED_AUTHORITATIVE_RULES else f"{loaded} of {EXPECTED_AUTHORITATIVE_RULES} rules from the source document are loaded. Rules are imported with scripts/import_coverage_rules.py once the document's rules have been transcribed; none are invented.",
        },
        "by_category": sorted(by_category.values(), key=lambda c: c["category"]),
        "rules_needing_review": [{"rule_id": r.rule_id, "rule_name": r.rule_name, "source_section": r.source_section, "disclaimer": r.disclaimer or None} for r in rules if r.needs_compliance_review],
        "reference_data": REFERENCE_DATA,
        "notice": COMPLIANCE_NOTICE if illustrative else None,
    }


@router.get("/rules/{rule_id}", summary="Coverage rule detail")
async def get_rule(rule_id: str, ctx: Ctx = Depends(require("coverage:read"))):
    for r in await coverage_rules(ctx.db):
        if r.rule_id == rule_id:
            return _rule(r)
    raise NotFound(f"Coverage rule '{rule_id}' not found.")


@router.post("/evaluate", summary="Evaluate a claim against coverage rules")
async def evaluate(body: CoverageEvaluateIn, ctx: Ctx = Depends(require("coverage:read"))):
    codes = list(dict.fromkeys(([body.procedure_code] if body.procedure_code else []) + body.procedure_codes))
    inp = CoverageInput(
        claim_id=body.claim_id, plan_type=body.plan_type, member_age=body.member_age, policy_start_date=body.policy_start_date,
        service_date=body.service_date, procedure_codes=codes, diagnosis_codes=[d.upper() for d in body.diagnosis_codes],
        service_location=body.service_location, pre_auth_number=body.pre_auth_number, documents_provided=body.documents_provided,
        claim_type=body.claim_type, total_billed=body.total_billed, attributes=body.attributes,
    )
    return CoverageRulesEngine(await coverage_rules(ctx.db)).evaluate(inp).to_dict()


@router.get("/plans", summary="List plan types")
async def list_plans(ctx: Ctx = Depends(require("coverage:read"))):
    return {"plans": CoverageRuleLoader().plans()}


@router.get("/plans/{plan_type}", summary="Plan detail")
async def get_plan(plan_type: str, ctx: Ctx = Depends(require("coverage:read"))):
    for plan in CoverageRuleLoader().plans():
        if plan["plan_type"] == plan_type:
            return plan
    raise NotFound(f"Plan type '{plan_type}' not found.")
