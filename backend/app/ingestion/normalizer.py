import re
from collections import OrderedDict

from app.ingestion.field_mapping import CLAIM_FIELDS, LINE_FIELDS
from app.utils.dates import parse_date

_ICD_NO_DOT = re.compile(r"^[A-Z]\d[0-9A-Z]{2,5}$")


def normalize_icd(code: str) -> str:
    code = code.strip().upper()
    return f"{code[:3]}.{code[3:]}" if _ICD_NO_DOT.match(code) and "." not in code else code


def _amount(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    return float(cleaned) if cleaned not in ("", "-", ".") else None


def _list(value) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in re.split(r"[,;| ]+", str(value)) if v.strip()]


def normalize_line(line: dict, index: int, claim_id: str) -> dict:
    out = {k: v for k, v in line.items() if k in LINE_FIELDS or k == "service_date"}
    out["line_id"] = str(line.get("line_id") or f"{claim_id}-L{index + 1}")
    if out.get("cpt_code") is not None:
        out["cpt_code"] = str(out["cpt_code"]).strip().upper()
    out["modifiers"] = [m.upper() for m in _list(line.get("modifiers"))]
    out["units"] = int(_amount(line.get("units")) or 1)
    out["billed_amount"] = _amount(line.get("billed_amount")) or 0.0
    out["paid_amount"] = _amount(line.get("paid_amount")) or 0.0
    d = parse_date(line.get("service_date"))
    out["service_date"] = d.isoformat() if d else None
    pointers = line.get("diagnosis_pointer")
    out["diagnosis_pointer"] = [int(p) for p in (pointers if isinstance(pointers, list) else _list(pointers)) if str(p).isdigit()]
    return out


def normalize_claim(record: dict) -> dict:
    """Canonical shape and types. Unknown top-level fields are kept under `attributes` so coverage
    rules can use them and nothing a tenant sends is silently dropped."""
    out: dict = {k: v for k, v in record.items() if k in CLAIM_FIELDS}
    attributes = dict(record.get("attributes") or {})
    attributes.update({k: v for k, v in record.items() if k not in CLAIM_FIELDS and v not in (None, "")})
    out["attributes"] = attributes
    for key in ("claim_id", "member_id", "provider_id", "facility_id", "referring_provider_id", "pre_auth_number", "plan_type"):
        if out.get(key) is not None:
            out[key] = str(out[key]).strip() or None
    if out.get("plan_type"):
        out["plan_type"] = out["plan_type"].lower().replace(" ", "_")
    for key in ("service_date", "policy_start_date"):
        d = parse_date(out.get(key))
        out[key] = d.isoformat() if d else None
    out["diagnosis_codes"] = [normalize_icd(c) for c in _list(out.get("diagnosis_codes"))]
    claim_id = out.get("claim_id") or ""
    out["lines"] = [normalize_line(l, i, claim_id) for i, l in enumerate(out.get("lines") or []) if isinstance(l, dict)]
    for l in out["lines"]:
        l["service_date"] = l["service_date"] or out["service_date"]
    billed = _amount(out.get("total_billed"))
    out["total_billed"] = billed if billed is not None else round(sum(l["billed_amount"] for l in out["lines"]), 2)
    paid = _amount(out.get("total_paid"))
    out["total_paid"] = paid if paid is not None else round(sum(l["paid_amount"] for l in out["lines"]), 2)
    if out.get("member_age") not in (None, ""):
        out["member_age"] = int(_amount(out["member_age"]) or 0)
    else:
        out.pop("member_age", None)
    return out


def rows_to_claims(rows: list[dict]) -> list[dict]:
    """Groups flat rows (one row per service line, as in a CSV extract) into claims with lines."""
    claims: "OrderedDict[str, dict]" = OrderedDict()
    for row in rows:
        claim_id = str(row.get("claim_id") or "").strip()
        if not claim_id:
            continue
        claim = claims.setdefault(claim_id, {**{k: v for k, v in row.items() if k not in LINE_FIELDS}, "lines": [], "total_billed": None, "total_paid": None})
        if row.get("cpt_code"):
            claim["lines"].append({k: row.get(k) for k in LINE_FIELDS | {"service_date"} if row.get(k) not in (None, "")})
        dx = _list(row.get("diagnosis_codes"))
        claim["diagnosis_codes"] = list(dict.fromkeys(_list(claim.get("diagnosis_codes")) + dx))
    return list(claims.values())
