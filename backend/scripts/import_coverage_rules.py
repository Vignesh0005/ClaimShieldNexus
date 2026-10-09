"""Imports coverage rules transcribed from the IRDAI framework document
(Health_Insurance_Coverage_Criteria_and_Rules.pdf) as the authoritative rule set.

    python -m scripts.import_coverage_rules --file transcribed_rules.json [--allow-partial]

The input is a JSON list (or {"rules": [...]}) where each rule has:
    rule_id, category, rule_name, description, source_section ("Section N \u2014 name"), check
and optionally inputs, valid_values, conditions, on_pass, on_fail, on_uncertain.
`check` names an evaluator in app/detection/coverage/rules, or "reference_only" for a rule that is
recorded and reported but not evaluated automatically.

This script never writes rule text of its own. It refuses the import unless every rule cites its
source section, and by default unless all 78 rules are present. Imported rules are marked
authoritative=true and needs_compliance_review=false, so only import a transcription that a
compliance owner has checked against the document."""
import argparse
import asyncio
import json
from pathlib import Path

from app.detection.coverage.loader import AUTHORITATIVE_FILE, AUTHORITATIVE_SOURCE, EXPECTED_AUTHORITATIVE_RULES, validate_authoritative


async def sync_database() -> int:
    from app.config import get_settings
    from app.db.seed.seed_coverage_rules import seed_coverage_rules
    from app.db.session import create_all, dispose_engine, session_scope

    if get_settings().database_url.startswith("sqlite"):
        await create_all()
    async with session_scope() as db:
        count = await seed_coverage_rules(db)
    await dispose_engine()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--allow-partial", action="store_true", help=f"Import even if fewer than {EXPECTED_AUTHORITATIVE_RULES} rules are present")
    parser.add_argument("--no-database", action="store_true", help="Write the rule file only")
    args = parser.parse_args()

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    rules = data["rules"] if isinstance(data, dict) else data
    errors = [f"{r.get('rule_id', f'rule #{i + 1}')}: {p}" for i, r in enumerate(rules) for p in validate_authoritative(r)]
    ids = [r.get("rule_id") for r in rules]
    errors += [f"duplicate rule_id {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if errors:
        raise SystemExit("Not imported. Fix these and run again:\n  " + "\n  ".join(errors))
    if len(rules) != EXPECTED_AUTHORITATIVE_RULES and not args.allow_partial:
        raise SystemExit(f"Not imported: the file has {len(rules)} rules and the document has {EXPECTED_AUTHORITATIVE_RULES}. Use --allow-partial to import a subset.")

    AUTHORITATIVE_FILE.write_text(json.dumps({"source_document": AUTHORITATIVE_SOURCE, "rules": rules}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rules)} authoritative rules to {AUTHORITATIVE_FILE}")
    if not args.no_database:
        print(f"Coverage rules now in the database: {asyncio.run(sync_database())}")


if __name__ == "__main__":
    main()
