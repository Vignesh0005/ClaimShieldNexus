"""Exports the coverage rules as JSON or a Markdown table for review by a compliance team.

    python -m scripts.export_coverage_rules [--format markdown] [--out coverage_rules.md]"""
import argparse
import json
from pathlib import Path

from app.detection.coverage.loader import CoverageRuleLoader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--out")
    args = parser.parse_args()

    rules = CoverageRuleLoader().load_all()
    if args.format == "json":
        text = json.dumps([r.__dict__ for r in rules], indent=2, ensure_ascii=False)
    else:
        rows = ["| Rule ID | Category | Rule | Source | If uncertain |", "|---|---|---|---|---|"]
        rows += [f"| {r.rule_id} | {r.category} | {r.rule_name}: {r.description} | {r.source_section} | {r.on_uncertain} |" for r in rules]
        text = f"# Coverage rules ({len(rules)})\n\n{rules[0].source_document}\n\n" + "\n".join(rows) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {len(rules)} rules to {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
