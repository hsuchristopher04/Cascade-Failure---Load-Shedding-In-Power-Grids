"""Run the full cascade analysis for one or more IEEE cases and save the results.

Examples:
    python run_analysis.py --case case118
    python run_analysis.py --case all --sweep
    python run_analysis.py --case case300 --alpha 0.3 --out results_alpha03
"""

import argparse
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from clf import (  # noqa: E402
    build_graph,
    build_multigraph,
    compute_edge_metrics,
    compute_node_metrics,
    edge_metric_summary,
    load_case,
    node_metric_summary,
    scan_edge_cascades,
    scan_node_cascades,
    sensitivity_sweep,
)
from clf.cascade import DEFAULT_ALPHA, DEFAULT_MIN_BASE_LOADING  # noqa: E402
from clf.grid import SUPPORTED_CASES  # noqa: E402


def scatter(df, x, y, xlabel, ylabel, path):
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(df[x], df[y], s=14)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{xlabel} vs. {ylabel}")
    ax.grid(True)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def heatmap(sweep_df, value_col, title, path):
    pivot = sweep_df.pivot(index="alpha", columns="min_base_loading", values=value_col)
    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(pivot.values, aspect="auto")
    fig.colorbar(im, ax=ax, label=value_col)
    ax.set_xticks(range(len(pivot.columns)), [str(c) for c in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), [str(i) for i in pivot.index])
    ax.set_xlabel("min_base_loading")
    ax.set_ylabel("alpha")
    ax.set_title(title)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(j, i, f"{pivot.values[i, j]:.2f}", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def analyze(case, alpha, min_base_loading, run_sweep, out_root):
    start = time.time()
    out = out_root / case
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n=== {case} (alpha={alpha}, min_base_loading={min_base_loading}) ===")
    net = load_case(case)
    print(f"{len(net.bus)} buses, {len(net.line)} lines, {len(net.trafo)} transformers, "
          f"{net.load['p_mw'].sum():.0f} MW load")

    node_metrics = compute_node_metrics(build_graph(net))
    edge_metrics = compute_edge_metrics(build_multigraph(net))

    print("Running edge (line) outage scan...")
    edge_cascades = scan_edge_cascades(net, alpha=alpha, min_base_loading=min_base_loading)
    print("Running node (bus) outage scan...")
    node_cascades = scan_node_cascades(net, alpha=alpha, min_base_loading=min_base_loading)

    node_summary = node_metric_summary(node_metrics, node_cascades)
    edge_summary = edge_metric_summary(edge_metrics, edge_cascades)

    node_metrics.to_csv(out / "node_metrics.csv", index=False)
    edge_metrics.to_csv(out / "edge_metrics.csv", index=False)
    edge_cascades.to_csv(out / "edge_cascades.csv", index=False)
    node_cascades.to_csv(out / "node_cascades.csv", index=False)
    node_summary.to_csv(out / "node_metric_summary.csv", index=False)
    edge_summary.to_csv(out / "edge_metric_summary.csv", index=False)

    node_compare = node_metrics.merge(node_cascades, left_on="bus_id", right_on="initial_bus")
    node_compare = node_compare[~node_compare["solver_failed"]]
    scatter(node_compare, "degree", "shed_percent", "Node Degree", "Load Shed (%)",
            out / "degree_vs_shed.png")
    scatter(node_compare, "node_betweenness", "shed_percent", "Node Betweenness", "Load Shed (%)",
            out / "node_betweenness_vs_shed.png")

    line_metrics = edge_metrics[edge_metrics["element"] == "line"]
    edge_compare = line_metrics.merge(edge_cascades, left_on="element_id", right_on="initial_line")
    edge_compare = edge_compare[~edge_compare["solver_failed"]]
    scatter(edge_compare, "edge_betweenness", "shed_percent", "Edge Betweenness", "Load Shed (%)",
            out / "edge_betweenness_vs_shed.png")

    n_edge_fail = int(edge_cascades["solver_failed"].sum())
    n_node_fail = int(node_cascades["solver_failed"].sum())
    print(f"Solver failures (excluded from correlations): "
          f"{n_edge_fail}/{len(edge_cascades)} line outages, {n_node_fail}/{len(node_cascades)} bus outages")
    print("\nNode metrics vs. simulated severity:")
    print(node_summary.to_string(index=False))
    print("\nEdge betweenness vs. simulated severity:")
    print(edge_summary.to_string(index=False))

    if run_sweep:
        print("\nRunning sensitivity sweep (12 full line scans, this takes a while)...")
        sweep = sensitivity_sweep(net, edge_metrics)
        sweep.to_csv(out / "sweep.csv", index=False)
        heatmap(sweep, "mean_shed_percent", "Mean Load Shed (%)", out / "sweep_mean_shed.png")
        heatmap(sweep, "spearman_betweenness_vs_shed", "Spearman: Edge Betweenness vs Shed",
                out / "sweep_spearman_shed.png")
        heatmap(sweep, "spearman_betweenness_vs_cascade", "Spearman: Edge Betweenness vs Cascade Size",
                out / "sweep_spearman_cascade.png")
        print(sweep.to_string(index=False))

    print(f"\nSaved results to {out}/ ({time.time() - start:.0f}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=[*SUPPORTED_CASES, "all"], default="case118",
                        help="IEEE test case to analyze (default: case118)")
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                        help=f"relative overload margin (default: {DEFAULT_ALPHA})")
    parser.add_argument("--min-base-loading", type=float, default=DEFAULT_MIN_BASE_LOADING,
                        help=f"floor for baseline line loading, in percent (default: {DEFAULT_MIN_BASE_LOADING})")
    parser.add_argument("--sweep", action="store_true",
                        help="also run the alpha/min_base_loading sensitivity sweep")
    parser.add_argument("--out", type=Path, default=Path("results"),
                        help="output directory (default: results/)")
    args = parser.parse_args()

    if args.alpha < 0:
        parser.error("--alpha must be non-negative")
    if args.min_base_loading <= 0:
        parser.error("--min-base-loading must be positive")

    warnings.filterwarnings("ignore", category=DeprecationWarning, module="pandapower")
    warnings.filterwarnings("ignore", category=FutureWarning, module="pandapower")

    cases = SUPPORTED_CASES if args.case == "all" else (args.case,)
    for case in cases:
        analyze(case, args.alpha, args.min_base_loading, args.sweep, args.out)


if __name__ == "__main__":
    main()
