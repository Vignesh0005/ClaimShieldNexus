import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFound
from app.detection.graph.builder import ClaimEdge, ReferralEdge, build_bipartite_graph, build_referral_graph
from app.detection.graph.centrality import provider_centrality
from app.detection.graph.communities import detect_communities
from app.detection.graph.ownership import ownership_groups
from app.detection.graph.referral_loops import find_loops, loop_referral_count
from app.detection.graph.shared_address import shared_address_groups
from app.detection.graph.time_travel import replay, snapshot
from app.detection.graph.visualizer import export_graph
from app.models import Claim, GraphSnapshot, Provider, Referral

MAX_EDGES = 100_000


async def load_edges(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[list[ClaimEdge], list[ReferralEdge]]:
    # One row per provider-member-facility-day keeps the graph small without losing any edge.
    rows = await db.execute(
        select(Claim.provider_id, Claim.member_id, Claim.facility_id, Claim.service_date, func.sum(Claim.total_billed))
        .where(Claim.tenant_id == tenant_id, Claim.provider_id.isnot(None))
        .group_by(Claim.provider_id, Claim.member_id, Claim.facility_id, Claim.service_date)
        .limit(MAX_EDGES)
    )
    claims = [ClaimEdge(p, m, f, d, float(b or 0)) for p, m, f, d, b in rows.all()]
    refs = await db.execute(select(Referral.from_provider_id, Referral.to_provider_id, Referral.referral_date, Referral.member_id).where(Referral.tenant_id == tenant_id).limit(MAX_EDGES))
    return claims, [ReferralEdge(a, b, d, m) for a, b, d, m in refs.all()]


def _range(claims: list[ClaimEdge], referrals: list[ReferralEdge]) -> dict:
    dates = [c.service_date for c in claims if c.service_date] + [r.referral_date for r in referrals if r.referral_date]
    return {"from": min(dates).isoformat() if dates else None, "to": max(dates).isoformat() if dates else None}


async def global_graph(db: AsyncSession, tenant_id: uuid.UUID, as_of: date | None = None) -> dict:
    claims, referrals = await load_edges(db, tenant_id)
    loops = find_loops(build_referral_graph(referrals, as_of))
    in_loop = {p for loop in loops for p in loop}
    data = export_graph(build_bipartite_graph(claims, referrals, as_of), in_loop=in_loop)
    data.update(range=_range(claims, referrals), referral_loops=len(loops))
    return data


async def node_network(db: AsyncSession, tenant_id: uuid.UUID, node_id: str, as_of: date | None = None) -> dict:
    claims, referrals = await load_edges(db, tenant_id)
    graph = build_bipartite_graph(claims, referrals, as_of)
    if node_id not in graph:
        raise NotFound(f"'{node_id}' has no claims or referrals in this tenant.")
    loops = find_loops(build_referral_graph(referrals, as_of))
    data = export_graph(graph, in_loop={p for loop in loops for p in loop}, focus={node_id})
    data.update(center_id=node_id, range=_range(claims, referrals))
    return data


async def clusters(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    claims, referrals = await load_edges(db, tenant_id)
    graph = build_bipartite_graph(claims, referrals)
    providers = (await db.execute(select(Provider.provider_id, Provider.address, Provider.owner_id).where(Provider.tenant_id == tenant_id))).all()
    return {
        "clusters": detect_communities(graph)[:50],
        "central_providers": provider_centrality(graph),
        "shared_addresses": shared_address_groups({p: a for p, a, _ in providers}),
        "shared_ownership": ownership_groups({p: o for p, _, o in providers}),
    }


async def referral_loops(db: AsyncSession, tenant_id: uuid.UUID) -> dict:
    _, referrals = await load_edges(db, tenant_id)
    g = build_referral_graph(referrals)
    loops = sorted(find_loops(g), key=lambda loop: loop_referral_count(g, loop), reverse=True)
    out = []
    for loop in loops[:50]:
        n, dollars, members = (
            await db.execute(select(func.count(), func.coalesce(func.sum(Claim.total_billed), 0), func.count(func.distinct(Claim.member_id))).where(Claim.tenant_id == tenant_id, Claim.provider_id.in_(loop)))
        ).one()
        out.append({"loop_members": loop, "size": len(loop), "referrals_in_loop": loop_referral_count(g, loop), "total_claims": int(n), "total_dollars": float(dollars), "members_affected": int(members)})
    return {"loops": out, "total": len(loops), "note": "A referral loop is a pattern to review. Integrated care groups legitimately refer in loops."}


async def time_travel(db: AsyncSession, tenant_id: uuid.UUID, as_of: date | None, provider_id: str | None = None, store: bool = False) -> dict:
    claims, referrals = await load_edges(db, tenant_id)
    rng = _range(claims, referrals)
    if rng["to"] is None:
        return {"nodes": [], "edges": [], "frames": [], "range": rng, "as_of": None}
    start, end = date.fromisoformat(rng["from"]), date.fromisoformat(rng["to"])
    as_of = min(as_of or end, end)
    data = snapshot(claims, referrals, as_of, focus={provider_id} if provider_id else None)
    data.update(range=rng, frames=replay(claims, referrals, start, end))
    if store:
        db.add(GraphSnapshot(tenant_id=tenant_id, snapshot_date=as_of, nodes=data["nodes"], edges=data["edges"], metrics=data["metrics"]))
        await db.flush()
    return data


async def geo_conflicts(db: AsyncSession, tenant_id: uuid.UUID, limit: int = 200) -> list[dict]:
    """Pairs of claims that place one member at two distant facilities on the same day, taken from
    stored impossible-geography findings. Claims carry dates, not times, so no travel speed is given."""
    from app.models import Case, DetectionSignal, Facility

    rows = (
        await db.execute(
            select(DetectionSignal, Claim)
            .join(Claim, Claim.id == DetectionSignal.claim_id)
            .where(DetectionSignal.tenant_id == tenant_id, Claim.tenant_id == tenant_id, DetectionSignal.rule_name == "impossible_timing")
            .order_by(Claim.service_date.desc())
            .limit(2000)
        )
    ).all()
    found = [(s, c) for s, c in rows if (s.evidence or {}).get("pattern") == "impossible_geography"]
    other_ids = {s.evidence.get("other_claim_id") for s, _ in found}
    others = {c.claim_id: c for c in (await db.execute(select(Claim).where(Claim.tenant_id == tenant_id, Claim.claim_id.in_(other_ids)))).scalars()} if other_ids else {}
    facility_ids = {c.facility_id for _, c in found} | {o.facility_id for o in others.values()}
    facilities = {f.facility_id: f for f in (await db.execute(select(Facility).where(Facility.tenant_id == tenant_id, Facility.facility_id.in_(facility_ids)))).scalars()} if facility_ids else {}
    case_ids = {c.case_ref for _, c in found if c.case_ref}
    cases = dict((await db.execute(select(Case.id, Case.case_id).where(Case.tenant_id == tenant_id, Case.id.in_(case_ids)))).all()) if case_ids else {}

    def place(claim) -> dict | None:
        f = facilities.get(claim.facility_id)
        if f is None or f.lat is None or f.lng is None:
            return None
        return {"claim_id": claim.claim_id, "provider_id": claim.provider_id, "facility_id": f.facility_id, "city": f.city or f.facility_id, "lat": f.lat, "lng": f.lng}

    out, seen = [], set()
    for s, c in found:
        other = others.get(s.evidence.get("other_claim_id"))
        key = (c.member_id, c.service_date)
        if other is None or key in seen:
            continue
        a, b = place(other), place(c)
        if a is None or b is None:
            continue
        seen.add(key)
        out.append({"id": f"{c.claim_id}:{s.signal_id}", "subject": c.member_id, "subject_type": "member", "date": c.service_date, "case_id": cases.get(c.case_ref), "severity": c.severity, "distance_km": s.evidence.get("distance_km"), "confidence": s.confidence, "a": a, "b": b})
        if len(out) >= limit:
            break
    return out
