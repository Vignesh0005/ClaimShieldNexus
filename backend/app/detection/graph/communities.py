import networkx as nx


def detect_communities(g: nx.Graph, min_size: int = 4, seed: int = 7) -> list[dict]:
    """Louvain communities over the provider-member-facility graph, largest first."""
    if g.number_of_edges() == 0:
        return []
    out = []
    for i, nodes in enumerate(sorted(nx.community.louvain_communities(g, weight="weight", seed=seed), key=len, reverse=True)):
        if len(nodes) < min_size:
            continue
        kinds = [g.nodes[n].get("type") for n in nodes]
        sub = g.subgraph(nodes)
        out.append(
            {
                "cluster_id": f"CL-{i + 1:03d}",
                "size": len(nodes),
                "providers": sorted(n for n in nodes if g.nodes[n].get("type") == "provider"),
                "member_count": kinds.count("member"),
                "facility_count": kinds.count("facility"),
                "referral_edges": sum(1 for _, _, d in sub.edges(data=True) if d.get("type") == "referral"),
                "density": round(nx.density(sub), 4),
            }
        )
    return out
