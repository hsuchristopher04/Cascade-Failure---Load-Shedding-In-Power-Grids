"""Iterative line-tripping cascade simulation."""

import copy

import networkx as nx
import pandas as pd
import pandapower as pp

from clf.grid import build_graph

DEFAULT_ALPHA = 0.20
DEFAULT_MIN_BASE_LOADING = 0.10


def compute_load_shed(net):
    """Return ``(served_mw, shed_mw, shed_percent)`` for the current state of ``net``.

    A load counts as served if its bus touches at least one in-service line.
    """
    total_load = net.load["p_mw"].sum()

    active_lines = net.line[net.line["in_service"]]
    active_buses = set(active_lines["from_bus"].astype(int)) | set(active_lines["to_bus"].astype(int))

    served_load = net.load[net.load["bus"].isin(active_buses)]["p_mw"].sum()
    shed_load = total_load - served_load
    shed_percent = 100.0 * shed_load / total_load if total_load > 0 else 0.0

    return served_load, shed_load, shed_percent


def _largest_component_size(net):
    G = build_graph(net)
    if G.number_of_edges() == 0:
        return 1
    return len(max(nx.connected_components(G), key=len))


def _summarize(netc, initial_lines, initial_trafos, tripped_lines, iterations, solver_failed):
    served_load, shed_load, shed_percent = compute_load_shed(netc)
    single_line = len(initial_lines) == 1 and not initial_trafos
    return {
        "initial_line": int(initial_lines[0]) if single_line else None,
        "initial_lines": initial_lines,
        "initial_trafos": initial_trafos,
        "cascade_size": len(tripped_lines) + len(initial_trafos),
        "tripped_lines": tripped_lines,
        "iterations": iterations,
        "solver_failed": solver_failed,
        "lcc_size": _largest_component_size(netc),
        "served_load_mw": served_load,
        "shed_load_mw": shed_load,
        "shed_percent": shed_percent,
    }


def run_cascade(net, initial_line=None, initial_lines=None, initial_trafos=None,
                alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING):
    """Simulate a cascade triggered by removing lines and/or transformers.

    ``net`` must already have a solved baseline power flow (``net.res_line``).
    A line trips when its loading exceeds
    ``max(baseline_loading, min_base_loading) * (1 + alpha)``.
    The loop repeats AC power flow until no new lines trip or the solver fails.
    Only lines can trip during the cascade; transformers are removed only as
    initial outages.

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

    iterations = 0
    while True:
        iterations += 1
        try:
            pp.runpp(netc)
        except Exception:
            return _summarize(netc, initial_lines, initial_trafos, tripped_lines, iterations, solver_failed=True)

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

    return _summarize(netc, initial_lines, initial_trafos, tripped_lines, iterations, solver_failed=False)


def run_node_cascade(net, bus_id, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING):
    """Simulate a cascade triggered by removing every line and transformer incident to ``bus_id``."""
    lines = net.line[net.line["in_service"]]
    trafos = net.trafo[net.trafo["in_service"]]
    incident_lines = lines.index[(lines["from_bus"] == bus_id) | (lines["to_bus"] == bus_id)].tolist()
    incident_trafos = trafos.index[(trafos["hv_bus"] == bus_id) | (trafos["lv_bus"] == bus_id)].tolist()

    result = run_cascade(net, initial_lines=incident_lines, initial_trafos=incident_trafos,
                         alpha=alpha, min_base_loading=min_base_loading)
    result["initial_bus"] = int(bus_id)
    result["incident_line_count"] = len(incident_lines)
    result["incident_trafo_count"] = len(incident_trafos)
    return result


def scan_edge_cascades(net, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING):
    """Run an N-1 cascade for every line and return the results as a DataFrame."""
    return pd.DataFrame([
        run_cascade(net, initial_line=int(line_id), alpha=alpha, min_base_loading=min_base_loading)
        for line_id in net.line.index
    ])


def scan_node_cascades(net, alpha=DEFAULT_ALPHA, min_base_loading=DEFAULT_MIN_BASE_LOADING):
    """Run a node-removal cascade for every bus and return the results as a DataFrame."""
    return pd.DataFrame([
        run_node_cascade(net, bus_id=int(bus_id), alpha=alpha, min_base_loading=min_base_loading)
        for bus_id in net.bus.index
    ])
