import networkx as nx

MIN_LOOP, MAX_LOOP = 3, 8


def find_loops(g: nx.DiGraph, min_edge_weight: int = 2, limit: int = 200) -> list[list[str]]:
    """Closed referral cycles of 3 to 8 providers where every hop carried at least
    min_edge_weight referrals. One-off referrals in a circle are ordinary; repeated ones are the
    pattern worth reviewing. A loop is not evidence of wrongdoing: integrated care groups refer in
    circles legitimately, which the evidence limitations always state."""
    strong = nx.DiGraph((u, v, d) for u, v, d in g.edges(data=True) if d.get("weight", 1) >= min_edge_weight)
    loops: list[list[str]] = []
    for cycle in nx.simple_cycles(strong, length_bound=MAX_LOOP):
        if len(cycle) >= MIN_LOOP:
            start = cycle.index(min(cycle))  # canonical rotation so the same loop is reported one way
            loops.append(cycle[start:] + cycle[:start])
            if len(loops) >= limit:
                break
    return loops


def loops_for_provider(g: nx.DiGraph, provider_id: str, min_edge_weight: int = 2) -> list[list[str]]:
    if provider_id not in g:
        return []
    # Restrict the search to the provider's strongly connected component: cycles cannot leave it.
    for component in nx.strongly_connected_components(g):
        if provider_id in component:
            if len(component) < MIN_LOOP:
                return []
            return [loop for loop in find_loops(g.subgraph(component), min_edge_weight) if provider_id in loop]
    return []


def loop_referral_count(g: nx.DiGraph, loop: list[str]) -> int:
    return sum(g[a][b].get("weight", 1) for a, b in zip(loop, loop[1:] + loop[:1]) if g.has_edge(a, b))
