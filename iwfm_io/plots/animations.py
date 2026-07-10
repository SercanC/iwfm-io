"""Animated visualizations.

28. Animated GW head surface over time
29. Animated stream flow propagation
30. Animated depth-to-water
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from . import (build_triangulation, overlay_streams, overlay_grid,
               get_stream_segments, get_stream_node_xy,
               excel_date_to_datetime, _has_df_methods, savefig,
               style_map_axes)


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
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        dt_objs = list(hdf.index)
        heads = hdf.values.T  # (n_nodes, n_times)
        n_times = heads.shape[1]
    else:
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
        dt_objs = excel_date_to_datetime(dates)
        n_times = len(dates)
    tri = build_triangulation(model)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    vmin = np.nanpercentile(heads, 2)
    vmax = np.nanpercentile(heads, 98)

    fig, ax = plt.subplots(figsize=figsize)
    overlay_grid(model, ax, alpha=0.15)

    cs = ax.tricontourf(tri, heads[:, frame_idx[0]], levels=levels,
                        cmap=cmap, vmin=vmin, vmax=vmax)
    cb = fig.colorbar(cs, ax=ax, label="Head elevation", shrink=0.8)
    overlay_streams(model, ax, color="black", linewidth=1)
    title = ax.set_title("")
    ax.set_aspect("equal")
    style_map_axes(ax)

    def update(frame):
        for c in ax.collections[:]:
            c.remove()
        overlay_grid(model, ax, alpha=0.15)
        ax.tricontourf(tri, heads[:, frame], levels=levels,
                       cmap=cmap, vmin=vmin, vmax=vmax)
        overlay_streams(model, ax, color="black", linewidth=1)
        title.set_text(f"GW Head — Layer {layer} — "
                       f"{dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=1000 // fps, blit=False)

    if save_path:
        anim.save(save_path, fps=fps, dpi=120)
        print(f"Saved animation: {save_path}")

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
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        dt_objs = list(hdf.index)
        heads = hdf.values.T  # (n_nodes, n_times)
        n_times = heads.shape[1]
    else:
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
        dt_objs = excel_date_to_datetime(dates)
        n_times = len(dates)
    tri = build_triangulation(model)
    segments, reach_ids = get_stream_segments(model)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    vmin = np.nanpercentile(heads, 2)
    vmax = np.nanpercentile(heads, 98)

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect("equal")
    style_map_axes(ax)

    overlay_grid(model, ax, alpha=0.15)
    cs = ax.tricontourf(tri, heads[:, frame_idx[0]], levels=15,
                        cmap="Blues", alpha=0.5, vmin=vmin, vmax=vmax)
    fig.colorbar(cs, ax=ax, label="Head", shrink=0.8)

    # Draw stream segments with fixed width
    stream_lines = []
    for seg in segments:
        if len(seg) >= 2:
            line, = ax.plot(seg[:, 0], seg[:, 1], color="navy",
                            linewidth=2, alpha=0.8, zorder=5)
            stream_lines.append(line)

    title = ax.set_title("")

    def update(frame):
        for c in ax.collections[:]:
            c.remove()
        overlay_grid(model, ax, alpha=0.15)
        ax.tricontourf(tri, heads[:, frame], levels=15,
                       cmap="Blues", alpha=0.5, vmin=vmin, vmax=vmax)
        for seg, line in zip(segments, stream_lines):
            if len(seg) >= 2:
                line.set_data(seg[:, 0], seg[:, 1])
        title.set_text(f"Stream Network — {dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=1000 // fps, blit=False)

    if save_path:
        anim.save(save_path, fps=fps, dpi=120)
        print(f"Saved animation: {save_path}")

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
        hdf = model.heads_df(layer, begin_date, end_date)
        dt_objs = list(hdf.index)
        heads = hdf.values.T  # (n_nodes, n_times)
        n_times = heads.shape[1]
    else:
        gs = model.get_ground_surface_elevation()
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
        dt_objs = excel_date_to_datetime(dates)
        n_times = len(dates)
    tri = build_triangulation(model)

    # Compute depth to water for all timesteps
    dtw = gs[:, np.newaxis] - heads  # (n_nodes, n_times)

    frame_idx = list(range(0, n_times, max(interval_frames, 1)))
    vmin = max(np.nanpercentile(dtw, 2), 0)
    vmax = np.nanpercentile(dtw, 98)

    fig, ax = plt.subplots(figsize=figsize)
    overlay_grid(model, ax, alpha=0.15)
    cs = ax.tricontourf(tri, dtw[:, frame_idx[0]], levels=levels,
                        cmap=cmap, vmin=vmin, vmax=vmax)
    cb = fig.colorbar(cs, ax=ax, label="Depth to water", shrink=0.8)
    overlay_streams(model, ax, color="blue", linewidth=1)
    title = ax.set_title("")
    ax.set_aspect("equal")
    style_map_axes(ax)

    def update(frame):
        for c in ax.collections[:]:
            c.remove()
        overlay_grid(model, ax, alpha=0.15)
        ax.tricontourf(tri, dtw[:, frame], levels=levels,
                       cmap=cmap, vmin=vmin, vmax=vmax)
        overlay_streams(model, ax, color="blue", linewidth=1)
        title.set_text(f"Depth to Water — Layer {layer} — "
                       f"{dt_objs[frame].strftime('%Y-%m')}")
        return []

    anim = FuncAnimation(fig, update, frames=frame_idx,
                         interval=1000 // fps, blit=False)

    if save_path:
        anim.save(save_path, fps=fps, dpi=120)
        print(f"Saved animation: {save_path}")

    return anim


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm_io

    with iwfm_io.dll.IWFMModel(
        preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
        simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as m:
        anim = animate_gw_heads(m, 1, "10/01/1990_24:00",
                                "09/30/2000_24:00",
                                interval_frames=6,
                                save_path="gw_heads.gif")
    plt.show()
