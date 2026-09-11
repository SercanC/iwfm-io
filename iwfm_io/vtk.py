"""VTK exports — the IWFM model as a 3D layered mesh for ParaView.

Writes VTK XML files with **no VTK dependency** — plain numpy and text:

- :func:`export_vtk` — the model as one ``.vtu`` (UnstructuredGrid):
  the 2D finite-element grid extruded through the stratigraphy into 3D
  cells (wedges for triangles, hexahedra for quads), one cell layer per
  aquifer layer, with optional point/cell data arrays.
- :func:`export_vtk_timeseries` — a ParaView time series: one ``.vtu``
  per timestep carrying simulated heads as point data, plus the ``.pvd``
  collection file that animates them.

Geometry comes from ``nodes_df()`` + ``elements_df()`` +
``stratigraphy_df()``, so both :class:`~iwfm_io.IOModelAdapter` and the
DLL :class:`~iwfm_io.dll.IWFMModel` work as sources. Aquifer-layer
elevations follow IWFM's stratigraphy convention: each layer's aquitard
(interbed) thickness sits *above* its aquifer —

    top(1)    = ground surface − aquitard_1
    bottom(k) = top(k) − aquifer_k
    top(k+1)  = bottom(k) − aquitard_{k+1}

Each aquifer layer gets its own top and bottom point sheets, so
aquitard gaps between layers are represented faithfully (aquitards
themselves are not meshed). Nodes where a layer pinches out produce
zero-height cells, which ParaView renders as collapsed — filter on the
``thickness`` cell array to hide them.

Open the result in ParaView: *File → Open*, pick the ``.vtu`` (or the
``.pvd`` for a time series), Apply. Vertical exaggeration is baked in
via ``z_scale`` (regional models are far wider than thick — start
around 20–100).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from xml.sax.saxutils import quoteattr
import pandas as pd

logger = logging.getLogger(__name__)

_VTK_WEDGE = 13
_VTK_HEXAHEDRON = 12


# ---------------------------------------------------------------------------
# Geometry assembly
# ---------------------------------------------------------------------------


def _grid_frames(model):
    nodes = pd.DataFrame(model.nodes_df().drop(columns="geometry",
                                               errors="ignore"))
    elems = pd.DataFrame(model.elements_df().drop(columns="geometry",
                                                  errors="ignore"))
    strat = pd.DataFrame(model.stratigraphy_df())
    strat = (nodes[["node_id"]].merge(strat, on="node_id", how="left")
             if "node_id" in strat.columns else strat)
    if strat[["elevation"]].isna().any().any():
        raise ValueError("stratigraphy is missing rows for some nodes")
    return nodes.reset_index(drop=True), elems.reset_index(drop=True), \
        strat.reset_index(drop=True)


def _layer_elevations(strat):
    """Return (tops, bottoms) arrays of shape (n_nodes, n_layers)."""
    n_layers = len([c for c in strat.columns if c.startswith("aquifer_")])
    if n_layers == 0:
        raise ValueError("stratigraphy has no aquifer_* thickness columns")
    z = strat["elevation"].to_numpy(dtype=float)
    tops = np.empty((len(strat), n_layers))
    bottoms = np.empty((len(strat), n_layers))
    for k in range(1, n_layers + 1):
        aquitard = strat.get(f"aquitard_{k}")
        thick = (aquitard.to_numpy(dtype=float)
                 if aquitard is not None else 0.0)
        z = z - thick                        # aquitard sits above aquifer k
        tops[:, k - 1] = z
        z = z - strat[f"aquifer_{k}"].to_numpy(dtype=float)
        bottoms[:, k - 1] = z
    return tops, bottoms


def _build_mesh(model, z_scale=1.0, layers=None):
    """Assemble the 3D layered mesh.

    Returns a dict with points ``(n_pts, 3)``, connectivity/offsets/
    types arrays, and the index frames needed to attach data.
    """
    nodes, elems, strat = _grid_frames(model)
    tops, bottoms = _layer_elevations(strat)
    n_layers_all = tops.shape[1]
    layer_ids = (list(range(1, n_layers_all + 1)) if layers is None
                 else sorted(set(int(k) for k in layers)))
    bad = [k for k in layer_ids if not 1 <= k <= n_layers_all]
    if bad:
        raise ValueError(f"layers {bad} out of range 1..{n_layers_all}")

    n = len(nodes)
    x = nodes["x"].to_numpy(dtype=float)
    y = nodes["y"].to_numpy(dtype=float)
    node_index = {int(i): j for j, i in enumerate(nodes["node_id"])}

    # points: per exported layer, a top sheet then a bottom sheet
    pts = []
    for k in layer_ids:
        pts.append(np.column_stack([x, y, tops[:, k - 1] * z_scale]))
        pts.append(np.column_stack([x, y, bottoms[:, k - 1] * z_scale]))
    points = np.vstack(pts)

    configs = elems[["node1", "node2", "node3", "node4"]].to_numpy(int)
    conn, offsets, types = [], [], []
    cell_layer, cell_elem = [], []
    off = 0
    for li, k in enumerate(layer_ids):
        top0 = li * 2 * n
        bot0 = top0 + n
        for e, cfg in enumerate(configs):
            nv = 3 if cfg[3] == 0 else 4
            idx = [node_index[c] for c in cfg[:nv]]
            # Two faces with edges joining i -> i+nv. IWFM elements are
            # counterclockwise viewed from above; VTK's wedge and
            # hexahedron define the first face with opposite senses, so
            # positive cell volumes need bottom-face-first for hexahedra
            # but top-face-first for wedges (verified via pyvista
            # compute_cell_sizes on both cell types).
            first0, second0 = (top0, bot0) if nv == 3 else (bot0, top0)
            conn.extend([first0 + i for i in idx])
            conn.extend([second0 + i for i in idx])
            off += 2 * nv
            offsets.append(off)
            types.append(_VTK_WEDGE if nv == 3 else _VTK_HEXAHEDRON)
            cell_layer.append(k)
            cell_elem.append(e)

    return {
        "nodes": nodes, "elems": elems,
        "tops": tops, "bottoms": bottoms,
        "layer_ids": layer_ids, "n_nodes": n,
        "points": points,
        "connectivity": np.asarray(conn, dtype=np.int64),
        "offsets": np.asarray(offsets, dtype=np.int64),
        "types": np.asarray(types, dtype=np.uint8),
        "cell_layer": np.asarray(cell_layer),
        "cell_elem": np.asarray(cell_elem),   # positional element index
    }


# ---------------------------------------------------------------------------
# Data array expansion
# ---------------------------------------------------------------------------


def _expand_point_array(mesh, values, name):
    """Per-node values -> one value per mesh point.

    Accepts shape ``(n_nodes,)`` (same on every layer) or
    ``(n_nodes, n_layers_exported)`` (per layer; that layer's top and
    bottom sheets share the value).
    """
    n = mesh["n_nodes"]
    arr = np.asarray(values, dtype=float)
    if arr.shape == (n,):
        return np.tile(arr, 2 * len(mesh["layer_ids"]))
    if arr.shape == (n, len(mesh["layer_ids"])):
        return np.concatenate([np.tile(arr[:, i], 2)
                               for i in range(arr.shape[1])])
    raise ValueError(
        f"point array {name!r} has shape {arr.shape}; expected ({n},) or "
        f"({n}, {len(mesh['layer_ids'])}) for layers {mesh['layer_ids']}")


def _expand_cell_array(mesh, values, name):
    """Per-element values -> one value per 3D cell."""
    n_el = len(mesh["elems"])
    arr = np.asarray(values, dtype=float)
    if arr.shape == (n_el,):
        return arr[mesh["cell_elem"]]
    if arr.shape == (n_el, len(mesh["layer_ids"])):
        li = {k: i for i, k in enumerate(mesh["layer_ids"])}
        col = np.asarray([li[k] for k in mesh["cell_layer"]])
        return arr[mesh["cell_elem"], col]
    raise ValueError(
        f"cell array {name!r} has shape {arr.shape}; expected ({n_el},) or "
        f"({n_el}, {len(mesh['layer_ids'])}) for layers {mesh['layer_ids']}")


def _default_arrays(mesh):
    """Built-in point and cell arrays every export carries."""
    layer_pos = {k: i for i, k in enumerate(mesh["layer_ids"])}
    tops = mesh["tops"][:, [k - 1 for k in mesh["layer_ids"]]]
    bottoms = mesh["bottoms"][:, [k - 1 for k in mesh["layer_ids"]]]

    point_data = {
        "node_id": np.tile(mesh["nodes"]["node_id"].to_numpy(float),
                           2 * len(mesh["layer_ids"])),
    }

    thick = tops - bottoms
    elems = mesh["elems"]
    cfg = elems[["node1", "node2", "node3", "node4"]].to_numpy(int)
    node_index = {int(i): j for j, i in
                  enumerate(mesh["nodes"]["node_id"])}
    elem_thick = np.empty((len(elems), len(mesh["layer_ids"])))
    for e, c in enumerate(cfg):
        nv = 3 if c[3] == 0 else 4
        idx = [node_index[i] for i in c[:nv]]
        elem_thick[e, :] = thick[idx, :].mean(axis=0)

    cell_data = {
        "element_id": mesh["elems"]["element_id"]
        .to_numpy(float)[mesh["cell_elem"]],
        "layer": mesh["cell_layer"].astype(float),
        "thickness": np.asarray(
            [elem_thick[e, layer_pos[k]] for e, k in
             zip(mesh["cell_elem"], mesh["cell_layer"])]),
    }
    if "subregion" in mesh["elems"].columns:
        cell_data["subregion"] = mesh["elems"]["subregion"] \
            .to_numpy(float)[mesh["cell_elem"]]
    return point_data, cell_data


# ---------------------------------------------------------------------------
# XML writing
# ---------------------------------------------------------------------------


def _fmt(arr, per_line=6):
    arr = np.asarray(arr)
    flat = arr.reshape(-1)
    if arr.dtype.kind in "ui":
        toks = [str(int(v)) for v in flat]
    else:
        toks = [f"{v:.10g}" for v in flat]
    lines = [" ".join(toks[i:i + per_line * 3])
             for i in range(0, len(toks), per_line * 3)]
    return "\n".join(lines)


def _data_array(name, arr, indent="        "):
    kind = np.asarray(arr).dtype.kind
    vtype = {"u": "UInt8", "i": "Int64", "f": "Float64"}[kind]
    ncomp = "" if np.asarray(arr).ndim == 1 else \
        f' NumberOfComponents="{np.asarray(arr).shape[1]}"'
    head = (f'{indent}<DataArray type="{vtype}" Name={quoteattr(str(name))}'
            f'{ncomp} format="ascii">')
    return f"{head}\n{_fmt(arr)}\n{indent}</DataArray>"


def _write_vtu(mesh, path, point_data, cell_data):
    n_pts = len(mesh["points"])
    n_cells = len(mesh["types"])
    parts = [
        '<?xml version="1.0"?>',
        '<VTKFile type="UnstructuredGrid" version="0.1" '
        'byte_order="LittleEndian">',
        "  <UnstructuredGrid>",
        f'    <Piece NumberOfPoints="{n_pts}" NumberOfCells="{n_cells}">',
        "      <Points>",
        _data_array("Points", mesh["points"]),
        "      </Points>",
        "      <Cells>",
        _data_array("connectivity", mesh["connectivity"]),
        _data_array("offsets", mesh["offsets"]),
        _data_array("types", mesh["types"]),
        "      </Cells>",
    ]
    if point_data:
        parts.append("      <PointData>")
        parts += [_data_array(k, v) for k, v in point_data.items()]
        parts.append("      </PointData>")
    if cell_data:
        parts.append("      <CellData>")
        parts += [_data_array(k, v) for k, v in cell_data.items()]
        parts.append("      </CellData>")
    parts += ["    </Piece>", "  </UnstructuredGrid>", "</VTKFile>"]
    Path(path).write_text("\n".join(parts), encoding="ascii")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_vtk(model, path, point_data=None, cell_data=None,
               z_scale=1.0, layers=None):
    """Write the model as a 3D layered mesh to a VTK ``.vtu`` file.

    Parameters
    ----------
    model : IOModelAdapter or IWFMModel
        Anything exposing ``nodes_df()`` / ``elements_df()`` /
        ``stratigraphy_df()``.
    path : str or Path
        Output file; ``.vtu`` is appended if missing.
    point_data : dict, optional
        ``{name: values}`` per-node arrays — shape ``(n_nodes,)``
        (constant over layers, e.g. ground-surface elevation) or
        ``(n_nodes, n_layers_exported)`` (per layer, e.g. heads).
        Values follow ``nodes_df()`` row order.
    cell_data : dict, optional
        ``{name: values}`` per-element arrays — shape ``(n_elements,)``
        or ``(n_elements, n_layers_exported)``, in ``elements_df()``
        row order.
    z_scale : float
        Vertical exaggeration multiplier applied to elevations
        (regional models want 20–100 to be legible in 3D).
    layers : sequence of int, optional
        Aquifer layers to export (1-based); default all.

    Returns
    -------
    dict with ``path``, ``n_points``, ``n_cells``, ``layers``.

    Built-in arrays: ``node_id`` (points); ``element_id``, ``layer``,
    ``thickness``, ``subregion`` (cells).
    """
    path = Path(path)
    if path.suffix.lower() != ".vtu":
        path = path.with_suffix(".vtu")
    path.parent.mkdir(parents=True, exist_ok=True)

    mesh = _build_mesh(model, z_scale=z_scale, layers=layers)
    pdata, cdata = _default_arrays(mesh)
    for name, values in (point_data or {}).items():
        pdata[name] = _expand_point_array(mesh, values, name)
    for name, values in (cell_data or {}).items():
        cdata[name] = _expand_cell_array(mesh, values, name)

    _write_vtu(mesh, path, pdata, cdata)
    logger.info("export_vtk: %d points, %d cells, layers %s -> %s",
                len(mesh["points"]), len(mesh["types"]),
                mesh["layer_ids"], path)
    return {"path": str(path), "n_points": len(mesh["points"]),
            "n_cells": len(mesh["types"]), "layers": mesh["layer_ids"]}


def export_vtk_timeseries(model, out_dir, name="heads", begin_date=None,
                          end_date=None, stride=1, z_scale=1.0,
                          layers=None):
    """Write simulated heads as a ParaView time series (``.pvd``).

    One ``.vtu`` per (strided) timestep with a ``head`` point array and
    a ``dtw`` (depth to water, ground surface − layer-1 head) array,
    plus ``<name>.pvd`` — open the ``.pvd`` in ParaView and press play.

    Parameters
    ----------
    model : IOModelAdapter or IWFMModel
        Must additionally expose ``heads_df(layer=...)``.
    out_dir : str or Path
        Directory for the ``.pvd`` and its ``.vtu`` frames.
    name : str
        Base name for the files (``<name>.pvd``, ``<name>_0000.vtu`` …).
    begin_date, end_date : str, optional
        IWFM-format window passed to ``heads_df``.
    stride : int
        Keep every *stride*-th timestep (daily output is usually far
        denser than an animation needs).
    z_scale, layers
        As in :func:`export_vtk`.

    Returns
    -------
    dict with ``pvd`` path, ``n_steps``, ``n_cells``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mesh = _build_mesh(model, z_scale=z_scale, layers=layers)
    pdata0, cdata = _default_arrays(mesh)

    kwargs = {}
    if begin_date is not None:
        kwargs["begin_date"] = begin_date
    if end_date is not None:
        kwargs["end_date"] = end_date
    heads = {k: pd.DataFrame(model.heads_df(layer=k, **kwargs))
             for k in mesh["layer_ids"]}
    times = heads[mesh["layer_ids"][0]].index[::stride]
    if len(times) == 0:
        raise ValueError("no timesteps in the requested window")

    gse = mesh["nodes"].merge(
        pd.DataFrame(model.stratigraphy_df()), on="node_id",
        how="left")["elevation"].to_numpy(float)

    datasets = []
    t0 = times[0]
    for i, t in enumerate(times):
        hmat = np.column_stack(
            [heads[k].loc[t].to_numpy(dtype=float)
             for k in mesh["layer_ids"]])
        pdata = dict(pdata0)
        pdata["head"] = _expand_point_array(mesh, hmat, "head")
        pdata["dtw"] = _expand_point_array(mesh, gse - hmat[:, 0], "dtw")
        frame = out_dir / f"{name}_{i:04d}.vtu"
        _write_vtu(mesh, frame, pdata, cdata)
        offset_days = (pd.Timestamp(t) - pd.Timestamp(t0)).days
        datasets.append(
            f'    <DataSet timestep="{offset_days}" part="0" '
            f'file="{frame.name}"/>')

    pvd = out_dir / f"{name}.pvd"
    pvd.write_text("\n".join([
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" '
        'byte_order="LittleEndian">',
        "  <Collection>",
        *datasets,
        "  </Collection>",
        "</VTKFile>",
    ]), encoding="ascii")
    logger.info("export_vtk_timeseries: %d frames (%d cells each) -> %s",
                len(datasets), len(mesh["types"]), pvd)
    return {"pvd": str(pvd), "n_steps": len(datasets),
            "n_cells": len(mesh["types"])}
