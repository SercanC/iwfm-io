"""Spatial map visualizations for IWFM model data.

Provides 11 map-plotting functions that cover grid geometry, aquifer
parameters, groundwater heads, stream networks, wells, lakes,
diversions, and tile drains.  All functions rely on the shared helpers
defined in ``iwfm_io.plots.__init__``.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches

from . import (
    _has_df_methods,
    build_element_polygons,
    build_triangulation,
    get_element_centroids,
    node_values_to_element,
    get_stream_segments,
    get_stream_node_xy,
    _id_to_index_map,
    plot_element_map,
    plot_contour_map,
    overlay_streams,
    overlay_grid,
    savefig,
    excel_date_to_datetime,
)


# ──────────────────────────────────────────────────────────────────
# 1. Grid / mesh
# ──────────────────────────────────────────────────────────────────

def plot_grid_mesh(model, color_by="subregion", ax=None, figsize=(10, 8),
                   title="Model Grid", cmap="Set3", edgecolor="gray",
                   linewidth=0.3, alpha=0.7, save_path=None):
    """Plot the finite-element mesh, optionally colored by subregion.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    color_by : str, optional
        ``"subregion"`` to color each element by its subregion ID, or
        ``None`` / ``"none"`` for a plain mesh outline.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.  A new figure is created when *None*.
    figsize : tuple
        Figure size when creating a new figure.
    title : str
        Plot title.
    cmap : str
        Matplotlib colormap name (categorical maps work best).
    edgecolor : str
        Edge color for element boundaries.
    linewidth : float
        Edge width.
    alpha : float
        Polygon fill opacity.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    polygons = build_element_polygons(model)

    if color_by and color_by.lower() not in ("none", ""):
        if _has_df_methods(model):
            # DataFrame path
            edf = model.elements_df()
            elem_subs = edf["subregion"].values
            unique_subs = np.unique(elem_subs)
            n_unique = len(unique_subs)
            colormap = plt.get_cmap(cmap, n_unique)
            sub_to_idx = {int(s): i for i, s in enumerate(unique_subs)}

            face_colors = [colormap(sub_to_idx[int(s)]) for s in elem_subs]
            pc = PolyCollection(
                polygons,
                facecolors=face_colors,
                edgecolors=edgecolor,
                linewidths=linewidth,
                alpha=alpha,
            )
            ax.add_collection(pc)

            # Build legend from subregions_df
            sub_df = model.subregions_df()
            sub_name_map = {
                int(row["subregion_id"]): row.get("name", "")
                for _, row in sub_df.iterrows()
            }
            handles = []
            for s in unique_subs:
                idx = sub_to_idx[int(s)]
                name = sub_name_map.get(int(s), "")
                label_text = (f"{name} (ID {int(s)})" if name
                              else f"Subregion {int(s)}")
                handles.append(
                    mpatches.Patch(facecolor=colormap(idx), edgecolor="gray",
                                   label=label_text, alpha=alpha)
                )
            ax.legend(handles=handles, loc="best", fontsize="small",
                      title="Subregions", framealpha=0.9)
        else:
            # Legacy DLL path
            sub_ids = model.get_subregion_ids()
            elem_subs = model.get_element_subregions()
            unique_subs = np.unique(elem_subs)
            n_unique = len(unique_subs)
            colormap = plt.get_cmap(cmap, n_unique)
            sub_to_idx = {int(s): i for i, s in enumerate(unique_subs)}

            face_colors = [colormap(sub_to_idx[int(s)]) for s in elem_subs]
            pc = PolyCollection(
                polygons,
                facecolors=face_colors,
                edgecolors=edgecolor,
                linewidths=linewidth,
                alpha=alpha,
            )
            ax.add_collection(pc)

            # Build legend
            handles = []
            for s in unique_subs:
                idx = sub_to_idx[int(s)]
                name = model.get_subregion_name(int(s))
                label_text = (f"{name} (ID {int(s)})" if name
                              else f"Subregion {int(s)}")
                handles.append(
                    mpatches.Patch(facecolor=colormap(idx), edgecolor="gray",
                                   label=label_text, alpha=alpha)
                )
            ax.legend(handles=handles, loc="best", fontsize="small",
                      title="Subregions", framealpha=0.9)
    else:
        pc = PolyCollection(
            polygons,
            facecolors="none",
            edgecolors=edgecolor,
            linewidths=linewidth,
        )
        ax.add_collection(pc)

    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 2. Ground surface elevation
# ──────────────────────────────────────────────────────────────────

def plot_ground_surface_elevation(model, ax=None, cmap="terrain", levels=25,
                                  title="Ground Surface Elevation",
                                  label="Elevation (ft)", figsize=(10, 8),
                                  show_streams=False, save_path=None):
    """Plot a filled contour map of ground surface elevation.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap name (``"terrain"`` works well for elevation data).
    levels : int
        Number of contour levels.
    title : str
        Plot title.
    label : str
        Colorbar label.
    figsize : tuple
        Figure size.
    show_streams : bool
        Overlay the stream network on top of the contour.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if _has_df_methods(model):
        gse = model.stratigraphy_df()["elevation"].values
    else:
        gse = model.get_ground_surface_elevation()
    fig, ax, cs, cb = plot_contour_map(
        model, gse, ax=ax, cmap=cmap, levels=levels,
        label=label, title=title, filled=True, figsize=figsize,
    )
    if show_streams:
        overlay_streams(model, ax)
        ax.legend(loc="upper right", fontsize="small")

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 3. Layer thickness
# ──────────────────────────────────────────────────────────────────

def plot_layer_thickness(model, layer=1, ax=None, cmap="YlOrBr", levels=20,
                         title=None, label="Thickness (ft)",
                         figsize=(10, 8), save_path=None):
    """Plot a filled contour map of aquifer layer thickness.

    Thickness is computed as top elevation minus bottom elevation for
    the specified layer.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    layer : int
        1-based layer index.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap name.
    levels : int
        Number of contour levels.
    title : str, optional
        Plot title; auto-generated when *None*.
    label : str
        Colorbar label.
    figsize : tuple
        Figure size.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if _has_df_methods(model):
        sdf = model.stratigraphy_df()
        top = sdf[f"aquitard_{layer}"].values
        bottom = sdf[f"aquifer_{layer}"].values
        thickness = top - bottom
    else:
        top = model.get_aquifer_top_elevation()     # (n_nodes, n_layers)
        bottom = model.get_aquifer_bottom_elevation()
        layer_idx = layer - 1
        thickness = top[:, layer_idx] - bottom[:, layer_idx]

    if title is None:
        title = f"Layer {layer} Thickness"

    fig, ax, cs, cb = plot_contour_map(
        model, thickness, ax=ax, cmap=cmap, levels=levels,
        label=label, title=title, filled=True, figsize=figsize,
    )

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 4. Aquifer parameter
# ──────────────────────────────────────────────────────────────────

_PARAM_GETTERS = {
    "kh":  ("get_aquifer_horizontal_k",   "Horizontal K (ft/day)"),
    "kv":  ("get_aquifer_vertical_k",     "Vertical K (ft/day)"),
    "sy":  ("get_aquifer_specific_yield",  "Specific Yield (-)"),
    "ss":  ("get_aquifer_specific_storage", "Specific Storage (1/ft)"),
}


def plot_aquifer_parameter(model, parameter="Kh", layer=1, ax=None,
                           cmap="viridis", title=None, label=None,
                           figsize=(10, 8), show_mesh=False,
                           vmin=None, vmax=None, log_scale=False,
                           save_path=None):
    """Plot a per-element map of an aquifer parameter for a given layer.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    parameter : str
        One of ``"Kh"``, ``"Kv"``, ``"Sy"``, ``"Ss"`` (case-insensitive).
    layer : int
        1-based layer index.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap name.
    title : str, optional
        Plot title; auto-generated when *None*.
    label : str, optional
        Colorbar label; auto-generated when *None*.
    figsize : tuple
        Figure size.
    show_mesh : bool
        Show element edges.
    vmin, vmax : float, optional
        Colorbar limits.
    log_scale : bool
        Apply log10 transform before plotting (useful for K values
        spanning several orders of magnitude).
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    key = parameter.lower()
    if key not in _PARAM_GETTERS:
        raise ValueError(
            f"Unknown parameter '{parameter}'. "
            f"Choose from: {', '.join(p.upper() for p in _PARAM_GETTERS)}"
        )
    method_name, default_label = _PARAM_GETTERS[key]
    getter = getattr(model, method_name)
    node_vals_all = getter()  # (n_nodes, n_layers)
    layer_idx = layer - 1
    node_vals = node_vals_all[:, layer_idx]

    # Average to elements for the element-map display
    elem_vals = node_values_to_element(model, node_vals)

    if log_scale:
        elem_vals = np.where(elem_vals > 0, np.log10(elem_vals), np.nan)
        default_label = f"log10 {default_label}"

    if title is None:
        title = f"Layer {layer} {parameter.upper()}"
    if label is None:
        label = default_label

    fig, ax, pc, cb = plot_element_map(
        model, elem_vals, ax=ax, cmap=cmap, label=label,
        title=title, show_mesh=show_mesh, vmin=vmin, vmax=vmax,
        figsize=figsize,
    )

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 5. Groundwater head contour
# ──────────────────────────────────────────────────────────────────

def plot_gw_head_contour(model, layer=1, time_index=None,
                         begin_date=None, end_date=None, factor=1.0,
                         ax=None, cmap="coolwarm", levels=25,
                         title=None, label="Head (ft)",
                         figsize=(10, 8), show_streams=False,
                         save_path=None):
    """Plot a groundwater head contour map.

    If *time_index* is ``None`` (and no date range is given), the
    initial head condition is used.  When a date range is provided
    together with *time_index*, the head at that time step within the
    returned time series is plotted.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    layer : int
        1-based layer index.
    time_index : int, optional
        0-based time index into the date-range query result.  Use
        ``-1`` for the last time step.
    begin_date, end_date : str, optional
        IWFM date strings (``"MM/DD/YYYY_HH:MM"``).  Required when
        *time_index* is not ``None``.
    factor : float
        Unit conversion factor passed to ``get_gw_heads_for_layer``.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap name.
    levels : int
        Number of contour levels.
    title : str, optional
        Plot title; auto-generated when *None*.
    label : str
        Colorbar label.
    figsize : tuple
        Figure size.
    show_streams : bool
        Overlay the stream network.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if time_index is not None and begin_date is not None and end_date is not None:
        dates, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=factor
        )
        head_vals = heads[:, time_index]
        dt_list = excel_date_to_datetime(dates)
        date_label = dt_list[time_index].strftime("%Y-%m-%d")
        default_title = f"Layer {layer} Head  ({date_label})"
    else:
        from . import get_heads_snapshot
        head_vals = get_heads_snapshot(model, layer)
        default_title = f"Layer {layer} Head (last output)"

    if title is None:
        title = default_title

    fig, ax, cs, cb = plot_contour_map(
        model, head_vals, ax=ax, cmap=cmap, levels=levels,
        label=label, title=title, filled=True, figsize=figsize,
    )

    if show_streams:
        overlay_streams(model, ax)
        ax.legend(loc="upper right", fontsize="small")

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 6. Depth to water
# ──────────────────────────────────────────────────────────────────

def plot_depth_to_water(model, layer=1, ax=None, cmap="YlGnBu",
                        levels=20, title=None,
                        label="Depth to Water (ft)", figsize=(10, 8),
                        save_path=None):
    """Plot depth to water (ground surface minus head at last output timestep).

    Positive values indicate the water table is below ground surface.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    layer : int
        1-based layer index.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap name (sequential blues work well).
    levels : int
        Number of contour levels.
    title : str, optional
        Plot title; auto-generated when *None*.
    label : str
        Colorbar label.
    figsize : tuple
        Figure size.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    from . import get_heads_snapshot
    if _has_df_methods(model):
        gse = model.stratigraphy_df()["elevation"].values
    else:
        gse = model.get_ground_surface_elevation()
    head_vals = get_heads_snapshot(model, layer)
    dtw = gse - head_vals

    if title is None:
        title = f"Layer {layer} Depth to Water"

    fig, ax, cs, cb = plot_contour_map(
        model, dtw, ax=ax, cmap=cmap, levels=levels,
        label=label, title=title, filled=True, figsize=figsize,
    )

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 7. Head change (difference map)
# ──────────────────────────────────────────────────────────────────

def plot_head_change(model, layer, heads_t1, heads_t2, ax=None,
                     cmap="coolwarm", levels=20, title=None,
                     label="Head Change (ft)", figsize=(10, 8),
                     symmetric=True, save_path=None):
    """Plot the difference between two head arrays (t2 minus t1).

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    layer : int
        1-based layer index (used only for the default title).
    heads_t1 : np.ndarray, shape ``(n_nodes,)``
        Head values at the earlier time.
    heads_t2 : np.ndarray, shape ``(n_nodes,)``
        Head values at the later time.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Diverging colormap recommended.
    levels : int
        Number of contour levels.
    title : str, optional
        Plot title; auto-generated when *None*.
    label : str
        Colorbar label.
    figsize : tuple
        Figure size.
    symmetric : bool
        Force the contour limits to be symmetric around zero so that
        the diverging colormap is centred.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    diff = heads_t2 - heads_t1

    if title is None:
        title = f"Layer {layer} Head Change"

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    tri = build_triangulation(model)

    if symmetric:
        abs_max = np.nanmax(np.abs(diff))
        contour_levels = np.linspace(-abs_max, abs_max, levels)
    else:
        contour_levels = levels

    cs = ax.tricontourf(tri, diff, levels=contour_levels, cmap=cmap)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)
    cb = fig.colorbar(cs, ax=ax, label=label, shrink=0.8)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 8. Stream network
# ──────────────────────────────────────────────────────────────────

def plot_stream_network(model, color_by="reach", ax=None, cmap="tab20",
                        linewidth=2.0, alpha=0.9, title="Stream Network",
                        figsize=(10, 8), show_grid=True,
                        show_bottom_elev=False, save_path=None):
    """Plot the stream network on top of the model grid.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    color_by : str
        ``"reach"`` to assign a unique color per reach, or ``"none"``
        for a single color.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap for reach coloring.
    linewidth : float
        Stream line width.
    alpha : float
        Stream line opacity.
    title : str
        Plot title.
    figsize : tuple
        Figure size.
    show_grid : bool
        Overlay the element mesh outline.
    show_bottom_elev : bool
        If *True*, color stream nodes by bottom elevation instead of
        uniform reach coloring.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if show_grid:
        overlay_grid(model, ax)

    segments, reach_ids = get_stream_segments(model)

    if show_bottom_elev:
        # Scatter stream nodes colored by bottom elevation
        sx, sy = get_stream_node_xy(model)
        if _has_df_methods(model):
            rt_df = model.stream_rating_tables_df()
            sn_df = model.stream_nodes_df()
            # Get the bottom elevation for each stream node from the
            # rating table (one bottom_elev per stream_node_id)
            bot_map = rt_df.groupby("stream_node_id")["bottom_elev"].first()
            sn_ids = sn_df["stream_node_id"].values
            bot = np.array([bot_map.get(int(sid), np.nan) for sid in sn_ids])
        else:
            bot = model.get_stream_bottom_elevations()
        sc = ax.scatter(sx, sy, c=bot, cmap="terrain", s=10, zorder=6,
                        label="Stream nodes")
        fig.colorbar(sc, ax=ax, label="Stream Bottom Elev (ft)", shrink=0.8)
    elif color_by and color_by.lower() not in ("none", ""):
        n_reaches = len(reach_ids)
        colormap = plt.get_cmap(cmap, n_reaches)
        for i, seg in enumerate(segments):
            if len(seg) >= 2:
                ax.plot(seg[:, 0], seg[:, 1], color=colormap(i),
                        linewidth=linewidth, alpha=alpha, zorder=5,
                        label=f"Reach {int(reach_ids[i])}")
        # Show legend only when the number of reaches is manageable
        if n_reaches <= 20:
            ax.legend(loc="best", fontsize="x-small", ncol=2,
                      framealpha=0.9, title="Reaches")
    else:
        for seg in segments:
            if len(seg) >= 2:
                ax.plot(seg[:, 0], seg[:, 1], color="dodgerblue",
                        linewidth=linewidth, alpha=alpha, zorder=5)

    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 9. Well locations
# ──────────────────────────────────────────────────────────────────

def plot_well_locations(model, ax=None, cmap="plasma", figsize=(10, 8),
                        title="Well Locations", show_grid=True,
                        show_streams=False, marker_size_range=(20, 120),
                        save_path=None):
    """Plot well locations colored/sized by perforation depth.

    The marker color reflects the top-of-perforation elevation and the
    marker size reflects the perforation interval length (bottom minus
    top).

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    cmap : str
        Colormap for perforation depth coloring.
    figsize : tuple
        Figure size.
    title : str
        Plot title.
    show_grid : bool
        Overlay the element mesh outline.
    show_streams : bool
        Overlay the stream network.
    marker_size_range : tuple of float
        ``(min_size, max_size)`` in points-squared for the scatter
        markers.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if show_grid:
        overlay_grid(model, ax)
    if show_streams:
        overlay_streams(model, ax)

    if _has_df_methods(model):
        wdf = model.wells_df()
        n_wells = len(wdf)
    else:
        n_wells = model.n_wells

    if n_wells == 0:
        ax.set_title(title + " (no wells)")
        ax.autoscale_view()
        ax.set_aspect("equal")
        if save_path:
            savefig(fig, save_path)
        return fig, ax

    if _has_df_methods(model):
        wx = wdf["x"].values.astype(np.float64)
        wy = wdf["y"].values.astype(np.float64)
        perf_top = wdf["perf_top"].values.astype(np.float64)
        perf_bot = wdf["perf_bot"].values.astype(np.float64)
    else:
        wx, wy = model.get_well_coordinates()
        perf_top, perf_bot = model.get_well_perforation_top_bottom()
    perf_interval = np.abs(perf_top - perf_bot)

    # Scale marker sizes
    s_min, s_max = marker_size_range
    if perf_interval.max() - perf_interval.min() > 0:
        s_norm = (perf_interval - perf_interval.min()) / (
            perf_interval.max() - perf_interval.min()
        )
    else:
        s_norm = np.ones_like(perf_interval) * 0.5
    sizes = s_min + s_norm * (s_max - s_min)

    sc = ax.scatter(wx, wy, c=perf_top, s=sizes, cmap=cmap,
                    edgecolors="black", linewidths=0.4, zorder=7,
                    alpha=0.85)
    fig.colorbar(sc, ax=ax, label="Perforation Top Elev (ft)", shrink=0.8)

    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 10. Lake and diversion elements
# ──────────────────────────────────────────────────────────────────

def plot_lake_and_diversion_elements(model, ax=None, figsize=(10, 8),
                                     title="Lakes & Diversions",
                                     lake_color="deepskyblue",
                                     diversion_color="coral",
                                     alpha=0.55, show_grid=True,
                                     show_streams=False,
                                     save_path=None):
    """Highlight lake and diversion element groups on the model grid.

    Lake elements are filled with *lake_color* and diversion elements
    with *diversion_color*.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    figsize : tuple
        Figure size.
    title : str
        Plot title.
    lake_color : str
        Fill color for lake elements.
    diversion_color : str
        Fill color for diversion elements.
    alpha : float
        Fill opacity.
    show_grid : bool
        Overlay the element mesh outline.
    show_streams : bool
        Overlay the stream network.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if show_grid:
        overlay_grid(model, ax)
    if show_streams:
        overlay_streams(model, ax, color="dodgerblue", linewidth=1.0,
                        alpha=0.6, label="Streams")

    polygons = build_element_polygons(model)

    if _has_df_methods(model):
        edf = model.elements_df()
        elem_ids = edf["element_id"].values
        eid_to_idx = {int(e): i for i, e in enumerate(elem_ids)}

        # --- Lakes ---
        lk_df = model.lakes_df()
        lake_ids = lk_df["lake_id"].values if len(lk_df) > 0 else np.array([])
        lake_polys = []
        for _, row in lk_df.iterrows():
            for eid in row["elements"]:
                idx = eid_to_idx.get(int(eid))
                if idx is not None:
                    lake_polys.append(polygons[idx])

        if lake_polys:
            pc_lake = PolyCollection(
                lake_polys, facecolors=lake_color, edgecolors="navy",
                linewidths=0.5, alpha=alpha, zorder=4,
            )
            ax.add_collection(pc_lake)

        # --- Diversions ---
        dv_df = model.diversions_df()
        div_ids = dv_df["diversion_id"].values if len(dv_df) > 0 else np.array([])
        div_polys = []
        for _, row in dv_df.iterrows():
            elems = row.get("elements", [])
            if elems is not None:
                for eid in elems:
                    idx = eid_to_idx.get(int(eid))
                    if idx is not None:
                        div_polys.append(polygons[idx])

        if div_polys:
            pc_div = PolyCollection(
                div_polys, facecolors=diversion_color, edgecolors="darkred",
                linewidths=0.5, alpha=alpha, zorder=4,
            )
            ax.add_collection(pc_div)
    else:
        elem_ids = model.get_element_ids()
        eid_to_idx = {int(e): i for i, e in enumerate(elem_ids)}

        # --- Lakes ---
        lake_ids = model.get_lake_ids() if model.n_lakes > 0 else np.array([])
        lake_polys = []
        for lid in lake_ids:
            elems = model.get_elements_in_lake(int(lid))
            for eid in elems:
                idx = eid_to_idx.get(int(eid))
                if idx is not None:
                    lake_polys.append(polygons[idx])

        if lake_polys:
            pc_lake = PolyCollection(
                lake_polys, facecolors=lake_color, edgecolors="navy",
                linewidths=0.5, alpha=alpha, zorder=4,
            )
            ax.add_collection(pc_lake)

        # --- Diversions ---
        div_ids = model.get_diversion_ids() if model.n_diversions > 0 else np.array([])
        div_polys = []
        for did in div_ids:
            elems = model.get_diversion_elements(int(did))
            for eid in elems:
                idx = eid_to_idx.get(int(eid))
                if idx is not None:
                    div_polys.append(polygons[idx])

        if div_polys:
            pc_div = PolyCollection(
                div_polys, facecolors=diversion_color, edgecolors="darkred",
                linewidths=0.5, alpha=alpha, zorder=4,
            )
            ax.add_collection(pc_div)

    # Legend
    handles = []
    if lake_polys:
        handles.append(mpatches.Patch(facecolor=lake_color, edgecolor="navy",
                                      alpha=alpha, label=f"Lakes ({len(lake_ids)})"))
    if div_polys:
        handles.append(mpatches.Patch(facecolor=diversion_color,
                                      edgecolor="darkred", alpha=alpha,
                                      label=f"Diversions ({len(div_ids)})"))
    if not lake_polys and not div_polys:
        handles.append(mpatches.Patch(facecolor="white", edgecolor="gray",
                                      label="None found"))
    ax.legend(handles=handles, loc="best", fontsize="small", framealpha=0.9)

    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 11. Tile drain locations
# ──────────────────────────────────────────────────────────────────

def plot_tile_drain_locations(model, ax=None, figsize=(10, 8),
                              title="Tile Drain Locations",
                              marker="s", marker_size=30,
                              color="limegreen", edgecolor="darkgreen",
                              show_grid=True, show_streams=False,
                              save_path=None):
    """Plot tile drain node locations on the model grid.

    Parameters
    ----------
    model : IWFMModel
        An open IWFM model instance.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.
    figsize : tuple
        Figure size.
    title : str
        Plot title.
    marker : str
        Matplotlib marker style.
    marker_size : float
        Marker size in points-squared.
    color : str
        Marker fill color.
    edgecolor : str
        Marker edge color.
    show_grid : bool
        Overlay the element mesh outline.
    show_streams : bool
        Overlay the stream network.
    save_path : str, optional
        If given, save the figure to this path.

    Returns
    -------
    fig, ax
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if show_grid:
        overlay_grid(model, ax)
    if show_streams:
        overlay_streams(model, ax, color="dodgerblue", linewidth=1.0,
                        alpha=0.6)

    if _has_df_methods(model):
        td_df = model.tile_drains_df()
        n_td = len(td_df)
    else:
        n_td = model.get_n_tile_drain_nodes()

    if n_td == 0:
        ax.set_title(title + " (no tile drains)")
        ax.autoscale_view()
        ax.set_aspect("equal")
        if save_path:
            savefig(fig, save_path)
        return fig, ax

    if _has_df_methods(model):
        td_x = td_df["x"].values.astype(np.float64)
        td_y = td_df["y"].values.astype(np.float64)
        # Filter out any NaN coordinates
        valid = ~(np.isnan(td_x) | np.isnan(td_y))
        td_x = td_x[valid]
        td_y = td_y[valid]
    else:
        td_node_ids = model.get_tile_drain_nodes()
        x, y = model.get_node_coordinates()
        id_map = _id_to_index_map(model)

        td_x = []
        td_y = []
        for nid in td_node_ids:
            idx = id_map.get(int(nid))
            if idx is not None:
                td_x.append(x[idx])
                td_y.append(y[idx])
        td_x = np.array(td_x)
        td_y = np.array(td_y)

    ax.scatter(td_x, td_y, s=marker_size, c=color, edgecolors=edgecolor,
               marker=marker, linewidths=0.6, zorder=7, alpha=0.85,
               label=f"Tile drains ({len(td_x)})")

    ax.legend(loc="best", fontsize="small", framealpha=0.9)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# Example usage
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    # Add the project root to the path so the iwfm package resolves
    # when running this module directly from a repo checkout.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import iwfm_io

    # --- Open the model in inquiry mode (read-only, no simulation) ---
    # Adjust these paths to match your local sample-model layout.
    preprocessor_file = os.path.join(
        project_root, ".assets", "sample_model", "Preprocessor", "PreProcessor_Main.dat"
    )
    simulation_file = os.path.join(
        project_root, ".assets", "sample_model", "Simulation", "Simulation_Main.dat"
    )

    model = iwfm_io.dll.IWFMModel(preprocessor_file, simulation_file, is_for_inquiry=True)

    try:
        # 1. Grid mesh colored by subregion
        fig, ax = plot_grid_mesh(model, color_by="subregion",
                                 save_path="grid_mesh.png")
        plt.close(fig)

        # 2. Ground surface elevation
        fig, ax = plot_ground_surface_elevation(
            model, show_streams=True, save_path="ground_surface.png"
        )
        plt.close(fig)

        # 3. Layer 1 thickness
        fig, ax = plot_layer_thickness(model, layer=1,
                                       save_path="layer1_thickness.png")
        plt.close(fig)

        # 4. Horizontal hydraulic conductivity
        fig, ax = plot_aquifer_parameter(model, parameter="Kh", layer=1,
                                         log_scale=True,
                                         save_path="layer1_kh.png")
        plt.close(fig)

        # 5. Initial head contour
        fig, ax = plot_gw_head_contour(model, layer=1, show_streams=True,
                                       save_path="initial_head.png")
        plt.close(fig)

        # 6. Depth to water
        fig, ax = plot_depth_to_water(model, layer=1,
                                      save_path="depth_to_water.png")
        plt.close(fig)

        # 7. Head change (example: last head vs. itself = zero map)
        init = get_heads_snapshot(model, 1)
        fig, ax = plot_head_change(model, layer=1, heads_t1=init,
                                   heads_t2=init,
                                   save_path="head_change_example.png")
        plt.close(fig)

        # 8. Stream network colored by reach
        fig, ax = plot_stream_network(model, color_by="reach",
                                      save_path="stream_network.png")
        plt.close(fig)

        # 9. Well locations
        fig, ax = plot_well_locations(model, show_grid=True,
                                      show_streams=True,
                                      save_path="well_locations.png")
        plt.close(fig)

        # 10. Lakes and diversions
        fig, ax = plot_lake_and_diversion_elements(
            model, show_grid=True, show_streams=True,
            save_path="lakes_diversions.png"
        )
        plt.close(fig)

        # 11. Tile drain locations
        fig, ax = plot_tile_drain_locations(model, show_grid=True,
                                           show_streams=True,
                                           save_path="tile_drains.png")
        plt.close(fig)

        print("All maps generated successfully.")

    finally:
        del model
