"""Common plotting utilities for IWFM visualizations.

Provides grid-building helpers, stream network extraction, date
conversion, and reusable map/contour plotting functions that all
the individual visualization modules share.

All grid/stream helpers accept either:
- An ``IWFMModel`` instance (legacy numpy interface), or
- Any object with ``nodes_df()`` / ``elements_df()`` methods
  (e.g. ``IWFMModel`` with its new DataFrame methods, or
  ``IOModelAdapter``).
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.tri import Triangulation
from datetime import datetime, timedelta


# ──────────────────────────────────────────────────────────────────
# Date conversion
# ──────────────────────────────────────────────────────────────────

def excel_date_to_datetime(dates):
    """Convert Excel serial date numbers to Python datetime objects.

    IWFM DLL returns dates as modified Julian numbers shifted to the
    Excel epoch (days since 1899-12-30).
    """
    base = datetime(1899, 12, 30)
    if np.isscalar(dates):
        return base + timedelta(days=float(dates))
    return [base + timedelta(days=float(d)) for d in dates]


def iwfm_datestr_to_datetime(datestr):
    """Convert IWFM date string 'MM/DD/YYYY_HH:MM' to datetime."""
    date_part, time_part = datestr.split("_")
    month, day, year = date_part.split("/")
    hour, minute = time_part.split(":")
    h = int(hour)
    if h == 24:
        dt = datetime(int(year), int(month), int(day)) + timedelta(days=1)
    else:
        dt = datetime(int(year), int(month), int(day), h, int(minute))
    return dt


# ──────────────────────────────────────────────────────────────────
# Source resolution helpers
# ──────────────────────────────────────────────────────────────────

def _has_df_methods(source):
    """True if *source* has the DataFrame-returning interface."""
    return hasattr(source, "nodes_df") and callable(source.nodes_df)


def _resolve_grid(source):
    """Return ``(nodes_df, elements_df)`` from either interface.

    Parameters
    ----------
    source : IWFMModel, IOModelAdapter, or tuple
        If a model/adapter, calls ``nodes_df()`` and ``elements_df()``.
        If a ``(nodes_df, elements_df)`` tuple, returns as-is.
    """
    if isinstance(source, tuple) and len(source) == 2:
        return source
    if _has_df_methods(source):
        return source.nodes_df(), source.elements_df()
    raise TypeError(
        f"Cannot resolve grid from {type(source).__name__}. "
        "Expected an object with nodes_df()/elements_df() or a 2-tuple."
    )


def _get_node_arrays(source):
    """Return ``(node_ids, x, y)`` numpy arrays from either interface."""
    if _has_df_methods(source):
        ndf = source.nodes_df()
        return (ndf["node_id"].values,
                ndf["x"].values.astype(np.float64),
                ndf["y"].values.astype(np.float64))
    # Legacy IWFMModel
    ids = source.get_node_ids()
    x, y = source.get_node_coordinates()
    return ids, x, y


def _get_id_map(source):
    """Return dict mapping node ID -> 0-based index."""
    ids, _, _ = _get_node_arrays(source)
    return {int(nid): i for i, nid in enumerate(ids)}


def _get_element_configs(source):
    """Return (elem_ids, configs) where configs is list of [n1, n2, n3, n4]."""
    if _has_df_methods(source):
        edf = source.elements_df()
        elem_ids = edf["element_id"].values
        configs = []
        for _, row in edf.iterrows():
            configs.append([int(row["node1"]), int(row["node2"]),
                            int(row["node3"]), int(row["node4"])])
        return elem_ids, configs
    # Legacy
    elem_ids = source.get_element_ids()
    configs = [source.get_element_config(int(eid)).tolist() for eid in elem_ids]
    return elem_ids, configs


# ──────────────────────────────────────────────────────────────────
# Heads snapshot
# ──────────────────────────────────────────────────────────────────

def get_heads_snapshot(source, layer, time_index=-1):
    """Return a 1D array of head values at nodes for a single layer and timestep.

    Parameters
    ----------
    source : IWFMModel or IOModelAdapter
    layer : int
        1-based layer index.
    time_index : int
        Which output timestep to use (default -1 = last).

    Returns
    -------
    np.ndarray, shape ``(n_nodes,)``
    """
    if _has_df_methods(source):
        hdf = source.heads_df(layer)
        return hdf.iloc[time_index].values
    # Legacy path
    ts = source.get_time_specs()
    dates, heads = source.get_gw_heads_for_layer(
        layer, ts["dates"][0], ts["dates"][-1]
    )
    return heads[:, time_index]


# ──────────────────────────────────────────────────────────────────
# Grid construction
# ──────────────────────────────────────────────────────────────────

def _id_to_index_map(model):
    """Return dict mapping node ID -> 0-based index."""
    return _get_id_map(model)


def build_element_polygons(source):
    """Build polygon vertex arrays for every element.

    Parameters
    ----------
    source : IWFMModel, IOModelAdapter, or object with nodes_df()/elements_df()

    Returns
    -------
    polygons : list of np.ndarray
        Each entry is shape ``(n_verts, 2)`` with ``(x, y)`` columns.
    """
    ids, x, y = _get_node_arrays(source)
    id_map = {int(nid): i for i, nid in enumerate(ids)}
    _, configs = _get_element_configs(source)
    polygons = []
    for cfg in configs:
        n_v = 3 if cfg[3] == 0 else 4
        idx = [id_map[cfg[j]] for j in range(n_v)]
        polygons.append(np.column_stack([x[idx], y[idx]]))
    return polygons


def build_triangulation(source):
    """Build a ``matplotlib.tri.Triangulation`` for contour plotting.

    Quadrilateral elements are split into two triangles.
    """
    ids, x, y = _get_node_arrays(source)
    id_map = {int(nid): i for i, nid in enumerate(ids)}
    _, configs = _get_element_configs(source)
    triangles = []
    for cfg in configs:
        if cfg[3] == 0:
            triangles.append([id_map[cfg[j]] for j in range(3)])
        else:
            idx = [id_map[cfg[j]] for j in range(4)]
            triangles.append([idx[0], idx[1], idx[2]])
            triangles.append([idx[0], idx[2], idx[3]])
    return Triangulation(x, y, np.array(triangles))


def get_element_centroids(source):
    """Return ``(cx, cy)`` arrays of element centroid coordinates."""
    ids, x, y = _get_node_arrays(source)
    id_map = {int(nid): i for i, nid in enumerate(ids)}
    elem_ids, configs = _get_element_configs(source)
    cx = np.zeros(len(elem_ids))
    cy = np.zeros(len(elem_ids))
    for i, cfg in enumerate(configs):
        n_v = 3 if cfg[3] == 0 else 4
        idx = [id_map[cfg[j]] for j in range(n_v)]
        cx[i] = x[idx].mean()
        cy[i] = y[idx].mean()
    return cx, cy


def node_values_to_element(source, node_values):
    """Average node values to element centroids.

    Parameters
    ----------
    node_values : np.ndarray, shape ``(n_nodes,)``

    Returns
    -------
    np.ndarray, shape ``(n_elements,)``
    """
    ids, _, _ = _get_node_arrays(source)
    id_map = {int(nid): i for i, nid in enumerate(ids)}
    elem_ids, configs = _get_element_configs(source)
    out = np.zeros(len(elem_ids))
    for i, cfg in enumerate(configs):
        n_v = 3 if cfg[3] == 0 else 4
        idx = [id_map[cfg[j]] for j in range(n_v)]
        out[i] = node_values[idx].mean()
    return out


# ──────────────────────────────────────────────────────────────────
# Stream network
# ──────────────────────────────────────────────────────────────────

def get_stream_segments(source):
    """Extract stream network as polyline segments.

    Returns
    -------
    segments : list of np.ndarray
        One ``(n, 2)`` array per reach (x, y polyline).
    reach_ids : np.ndarray
    """
    if _has_df_methods(source):
        ndf = source.nodes_df()
        coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
        sn_df = source.stream_nodes_df()
        rdf = source.reaches_df()
        reach_ids = rdf["reach_id"].values
        segments = []
        for rid in reach_ids:
            mask = sn_df["reach_id"] == rid
            gw_nodes = sn_df.loc[mask, "gw_node_id"].values
            pts = []
            for gn in gw_nodes:
                if int(gn) in coord:
                    pts.append(coord[int(gn)])
            if len(pts) >= 2:
                segments.append(np.array(pts))
            else:
                segments.append(np.empty((0, 2)))
        return segments, reach_ids

    # Legacy
    x, y = source.get_node_coordinates()
    id_map = _get_id_map(source)
    reach_ids = source.get_reach_ids()
    segments = []
    for rid in reach_ids:
        gw_nodes = source.get_reach_gw_nodes(int(rid))
        idx = [id_map[int(n)] for n in gw_nodes if int(n) in id_map]
        if len(idx) >= 2:
            segments.append(np.column_stack([x[idx], y[idx]]))
        else:
            segments.append(np.empty((0, 2)))
    return segments, reach_ids


def get_stream_node_xy(source):
    """Return ``(sx, sy)`` coordinate arrays for all stream nodes.

    Maps each stream node to its associated GW node coordinates via
    the reach connectivity.
    """
    if _has_df_methods(source):
        ndf = source.nodes_df()
        coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
        sn_df = source.stream_nodes_df()
        sx = np.zeros(len(sn_df))
        sy = np.zeros(len(sn_df))
        for i, (_, row) in enumerate(sn_df.iterrows()):
            gw_id = int(row["gw_node_id"])
            if gw_id in coord:
                sx[i], sy[i] = coord[gw_id]
        return sx, sy

    # Legacy
    x, y = source.get_node_coordinates()
    id_map = _get_id_map(source)
    n_sn = source.n_stream_nodes
    sx = np.zeros(n_sn)
    sy = np.zeros(n_sn)
    sn_ids = source.get_stream_node_ids()
    sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}

    reach_ids = source.get_reach_ids()
    for rid in reach_ids:
        strm_nodes = source.get_reach_stream_nodes(int(rid))
        gw_nodes = source.get_reach_gw_nodes(int(rid))
        for sn, gn in zip(strm_nodes, gw_nodes):
            si = sn_map.get(int(sn))
            gi = id_map.get(int(gn))
            if si is not None and gi is not None:
                sx[si] = x[gi]
                sy[si] = y[gi]
    return sx, sy


# ──────────────────────────────────────────────────────────────────
# Reusable plotting primitives
# ──────────────────────────────────────────────────────────────────

def plot_element_map(source, values, ax=None, cmap="viridis", label="",
                     title="", show_mesh=False, vmin=None, vmax=None,
                     figsize=(10, 8)):
    """Plot a color-filled element map.

    Parameters
    ----------
    source : IWFMModel, IOModelAdapter, or object with nodes_df()/elements_df()
    values : array-like, shape ``(n_elements,)``
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    polygons = build_element_polygons(source)
    pc = PolyCollection(
        polygons, array=np.asarray(values, dtype=float), cmap=cmap,
        edgecolors="gray" if show_mesh else "face",
        linewidths=0.3 if show_mesh else 0,
    )
    if vmin is not None:
        pc.set_clim(vmin=vmin)
    if vmax is not None:
        pc.set_clim(vmax=vmax)
    ax.add_collection(pc)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)
    cb = fig.colorbar(pc, ax=ax, label=label, shrink=0.8)
    return fig, ax, pc, cb


def plot_contour_map(source, node_values, ax=None, cmap="viridis",
                     levels=20, label="", title="", filled=True,
                     figsize=(10, 8)):
    """Plot a contour map from node values."""
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    tri = build_triangulation(source)
    if filled:
        cs = ax.tricontourf(tri, node_values, levels=levels, cmap=cmap)
    else:
        cs = ax.tricontour(tri, node_values, levels=levels, cmap=cmap)
    ax.set_aspect("equal")
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    if title:
        ax.set_title(title)
    cb = fig.colorbar(cs, ax=ax, label=label, shrink=0.8)
    return fig, ax, cs, cb


def overlay_streams(source, ax, color="dodgerblue", linewidth=1.5,
                    alpha=0.9, label="Stream network"):
    """Add stream network lines to an existing axes."""
    segments, _ = get_stream_segments(source)
    for i, seg in enumerate(segments):
        if len(seg) >= 2:
            ax.plot(seg[:, 0], seg[:, 1], color=color,
                    linewidth=linewidth, alpha=alpha, zorder=5,
                    label=label if i == 0 else None)


def overlay_grid(source, ax, color="gray", linewidth=0.2, alpha=0.4):
    """Add element mesh outline to an existing axes."""
    polygons = build_element_polygons(source)
    pc = PolyCollection(polygons, facecolors="none", edgecolors=color,
                        linewidths=linewidth, alpha=alpha)
    ax.add_collection(pc)


def savefig(fig, path, dpi=150):
    """Save figure with tight layout."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"Saved: {path}")


# ──────────────────────────────────────────────────────────────────
# Visualization modules
# ──────────────────────────────────────────────────────────────────
# Imported last (they use the shared helpers above) so that
# `iwfm.plots.maps` etc. are available directly after `import iwfm.plots`.

from . import (  # noqa: E402,F401
    animations,
    connectivity,
    cross_sections,
    maps,
    profiles,
    seasonal,
    spatial_patterns,
    stream_analysis,
    subsidence,
    summary,
    supply_demand,
    timeseries,
    trends,
    water_balance,
)
