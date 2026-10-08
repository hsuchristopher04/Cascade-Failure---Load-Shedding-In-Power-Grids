import copy

import pandapower as pp
import pytest

from clf import compute_load_shed, run_cascade, run_node_cascade, supplied_buses
from clf.cascade import DEFAULT_SHED_STEP, SHED_BISECTION_ROUNDS


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


@pytest.fixture(scope="module")
def stressed118(net118):
    # Four times the load and generation, applied after the baseline solve:
    # AC power flow no longer converges at full load but does at lower load.
    net = copy.deepcopy(net118)
    net.load["p_mw"] *= 4
    net.load["q_mvar"] *= 4
    net.gen["p_mw"] *= 4
    return net


# alpha is huge so no line trips: any load shed comes from emergency shedding alone.
NO_TRIP_ALPHA = 1e6


def test_nonconvergence_sheds_load_until_power_flow_solves(stressed118):
    result = run_cascade(stressed118, initial_line=5, alpha=NO_TRIP_ALPHA)
    assert not result["solver_failed"]
    assert 0 < result["load_scale"] < 1
    assert result["cascade_size"] == 1
    assert result["shed_percent"] == pytest.approx(100 * (1 - result["load_scale"]))


def test_emergency_shed_is_close_to_minimal(stressed118):
    result = run_cascade(stressed118, initial_line=5, alpha=NO_TRIP_ALPHA)
    net = copy.deepcopy(stressed118)
    net.line.at[5, "in_service"] = False
    scale = result["load_scale"] + DEFAULT_SHED_STEP / 2 ** SHED_BISECTION_ROUNDS
    for element in ("load", "gen", "sgen"):
        net[element]["scaling"] = scale
    with pytest.raises(pp.LoadflowNotConverged):
        pp.runpp(net)


def test_shedding_can_be_disabled(stressed118):
    result = run_cascade(stressed118, initial_line=5, alpha=NO_TRIP_ALPHA, shed_step=None)
    assert result["solver_failed"]
    assert result["load_scale"] == 1.0


def test_shedding_does_not_modify_input(stressed118):
    run_cascade(stressed118, initial_line=5, alpha=NO_TRIP_ALPHA)
    assert (stressed118.load["scaling"] == 1.0).all()
    assert (stressed118.gen["scaling"] == 1.0).all()


def test_converging_cascade_sheds_nothing_extra(net118):
    result = run_cascade(net118, initial_line=5)
    assert result["load_scale"] == 1.0
