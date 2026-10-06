"""Comparing graph metrics against simulated cascade severity."""

from itertools import product

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from clf.cascade import scan_edge_cascades

NODE_METRICS = ("degree", "node_betweenness", "closeness", "eigenvector")
TARGETS = ("shed_percent", "cascade_size")


def safe_corr(x, y, method="pearson"):
    """Correlation of ``x`` and ``y`` that drops NaNs and returns NaN when undefined."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(df) < 2 or df["x"].nunique() < 2 or df["y"].nunique() < 2:
        return np.nan
    if method == "pearson":
        return pearsonr(df["x"], df["y"])[0]
    if method == "spearman":
        return spearmanr(df["x"], df["y"])[0]
    raise ValueError("method must be 'pearson' or 'spearman'")


def top_k_overlap(df, metric_col, target_col, k=10, id_col="bus_id"):
    """Overlap between the top-``k`` ids ranked by ``metric_col`` and by ``target_col``.

    Returns ``(overlap_count, jaccard, top_by_metric, top_by_target)``.
    """
    top_metric = set(df.nlargest(k, metric_col)[id_col])
    top_target = set(df.nlargest(k, target_col)[id_col])
    overlap = len(top_metric & top_target)
    union = len(top_metric | top_target)
    jaccard = overlap / union if union > 0 else np.nan
    return overlap, jaccard, top_metric, top_target


def node_metric_summary(node_metrics_df, node_cascade_df, k=10):
    """Correlations and top-k overlap of each node metric against cascade severity.

    Rows where the power flow solver failed are excluded.
    """
    compare = node_metrics_df.merge(
        node_cascade_df[["initial_bus", "cascade_size", "shed_percent", "solver_failed"]],
        left_on="bus_id", right_on="initial_bus", how="left",
    )
    valid = compare[~compare["solver_failed"].astype(bool)]

    rows = []
    for metric in NODE_METRICS:
        row = {"metric": metric}
        for target, label in (("shed_percent", "shed"), ("cascade_size", "cascade")):
            row[f"pearson_vs_{label}"] = safe_corr(valid[metric], valid[target], "pearson")
            row[f"spearman_vs_{label}"] = safe_corr(valid[metric], valid[target], "spearman")
        for target, label in (("shed_percent", "shed"), ("cascade_size", "cascade")):
            overlap, jaccard, _, _ = top_k_overlap(valid, metric, target, k=k)
            row[f"top{k}_overlap_vs_{label}"] = overlap
            row[f"top{k}_jaccard_vs_{label}"] = jaccard
        rows.append(row)

    return pd.DataFrame(rows).sort_values("spearman_vs_shed", ascending=False)


def edge_metric_summary(edge_metrics_df, edge_cascade_df):
    """Correlations of edge betweenness against cascade severity (solver failures excluded)."""
    compare = edge_metrics_df.merge(
        edge_cascade_df[["initial_line", "cascade_size", "shed_percent", "solver_failed"]],
        left_on="line_id", right_on="initial_line", how="inner",
    )
    valid = compare[~compare["solver_failed"].astype(bool)]

    return pd.DataFrame([{
        "pearson_betweenness_vs_shed": safe_corr(valid["edge_betweenness"], valid["shed_percent"], "pearson"),
        "spearman_betweenness_vs_shed": safe_corr(valid["edge_betweenness"], valid["shed_percent"], "spearman"),
        "pearson_betweenness_vs_cascade": safe_corr(valid["edge_betweenness"], valid["cascade_size"], "pearson"),
        "spearman_betweenness_vs_cascade": safe_corr(valid["edge_betweenness"], valid["cascade_size"], "spearman"),
    }])


def sensitivity_sweep(net, edge_metrics_df, alphas=(0.10, 0.20, 0.30, 0.40),
                      min_base_loadings=(0.01, 0.05, 0.10), k=10):
    """Re-run the full edge scan for every ``(alpha, min_base_loading)`` pair."""
    rows = []
    for alpha, min_base_loading in product(alphas, min_base_loadings):
        cascades = scan_edge_cascades(net, alpha=alpha, min_base_loading=min_base_loading)
        compare = edge_metrics_df.merge(
            cascades[["initial_line", "cascade_size", "shed_percent", "solver_failed"]],
            left_on="line_id", right_on="initial_line", how="inner",
        )
        valid = compare[~compare["solver_failed"].astype(bool)]
        overlap, jaccard, _, _ = top_k_overlap(valid, "edge_betweenness", "shed_percent",
                                               k=k, id_col="line_id")
        rows.append({
            "alpha": alpha,
            "min_base_loading": min_base_loading,
            "mean_shed_percent": cascades["shed_percent"].mean(),
            "max_shed_percent": cascades["shed_percent"].max(),
            "mean_cascade_size": cascades["cascade_size"].mean(),
            "max_cascade_size": cascades["cascade_size"].max(),
            "solver_failures": int(cascades["solver_failed"].sum()),
            "spearman_betweenness_vs_shed": safe_corr(valid["edge_betweenness"], valid["shed_percent"], "spearman"),
            "spearman_betweenness_vs_cascade": safe_corr(valid["edge_betweenness"], valid["cascade_size"], "spearman"),
            f"top{k}_overlap": overlap,
            f"top{k}_jaccard": jaccard,
        })
    return pd.DataFrame(rows)
