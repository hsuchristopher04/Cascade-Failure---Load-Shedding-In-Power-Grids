import copy

import pytest

from clf import compute_load_shed, run_cascade, run_node_cascade, supplied_buses


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


@pytest.mark.parametrize("fixture", ["net118", "net300"])
def test_no_load_shed_at_baseline(fixture, request):
    net = request.getfixturevalue(fixture)
    served, shed, shed_percent = compute_load_shed(net)
    assert shed == pytest.approx(0.0)
    assert shed_percent == pytest.approx(0.0)
    assert served == pytest.approx(net.load["p_mw"].sum())


def test_isolated_load_bus_is_shed(net118):
    net = copy.deepcopy(net118)
    load = net.load.iloc[0]
    bus = int(load["bus"])
    net.line.loc[(net.line["from_bus"] == bus) | (net.line["to_bus"] == bus), "in_service"] = False
    net.trafo.loc[(net.trafo["hv_bus"] == bus) | (net.trafo["lv_bus"] == bus), "in_service"] = False

    served, shed, _ = compute_load_shed(net)
    expected_shed = net.load.loc[net.load["bus"] == bus, "p_mw"].sum()
    assert shed == pytest.approx(expected_shed)
    assert served + shed == pytest.approx(net.load["p_mw"].sum())


def test_island_without_slack_is_shed_even_if_it_has_lines(net118):
    # Cut every branch between the slack bus's component and buses 0-1-2,
    # leaving a small island that still has internal lines but no slack bus.
    net = copy.deepcopy(net118)
    island = {0, 1, 2}
    assert island <= supplied_buses(net)  # all supplied at baseline
    from_in = net.line["from_bus"].isin(island)
    to_in = net.line["to_bus"].isin(island)
    net.line.loc[from_in ^ to_in, "in_service"] = False
    net.trafo.loc[net.trafo["hv_bus"].isin(island) ^ net.trafo["lv_bus"].isin(island), "in_service"] = False

    assert supplied_buses(net).isdisjoint(island)
    _, shed, _ = compute_load_shed(net)
    assert shed == pytest.approx(net.load.loc[net.load["bus"].isin(island), "p_mw"].sum())


def test_node_cascade_sheds_at_least_the_removed_bus_load(net118):
    bus = int(net118.load["bus"].iloc[0])
    result = run_node_cascade(net118, bus)
    bus_load = net118.load.loc[net118.load["bus"] == bus, "p_mw"].sum()
    assert result["shed_load_mw"] >= bus_load - 1e-9
