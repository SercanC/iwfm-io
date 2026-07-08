"""Cross-section and longitudinal profile visualizations.

19. Stratigraphic cross-section along a transect with GW head
20. Stream longitudinal profile — bottom elevation along reaches
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from . import (build_triangulation, _id_to_index_map,
               get_stream_node_xy, _has_df_methods, savefig)


# ──────────────────────────────────────────────────────────────────
# 19. Stratigraphic cross-section
# ──────────────────────────────────────────────────────────────────

def plot_stratigraphic_cross_section(model, points, n_samples=100,
                                     show_heads=True, layer_colors=None,
                                     ax=None, figsize=(14, 5),
                                     save_path=None):
    """Plot a stratigraphic cross-section along a transect.

    Parameters
    ----------
    model : IWFMModel
    points : list of (x, y) tuples
        At least two points defining the transect polyline.
    n_samples : int
        Number of sample points along the transect.
    show_heads : bool
        Overlay initial GW head on the cross-section.
    layer_colors : list of str, optional
        Colors for each aquifer layer fill.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    points = np.asarray(points)
    # Build cumulative distance along polyline
    seg_vecs = np.diff(points, axis=0)
    seg_lens = np.linalg.norm(seg_vecs, axis=1)
    total_dist = seg_lens.sum()
    cum_dist = np.concatenate([[0], np.cumsum(seg_lens)])

    # Sample points along polyline
    dists = np.linspace(0, total_dist, n_samples)
    sample_xy = np.zeros((n_samples, 2))
    for i, d in enumerate(dists):
        seg_idx = np.searchsorted(cum_dist[1:], d, side="right")
        seg_idx = min(seg_idx, len(seg_lens) - 1)
        frac = (d - cum_dist[seg_idx]) / seg_lens[seg_idx] if seg_lens[seg_idx] > 0 else 0
        sample_xy[i] = points[seg_idx] + frac * seg_vecs[seg_idx]

    nl = model.n_layers

    # Get stratigraphy at each sample point
    gs = np.zeros(n_samples)
    tops = np.zeros((n_samples, nl))
    bots = np.zeros((n_samples, nl))
    heads_init = np.zeros((n_samples, nl))

    for i in range(n_samples):
        strat = model.get_stratigraphy_at_xy(sample_xy[i, 0], sample_xy[i, 1])
        gs[i] = strat["GSElev"]
        tops[i] = strat["TopElevs"]
        bots[i] = strat["BottomElevs"]

    # Interpolate heads using triangulation (last output timestep)
    if show_heads:
        tri = build_triangulation(model)
        from . import get_heads_snapshot
        from matplotlib.tri import LinearTriInterpolator
        for lay in range(nl):
            head_vals = get_heads_snapshot(model, lay + 1)
            interp = LinearTriInterpolator(tri, head_vals)
            heads_init[:, lay] = interp(sample_xy[:, 0], sample_xy[:, 1])

    # Default layer colors
    if layer_colors is None:
        cmap = plt.cm.YlOrBr
        layer_colors = [cmap(0.3 + 0.5 * k / max(nl - 1, 1)) for k in range(nl)]

    # Plot ground surface
    ax.fill_between(dists, gs, gs.max() * 1.05, color="green", alpha=0.15,
                    label="Surface")
    ax.plot(dists, gs, "k-", linewidth=1.5, label="Ground surface")

    # Plot layers
    for k in range(nl):
        ax.fill_between(dists, tops[:, k], bots[:, k], color=layer_colors[k],
                        alpha=0.5, label=f"Layer {k + 1}")
        ax.plot(dists, tops[:, k], "k-", linewidth=0.5)
        ax.plot(dists, bots[:, k], "k-", linewidth=0.5)

    # Overlay heads
    if show_heads:
        for k in range(nl):
            style = "-" if k == 0 else "--"
            ax.plot(dists, heads_init[:, k], style, color="blue",
                    linewidth=1.5, alpha=0.8,
                    label=f"Head L{k + 1}" if k < 3 else None)

    ax.set_xlabel("Distance along transect")
    ax.set_ylabel("Elevation")
    ax.set_title("Stratigraphic Cross-Section")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 20. Stream longitudinal profile
# ──────────────────────────────────────────────────────────────────

def plot_stream_longitudinal_profile(model, reach_ids=None,
                                      ax=None, figsize=(14, 5),
                                      save_path=None):
    """Plot stream bottom elevation along reaches.

    Parameters
    ----------
    model : IWFMModel
    reach_ids : list of int, optional
        Specific reaches to plot. If None, plots all reaches
        connected in downstream order.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if _has_df_methods(model):
        sn_df = model.stream_nodes_df()
        sn_ids = sn_df["stream_node_id"].values
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        if reach_ids is None:
            reach_ids = model.reaches_df()["reach_id"].values
        # Build bottom elevations array aligned with stream node order
        rt_df = model.stream_rating_tables_df()
        bot_elevs = np.zeros(len(sn_ids))
        bot_lookup = rt_df.groupby("stream_node_id")["bottom_elev"].first()
        for idx, sid in enumerate(sn_ids):
            if int(sid) in bot_lookup.index:
                bot_elevs[idx] = bot_lookup[int(sid)]
    else:
        if reach_ids is None:
            reach_ids = model.get_reach_ids()
        sn_ids = model.get_stream_node_ids()
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        bot_elevs = model.get_stream_bottom_elevations()
        sn_df = None

    sx, sy = get_stream_node_xy(model)

    # Build cumulative distance along the concatenated reaches
    cum_dist = 0.0
    colors = plt.cm.tab10(np.linspace(0, 1, min(len(reach_ids), 10)))

    for ri, rid in enumerate(reach_ids):
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
        elevs = bot_elevs[indices]

        # Compute distance along this reach
        dx = np.diff(xs)
        dy = np.diff(ys)
        seg_dist = np.sqrt(dx**2 + dy**2)
        local_dist = np.concatenate([[0], np.cumsum(seg_dist)])
        dists = cum_dist + local_dist

        color = colors[ri % len(colors)]
        ax.plot(dists, elevs, "-o", color=color, markersize=2,
                linewidth=1.5, label=f"Reach {int(rid)}")
        cum_dist = dists[-1]

    ax.set_xlabel("Cumulative distance along stream")
    ax.set_ylabel("Bottom elevation")
    ax.set_title("Stream Longitudinal Profile")
    ax.grid(True, alpha=0.3)
    if len(reach_ids) <= 15:
        ax.legend(fontsize=7, ncol=2)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm

    with iwfm.IWFMModel(
        preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
        simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as m:
        x, y = m.get_node_coordinates()
        p1 = (x.min(), y.mean())
        p2 = (x.max(), y.mean())
        plot_stratigraphic_cross_section(m, [p1, p2], save_path="xsection.png")
        plot_stream_longitudinal_profile(m, save_path="stream_profile.png")
    plt.show()
