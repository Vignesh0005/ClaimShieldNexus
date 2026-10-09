from datetime import date

from app.detection.graph.builder import ClaimEdge, ReferralEdge, build_bipartite_graph, build_referral_graph
from app.detection.graph.referral_loops import find_loops
from app.detection.graph.visualizer import export_graph


def month_ends(start: date, end: date) -> list[date]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        out.append(min(date.fromordinal(nxt.toordinal() - 1), end))
        y, m = nxt.year, nxt.month
    return out


def snapshot(claims: list[ClaimEdge], referrals: list[ReferralEdge], as_of: date, focus: set[str] | None = None) -> dict:
    """The network exactly as it stood on a date: only claims and referrals up to then."""
    loops = find_loops(build_referral_graph(referrals, as_of))
    in_loop = {p for loop in loops for p in loop}
    graph = build_bipartite_graph(claims, referrals, as_of)
    data = export_graph(graph, in_loop=in_loop, focus=focus)
    data["as_of"] = as_of.isoformat()
    data["metrics"] = {"nodes": len(data["nodes"]), "edges": len(data["edges"]), "referral_loops": len(loops), "providers_in_loops": len(in_loop)}
    return data


def replay(claims: list[ClaimEdge], referrals: list[ReferralEdge], start: date, end: date) -> list[dict]:
    """Month-by-month metrics, showing when loops first appear."""
    frames = []
    for d in month_ends(start, end):
        loops = find_loops(build_referral_graph(referrals, d))
        frames.append({"as_of": d.isoformat(), "referral_loops": len(loops), "providers_in_loops": len({p for loop in loops for p in loop})})
    return frames
