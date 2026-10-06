"""Loading IEEE test cases and building graph representations of the grid."""

import networkx as nx
import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn

SUPPORTED_CASES = ("case118", "case300")


def load_case(name):
    """Load a pandapower IEEE test case by name and solve its baseline power flow."""
    if name not in SUPPORTED_CASES:
        raise ValueError(f"Unsupported case {name!r}; expected one of {SUPPORTED_CASES}")
    net = getattr(pn, name)()
    pp.runpp(net)
    return net


def build_graph(net):
    """Build an undirected bus graph from the in-service lines of ``net``.

    Each edge stores the ``line_id`` of the line that created it.
    """
    G = nx.Graph()
    G.add_nodes_from(int(bus_id) for bus_id in net.bus.index)

    active_lines = net.line[net.line["in_service"]]
    for line_id, row in active_lines.iterrows():
        G.add_edge(int(row["from_bus"]), int(row["to_bus"]), line_id=int(line_id))

    return G


def compute_node_metrics(G):
    """Return a DataFrame of degree, betweenness, closeness, and eigenvector centrality per bus."""
    degree = dict(G.degree())
    betweenness = nx.betweenness_centrality(G, normalized=True)
    closeness = nx.closeness_centrality(G)

    try:
        eigenvector = nx.eigenvector_centrality(G, max_iter=5000, tol=1e-06)
    except nx.PowerIterationFailedConvergence:
        eigenvector = {node: np.nan for node in G.nodes()}

    nodes = list(G.nodes())
    return pd.DataFrame({
        "bus_id": nodes,
        "degree": [degree[n] for n in nodes],
        "node_betweenness": [betweenness[n] for n in nodes],
        "closeness": [closeness[n] for n in nodes],
        "eigenvector": [eigenvector[n] for n in nodes],
    }).sort_values("node_betweenness", ascending=False)


def compute_edge_metrics(G):
    """Return a DataFrame of edge betweenness centrality per line."""
    rows = []
    for (u, v), eb in nx.edge_betweenness_centrality(G, normalized=True).items():
        rows.append({
            "line_id": int(G[u][v]["line_id"]),
            "from_bus": int(u),
            "to_bus": int(v),
            "edge_betweenness": eb,
        })
    return pd.DataFrame(rows).sort_values("edge_betweenness", ascending=False)
