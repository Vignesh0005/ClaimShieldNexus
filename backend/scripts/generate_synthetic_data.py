"""Writes synthetic claims to disk as JSON (API format) and CSV (one row per service line).

    python -m scripts.generate_synthetic_data --out data/synthetic [--days 120] [--labels]

Everything is invented. `--labels` keeps the planted-pattern labels for model evaluation; leave
it off for files you intend to ingest."""
import argparse
import csv
import json
from datetime import date
from pathlib import Path

from app.db.seed.synthetic import generate, public_claim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/synthetic")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--labels", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = generate(seed=args.seed, days=args.days, end=date.today())
    claims = data.claims if args.labels else [public_claim(c) for c in data.claims]
    (out / "claims.json").write_text(json.dumps({"claims": claims}, indent=1), encoding="utf-8")
    for name in ("providers", "members", "facilities"):
        (out / f"{name}.json").write_text(json.dumps(getattr(data, name), indent=1), encoding="utf-8")
    with (out / "claims.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["claim_id", "member_id", "provider_id", "facility_id", "referring_provider_id", "service_date", "cpt_code", "units", "billed_amount", "paid_amount", "diagnosis_codes", "plan_type", "policy_start_date", "member_age"])
        for c in data.claims:
            for line in c["lines"]:
                writer.writerow([c["claim_id"], c["member_id"], c["provider_id"], c["facility_id"], c["referring_provider_id"] or "", c["service_date"], line["cpt_code"], line["units"], line["billed_amount"], line["paid_amount"], " ".join(c["diagnosis_codes"]), c["plan_type"], c["policy_start_date"], c["member_age"]])
    planted = sum(c["_label"] for c in data.claims)
    print(f"Wrote {len(data.claims)} claims ({planted} with planted patterns), {len(data.providers)} providers and {len(data.members)} members to {out}/")


if __name__ == "__main__":
    main()
