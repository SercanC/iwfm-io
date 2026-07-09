"""Subsidence analysis visualizations.

43. Subsidence bowl map — cumulative subsidence contours
44. Subsidence vs head cross-plot — elastic vs inelastic behavior
"""

import numpy as np
import matplotlib.pyplot as plt
from . import (plot_contour_map, overlay_streams, overlay_grid,
               build_triangulation, excel_date_to_datetime,
               _has_df_methods, savefig)


# ──────────────────────────────────────────────────────────────────
# 43. Subsidence bowl map
# ──────────────────────────────────────────────────────────────────

def plot_subsidence_bowl(model, subsidence_values, layer=None,
                          cmap="Reds", levels=20, ax=None,
                          figsize=(10, 8), save_path=None):
    """Contour map of cumulative subsidence.

    Parameters
    ----------
    model : IWFMModel
    subsidence_values : np.ndarray
        Shape ``(n_nodes,)`` of cumulative subsidence at each node.
        If None, uses ``model.get_subsidence_all()`` summed across layers.
    layer : int, optional
        If provided, show subsidence for this layer only from
        get_subsidence_all(). Ignored if subsidence_values is given.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if subsidence_values is None:
        if _has_df_methods(model):
            sdf = model.subsidence_df()
            layer_cols = [c for c in sdf.columns if c.startswith("layer_")]
            if layer is not None:
                subsidence_values = sdf[f"layer_{layer}"].values
            else:
                subsidence_values = sdf[layer_cols].sum(axis=1).values
        else:
            subs = model.get_subsidence_all()  # (n_nodes, n_layers)
            if layer is not None:
                subsidence_values = subs[:, layer - 1]
            else:
                subsidence_values = subs.sum(axis=1)

    fig, ax, cs, cb = plot_contour_map(
        model, subsidence_values, ax=ax, cmap=cmap, levels=levels,
        label="Cumulative subsidence",
        title="Subsidence Bowl",
    )
    overlay_streams(model, ax, color="blue", linewidth=0.8)

    # Add contour lines for emphasis
    tri = build_triangulation(model)
    ax.tricontour(tri, subsidence_values, levels=10, colors="darkred",
                  linewidths=0.5, alpha=0.6)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 44. Subsidence vs head cross-plot
# ──────────────────────────────────────────────────────────────────

def plot_subsidence_vs_head(heads_ts, subsidence_ts, dates=None,
                             node_label="", ax=None, figsize=(8, 6),
                             save_path=None):
    """Cross-plot of subsidence vs head at a single node over time.

    Reveals the elastic (reversible) vs inelastic (irreversible)
    compaction relationship. A hysteresis loop indicates inelastic
    behavior.

    Parameters
    ----------
    heads_ts : array-like
        Head time series at the node.
    subsidence_ts : array-like
        Cumulative subsidence time series at the node.
    dates : list of datetime, optional
        For color-coding by time.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    heads_ts = np.asarray(heads_ts, dtype=float)
    subsidence_ts = np.asarray(subsidence_ts, dtype=float)

    if dates is not None:
        # Color by time
        t = np.arange(len(dates))
        sc = ax.scatter(heads_ts, subsidence_ts, c=t, cmap="viridis",
                        s=15, alpha=0.7, edgecolors="none")
        cb = fig.colorbar(sc, ax=ax, label="Time step")
        # Connect with thin lines to show path
        ax.plot(heads_ts, subsidence_ts, "k-", linewidth=0.3, alpha=0.4)
    else:
        ax.plot(heads_ts, subsidence_ts, "b-o", markersize=3,
                linewidth=1, alpha=0.7)

    # Add direction arrows at a few points
    n = len(heads_ts)
    arrow_indices = [n // 4, n // 2, 3 * n // 4]
    for ai in arrow_indices:
        if ai + 1 < n:
            dx = heads_ts[ai + 1] - heads_ts[ai]
            dy = subsidence_ts[ai + 1] - subsidence_ts[ai]
            ax.annotate("", xy=(heads_ts[ai + 1], subsidence_ts[ai + 1]),
                        xytext=(heads_ts[ai], subsidence_ts[ai]),
                        arrowprops=dict(arrowstyle="->", color="red",
                                        lw=1.5))

    ax.set_xlabel("Groundwater head")
    ax.set_ylabel("Cumulative subsidence")
    title = "Subsidence vs Head"
    if node_label:
        title += f" — {node_label}"
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    # Annotate behavior
    ax.text(0.05, 0.95, "Elastic: slope reverses\nInelastic: hysteresis loop",
            transform=ax.transAxes, fontsize=8, va="top",
            style="italic", color="gray")

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm_io

    # Note: subsidence data requires a model that has been run
    # (not just inquiry mode for most configurations).
    # This example assumes you have subsidence output available.
    print("Subsidence plots require simulation output data.")
    print("See function docstrings for usage with precomputed arrays.")
