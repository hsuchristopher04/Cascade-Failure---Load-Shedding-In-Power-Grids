"""The package must reproduce the sanity-check results recorded in the notebooks."""

import pytest

from clf import build_graph, run_cascade


def test_graph_matches_notebook(net118, net300):
    assert build_graph(net118).number_of_edges() == 166
    assert build_graph(net300).number_of_edges() == 281


def test_case118_line0_matches_notebook(net118):
    result = run_cascade(net118, initial_line=0)
    assert result["solver_failed"] is False
    assert result["cascade_size"] == 99
    assert result["iterations"] == 13
    assert result["lcc_size"] == 11
    assert result["tripped_lines"][:9] == [0, 1, 15, 17, 18, 28, 40, 49, 51]
    assert result["shed_load_mw"] == pytest.approx(1567.0)
    assert result["shed_percent"] == pytest.approx(36.94012258368694)


def test_case300_line0_matches_notebook(net300):
    result = run_cascade(net300, initial_line=0)
    assert result["solver_failed"] is False
    assert result["tripped_lines"] == [0, 57]
    assert result["iterations"] == 2
    assert result["lcc_size"] == 85
    assert result["shed_percent"] == pytest.approx(16.761525768786456)
