"""Cross-section storytelling visualizations.

50. Animated cross-section — water table moving over time
51. Multi-layer head panel — same transect, one panel per layer
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from . import (build_triangulation, excel_date_to_datetime,
               _has_df_methods, savefig)


def _sample_transect(model, points, n_samples):
    """Sample stratigraphy and return transect geometry.

    Returns
    -------
    dists : 1D array of distances along transect
    sample_xy : (n_samples, 2) array
    gs, tops, bots : arrays of shape (n_samples,) or (n_samples, n_layers)
    """
    points = np.asarray(points)
    seg_vecs = np.diff(points, axis=0)
    seg_lens = np.linalg.norm(seg_vecs, axis=1)
    total_dist = seg_lens.sum()
    cum_dist = np.concatenate([[0], np.cumsum(seg_lens)])

    dists = np.linspace(0, total_dist, n_samples)
    sample_xy = np.zeros((n_samples, 2))
    for i, d in enumerate(dists):
        seg_idx = np.searchsorted(cum_dist[1:], d, side="right")
        seg_idx = min(seg_idx, len(seg_lens) - 1)
        frac = (d - cum_dist[seg_idx]) / seg_lens[seg_idx] if seg_lens[seg_idx] > 0 else 0
        sample_xy[i] = points[seg_idx] + frac * seg_vecs[seg_idx]

    nl = model.n_layers
    gs = np.zeros(n_samples)
    tops = np.zeros((n_samples, nl))
    bots = np.zeros((n_samples, nl))

    for i in range(n_samples):
        strat = model.get_stratigraphy_at_xy(sample_xy[i, 0], sample_xy[i, 1])
        gs[i] = strat["GSElev"]
        tops[i] = strat["TopElevs"]
        bots[i] = strat["BottomElevs"]

    return dists, sample_xy, gs, tops, bots


# ──────────────────────────────────────────────────────────────────
# 50. Animated cross-section
# ──────────────────────────────────────────────────────────────────

def animate_cross_section(model, points, layer, begin_date, end_date,
                           n_samples=80, interval_frames=1,
                           figsize=(14, 5), fps=4, save_path=None):
    """Animate the water table along a cross-section over time.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    points : list of (x, y) tuples
        Transect polyline.
    layer : int
    begin_date, end_date : str
    n_samples : int
    interval_frames : int
        Skip every N frames.
    """
    dists, sample_xy, gs, tops, bots = _sample_transect(
        model, points, n_samples,
    )
    nl = model.n_layers

    # Get heads time series
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        dt_objs = list(hdf.index)
        heads = hdf.values.T  # (n_nodes, n_times)
        dates = dt_objs  # placeholder for length
    else:
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
        dt_objs = excel_date_to_datetime(dates)
    tri = build_triangulation(model)

    # Interpolate heads at sample points for all timesteps
    from matplotlib.tri import LinearTriInterpolator
    n_times = len(dates)
    heads_xsec = np.zeros((n_samples, n_times))
    for t in range(n_times):
        interp = LinearTriInterpolator(tri, heads[:, t])
        heads_xsec[:, t] = interp(sample_xy[:, 0], sample_xy[:, 1])

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))

    fig, ax = plt.subplots(figsize=figsize)

    # Static layers
    layer_colors = plt.cm.YlOrBr(np.linspace(0.3, 0.8, nl))
    for k in range(nl):
        ax.fill_between(dists, tops[:, k], bots[:, k],
                        color=layer_colors[k], alpha=0.4)
        ax.plot(dists, tops[:, k], "k-", linewidth=0.5)
        ax.plot(dists, bots[:, k], "k-", linewidth=0.5)

    ax.fill_between(dists, gs, gs.max() * 1.05, color="green", alpha=0.1)
    ax.plot(dists, gs, "k-", linewidth=1.5)

    # Water table line (animated)
    wt_line, = ax.plot(dists, heads_xsec[:, 0], "b-", linewidth=2.5,
                       label="Water table")
    wt_fill = ax.fill_between(dists, bots[:, -1].min(),
                               heads_xsec[:, 0],
                               color="deepskyblue", alpha=0.15)
    title = ax.set_title("")
    ax.set_xlabel("Distance along transect")
    ax.set_ylabel("Elevation")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    def update(frame):
        nonlocal wt_fill
        wt_line.set_ydata(heads_xsec[:, frame])
        wt_fill.remove()
        wt_fill = ax.fill_between(dists, bots[:, -1].min(),
                                   heads_xsec[:, frame],
                                   color="deepskyblue", alpha=0.15)
        title.set_text(f"Cross-Section — {dt_objs[frame].strftime('%Y-%m')}")
        return [wt_line]

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=1000 // fps, blit=False)

    if save_path:
        anim.save(save_path, fps=fps, dpi=120)
        print(f"Saved animation: {save_path}")

    return anim


# ──────────────────────────────────────────────────────────────────
# 51. Multi-layer head panel
# ──────────────────────────────────────────────────────────────────

def plot_multi_layer_head_panel(model, points, begin_date, end_date,
                                  n_samples=80, time_index=0,
                                  figsize=(14, 10), save_path=None):
    """Same transect, one subplot per layer, showing how head
    responses differ by depth.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    points : list of (x, y) tuples
    time_index : int
        Which time step to show (0 = first).
    """
    dists, sample_xy, gs, tops, bots = _sample_transect(
        model, points, n_samples,
    )
    nl = model.n_layers
    tri = build_triangulation(model)

    fig, axes = plt.subplots(nl, 1, figsize=figsize, sharex=True)
    if nl == 1:
        axes = [axes]

    layer_colors = plt.cm.YlOrBr(np.linspace(0.3, 0.8, nl))

    for lay in range(nl):
        ax = axes[lay]
        if _has_df_methods(model):
            hdf = model.heads_df(lay + 1, begin_date, end_date)
            dates = list(hdf.index)
            heads = hdf.values.T  # (n_nodes, n_times)
        else:
            dates, heads = model.get_gw_heads_for_layer(
                lay + 1, begin_date, end_date, factor=1.0,
            )

        from matplotlib.tri import LinearTriInterpolator
        ti = min(time_index, heads.shape[1] - 1)
        interp = LinearTriInterpolator(tri, heads[:, ti])
        h_xsec = interp(sample_xy[:, 0], sample_xy[:, 1])

        # Draw layer
        ax.fill_between(dists, tops[:, lay], bots[:, lay],
                        color=layer_colors[lay], alpha=0.4,
                        label=f"Layer {lay + 1}")
        ax.plot(dists, tops[:, lay], "k-", linewidth=0.5)
        ax.plot(dists, bots[:, lay], "k-", linewidth=0.5)

        # Draw head
        ax.plot(dists, h_xsec, "b-", linewidth=2, label="Head")
        ax.fill_between(dists, bots[:, lay], h_xsec,
                        where=h_xsec > bots[:, lay],
                        color="deepskyblue", alpha=0.2)

        if lay == 0:
            ax.plot(dists, gs, "k-", linewidth=1.5, label="Ground surface")

        ax.set_ylabel("Elevation")
        ax.set_title(f"Layer {lay + 1}", fontsize=10)
        ax.legend(loc="upper right", fontsize=7)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Distance along transect")
    if _has_df_methods(model):
        dt_objs = dates  # already datetime objects
    else:
        dt_objs = excel_date_to_datetime(dates)
    fig.suptitle(f"Multi-Layer Cross-Section — "
                 f"{dt_objs[ti].strftime('%Y-%m')}", fontsize=13)
    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)
    return fig, axes


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
        bd, ed = "10/01/1990_24:00", "09/30/2000_24:00"
        plot_multi_layer_head_panel(m, [p1, p2], bd, ed,
                                     save_path="multi_layer.png")
    plt.show()
