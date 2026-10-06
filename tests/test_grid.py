import networkx as nx
import pytest

from clf import build_graph, build_multigraph, compute_edge_metrics, compute_node_metrics


@pytest.mark.parametrize("fixture", ["net118", "net300"])
def test_graph_is_connected_when_transformers_are_included(fixture, request):
    net = request.getfixturevalue(fixture)
    G = build_graph(net)
    assert G.number_of_nodes() == len(net.bus)
    assert nx.is_connected(G)


@pytest.mark.parametrize("fixture", ["net118", "net300"])
def test_every_branch_appears_in_graphs(fixture, request):
    net = request.getfixturevalue(fixture)
    n_branches = len(net.line) + len(net.trafo)

    MG = build_multigraph(net)
    assert MG.number_of_edges() == n_branches

    G = build_graph(net)
    assert sum(len(data["elements"]) for _, _, data in G.edges(data=True)) == n_branches


def test_parallel_lines_each_get_an_edge_metric(net118):
    edge_df = compute_edge_metrics(build_multigraph(net118))
    lines = edge_df[edge_df["element"] == "line"]
    assert sorted(lines["element_id"]) == sorted(net118.line.index)
    assert (edge_df["element"] == "trafo").sum() == len(net118.trafo)


def test_node_metrics_cover_every_bus(net118):
    node_df = compute_node_metrics(build_graph(net118))
    assert len(node_df) == len(net118.bus)
    assert node_df["eigenvector"].notna().all()
