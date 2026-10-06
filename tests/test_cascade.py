import pytest

from clf import run_cascade, run_node_cascade


def test_run_cascade_requires_an_outage(net118):
    with pytest.raises(ValueError):
        run_cascade(net118)


def test_run_cascade_does_not_modify_input(net118):
    before = net118.line["in_service"].copy()
    run_cascade(net118, initial_line=0)
    assert net118.line["in_service"].equals(before)


def test_line_cascade_reports_initial_line(net118):
    result = run_cascade(net118, initial_line=5)
    assert result["initial_line"] == 5
    assert result["tripped_lines"][0] == 5
    assert result["cascade_size"] == len(result["tripped_lines"])


def test_node_cascade_removes_incident_transformers(net118):
    trafo = net118.trafo.iloc[0]
    bus = int(trafo["lv_bus"])
    result = run_node_cascade(net118, bus)
    assert result["incident_trafo_count"] >= 1
    assert int(net118.trafo.index[0]) in result["initial_trafos"]
