"""Stream–aquifer interaction analysis.

31. Stream gain/loss longitudinal profile
32. Stream–aquifer exchange spatial map
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from . import (get_stream_segments, get_stream_node_xy, overlay_grid,
               plot_contour_map, _has_df_methods, savefig,
               style_map_axes, map_legend_outside)


# ──────────────────────────────────────────────────────────────────
# 31. Stream gain/loss profile
# ──────────────────────────────────────────────────────────────────

def plot_stream_gain_loss_profile(model, reach_ids=None,
                                   factor=1.0, ax=None,
                                   figsize=(14, 5), save_path=None):
    """Longitudinal plot coloring each segment by GW gain/loss.

    Blue segments = gaining (GW feeds stream).
    Red segments  = losing (stream recharges GW).

    Parameters
    ----------
    model : IWFMModel  (must be at a simulation timestep, not inquiry-only
            for current-timestep flow data; alternatively pass precomputed
            gain_from_gw array via the factor parameter)
    reach_ids : list of int, optional
    factor : float
        Unit conversion factor.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if _has_df_methods(model):
        sf_df = model.stream_flows_df(factor)
        gain_gw = sf_df["gain_from_gw"].values
        sn_df = model.stream_nodes_df()
        sn_ids = sn_df["stream_node_id"].values
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        if reach_ids is None:
            reach_ids = model.reaches_df()["reach_id"].values
    else:
        gain_gw = model.get_stream_gain_from_gw(factor)
        sn_ids = model.get_stream_node_ids()
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        if reach_ids is None:
            reach_ids = model.get_reach_ids()
        sn_df = None

    sx, sy = get_stream_node_xy(model)

    cum_dist = 0.0
    for rid in reach_ids:
        if _has_df_methods(model):
            mask = sn_df["reach_id"] == int(rid)
            strm_nodes = sn_df.loc[mask, "stream_node_id"].values
        else:
            strm_nodes = model.get_reach_stream_nodes(int(rid))
        indices = [sn_map[int(sn)] for sn in strm_nodes if int(sn) in sn_map]
        if len(indices) < 2:
            continue

        xs = sx[indices]
        ys = sy[indices]
        gains = gain_gw[indices]

        seg_dist = np.sqrt(np.diff(xs)**2 + np.diff(ys)**2)
        local_dist = np.concatenate([[0], np.cumsum(seg_dist)])
        dists = cum_dist + local_dist

        # Color each segment by midpoint gain
        for j in range(len(indices) - 1):
            mid_gain = 0.5 * (gains[j] + gains[j + 1])
            color = "steelblue" if mid_gain >= 0 else "indianred"
            ax.fill_between(
                [dists[j], dists[j + 1]], 0, [gains[j], gains[j + 1]],
                color=color, alpha=0.6,
            )
            ax.plot([dists[j], dists[j + 1]], [gains[j], gains[j + 1]],
                    color=color, linewidth=1)

        cum_dist = dists[-1]

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Cumulative distance along stream")
    ax.set_ylabel("Gain from GW (positive = gaining)")
    ax.set_title("Stream Gain/Loss from Groundwater")
    ax.grid(True, alpha=0.3)

    # Legend
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color="steelblue", alpha=0.6, label="Gaining (GW → stream)"),
        Patch(color="indianred", alpha=0.6, label="Losing (stream → GW)"),
    ])

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 32. Stream–aquifer exchange map
# ──────────────────────────────────────────────────────────────────

def plot_stream_aquifer_exchange_map(model, layer=1, factor=1.0,
                                      show_heads=True, ax=None,
                                      figsize=(10, 8), save_path=None):
    """Spatial map of GW gain/loss magnitude at each stream node.

    Stream nodes are plotted as circles: blue = gaining, red = losing,
    size proportional to magnitude. Optionally overlays head contours.

    Parameters
    ----------
    model : IWFMModel
    layer : int
        Layer for head contour overlay.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    # Head contour background
    if show_heads:
        from . import get_heads_snapshot
        heads = get_heads_snapshot(model, layer)
        plot_contour_map(model, heads, ax=ax, cmap="Blues", levels=15,
                         label="Head", filled=True)

    overlay_grid(model, ax)

    # Stream gain/loss
    if _has_df_methods(model):
        gain_gw = model.stream_flows_df(factor)["gain_from_gw"].values
    else:
        gain_gw = model.get_stream_gain_from_gw(factor)
    sx, sy = get_stream_node_xy(model)

    # Normalize size
    abs_gain = np.abs(gain_gw)
    max_gain = abs_gain.max() if abs_gain.max() > 0 else 1.0
    sizes = 10 + 200 * abs_gain / max_gain

    gaining = gain_gw >= 0
    losing = ~gaining

    if gaining.any():
        ax.scatter(sx[gaining], sy[gaining], s=sizes[gaining],
                   c="steelblue", alpha=0.7, edgecolors="navy",
                   linewidths=0.5, label="Gaining", zorder=6)
    if losing.any():
        ax.scatter(sx[losing], sy[losing], s=sizes[losing],
                   c="indianred", alpha=0.7, edgecolors="darkred",
                   linewidths=0.5, label="Losing", zorder=6)

    # Stream lines
    segments, _ = get_stream_segments(model)
    for seg in segments:
        if len(seg) >= 2:
            ax.plot(seg[:, 0], seg[:, 1], "k-", linewidth=0.8, alpha=0.4,
                    zorder=5)

    ax.set_aspect("equal")
    style_map_axes(ax)
    ax.set_title("Stream–Aquifer Exchange")
    map_legend_outside(ax)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm_io

    with iwfm_io.dll.IWFMModel(
        preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
        simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as m:
        plot_stream_aquifer_exchange_map(m, save_path="strm_aq_exchange.png")
    plt.show()
