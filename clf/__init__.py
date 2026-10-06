"""Cascading load failure (CLF) simulation and graph-metric analysis for power grids.

Shared simulation code for the IEEE case118 and case300 analyses.
"""

from clf.grid import (
    build_graph,
    build_multigraph,
    compute_edge_metrics,
    compute_node_metrics,
    load_case,
)
from clf.cascade import (
    compute_load_shed,
    run_cascade,
    run_node_cascade,
    scan_edge_cascades,
    scan_node_cascades,
    supplied_buses,
)
from clf.analysis import (
    edge_metric_summary,
    node_metric_summary,
    safe_corr,
    sensitivity_sweep,
    top_k_overlap,
)

__all__ = [
    "build_graph",
    "build_multigraph",
    "compute_edge_metrics",
    "compute_load_shed",
    "compute_node_metrics",
    "edge_metric_summary",
    "load_case",
    "node_metric_summary",
    "run_cascade",
    "run_node_cascade",
    "safe_corr",
    "scan_edge_cascades",
    "scan_node_cascades",
    "sensitivity_sweep",
    "supplied_buses",
    "top_k_overlap",
]
