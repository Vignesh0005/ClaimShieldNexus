"""Synthetic claims generator with planted billing patterns. Everything here is invented: no real
provider, member or claim is represented. Used to train the models and to seed the demo tenant."""
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from app.detection.context import ClaimData, DetectionContext, LineData, MemberInfo, PeerStats, ProviderInfo
from app.detection.ml.feature_engineering import FEATURES, build_features, to_row
from app.utils.dates import parse_date

PRICES = {
    "99212": 75, "99213": 120, "99214": 180, "99215": 260, "99203": 170, "99204": 250, "80053": 45, "85025": 30, "36415": 12,
    "93000": 55, "97110": 40, "90837": 160, "E0601": 900, "82040": 14, "82247": 14, "82310": 15, "82374": 14, "82435": 14,
    "82565": 15, "82947": 13, "84075": 15, "84132": 14, "84155": 13, "84295": 14, "84450": 15, "84460": 15, "84520": 13,
}
EM_MIX = [("99212", 0.06), ("99213", 0.56), ("99214", 0.28), ("99215", 0.10)]
SPECIALTIES = ["Cardiology", "Orthopedics", "Dermatology", "Pain management", "Physical therapy", "Laboratory", "Family medicine", "Home health"]
DX_ACUTE = ["J06.9", "M54.5", "R51.9", "L30.9", "N39.0", "S93.401A", "R10.9", "H10.9"]
DX_CHRONIC = ["I25.10", "E11.9", "I10", "J45.909", "M17.11"]
CITIES = [("Mumbai", 19.076, 72.8777), ("Delhi", 28.6139, 77.209), ("Bengaluru", 12.9716, 77.5946), ("Chennai", 13.0827, 80.2707), ("Kolkata", 22.5726, 88.3639), ("Hyderabad", 17.385, 78.4867)]
PLANS = ["individual", "family_floater", "family_floater", "group", "senior_citizen"]
RING = ["PRV-1042", "PRV-0871", "PRV-0912", "PRV-0455", "PRV-0233"]
COMPONENTS = ["82040", "82247", "82310", "82374", "82435", "82565", "82947", "84075"]


@dataclass
class SyntheticData:
    providers: list[dict] = field(default_factory=list)
    members: list[dict] = field(default_factory=list)
    facilities: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)  # chronological; "_label" and "_scheme" are training-only
    end_date: date = date(2025, 1, 10)


def _pick(r: random.Random, weighted: list[tuple[str, float]]) -> str:
    x, acc = r.random(), 0.0
    for value, weight in weighted:
        acc += weight
        if x <= acc:
            return value
    return weighted[-1][0]


def generate(seed: int = 7, n_providers: int = 60, n_members: int = 500, days: int = 180, end: date = date(2025, 1, 10), daily_rate: float = 0.28) -> SyntheticData:
    r = random.Random(seed)
    data = SyntheticData(end_date=end)
    special = {"PRV-1042": "Cardiology", "PRV-0871": "Laboratory", "PRV-0912": "Pain management", "PRV-0455": "Orthopedics", "PRV-0233": "Physical therapy", "PRV-0318": "Home health", "PRV-0764": "Family medicine"}
    ids = list(special) + [f"PRV-{2000 + i * 7:04d}" for i in range(n_providers - len(special))]
    for i, pid in enumerate(ids):
        city, lat, lng = CITIES[i % len(CITIES)]
        shared = pid in ("PRV-1042", "PRV-0871", "PRV-0912")
        data.providers.append(
            {
                "provider_id": pid, "name": f"Dr. {'XYZWVUTSRQPNMLKJHGFEDCBA'[i % 24]}{i // 24 or ''}", "specialty": special.get(pid, SPECIALTIES[i % len(SPECIALTIES)]),
                "address": "Suite 400, 12 Harbour Road" if shared else f"{10 + i} Clinic Street", "city": city, "lat": lat, "lng": lng,
                "owner_id": "OWN-77" if pid in ("PRV-1042", "PRV-0871") else None, "license_status": "active", "active": True,
            }
        )
    for i, (city, lat, lng) in enumerate(CITIES):
        data.facilities.append({"facility_id": f"FAC-{i + 1:04d}", "name": f"{city} clinic", "city": city, "lat": lat, "lng": lng, "address": f"{i + 1} Hospital Road"})
    for i in range(n_members):
        age = max(1, min(92, int(r.gauss(46, 19))))
        data.members.append(
            {
                "member_id": f"MBR-{1000 + i * 3}", "age": age, "low_income_area": r.random() < 0.18, "plan_type": "senior_citizen" if age >= 65 and r.random() < 0.5 else r.choice(PLANS[:4]),
                "policy_start_date": (end - timedelta(days=r.randint(1200, 2600))).isoformat(), "postal_code": f"{400000 + r.randint(1, 99)}",
            }
        )
    members = {m["member_id"]: m for m in data.members}
    facility_of = {p["provider_id"]: data.facilities[i % len(data.facilities)]["facility_id"] for i, p in enumerate(data.providers)}
    seq = 0

    def claim(pid: str, member_id: str, d: date, codes: list[str], *, label: int = 0, scheme: str | None = None, referrer: str | None = None, units: dict | None = None, attrs: dict | None = None, facility: str | None = None, dx: list[str] | None = None) -> dict:
        nonlocal seq
        seq += 1
        m = members[member_id]
        claim_id = f"CLM-{d.year}-{seq:05d}"
        lines = []
        for i, code in enumerate(codes):
            u = (units or {}).get(code, 1)
            billed = round(PRICES.get(code, 100) * u * r.uniform(0.95, 1.08), 2)
            lines.append({"line_id": f"{claim_id}-L{i + 1}", "cpt_code": code, "modifiers": [], "units": u, "billed_amount": billed, "paid_amount": round(billed * 0.92, 2), "service_date": d.isoformat(), "diagnosis_pointer": [1]})
        chronic = m["age"] >= 55 and r.random() < 0.5
        out = {
            "claim_id": claim_id, "member_id": member_id, "provider_id": pid, "facility_id": facility or facility_of[pid], "referring_provider_id": referrer,
            "service_date": d.isoformat(), "claim_type": "professional", "total_billed": round(sum(l["billed_amount"] for l in lines), 2),
            "total_paid": round(sum(l["paid_amount"] for l in lines), 2), "diagnosis_codes": dx or [r.choice(DX_CHRONIC if chronic else DX_ACUTE)], "lines": lines,
            "plan_type": m["plan_type"], "policy_start_date": m["policy_start_date"], "member_age": m["age"], "service_location": "IN",
            "attributes": attrs or {}, "_label": label, "_scheme": scheme,
        }
        data.claims.append(out)
        return out

    start = end - timedelta(days=days)
    member_ids = [m["member_id"] for m in data.members]
    panels = {pid: r.sample(member_ids, 60) for pid in ids}

    # Ordinary practice.
    for offset in range(days + 1):
        d = start + timedelta(days=offset)
        if d.weekday() == 6:
            continue
        for pid in ids:
            n = np.random.default_rng(seed * 100_000 + offset * 100 + ids.index(pid)).poisson(daily_rate)
            for _ in range(int(n)):
                codes = [_pick(r, EM_MIX)]
                if r.random() < 0.22:
                    codes += r.choice([["80053", "36415"], ["85025", "36415"], ["93000"]])
                referrer = r.choice(ids[10:]) if r.random() < 0.05 else None
                claim(pid, r.choice(panels[pid]), d, codes, referrer=referrer if referrer != pid else None)

    recent = lambda lo, hi: end - timedelta(days=r.randint(lo, hi))  # noqa: E731

    # Referral ring: the same members circulate among five providers.
    ring_members = r.sample(member_ids, 38)
    for i, pid in enumerate(RING):
        prev = RING[i - 1]
        for _ in range(22):
            claim(pid, r.choice(ring_members), recent(0, 75), ["99215" if pid in ("PRV-1042", "PRV-0912") else "99214"], label=1, scheme="referral_ring", referrer=prev)

    # Upcoding and a billing spike at PRV-1042.
    for _ in range(90):
        claim("PRV-1042", r.choice(ring_members), recent(0, 28), ["99215", "93000"], label=1, scheme="upcoding")

    # Duplicate billing: recent PRV-1042 claims resubmitted unchanged.
    originals = [c for c in data.claims if c["provider_id"] == "PRV-1042" and c["service_date"] >= (end - timedelta(days=9)).isoformat()][:40]
    for o in originals:
        dup = claim("PRV-1042", o["member_id"], parse_date(o["service_date"]), [l["cpt_code"] for l in o["lines"]], label=1, scheme="duplicate", dx=o["diagnosis_codes"])
        for dl, ol in zip(dup["lines"], o["lines"]):
            dl["billed_amount"], dl["paid_amount"] = ol["billed_amount"], ol["paid_amount"]
        dup["total_billed"], dup["total_paid"] = o["total_billed"], o["total_paid"]

    # Unbundling at PRV-0455.
    for _ in range(35):
        claim("PRV-0455", r.choice(panels["PRV-0455"]), recent(0, 50), ["99213", *r.sample(COMPONENTS, 6), "36415"], label=1, scheme="unbundling")

    # Excessive utilisation at PRV-0233: a handful of members seen again and again.
    for m in r.sample(panels["PRV-0233"], 5):
        for k in range(12):
            claim("PRV-0233", m, end - timedelta(days=k * 2 + r.randint(0, 1)), ["97110"], label=1, scheme="excessive_utilization", units={"97110": 4})

    # Impossible day at PRV-0871.
    for d in (end - timedelta(days=4), end - timedelta(days=11)):
        for _ in range(24):
            claim("PRV-0871", r.choice(panels["PRV-0871"]), d, ["90837"], label=1, scheme="impossible_day")

    # Services with no encounter record at PRV-0318.
    for _ in range(30):
        claim("PRV-0318", r.choice(panels["PRV-0318"]), recent(0, 40), ["99214", "E0601"], label=1, scheme="phantom", attrs={"encounter_verified": False})

    # Identity misuse: one member billed in two distant cities on the same day.
    for m in r.sample(member_ids, 8):
        d = recent(0, 30)
        claim("PRV-0764", m, d, ["99214"], label=1, scheme="identity", facility="FAC-0001")
        claim(ids[20], m, d, ["99214"], label=1, scheme="identity", facility="FAC-0002")

    data.claims.sort(key=lambda c: (c["service_date"], c["claim_id"]))
    return data


def to_claim_data(c: dict) -> ClaimData:
    return ClaimData(
        claim_id=c["claim_id"], member_id=c["member_id"], provider_id=c["provider_id"], facility_id=c.get("facility_id"),
        referring_provider_id=c.get("referring_provider_id"), service_date=parse_date(c["service_date"]), claim_type=c.get("claim_type"),
        total_billed=c["total_billed"], total_paid=c.get("total_paid") or 0.0, diagnosis_codes=c.get("diagnosis_codes", []),
        lines=[LineData(l["line_id"], l["cpt_code"], l.get("modifiers", []), l.get("units", 1), l["billed_amount"], l.get("paid_amount", 0), parse_date(l.get("service_date"))) for l in c["lines"]],
        plan_type=c.get("plan_type"), policy_start_date=parse_date(c.get("policy_start_date")), member_age=c.get("member_age"), attributes=c.get("attributes", {}),
    )


def training_matrix(data: SyntheticData | None = None) -> tuple[np.ndarray, np.ndarray]:
    X, y, _ = training_matrix_with_groups(data)
    return X, y


def training_matrix_with_groups(data: SyntheticData | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Features for every synthetic claim, built with the same code the live pipeline uses and
    with only the history that existed on each claim's service date (no look-ahead). The third
    array is each claim's provider, used to evaluate on providers held out of training."""
    data = data or generate()
    members = {m["member_id"]: m for m in data.members}
    providers = {p["provider_id"]: p for p in data.providers}
    by_provider: dict[str, list[ClaimData]] = {}
    by_member: dict[str, list[ClaimData]] = {}
    peers = PeerStats()
    X, y, groups = [], [], []
    for raw in data.claims:
        c = to_claim_data(raw)
        cutoff = c.service_date - timedelta(days=90)
        ph = [h for h in by_provider.get(c.provider_id, []) if h.service_date >= cutoff]
        mh = [h for h in by_member.get(c.member_id, []) if h.service_date >= cutoff]
        m, p = members[c.member_id], providers[c.provider_id]
        ctx = DetectionContext(claim=c, provider=ProviderInfo(c.provider_id, True, p["specialty"]), member=MemberInfo(c.member_id, True, m["age"], m["low_income_area"]), provider_history=ph, member_history=mh, peers=peers)
        X.append(to_row(build_features(ctx), FEATURES))
        y.append(raw["_label"])
        groups.append(c.provider_id)
        by_provider.setdefault(c.provider_id, []).append(c)
        by_member.setdefault(c.member_id, []).append(c)
    return np.array(X, dtype=float), np.array(y, dtype=int), np.array(groups)


def public_claim(c: dict) -> dict:
    """Strips the training-only keys before a claim is sent through the API or pipeline."""
    return {k: v for k, v in c.items() if not k.startswith("_")}
