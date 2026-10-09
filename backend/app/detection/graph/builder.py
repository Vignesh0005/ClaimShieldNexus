from dataclasses import dataclass
from datetime import date

import networkx as nx


@dataclass
class ClaimEdge:
    provider_id: str
    member_id: str | None
    facility_id: str | None
    service_date: date | None
    billed: float = 0.0


@dataclass
class ReferralEdge:
    from_provider: str
    to_provider: str
    referral_date: date | None = None
    member_id: str | None = None


def build_referral_graph(referrals: list[ReferralEdge], as_of: date | None = None) -> nx.DiGraph:
    """Directed provider-to-provider graph; edge weight is the number of referrals."""
    g = nx.DiGraph()
    for r in referrals:
        if as_of and r.referral_date and r.referral_date > as_of:
            continue
        if r.from_provider == r.to_provider:
            continue
        if g.has_edge(r.from_provider, r.to_provider):
            g[r.from_provider][r.to_provider]["weight"] += 1
            if r.referral_date and r.referral_date < g[r.from_provider][r.to_provider]["first"]:
                g[r.from_provider][r.to_provider]["first"] = r.referral_date
        else:
            g.add_edge(r.from_provider, r.to_provider, weight=1, first=r.referral_date or date.min)
    return g


def build_bipartite_graph(claims: list[ClaimEdge], referrals: list[ReferralEdge], as_of: date | None = None) -> nx.Graph:
    """Providers, members and facilities as nodes; claims and referrals as edges."""
    g = nx.Graph()

    def touch(node: str, kind: str, d: date | None, billed: float = 0.0) -> None:
        if node not in g:
            g.add_node(node, type=kind, claims=0, amount=0.0, first_seen=d)
        data = g.nodes[node]
        data["claims"] += 1 if billed else 0
        data["amount"] += billed
        if d and (data["first_seen"] is None or d < data["first_seen"]):
            data["first_seen"] = d

    def link(a: str, b: str, kind: str, d: date | None) -> None:
        if g.has_edge(a, b):
            g[a][b]["weight"] += 1
            if d and (g[a][b]["date"] is None or d < g[a][b]["date"]):
                g[a][b]["date"] = d
        else:
            g.add_edge(a, b, type=kind, weight=1, date=d)

    for c in claims:
        if as_of and c.service_date and c.service_date > as_of:
            continue
        touch(c.provider_id, "provider", c.service_date, c.billed)
        if c.member_id:
            touch(c.member_id, "member", c.service_date, c.billed)
            link(c.member_id, c.provider_id, "claim", c.service_date)
        if c.facility_id:
            touch(c.facility_id, "facility", c.service_date, c.billed)
            link(c.provider_id, c.facility_id, "claim", c.service_date)
    for r in referrals:
        if as_of and r.referral_date and r.referral_date > as_of:
            continue
        touch(r.from_provider, "provider", r.referral_date)
        touch(r.to_provider, "provider", r.referral_date)
        link(r.from_provider, r.to_provider, "referral", r.referral_date)
    return g
