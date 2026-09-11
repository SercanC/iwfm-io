"""GIS exports — IWFM model geometry as GeoDataFrames, GeoPackage, or
shapefiles.

Turns a model's grid, stream network, lakes, and point features into
`geopandas` GeoDataFrames and writes them to standard GIS formats:

- :func:`export_gis` — one call writes every available layer to a
  GeoPackage (``.gpkg``, multi-layer) or a folder of ESRI Shapefiles.
- Per-layer builders (:func:`nodes_gdf`, :func:`elements_gdf`,
  :func:`subregions_gdf`, :func:`streams_gdf`, :func:`stream_nodes_gdf`,
  :func:`lakes_gdf`, :func:`tile_drains_gdf`, :func:`wells_gdf`) for
  working with individual layers in Python.

Every function takes a *model* — an :class:`~iwfm_io.IOModelAdapter`
(from :func:`~iwfm_io.open_model`) or a DLL
:class:`~iwfm_io.dll.IWFMModel` — anything exposing the
``nodes_df()`` / ``elements_df()`` DataFrame interface. Geometry is
constructed from node coordinates and element configurations, so the
source frames do not need to be GeoDataFrames themselves.

IWFM input files carry no coordinate reference system; pass ``crs=``
(e.g. ``"EPSG:26910"``) when you know the model's projection so the
written layers georeference correctly in GIS software.

Requires the ``[geo]`` extra (``pip install iwfm-io[geo]``); geopandas
and shapely are imported when the functions are called, not at module
import.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Layer name -> builder attribute, in export order.
GIS_LAYERS = (
    "nodes",
    "elements",
    "subregions",
    "streams",
    "stream_nodes",
    "lakes",
    "tile_drains",
    "wells",
)


def _require_geo():
    try:
        import geopandas as gpd
        import shapely  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "GIS exports require geopandas and shapely — "
            "install with: pip install iwfm-io[geo]"
        ) from exc
    return gpd


def _node_coords(model):
    """Return (id -> (x, y) dict, nodes DataFrame without geometry)."""
    ndf = pd.DataFrame(model.nodes_df().drop(columns="geometry",
                                             errors="ignore"))
    coords = dict(zip(ndf["node_id"].astype(int),
                      zip(ndf["x"].astype(float), ndf["y"].astype(float))))
    return coords, ndf


def _element_polygons(model):
    """Return (elements DataFrame without geometry, list of shapely Polygons)."""
    from shapely.geometry import Polygon

    coords, _ = _node_coords(model)
    edf = pd.DataFrame(model.elements_df().drop(columns="geometry",
                                                errors="ignore"))
    edf = edf.reset_index(drop=True)
    polys = []
    for n1, n2, n3, n4 in zip(edf["node1"], edf["node2"],
                              edf["node3"], edf["node4"]):
        ids = [n1, n2, n3] if int(n4) == 0 else [n1, n2, n3, n4]
        polys.append(Polygon([coords[int(i)] for i in ids]))
    return edf, polys


def _maybe_set_crs(gdf, crs):
    if crs is not None:
        return gdf.set_crs(crs, allow_override=True)
    return gdf


def _merge_data(df, data, key):
    """Left-merge an optional attribute DataFrame on *key*."""
    if data is None:
        return df
    data = pd.DataFrame(data)
    if key not in data.columns:
        raise ValueError(
            f"attribute data must carry a '{key}' column to join on; "
            f"got columns {list(data.columns)}")
    dup = [c for c in data.columns if c != key and c in df.columns]
    if dup:
        raise ValueError(
            f"attribute data columns {dup} collide with layer columns — "
            "rename them before exporting")
    return df.merge(data, on=key, how="left")


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------


def nodes_gdf(model, crs=None, data=None, stratigraphy=True):
    """Grid nodes as a Point layer.

    Attributes: ``node_id``, ``x``, ``y``; with ``stratigraphy=True``
    (default) also the stratigraphy table (ground-surface ``elevation``
    and per-layer aquitard/aquifer thicknesses) when the model provides
    it. ``data`` merges an extra per-node attribute DataFrame (must have
    a ``node_id`` column) — e.g. heads at a timestep or depth to water.
    """
    gpd = _require_geo()
    from shapely.geometry import Point

    _, ndf = _node_coords(model)
    if stratigraphy:
        try:
            strat = pd.DataFrame(model.stratigraphy_df())
            ndf = ndf.merge(strat, on="node_id", how="left")
        except Exception as exc:  # stratigraphy is optional context
            logger.warning("nodes_gdf: no stratigraphy joined (%s: %s); "
                           "exporting coordinates only",
                           type(exc).__name__, exc)
    ndf = _merge_data(ndf, data, "node_id")
    geom = [Point(x, y) for x, y in zip(ndf["x"], ndf["y"])]
    return _maybe_set_crs(gpd.GeoDataFrame(ndf, geometry=geom), crs)


def elements_gdf(model, crs=None, data=None):
    """Finite elements as a Polygon layer.

    Attributes: ``element_id``, ``node1``–``node4`` (``node4 == 0`` for
    triangles), ``subregion`` and, when available, the subregion
    ``subregion_name``. ``data`` merges an extra per-element attribute
    DataFrame (must have an ``element_id`` column) — e.g. land use or
    pumping.
    """
    gpd = _require_geo()

    edf, polys = _element_polygons(model)
    try:
        subs = pd.DataFrame(model.subregions_df()).rename(columns={
            "subregion_id": "subregion", "name": "subregion_name"})
        edf = edf.merge(subs, on="subregion", how="left")
    except Exception as exc:
        logger.warning("elements_gdf: subregion names not joined (%s: %s)",
                       type(exc).__name__, exc)
    edf = _merge_data(edf, data, "element_id")
    return _maybe_set_crs(gpd.GeoDataFrame(edf, geometry=polys), crs)


def subregions_gdf(model, crs=None):
    """Subregions as dissolved element polygons.

    Attributes: ``subregion_id``, ``name`` (when available),
    ``n_elements``, ``area`` (model length units squared).
    """
    gpd = _require_geo()
    from shapely.ops import unary_union

    edf, polys = _element_polygons(model)
    rows, geoms = [], []
    for sid, grp in edf.groupby("subregion"):
        merged = unary_union([polys[i] for i in grp.index])
        geoms.append(merged)
        rows.append({"subregion_id": int(sid), "n_elements": len(grp),
                     "area": merged.area})
    out = pd.DataFrame(rows)
    try:
        subs = pd.DataFrame(model.subregions_df())
        out = out.merge(subs, on="subregion_id", how="left")
        out = out[["subregion_id", "name", "n_elements", "area"]]
    except Exception as exc:
        logger.warning("subregions_gdf: subregion names not joined (%s: %s)",
                       type(exc).__name__, exc)
    return _maybe_set_crs(gpd.GeoDataFrame(out, geometry=geoms), crs)


def streams_gdf(model, crs=None):
    """Stream reaches as a LineString layer.

    One line per reach, following the reach's stream nodes (positioned
    at their groundwater nodes). Attributes: ``reach_id``, ``name``,
    ``n_nodes``, ``outflow_dest``.
    """
    gpd = _require_geo()
    from shapely.geometry import LineString

    coords, _ = _node_coords(model)
    sn = pd.DataFrame(model.stream_nodes_df().drop(columns="geometry",
                                                   errors="ignore"))
    reaches = pd.DataFrame(model.reaches_df())

    rows, geoms = [], []
    for _, reach in reaches.iterrows():
        rid = int(reach["reach_id"])
        gw_nodes = sn.loc[sn["reach_id"] == rid, "gw_node_id"].astype(int)
        pts = [coords[g] for g in gw_nodes if g in coords]
        if len(pts) < 2:
            logger.warning("streams_gdf: reach %s has fewer than two "
                           "locatable nodes — skipped", rid)
            continue
        geoms.append(LineString(pts))
        rows.append({k: reach[k] for k in reaches.columns})
    return _maybe_set_crs(
        gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms), crs)


def stream_nodes_gdf(model, crs=None):
    """Stream nodes as a Point layer (at their groundwater nodes).

    Attributes: ``stream_node_id``, ``reach_id``, ``gw_node_id``.
    """
    gpd = _require_geo()
    from shapely.geometry import Point

    coords, _ = _node_coords(model)
    sn = pd.DataFrame(model.stream_nodes_df().drop(columns="geometry",
                                                   errors="ignore"))
    geom = [Point(*coords[int(g)]) if int(g) in coords else None
            for g in sn["gw_node_id"]]
    return _maybe_set_crs(gpd.GeoDataFrame(sn, geometry=geom), crs)


def lakes_gdf(model, crs=None):
    """Lakes as merged element polygons.

    Attributes: ``lake_id``, ``n_elements`` (and any other scalar
    columns the lake file carries).
    """
    gpd = _require_geo()
    from shapely.ops import unary_union

    lakes = pd.DataFrame(model.lakes_df())
    if lakes.empty:
        return _maybe_set_crs(
            gpd.GeoDataFrame(lakes.drop(columns="elements",
                                        errors="ignore"),
                             geometry=[]), crs)
    edf, polys = _element_polygons(model)
    poly_of = dict(zip(edf["element_id"].astype(int), polys))

    geoms = [unary_union([poly_of[int(e)] for e in row["elements"]
                          if int(e) in poly_of])
             for _, row in lakes.iterrows()]
    out = lakes.drop(columns="elements", errors="ignore")
    return _maybe_set_crs(gpd.GeoDataFrame(out, geometry=geoms), crs)


def tile_drains_gdf(model, crs=None):
    """Tile drains as a Point layer (``id``, ``node``, ``x``, ``y``)."""
    gpd = _require_geo()
    from shapely.geometry import Point

    td = pd.DataFrame(model.tile_drains_df().drop(columns="geometry",
                                                  errors="ignore"))
    geom = [Point(x, y) if np.isfinite(x) else None
            for x, y in zip(td.get("x", []), td.get("y", []))]
    return _maybe_set_crs(gpd.GeoDataFrame(td, geometry=geom), crs)


def wells_gdf(model, crs=None):
    """Pumping wells as a Point layer (from the well specification file).

    Attributes: ``well_id``, ``x``, ``y``, ``radius``, ``perf_top``,
    ``perf_bot``, ``name``. Empty for models that pump by element only.
    """
    gpd = _require_geo()
    from shapely.geometry import Point

    wdf = pd.DataFrame(model.wells_df().drop(columns="geometry",
                                             errors="ignore"))
    geom = [Point(x, y) for x, y in zip(wdf.get("x", []), wdf.get("y", []))]
    return _maybe_set_crs(gpd.GeoDataFrame(wdf, geometry=geom), crs)


_BUILDERS = {
    "nodes": nodes_gdf,
    "elements": elements_gdf,
    "subregions": subregions_gdf,
    "streams": streams_gdf,
    "stream_nodes": stream_nodes_gdf,
    "lakes": lakes_gdf,
    "tile_drains": tile_drains_gdf,
    "wells": wells_gdf,
}


# ---------------------------------------------------------------------------
# One-call export
# ---------------------------------------------------------------------------


def export_gis(model, path, layers=None, crs=None,
               node_data=None, element_data=None):
    """Write a model's spatial layers to a GeoPackage or shapefiles.

    Parameters
    ----------
    model : IOModelAdapter or IWFMModel
        Anything exposing the ``nodes_df()``/``elements_df()`` interface
        (see :func:`iwfm_io.open_model`).
    path : str or Path
        Destination. A ``.gpkg`` suffix writes one multi-layer
        GeoPackage (recommended); anything else is treated as a
        directory and one ESRI Shapefile is written per layer inside it.
        An existing GeoPackage is replaced.
    layers : sequence of str, optional
        Layer names from :data:`GIS_LAYERS`; default is every layer the
        model can provide (layers whose source data is missing or empty
        are skipped with a log message).
    crs : str or pyproj.CRS, optional
        Coordinate reference system of the model's native coordinates
        (e.g. ``"EPSG:26910"``). IWFM files do not record one; without
        it the layers are written unreferenced.
    node_data, element_data : DataFrame, optional
        Extra attributes merged onto the ``nodes`` / ``elements`` layers
        (keyed on ``node_id`` / ``element_id``) — e.g. simulated heads,
        depth to water, land use, aquifer parameters.

    Returns
    -------
    dict
        ``{layer_name: rows_written}`` for the layers actually written.

    Examples
    --------
    >>> from iwfm_io import open_model, export_gis
    >>> m = open_model("path/to/model")
    >>> export_gis(m, "model.gpkg", crs="EPSG:26910")
    >>> heads = m.heads_df(layer=1)
    >>> dtw = m.stratigraphy_df()[["node_id"]].assign(
    ...     dtw=m.stratigraphy_df()["elevation"].values
    ...         - heads.iloc[-1].values)
    >>> export_gis(m, "model_dtw.gpkg", layers=["nodes"], node_data=dtw)
    """
    _require_geo()

    if layers is None:
        requested = list(GIS_LAYERS)
        explicit = False
    else:
        if isinstance(layers, str):
            layers = [layers]
        unknown = set(layers) - set(GIS_LAYERS)
        if unknown:
            raise ValueError(
                f"unknown GIS layer(s) {sorted(unknown)}; "
                f"available: {list(GIS_LAYERS)}")
        requested = list(layers)
        explicit = True

    path = Path(path)
    if path.suffix and path.suffix.lower() != ".gpkg":
        raise ValueError(
            f"export_gis writes a GeoPackage (.gpkg) or a folder of "
            f"shapefiles; {path.suffix!r} is not supported")
    for label, data in (("node_data", node_data), ("element_data", element_data)):
        if data is not None:
            key = "node_id" if label == "node_data" else "element_id"
            if key in data.columns and data[key].duplicated().any():
                dup = sorted(data.loc[data[key].duplicated(), key].unique()[:3])
                raise ValueError(
                    f"{label} has duplicate {key} values (e.g. {dup}); "
                    "one row per feature is required")
    as_gpkg = path.suffix.lower() == ".gpkg"
    if as_gpkg:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if explicit:
                logger.warning(
                    "export_gis: replacing existing %s -- a partial "
                    "export (layers=...) rewrites the whole file, layers "
                    "not listed are lost", path.name)
            path.unlink()
    else:
        path.mkdir(parents=True, exist_ok=True)

    extra = {"nodes": {"data": node_data},
             "elements": {"data": element_data}}

    written = {}
    for name in requested:
        try:
            gdf = _BUILDERS[name](model, crs=crs, **extra.get(name, {}))
        except Exception as exc:
            if explicit:
                raise
            logger.info("export_gis: skipping '%s' (%s)", name,
                        str(exc).splitlines()[0])
            continue
        if len(gdf) == 0:
            if explicit:
                logger.warning("export_gis: layer '%s' is empty", name)
            else:
                logger.info("export_gis: skipping empty layer '%s'", name)
                continue
        if as_gpkg:
            gdf.to_file(path, layer=name, driver="GPKG")
        else:
            gdf.to_file(path / f"{name}.shp")
        written[name] = len(gdf)

    if not written:
        raise RuntimeError("export_gis wrote no layers — the model "
                           "provided no exportable spatial data")
    logger.info("export_gis: wrote %s -> %s",
                ", ".join(f"{k}({v})" for k, v in written.items()), path)
    return written
