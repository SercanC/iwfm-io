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
# Budget post-processing
# ──────────────────────────────────────────────────────────────────

#: Cubic feet → acre-feet. IWFM models almost always carry volumes in
#: cubic feet internally, so budget plots use this as their default
#: ``fact_vl`` to display acre-feet; pass ``fact_vl=1.0`` for raw model
#: units (or your own factor for non-cubic-feet models).
CUFT_TO_AF = 1.0 / 43560.0

def filter_balance_components(names, values, extras=None, component_axis=1):
    """Keep only the components that enter the mass balance.

    IWFM budget outputs mix balance components — tagged ``(+)`` inflow,
    ``(-)`` outflow, ``(=)`` closure — with untagged reporting-only
    columns (e.g. the GW budget's 'Percolation', which informs but does
    not enter the balance; only 'Deep Percolation (+)' does). Budget
    plots should show the balance components:

    - tagged ``(+)`` / ``(-)`` components are kept,
    - the synthesized 'Change in Storage' is kept,
    - untagged reporting columns and ``(=)`` closure residuals drop.

    If *no* name carries a direction tag, the set came from IWFM's
    monthly/annual flows API, which is already balance-only — it passes
    through unchanged.

    Returns ``(names, values)`` or ``(names, values, extras)``.
    """
    upper = [str(n).upper() for n in names]
    if not any("(+)" in n or "(-)" in n for n in upper):
        return (names, values) if extras is None else (names, values, extras)

    keep = [i for i, n in enumerate(upper)
            if "(+)" in n or "(-)" in n or "CHANGE IN STORAGE" in n]
    names = [names[i] for i in keep]
    values = np.take(np.asarray(values, dtype=float), keep,
                     axis=component_axis)
    if extras is None:
        return names, values
    extras = np.take(np.asarray(extras, dtype=float), keep,
                     axis=component_axis)
    return names, values, extras


def sign_budget_components(names, values):
    """Convert IWFM budget magnitudes into signed in/out flows.

    IWFM budget columns hold positive magnitudes; the direction lives in
    the label — ``(+)`` inflow, ``(-)`` outflow, ``(=)`` closure residual
    (Discrepancy). Balance-style plots (Sankey, butterfly, in/out bars)
    need signed values instead:

    - ``(+)`` components keep their magnitude (inflow),
    - ``(-)`` components are negated (outflow),
    - ``(=)`` components and 'Time' are dropped,
    - 'Change in Storage' (ending − beginning) is negated: a storage
      *gain* removes water from the balance (outflow side), a storage
      *release* supplies it,
    - untagged components (e.g. 'Percolation') pass through unchanged.

    The direction tags are stripped from the returned names.

    Parameters
    ----------
    names : list of str
    values : array-like
        One value per component (e.g. time-averaged flows), or an
        ``(n_times, n_components)`` array.

    Returns
    -------
    (names, signed_values)
    """
    values = np.asarray(values, dtype=float)
    one_d = values.ndim == 1
    keep_idx, out_names, signs = [], [], []
    for i, raw in enumerate(names):
        s = str(raw)
        if "(=)" in s or s.strip().lower() == "time":
            continue
        clean = s.replace("(+)", "").replace("(-)", "").strip()
        if "CHANGE IN STORAGE" in s.upper():
            sign = -1.0
        elif "(-)" in s:
            sign = -1.0
        else:
            sign = 1.0
        keep_idx.append(i)
        out_names.append(clean)
        signs.append(sign)
    signs = np.asarray(signs)
    if one_d:
        return out_names, values[keep_idx] * signs
    return out_names, values[:, keep_idx] * signs


def combine_storage_terms(names, values, extras=None, component_axis=1):
    """Replace 'Beginning Storage' / 'Ending Storage' with 'Change in Storage'.

    IWFM budget outputs report cumulative aquifer storage at the start
    and end of each step. Those columns are orders of magnitude larger
    than the flux terms (drowning everything else in plots) and their
    absolute values are datum-dependent. Their difference — ending
    minus beginning, positive = storage gain — is a flux at the same
    scale as the other components, inserted where the pair was.

    Parameters
    ----------
    names : list of str
        Component names.
    values : array-like
        Component values, components along *component_axis*
        (1 for ``(n_times, n_components)`` time series, 0 for
        ``(n_components, ...)`` aggregates).
    extras : array-like, optional
        Companion per-component array (e.g. standard deviations),
        combined in quadrature — an approximation, since the two
        storage series are strongly correlated.
    component_axis : int

    Returns
    -------
    (names, values) — or (names, values, extras) when *extras* is
    given. Returned unchanged when the storage pair is not present.
    """
    upper = [str(n).upper() for n in names]

    # Running-total columns (e.g. 'Cumulative Subsidence') have the same
    # scale problem as the storage pair and always duplicate a flux-scale
    # twin — drop them.
    cum = [i for i, n in enumerate(upper) if n.startswith("CUMULATIVE")]
    if cum:
        keep0 = [i for i in range(len(names)) if i not in cum]
        names = [names[i] for i in keep0]
        values = np.take(np.asarray(values, dtype=float), keep0,
                         axis=component_axis)
        if extras is not None:
            extras = np.take(np.asarray(extras, dtype=float), keep0,
                             axis=component_axis)
        upper = [str(n).upper() for n in names]

    b = next((i for i, n in enumerate(upper) if "BEGINNING STORAGE" in n), None)
    e = next((i for i, n in enumerate(upper) if "ENDING STORAGE" in n), None)
    values = np.asarray(values, dtype=float)
    if b is None or e is None:
        return (names, values) if extras is None else (names, values, extras)

    begin = np.take(values, b, axis=component_axis)
    end = np.take(values, e, axis=component_axis)
    delta = end - begin

    keep = [i for i in range(len(names)) if i not in (b, e)]
    insert_at = sum(1 for i in keep if i < min(b, e))

    new_names = [names[i] for i in keep]
    new_names.insert(insert_at, "Change in Storage")
    new_values = np.take(values, keep, axis=component_axis)
    new_values = np.insert(new_values, insert_at, delta, axis=component_axis)

    if extras is None:
        return new_names, new_values
    extras = np.asarray(extras, dtype=float)
    combined = np.sqrt(np.take(extras, b, axis=component_axis) ** 2
                       + np.take(extras, e, axis=component_axis) ** 2)
    new_extras = np.take(extras, keep, axis=component_axis)
    new_extras = np.insert(new_extras, insert_at, combined, axis=component_axis)
    return new_names, new_values, new_extras


def water_year_totals(datetimes, values):
    """Sum a time-series table to water years (Oct–Sep).

    Parameters
    ----------
    datetimes : sequence of datetime
        Timestamps for each row of *values*.
    values : array-like, shape ``(n_times, n_components)``

    Returns
    -------
    (wy_ends, totals) — one row per water year, dated by the year's
    ending Sep 30. Change-in-Storage columns telescope to the true
    annual value under this sum. Incomplete leading/trailing water
    years (fewer time steps than a full year) are dropped — a stub
    total would read as a real annual value.
    """
    import pandas as pd
    df = pd.DataFrame(np.asarray(values, dtype=float),
                      index=pd.DatetimeIndex(datetimes))
    grouped = df.resample("YS-OCT")
    wy = grouped.sum()
    # Only the first and last bins can be incomplete; compare against
    # the median bin size (tolerating leap-year variation) rather than
    # the max, which would reject 365-day years next to a 366-day one.
    counts = grouped.size()
    if len(wy) > 1:
        med = counts.median()
        keep = np.ones(len(wy), dtype=bool)
        keep[0] = counts.iloc[0] >= 0.95 * med
        keep[-1] = counts.iloc[-1] >= 0.95 * med
        wy = wy[keep]
    ends = [(ts + pd.DateOffset(months=11, days=29)).to_pydatetime()
            for ts in wy.index]
    return ends, wy.to_numpy()


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
    style_map_axes(ax)
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
    style_map_axes(ax)
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


def style_map_axes(ax):
    """Shared map chrome: Easting/Northing axis labels without the
    coordinate tick labels (raw model coordinates rarely mean anything
    to the reader)."""
    ax.set_xlabel("Easting")
    ax.set_ylabel("Northing")
    ax.tick_params(labelbottom=False, labelleft=False)


def map_legend_outside(ax, handles=None, title=None, ncol=1):
    """Place a map legend outside the frame, at the right edge of the
    figure so it clears any colorbar. ``savefig``'s tight bounding box
    grows the saved image to include it. No-op without legend entries."""
    fig = ax.figure
    if handles is None:
        handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return None
    return fig.legend(handles=handles, title=title, ncol=ncol,
                      loc="center left", bbox_to_anchor=(0.98, 0.5),
                      fontsize="small", framealpha=0.9)


def savefig(fig, path, dpi=150):
    """Save figure with tight layout."""
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    print(f"Saved: {path}")


# ──────────────────────────────────────────────────────────────────
# Visualization modules
# ──────────────────────────────────────────────────────────────────
# Imported last (they use the shared helpers above) so that
# `iwfm_io.plots.maps` etc. are available directly after `import iwfm_io.plots`.

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
