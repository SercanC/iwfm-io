"""Animated visualizations.

28. Animated GW head surface over time
29. Animated stream flow propagation
30. Animated depth-to-water

The static overlays (element mesh, stream network, colorbar) are drawn
once; each frame replaces only the contour set it redraws.  Rebuilding
the mesh and stream polylines per frame is what made these animations
take minutes on large models.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from . import (frame_interval_ms, fixed_levels, build_triangulation, overlay_streams, overlay_grid,
               get_stream_segments, excel_date_to_datetime, _has_df_methods, style_map_axes)


def _heads_series(model, layer, begin_date, end_date):
    """Return ``(dt_objs, heads)`` with heads shaped ``(n_nodes, n_times)``."""
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        return list(hdf.index), hdf.values.T
    dates, heads = model.get_gw_heads_for_layer(
        layer, begin_date, end_date, factor=1.0,
    )
    return excel_date_to_datetime(dates), heads


def _remove_contours(cs):
    """Remove a contour set's artists from its axes.

    ``TriContourSet`` is itself a Collection since matplotlib 3.8; older
    releases hold one PathCollection per level in ``cs.collections``.
    """
    try:
        cs.remove()
    except (AttributeError, NotImplementedError):  # pragma: no cover
        for c in cs.collections:
            c.remove()


def _save_animation(anim, save_path, fps):
    if save_path:
        anim.save(save_path, fps=fps, dpi=120)
        print(f"Saved animation: {save_path}")


# ──────────────────────────────────────────────────────────────────
# 28. Animated GW head surface
# ──────────────────────────────────────────────────────────────────

def animate_gw_heads(model, layer, begin_date, end_date,
                     interval_frames=1, cmap="coolwarm_r",
                     levels=20, figsize=(10, 8), fps=4,
                     save_path=None):
    """Create an animation of groundwater head contours over time.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    layer : int
    begin_date, end_date : str
    interval_frames : int
        Plot every Nth timestep to speed up animation.
    save_path : str, optional
        Path to save (e.g. ``"heads.gif"`` or ``"heads.mp4"``).

    Returns
    -------
    anim : FuncAnimation
    """
    dt_objs, heads = _heads_series(model, layer, begin_date, end_date)
    n_times = heads.shape[1]
    tri = build_triangulation(model)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    if not frame_idx:
        raise ValueError("no head output between begin_date and end_date")
    levels = fixed_levels(heads, levels)   # same scale in every frame

    fig, ax = plt.subplots(figsize=figsize)
    # static overlays, drawn once: mesh below the contours, streams above
    overlay_grid(model, ax, alpha=0.15)
    overlay_streams(model, ax, color="black", linewidth=1)

    cs = ax.tricontourf(tri, heads[:, frame_idx[0]], levels=levels,
                        cmap=cmap, extend="both")
    fig.colorbar(cs, ax=ax, label="Head elevation", shrink=0.8)
    title = ax.set_title("")
    ax.set_aspect("equal")
    style_map_axes(ax)

    def update(frame):
        nonlocal cs
        _remove_contours(cs)
        cs = ax.tricontourf(tri, heads[:, frame], levels=levels,
                            cmap=cmap, extend="both")
        title.set_text(f"GW Head — Layer {layer} — "
                       f"{dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=frame_interval_ms(fps), blit=False)
    _save_animation(anim, save_path, fps)
    return anim


# ──────────────────────────────────────────────────────────────────
# 29. Animated stream flow propagation
# ──────────────────────────────────────────────────────────────────

def animate_stream_flows(model, layer, begin_date, end_date,
                          interval_frames=1, figsize=(10, 8),
                          fps=4, save_path=None):
    """Animate stream flow by varying line width and color over time.

    This requires running the model step-by-step or having precomputed
    flows. For inquiry mode, we use the hydrograph API to get stream
    flow time series and animate them.

    A simpler approach: animate head contours with stream network
    colored by gain/loss from the heads time series.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    """
    dt_objs, heads = _heads_series(model, layer, begin_date, end_date)
    n_times = heads.shape[1]
    tri = build_triangulation(model)
    segments, reach_ids = get_stream_segments(model)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    if not frame_idx:
        raise ValueError("no head output between begin_date and end_date")
    levels = fixed_levels(heads, 15)

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect("equal")
    style_map_axes(ax)

    overlay_grid(model, ax, alpha=0.15)
    cs = ax.tricontourf(tri, heads[:, frame_idx[0]], levels=levels,
                        cmap="Blues", alpha=0.5, extend="both")
    fig.colorbar(cs, ax=ax, label="Head", shrink=0.8)

    # Draw stream segments once, with fixed width (zorder above contours)
    for seg in segments:
        if len(seg) >= 2:
            ax.plot(seg[:, 0], seg[:, 1], color="navy",
                    linewidth=2, alpha=0.8, zorder=5)

    title = ax.set_title("")

    def update(frame):
        nonlocal cs
        _remove_contours(cs)
        cs = ax.tricontourf(tri, heads[:, frame], levels=levels,
                            cmap="Blues", alpha=0.5, extend="both")
        title.set_text(f"Stream Network — {dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=frame_interval_ms(fps), blit=False)
    _save_animation(anim, save_path, fps)
    return anim


# ──────────────────────────────────────────────────────────────────
# 30. Animated depth-to-water
# ──────────────────────────────────────────────────────────────────

def animate_depth_to_water(model, layer, begin_date, end_date,
                            interval_frames=1, cmap="YlOrRd",
                            levels=20, figsize=(10, 8), fps=4,
                            save_path=None):
    """Animate depth-to-water (GSE minus head) over time.

    Reveals where and when wells approach the surface or go dry.
    """
    if _has_df_methods(model):
        gs = model.stratigraphy_df()["elevation"].values
    else:
        gs = model.get_ground_surface_elevation()
    dt_objs, heads = _heads_series(model, layer, begin_date, end_date)
    n_times = heads.shape[1]
    tri = build_triangulation(model)

    # Compute depth to water for all timesteps
    dtw = gs[:, np.newaxis] - heads  # (n_nodes, n_times)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    if not frame_idx:
        raise ValueError("no head output between begin_date and end_date")
    levels = fixed_levels(dtw, levels, vmin=max(np.nanpercentile(dtw, 2), 0))

    fig, ax = plt.subplots(figsize=figsize)
    overlay_grid(model, ax, alpha=0.15)
    overlay_streams(model, ax, color="blue", linewidth=1)
    cs = ax.tricontourf(tri, dtw[:, frame_idx[0]], levels=levels,
                        cmap=cmap, extend="both")
    fig.colorbar(cs, ax=ax, label="Depth to water", shrink=0.8)
    title = ax.set_title("")
    ax.set_aspect("equal")
    style_map_axes(ax)

    def update(frame):
        nonlocal cs
        _remove_contours(cs)
        cs = ax.tricontourf(tri, dtw[:, frame], levels=levels,
                            cmap=cmap, extend="both")
        title.set_text(f"Depth to Water — Layer {layer} — "
                       f"{dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=frame_interval_ms(fps), blit=False)
    _save_animation(anim, save_path, fps)
    return anim


# ──────────────────────────────────────────────────────────────────
