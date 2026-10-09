from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detection.coverage.loader import CoverageRuleLoader
from app.models import CoverageRule


async def seed_coverage_rules(db: AsyncSession) -> int:
    """Loads the bundled coverage rules into the coverage_rules table. Existing rows keep their
    `enabled` flag, so a rule switched off for a deployment stays off after a re-seed."""
    existing = {r.rule_id: r for r in (await db.execute(select(CoverageRule))).scalars().all()}
    for rule in CoverageRuleLoader().load_all():
        row = existing.get(rule.rule_id)
        if row is None:
            row = CoverageRule(rule_id=rule.rule_id, enabled=rule.enabled)
            db.add(row)
        row.category, row.rule_name, row.description, row.check = rule.category, rule.rule_name, rule.description, rule.check
        row.source_section, row.source_document = rule.source_section, rule.source_document
        row.inputs, row.valid_values, row.conditions = rule.inputs, rule.valid_values, rule.conditions
        row.on_pass, row.on_fail, row.on_uncertain = rule.on_pass, rule.on_fail, rule.on_uncertain
        row.not_fraud = row.not_denial = True
        row.authoritative, row.needs_compliance_review, row.disclaimer = rule.authoritative, rule.needs_compliance_review, rule.disclaimer or None
    await db.flush()
    return len(CoverageRuleLoader().load_all())
