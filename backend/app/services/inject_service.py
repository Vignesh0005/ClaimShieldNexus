"""Demo only: sends a synthetic billing pattern through the real pipeline and reports which
detectors flagged it. Available to demo tenants; every injected record is clearly labelled."""
import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditLogger
from app.core.cache import cache
from app.core.exceptions import Forbidden, ValidationFailed
from app.core.security import Principal
from app.models import Facility, Member, Provider, Tenant
from app.services import claim_service
from app.utils.codes import TYPICAL_AMOUNTS

SCHEMES = {
    "phantom_billing": "Services billed with no matching encounter record",
    "duplicate_billing": "The same service submitted twice",
    "upcoding": "Highest-level visit codes billed far more often than peers",
    "unbundling": "Panel components billed one by one",
    "impossible_day": "More treatment time billed in a day than is plausible",
    "referral_ring": "Providers referring the same members in a closed loop",
    "dme_fraud": "Equipment billed with no prior visit",
    "identity_misuse": "One member billed in two distant cities on the same day",
    "units_cap": "Far more units of a service than one day allows",
    "amount_outlier": "A routine service billed at many times its usual amount",
    "diagnosis_procedure_mismatch": "A procedure billed with a diagnosis it does not fit",
    "demographic_mismatch": "A service that does not fit the member's gender",
    "peer_outlier": "A provider seeing each member far more often than its peers",
    "split_billing": "One service billed in parts on consecutive days",
    "modifier_overuse": "A distinct-service modifier on almost every line",
    "new_provider_burst": "A new provider submitting a large volume of claims",
    "provider_shopping": "One member obtaining the same service from many providers",
}
# Schemes that compare a provider with its peers. They bring their own specialty and peer group so
# the result does not depend on what else the tenant holds.
PEER_SCHEMES = {"peer_outlier", "modifier_overuse", "new_provider_burst"}
ALIASES = {"phantom": "phantom_billing", "duplicate": "duplicate_billing", "dme": "dme_fraud", "identity": "identity_misuse"}
COMPONENTS = ["82040", "82247", "82310", "82374", "82435", "82565"]


class _Builder:
    def __init__(self, tag: str):
        self.tag, self.n, self.today = tag, 0, date.today()

    def claim(self, provider: str, member: str, codes: list[str], *, day: date | None = None, referrer: str | None = None, attrs: dict | None = None, facility: str | None = None, amount: float | None = 240.0, units: int = 1, dx: list[str] | None = None, modifiers: list[str] | None = None, age: int = 71) -> dict:
        """`amount` is billed on every line; pass None to bill each code at its usual amount."""
        self.n += 1
        d = (day or self.today).isoformat()
        cid = f"CLM-INJ-{self.tag}-{self.n:03d}"
        billed = [amount if amount is not None else float(TYPICAL_AMOUNTS.get(c, 100)) for c in codes]
        lines = [{"line_id": f"{cid}-L{i + 1}", "cpt_code": c, "modifiers": modifiers or [], "units": units, "billed_amount": billed[i], "paid_amount": round(billed[i] * 0.9, 2), "service_date": d, "diagnosis_pointer": [1]} for i, c in enumerate(codes)]
        return {
            "claim_id": cid, "member_id": member, "provider_id": provider, "facility_id": facility, "referring_provider_id": referrer, "service_date": d,
            "claim_type": "professional", "total_billed": round(sum(billed), 2), "diagnosis_codes": dx or ["M54.5"], "lines": lines, "plan_type": "family_floater",
            "policy_start_date": (self.today - timedelta(days=1500)).isoformat(), "member_age": age, "service_location": "IN", "attributes": {"injected_demo": True, **(attrs or {})},
        }

    def peers(self, provider: str, member: str, codes: list[str]) -> list[dict]:
        """Five established providers with ten ordinary claims each, 35 to 79 days ago."""
        return [self.claim(f"{provider}-PEER{k}", f"{member}-P{k}-{i}", codes, day=self.today - timedelta(days=79 - 4 * i - k), amount=None) for k in range(5) for i in range(10)]


def _build(scheme: str, tag: str) -> list[dict]:
    """Claims for a scheme, in the order to ingest. The last one is the claim that is reported on;
    the earlier ones give the detectors the history a real pattern would have."""
    b = _Builder(tag)
    p, m = f"PRV-INJ-{tag}", f"MBR-INJ-{tag}"
    if scheme == "phantom_billing":
        return [b.claim(p, m, ["99214"], attrs={"encounter_verified": False})]
    if scheme == "duplicate_billing":
        return [b.claim(p, m, ["99215"]), b.claim(p, m, ["99215"])]
    if scheme == "upcoding":
        # Oldest first: detectors only look at history up to each claim's own service date.
        return [b.claim(p, f"{m}-{i}", ["99215"], day=b.today - timedelta(days=12 - i), amount=260) for i in range(13)]
    if scheme == "unbundling":
        return [b.claim(p, m, COMPONENTS, amount=15)]
    if scheme == "impossible_day":
        return [b.claim(p, f"{m}-{i}", ["90837"], amount=160) for i in range(18)]
    if scheme == "referral_ring":
        ring = [f"{p}-{k}" for k in "ABCD"]
        out = []
        for _ in range(3):
            for i, provider in enumerate(ring):
                out.append(b.claim(provider, f"{m}-{len(out) % 6}", ["99214"], referrer=ring[i - 1], day=b.today - timedelta(days=11 - len(out))))
        return out
    if scheme == "dme_fraud":
        return [b.claim(p, m, ["E0601"], amount=900)]
    if scheme == "identity_misuse":
        return [b.claim(f"{p}-A", m, ["99214"], facility=f"FAC-INJ-{tag}-A"), b.claim(f"{p}-B", m, ["99214"], facility=f"FAC-INJ-{tag}-B")]
    if scheme == "units_cap":
        return [b.claim(p, m, ["97112"], amount=2100, units=50)]
    if scheme == "amount_outlier":
        return [b.claim(p, m, ["99213"], amount=156_789)]
    if scheme == "diagnosis_procedure_mismatch":
        return [b.claim(p, m, ["29881"], amount=None, dx=["H10.9"])]
    if scheme == "demographic_mismatch":
        return [b.claim(p, m, ["55700"], amount=900, dx=["R97.20"], attrs={"member_gender": "F"}, age=58)]
    if scheme == "split_billing":
        return [b.claim(p, m, ["99213"], day=b.today - timedelta(days=1), amount=60), b.claim(p, m, ["99213"], amount=60)]
    if scheme == "provider_shopping":
        return [b.claim(f"{p}-{k}", m, ["99213"], day=b.today - timedelta(days=2 * (8 - i)), amount=None) for i, k in enumerate("ABCDEFGHI")]
    if scheme == "peer_outlier":
        # Thirty visits spread over five members in sixty days, against peers who see a member once.
        return b.peers(p, m, ["99213"]) + [b.claim(p, f"{m}-{i % 5}", ["99213"], day=b.today - timedelta(days=59 - 2 * i), amount=None) for i in range(30)]
    if scheme == "modifier_overuse":
        codes = ["99213", "85025", "36415", "93000"]
        return b.peers(p, m, codes) + [b.claim(p, f"{m}-{i}", codes, day=b.today - timedelta(days=7 - i), amount=None, modifiers=["59"]) for i in range(8)]
    if scheme == "new_provider_burst":
        return b.peers(p, m, ["99213"]) + [b.claim(p, f"{m}-{i}", ["99213"], day=b.today - timedelta(days=8 - i // 4), amount=None) for i in range(36)]
    raise ValidationFailed(f"Unknown scheme '{scheme}'.", available=list(SCHEMES))


async def inject(db: AsyncSession, tenant: Tenant, scheme: str, principal: Principal, request=None) -> dict:
    if not tenant.is_demo:
        raise Forbidden("Test schemes can only be injected into a demo tenant.")
    scheme = ALIASES.get(scheme, scheme)
    if scheme not in SCHEMES:
        raise ValidationFailed(f"Unknown scheme '{scheme}'.", available=list(SCHEMES))
    tag = uuid.uuid4().hex[:6].upper()
    claims = _build(scheme, tag)

    specialty = f"Injected demo specialty {tag}" if scheme in PEER_SCHEMES else "Family medicine"

    # Reference data, so the injected IDs look like ordinary known providers and members and the
    # only thing unusual about the claims is the pattern itself.
    for provider_id in {c["provider_id"] for c in claims} | {c["referring_provider_id"] for c in claims if c["referring_provider_id"]}:
        db.add(Provider(tenant_id=tenant.id, provider_id=provider_id, name="Injected demo provider", specialty=specialty, address=f"Demo address {provider_id}"))
    for member_id in {c["member_id"] for c in claims}:
        db.add(Member(tenant_id=tenant.id, member_id=member_id, age=71))
    if scheme == "identity_misuse":
        db.add(Facility(tenant_id=tenant.id, facility_id=f"FAC-INJ-{tag}-A", name="Injected demo clinic A", city="Mumbai", lat=19.076, lng=72.8777))
        db.add(Facility(tenant_id=tenant.id, facility_id=f"FAC-INJ-{tag}-B", name="Injected demo clinic B", city="Delhi", lat=28.6139, lng=77.209))
    await db.flush()

    result = None
    for i, record in enumerate(claims):
        if scheme in PEER_SCHEMES and i == len(claims) - 1:
            # Peer figures are cached for a few minutes; the reported claim must see the whole set.
            await cache.delete(f"peer-providers:{tenant.id}:{specialty}")
            await cache.delete(f"tenant-first-seen:{tenant.id}")
        _, _, result = await claim_service.ingest_record(db, tenant, record, source="inject", process=True, principal=principal)
    assert result is not None
    flags = []
    similar = next((s.evidence.get("similar_cases", []) for s in result.signals if s.detector == "similarity"), [])
    for s in (s for s in result.signals if s.detector != "similarity"):
        entry = {"detector": s.detector}
        if s.detector == "rule":
            entry.update(rule_name=s.name, confidence=s.confidence)
        elif s.detector == "ml":
            entry.update(model=s.name, score=s.score)
        else:
            entry.update(pattern=s.name, score=s.score)
        flags.append(entry)
    await AuditLogger(db).log("demo.scheme_injected", "claim", result.claim_id, principal=principal, details={"scheme": scheme, "claims_created": len(claims), "flags": len(flags)}, request=request)
    return {
        "claim_id": result.claim_id,
        "scheme": scheme,
        "caught": bool(flags),
        "latency_ms": result.processing_time_ms,
        "caught_by": list(dict.fromkeys(f["detector"] for f in flags)),
        "flags": flags,
        "risk_score": result.risk.risk_score if result.risk else None,
        "composite_risk": result.risk.composite_risk if result.risk else None,
        "max_rule_confidence": result.risk.max_rule_confidence if result.risk else None,
        "case_opening_reason": result.case_opening_reason,
        "case_id": result.case_id,
        "similar_cases": similar,
        # A flagged claim that meets none of the case-opening tiers is recorded without a case.
        "routed": result.case_id is not None,
        "claims_created": len(claims),
        "note": "Synthetic claims created for this demonstration. No real provider or member is involved.",
    }
