import networkx as nx

MAX_NODES = 600


def export_graph(g: nx.Graph, in_loop: set[str] | None = None, focus: set[str] | None = None, max_nodes: int = MAX_NODES) -> dict:
    """Serialises a graph for the frontend: {nodes: [{id, type, ...}], edges: [{source, target, type, date}]}.

    When `focus` is given only those nodes and their direct neighbours are returned. Large graphs
    are trimmed to the best-connected nodes so a browser can lay them out."""
    in_loop = in_loop or set()
    if focus:
        keep = set(focus) & set(g.nodes)
        for n in list(keep):
            keep.update(g.neighbors(n))
        g = g.subgraph(keep)
    truncated = g.number_of_nodes() > max_nodes
    if truncated:
        priority = sorted(g.nodes, key=lambda n: (n in in_loop, g.nodes[n].get("type") != "member", g.degree(n)), reverse=True)
        g = g.subgraph(priority[:max_nodes])
    nodes = [
        {
            "id": n,
            "label": n,
            "type": d.get("type", "provider"),
            "in_loop": n in in_loop,
            "claims": d.get("claims", 0),
            "amount": round(d.get("amount", 0.0), 2),
            "connections": g.degree(n),
            "first_seen": d["first_seen"].isoformat() if d.get("first_seen") else None,
        }
        for n, d in g.nodes(data=True)
    ]
    edges = [
        {"id": f"{u}|{v}", "source": u, "target": v, "type": d.get("type", "claim"), "weight": d.get("weight", 1), "date": d["date"].isoformat() if d.get("date") else None}
        for u, v, d in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges, "truncated": truncated}
