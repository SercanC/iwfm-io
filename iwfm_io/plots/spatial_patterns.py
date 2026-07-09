"""Spatial pattern discovery visualizations.

40. Sparkline grid — tiny hydrographs at each node location
41. Small multiples — same head contour map tiled per year
42. Head vs ground surface elevation scatter
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from . import (build_triangulation, overlay_streams, overlay_grid,
               excel_date_to_datetime, savefig, _has_df_methods)


# ──────────────────────────────────────────────────────────────────
# 40. Sparkline grid
# ──────────────────────────────────────────────────────────────────

def plot_sparkline_grid(model, layer, begin_date, end_date,
                        n_points=50, figsize=(14, 10),
                        save_path=None):
    """Plot tiny hydrographs at sampled node locations on the map.

    Provides a spatial overview of temporal behavior across the model.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    n_points : int
        Number of nodes to sample (evenly spaced by index).
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Background grid
    overlay_grid(model, ax, alpha=0.2)
    overlay_streams(model, ax, color="lightblue", linewidth=0.8, alpha=0.5)

    if _has_df_methods(model):
        ndf = model.nodes_df()
        x = ndf["x"].values.astype(np.float64)
        y = ndf["y"].values.astype(np.float64)
        hdf = model.heads_df(layer, begin_date, end_date)
        heads = hdf.values.T  # (n_nodes, n_times)
    else:
        x, y = model.get_node_coordinates()
        _, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
    n_nodes, n_times = heads.shape

    # Sample nodes
    step = max(n_nodes // n_points, 1)
    sample_idx = list(range(0, n_nodes, step))[:n_points]

    # Sparkline dimensions in data coordinates
    x_range = x.max() - x.min()
    y_range = y.max() - y.min()
    spark_w = x_range * 0.04  # width of each sparkline
    spark_h = y_range * 0.03  # height of each sparkline

    t_norm = np.linspace(0, 1, n_times)  # normalize time to [0, 1]

    for idx in sample_idx:
        h = heads[idx]
        if np.all(np.isnan(h)):
            continue
        h_min, h_max = np.nanmin(h), np.nanmax(h)
        h_range = h_max - h_min if h_max > h_min else 1.0

        # Scale to sparkline box
        sx = x[idx] + t_norm * spark_w - spark_w / 2
        sy = y[idx] + (h - h_min) / h_range * spark_h - spark_h / 2

        ax.plot(sx, sy, color="darkred", linewidth=0.5, alpha=0.8, zorder=10)

    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    ax.set_title(f"Sparkline Grid — Head Layer {layer}")

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 41. Small multiples
# ──────────────────────────────────────────────────────────────────

def plot_small_multiples(model, layer, begin_date, end_date,
                          n_panels=None, cmap="coolwarm_r",
                          levels=15, figsize=(18, 12),
                          save_path=None):
    """Tile the same head contour map for each year.

    Makes slow spatial changes visible through repetition.

    Parameters
    ----------
    n_panels : int, optional
        Number of panels. Defaults to number of years in the range.
    """
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        # Convert DatetimeIndex to Excel serial dates for compatibility
        from datetime import datetime as _dt, timedelta as _td
        _base = _dt(1899, 12, 30)
        dates = np.array([(d.to_pydatetime() - _base).total_seconds() / 86400.0
                          for d in hdf.index])
        heads = hdf.values.T  # (n_nodes, n_times)
    else:
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=1.0,
        )
    dt_objs = excel_date_to_datetime(dates)
    tri = build_triangulation(model)

    # Group time steps by year
    years = sorted(set(d.year for d in dt_objs))
    if n_panels is not None:
        step = max(len(years) // n_panels, 1)
        years = years[::step][:n_panels]

    n = len(years)
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    if nrows == 1 and ncols == 1:
        axes = np.array([[axes]])
    elif nrows == 1:
        axes = axes[np.newaxis, :]
    elif ncols == 1:
        axes = axes[:, np.newaxis]

    vmin = np.nanpercentile(heads, 2)
    vmax = np.nanpercentile(heads, 98)

    for i, year in enumerate(years):
        r, c = divmod(i, ncols)
        ax = axes[r, c]

        # Find timestep closest to mid-year
        year_mask = [d.year == year for d in dt_objs]
        year_indices = [j for j, m in enumerate(year_mask) if m]
        if not year_indices:
            ax.set_visible(False)
            continue
        mid = year_indices[len(year_indices) // 2]

        ax.tricontourf(tri, heads[:, mid], levels=levels, cmap=cmap,
                       vmin=vmin, vmax=vmax)
        overlay_streams(model, ax, color="black", linewidth=0.5, alpha=0.5)
        ax.set_aspect("equal")
        ax.set_title(str(year), fontsize=11, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])

    # Hide unused panels
    for i in range(n, nrows * ncols):
        r, c = divmod(i, ncols)
        axes[r, c].set_visible(False)

    fig.suptitle(f"Head Contours by Year — Layer {layer}", fontsize=14, y=1.01)
    fig.tight_layout()

    # Shared colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap,
                                norm=plt.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    fig.colorbar(sm, ax=axes.ravel().tolist(), label="Head elevation",
                 shrink=0.6, pad=0.02)

    if save_path:
        savefig(fig, save_path)
    return fig, axes


# ──────────────────────────────────────────────────────────────────
# 42. Head vs ground surface elevation scatter
# ──────────────────────────────────────────────────────────────────

def plot_head_vs_gse_scatter(model, layer=1, ax=None, figsize=(8, 8),
                              save_path=None):
    """Scatter plot of initial head vs ground surface elevation.

    Points above the 1:1 line indicate artesian (confined) conditions.
    Cluster patterns reveal confined vs unconfined behavior.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    layer : int
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    from . import get_heads_snapshot
    if _has_df_methods(model):
        sdf = model.stratigraphy_df()
        gs = sdf["elevation"].values
        heads = get_heads_snapshot(model, layer)
        top = sdf[f"aquitard_{layer}"].values
    else:
        gs = model.get_ground_surface_elevation()
        heads = get_heads_snapshot(model, layer)
        top = model.get_aquifer_top_elevation()[:, layer - 1]

    # Depth to water
    dtw = gs - heads

    sc = ax.scatter(gs, heads, c=dtw, cmap="RdYlBu_r", s=8, alpha=0.6,
                    edgecolors="none")
    fig.colorbar(sc, ax=ax, label="Depth to water", shrink=0.8)

    # 1:1 line
    lims = [min(gs.min(), heads.min()), max(gs.max(), heads.max())]
    ax.plot(lims, lims, "k--", linewidth=1, alpha=0.5, label="1:1 line")

    # Aquifer top line
    ax.scatter(gs, top, c="gray", s=3, alpha=0.3, label="Aquifer top")

    ax.set_xlabel("Ground surface elevation")
    ax.set_ylabel(f"Head elevation (Layer {layer})")
    ax.set_title("Head vs Ground Surface — Artesian Analysis")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal")

    # Annotate regions
    ax.text(0.95, 0.05, "Unconfined\n(head < GSE)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=9, color="steelblue", alpha=0.7)
    ax.text(0.05, 0.95, "Artesian\n(head > GSE)",
            transform=ax.transAxes, ha="left", va="top",
            fontsize=9, color="indianred", alpha=0.7)

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
        bd, ed = "10/01/1990_24:00", "09/30/2000_24:00"
        plot_sparkline_grid(m, 1, bd, ed, save_path="sparklines.png")
        plot_small_multiples(m, 1, bd, ed, save_path="small_multiples.png")
        plot_head_vs_gse_scatter(m, save_path="head_vs_gse.png")
    plt.show()
