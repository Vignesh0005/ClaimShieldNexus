import networkx as nx


def provider_centrality(g: nx.Graph, top: int = 20) -> list[dict]:
    """Degree and betweenness for providers. Betweenness is sampled on large graphs."""
    providers = [n for n, d in g.nodes(data=True) if d.get("type") == "provider"]
    if not providers:
        return []
    degree = nx.degree_centrality(g)
    k = min(200, g.number_of_nodes())
    between = nx.betweenness_centrality(g, k=k if k < g.number_of_nodes() else None, seed=7)
    ranked = sorted(providers, key=lambda n: (between.get(n, 0), degree.get(n, 0)), reverse=True)[:top]
    return [{"provider_id": n, "degree": round(degree.get(n, 0), 4), "betweenness": round(between.get(n, 0), 4), "connections": g.degree(n)} for n in ranked]
