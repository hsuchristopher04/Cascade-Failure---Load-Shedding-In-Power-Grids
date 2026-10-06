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


def iter_branches(net):
    """Yield ``(element, element_id, bus_a, bus_b)`` for every in-service line and transformer.

    Transformers are branches just like lines: leaving them out splits the
    graph into disconnected pieces (6 components for case118, 78 for case300).
    Only lines and two-winding transformers are handled; the IEEE cases used
    here have no switches, impedances, or three-winding transformers.
    """
    for line_id, row in net.line[net.line["in_service"]].iterrows():
        yield "line", int(line_id), int(row["from_bus"]), int(row["to_bus"])
    for trafo_id, row in net.trafo[net.trafo["in_service"]].iterrows():
        yield "trafo", int(trafo_id), int(row["hv_bus"]), int(row["lv_bus"])


def build_graph(net):
    """Build a simple undirected bus graph from in-service lines and transformers.

    Parallel branches between the same pair of buses collapse into one edge;
    each edge's ``elements`` attribute lists every ``(element, element_id)`` on it.
    Use this graph for node metrics and connectivity.
    """
    G = nx.Graph()
    G.add_nodes_from(int(bus_id) for bus_id in net.bus.index)
    for element, element_id, a, b in iter_branches(net):
        if G.has_edge(a, b):
            G[a][b]["elements"].append((element, element_id))
        else:
            G.add_edge(a, b, elements=[(element, element_id)])
    return G


def build_multigraph(net):
    """Build a bus multigraph with one edge per in-service line or transformer.

    Edge keys are ``(element, element_id)``. Use this graph for edge metrics so
    that every branch, including parallel lines, gets its own value.
    """
    G = nx.MultiGraph()
    G.add_nodes_from(int(bus_id) for bus_id in net.bus.index)
    for element, element_id, a, b in iter_branches(net):
        G.add_edge(a, b, key=(element, element_id))
    return G


def compute_node_metrics(G):
    """Return a DataFrame of degree, betweenness, closeness, and eigenvector centrality per bus.

    ``G`` should be the simple graph from :func:`build_graph`. Degree is the
    number of neighboring buses.
    """
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


def compute_edge_metrics(MG):
    """Return a DataFrame of edge betweenness centrality per branch.

    ``MG`` should be the multigraph from :func:`build_multigraph`. Shortest
    paths are split evenly across parallel branches.
    """
    rows = []
    for (u, v, (element, element_id)), eb in nx.edge_betweenness_centrality(MG, normalized=True).items():
        rows.append({
            "element": element,
            "element_id": int(element_id),
            "from_bus": int(u),
            "to_bus": int(v),
            "edge_betweenness": eb,
        })
    return pd.DataFrame(rows).sort_values("edge_betweenness", ascending=False)
