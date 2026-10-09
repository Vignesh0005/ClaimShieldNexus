from collections.abc import AsyncIterator

from app.ingestion.adapters.base import IngestionAdapter


def _ref(reference: dict | None) -> str | None:
    """'Patient/MBR-8821' -> 'MBR-8821'. Falls back to the identifier value."""
    if not reference:
        return None
    if reference.get("reference"):
        return reference["reference"].split("/")[-1]
    return (reference.get("identifier") or {}).get("value")


def _code(concept: dict | None) -> str | None:
    for coding in (concept or {}).get("coding", []):
        if coding.get("code"):
            return coding["code"]
    return None


def claim_from_fhir(resource: dict) -> dict:
    """Maps a FHIR R4 Claim resource to the canonical claim dict. Covers the elements detection
    uses (patient, provider, facility, diagnoses, items, totals); extensions are ignored."""
    identifiers = resource.get("identifier") or []
    claim_id = (identifiers[0].get("value") if identifiers else None) or resource.get("id")
    period = resource.get("billablePeriod") or {}
    lines = []
    for i, item in enumerate(resource.get("item") or []):
        net = (item.get("net") or {}).get("value")
        unit_price = (item.get("unitPrice") or {}).get("value")
        quantity = int((item.get("quantity") or {}).get("value") or 1)
        lines.append(
            {
                "line_id": f"{claim_id}-L{item.get('sequence', i + 1)}",
                "cpt_code": _code(item.get("productOrService")),
                "modifiers": [m for m in (_code(c) for c in item.get("modifier") or []) if m],
                "units": quantity,
                "billed_amount": net if net is not None else (unit_price or 0) * quantity,
                "service_date": item.get("servicedDate") or (item.get("servicedPeriod") or {}).get("start"),
                "diagnosis_pointer": item.get("diagnosisSequence") or [],
            }
        )
    return {
        "claim_id": claim_id,
        "member_id": _ref(resource.get("patient")),
        "provider_id": _ref(resource.get("provider")),
        "facility_id": _ref(resource.get("facility")),
        "referring_provider_id": _ref(resource.get("referral")),
        "service_date": period.get("start") or (lines[0]["service_date"] if lines else None) or resource.get("created"),
        "claim_type": _code(resource.get("type")) or "professional",
        "total_billed": (resource.get("total") or {}).get("value"),
        "diagnosis_codes": [c for c in (_code(d.get("diagnosisCodeableConcept")) for d in resource.get("diagnosis") or []) if c],
        "lines": lines,
    }


class FHIRAdapter(IngestionAdapter):
    """Accepts a single Claim resource or a Bundle containing Claim resources."""

    name = "fhir"

    def __init__(self, payload: dict):
        self.payload = payload

    def parse(self) -> list[dict]:
        if self.payload.get("resourceType") == "Bundle":
            resources = [e.get("resource") or {} for e in self.payload.get("entry") or []]
        else:
            resources = [self.payload]
        return [claim_from_fhir(r) for r in resources if r.get("resourceType") == "Claim"]

    async def records(self) -> AsyncIterator[dict]:
        for claim in self.parse():
            yield claim
