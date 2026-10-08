"""Iterative line-tripping cascade simulation."""

import copy

import networkx as nx
import pandas as pd
import pandapower as pp

from clf.grid import build_graph

DEFAULT_ALPHA = 0.20
DEFAULT_MIN_BASE_LOADING = 0.10
# Emergency load shedding when AC power flow does not converge: step load down
# by 5% of the original until it converges, then bisect 4 times, which finds the
# lowest workable shed to within 0.05 / 2**4 (about 0.3% of load).
DEFAULT_SHED_STEP = 0.05
SHED_BISECTION_ROUNDS = 4


def _slack_buses(net):
    buses = set(net.ext_grid.loc[net.ext_grid["in_service"], "bus"].astype(int))
    slack_gens = net.gen["in_service"] & net.gen["slack"].astype(bool)
    buses |= set(net.gen.loc[slack_gens, "bus"].astype(int))
    return buses


def supplied_buses(net, G=None):
    """Buses connected through in-service lines/transformers to a slack bus.

    This matches what pandapower's power flow can solve: buses in an island
    without a slack bus are left out of the solution, so their load is lost.
    """
    G = G if G is not None else build_graph(net)
    slacks = _slack_buses(net)
    supplied = set()
    for component in nx.connected_components(G):
        if component & slacks:
            supplied |= component
    return supplied


def compute_load_shed(net, total_load=None):
    """Return ``(served_mw, shed_mw, shed_percent)`` for the current state of ``net``.

    A load counts as served if its bus is still connected to a slack bus
    (see :func:`supplied_buses`). Loads in islands with no slack bus are shed.
    Load scaled down by :func:`_shed_until_solvable` is also shed, as long as
    ``total_load`` is the load before scaling (it defaults to the current load).
    """
    loads = net.load[net.load["in_service"]]
    p_mw = loads["p_mw"] * loads["scaling"]
    if total_load is None:
        total_load = p_mw.sum()

    served_load = p_mw[loads["bus"].isin(supplied_buses(net))].sum()
    shed_load = total_load - served_load
    shed_percent = 100.0 * shed_load / total_load if total_load > 0 else 0.0

    return served_load, shed_load, shed_percent


def _largest_component_size(net):
    G = build_graph(net)
    if G.number_of_edges() == 0:
        return 1
    return len(max(nx.connected_components(G), key=len))


def _set_injection_scale(netc, base_scaling, scale):
    """Scale every load and generator to ``scale`` times its original output."""
    for element, scaling in base_scaling.items():
        netc[element]["scaling"] = scaling * scale


def _converges_at(netc, base_scaling, scale):
    """Run AC power flow at ``scale`` and report whether it converged."""
    _set_injection_scale(netc, base_scaling, scale)
    try:
        pp.runpp(netc)
    except Exception:
        return False
    return True


def _shed_until_solvable(netc, base_scaling, scale, step):
    """Lower load and generation together until AC power flow converges.

    Called after power flow fails at ``scale``. Steps the scale down by ``step``
    until power flow converges, then bisects between the last failing and the
    first converging scale to shed no more than needed. Generation is scaled
    with load so the slack bus does not pick up the whole imbalance.

    Returns the new scale with ``netc`` solved at it, or ``None`` if power flow
    does not converge even with all load removed.
    """
    failing, solved = scale, None
    while failing > 0:
        candidate = max(round(failing - step, 10), 0.0)
        if _converges_at(netc, base_scaling, candidate):
            solved = candidate
            break
        failing = candidate
    if solved is None:
        return None

    last_tried = solved
    for _ in range(SHED_BISECTION_ROUNDS):
        mid = (failing + solved) / 2
        last_tried = mid
        if _converges_at(netc, base_scaling, mid):
            solved = mid
        else:
            failing = mid
    # netc holds the results of the last power flow tried; if that one failed,
    # solve again at the scale we return so res_line matches it.
    if last_tried != solved and not _converges_at(netc, base_scaling, solved):
        return None
    return solved


def _summarize(netc, initial_lines, initial_trafos, tripped_lines, iterations, solver_failed,
               total_load=None, load_scale=1.0):
    served_load, shed_load, shed_percent = compute_load_shed(netc, total_load=total_load)
    single_line = len(initial_lines) == 1 and not initial_trafos
    return {
        "initial_line": int(initial_lines[0]) if single_line else None,
        "initial_lines": initial_lines,
        "initial_trafos": initial_trafos,
        "cascade_size": len(tripped_lines) + len(initial_trafos),
        "tripped_lines": tripped_lines,
        "iterations": iterations,
        "solver_failed": solver_failed,
        "load_scale": load_scale,
        "lcc_size": _largest_component_size(netc),
        "served_load_mw": served_load,
        "shed_load_mw": shed_load,
        "shed_percent": shed_percent,
    }


def run_cascade(net, initial_line=None, initial_lines=None, initial_trafos=None,
                alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING,
                shed_step=DEFAULT_SHED_STEP):
    """Simulate a cascade triggered by removing lines and/or transformers.

    ``net`` must already have a solved baseline power flow (``net.res_line``).
    A line trips when its loading exceeds
    ``max(baseline_loading, min_base_loading) * (1 + alpha)``.
    The loop repeats AC power flow until no new lines trip.
    Only lines can trip during the cascade; transformers are removed only as
    initial outages.

    When AC power flow does not converge, load and generation are scaled down
    in steps of ``shed_step`` until it does (emergency load shedding), and the
    cascade continues at the lower level (shed load is never restored).
    ``load_scale`` in the result is the final fraction of load kept by that
    mechanism, and the scaled-down load counts as shed. ``solver_failed`` is
    only set if power flow fails even with all load removed, or on any failure
    when ``shed_step`` is ``None``.

    ``cascade_size`` counts every branch out of service at the end, including
    the initial outages.
    """
    if initial_line is None and initial_lines is None and initial_trafos is None:
        raise ValueError("Provide initial_line, initial_lines, or initial_trafos")
    if initial_lines is None:
        initial_lines = [] if initial_line is None else [int(initial_line)]
    else:
        initial_lines = [int(x) for x in initial_lines]
    initial_trafos = [int(x) for x in (initial_trafos or [])]

    netc = copy.deepcopy(net)
    baseline_loading = net.res_line.loading_percent.copy()
    threshold = baseline_loading.clip(lower=min_base_loading) * (1.0 + alpha)

    for trafo_id in initial_trafos:
        netc.trafo.at[trafo_id, "in_service"] = False

    tripped_lines = []
    for line_id in initial_lines:
        netc.line.at[line_id, "in_service"] = False
        tripped_lines.append(line_id)

    # Shed is measured against the load before any emergency shedding.
    loads = net.load[net.load["in_service"]]
    total_load = (loads["p_mw"] * loads["scaling"]).sum()
    base_scaling = {element: net[element]["scaling"].copy() for element in ("load", "gen", "sgen")}
    load_scale = 1.0

    def summarize(solver_failed):
        return _summarize(netc, initial_lines, initial_trafos, tripped_lines, iterations,
                          solver_failed, total_load=total_load, load_scale=load_scale)

    iterations = 0
    while True:
        iterations += 1
        try:
            pp.runpp(netc)
        except Exception:
            new_scale = None
            if shed_step is not None:
                new_scale = _shed_until_solvable(netc, base_scaling, load_scale, shed_step)
            if new_scale is None:
                _set_injection_scale(netc, base_scaling, load_scale)
                return summarize(solver_failed=True)
            load_scale = new_scale

        current_loading = netc.res_line.loading_percent
        overload_mask = netc.line["in_service"] & (current_loading > threshold)
        newly_overloaded = [
            int(line_id) for line_id in netc.line.index[overload_mask]
            if int(line_id) not in tripped_lines
        ]

        if not newly_overloaded:
            break

        for line_id in newly_overloaded:
            netc.line.at[line_id, "in_service"] = False
            tripped_lines.append(line_id)

    return summarize(solver_failed=False)


def run_node_cascade(net, bus_id, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING,
                     shed_step=DEFAULT_SHED_STEP):
    """Simulate a cascade triggered by removing every line and transformer incident to ``bus_id``."""
    lines = net.line[net.line["in_service"]]
    trafos = net.trafo[net.trafo["in_service"]]
    incident_lines = lines.index[(lines["from_bus"] == bus_id) | (lines["to_bus"] == bus_id)].tolist()
    incident_trafos = trafos.index[(trafos["hv_bus"] == bus_id) | (trafos["lv_bus"] == bus_id)].tolist()

    result = run_cascade(net, initial_lines=incident_lines, initial_trafos=incident_trafos,
                         alpha=alpha, min_base_loading=min_base_loading, shed_step=shed_step)
    result["initial_bus"] = int(bus_id)
    result["incident_line_count"] = len(incident_lines)
    result["incident_trafo_count"] = len(incident_trafos)
    return result


def scan_edge_cascades(net, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING,
                       shed_step=DEFAULT_SHED_STEP):
    """Run an N-1 cascade for every line and return the results as a DataFrame."""
    return pd.DataFrame([
        run_cascade(net, initial_line=int(line_id), alpha=alpha, min_base_loading=min_base_loading,
                    shed_step=shed_step)
        for line_id in net.line.index
    ])


def scan_node_cascades(net, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING,
                       shed_step=DEFAULT_SHED_STEP):
    """Run a node-removal cascade for every bus and return the results as a DataFrame."""
    return pd.DataFrame([
        run_node_cascade(net, bus_id=int(bus_id), alpha=alpha, min_base_loading=min_base_loading,
                         shed_step=shed_step)
        for bus_id in net.bus.index
    ])
