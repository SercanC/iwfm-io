"""
Multi-layer well observations: map real wells onto the IWFM mesh and
composite simulated heads across layers.

Observation wells rarely align with a single model layer. The
established approach (used in C2VSim-scale calibrations): find the
well's location on the mesh, intersect its perforated interval with the
layer stratigraphy, and weight each layer's simulated head by
transmissivity (``Kh × intersected thickness``). Wells with unknown
completions fall back to a chosen layer — ideally selected by comparing
per-layer simulated heads against the well's observed record.

Two-phase design:

- :func:`build_well_mapping` — the expensive step, run once at setup:
  spatial mapping (nearest node or inverse-distance over the *k*
  nearest) × vertical fractions → a :class:`WellMapping` whose
  ``weights`` table (``well_id, node, layer, weight``; weights sum to 1
  per well) is persistable via ``to_csv``/``from_csv``.
- :meth:`WellMapping.composite` — the fast path for the forward run:
  one sparse matrix multiply from simulated node × layer heads to
  per-well composite heads.

Completion rules per well (first match wins):

1. ``layer`` > 0 — all weight on that layer (explicit override).
2. valid ``perf_top``/``perf_bottom`` (depths below ground surface) —
   transmissivity-weighted fractions; wells whose interval misses every
   aquifer layer fall back (below model bottom → deepest layer,
   otherwise → layer 1, both logged).
3. neither — ``default_layer`` (use :func:`select_best_layers` to pick
   per-well layers from observed data, then rebuild).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["WellMapping", "build_well_mapping", "select_best_layers"]

logger = logging.getLogger(__name__)

_NODE_LAYER_RE = re.compile(r"^node_(\d+)_layer_(\d+)$")
_NODE_RE = re.compile(r"^node_(\d+)$")


# ----------------------------------------------------------------- helpers
def _layer_depths(strat) -> "tuple[pd.DataFrame, pd.DataFrame, int]":
    """Per-node aquifer top/bottom depths below ground surface.

    *strat* is the ``stratigraphy_df()`` layout: ``node_id, elevation``
    then alternating ``aquitard_L, aquifer_L`` thicknesses.
    """
    layers = sorted(int(m.group(1)) for c in strat.columns
                    if (m := re.match(r"^aquifer_(\d+)$", str(c))))
    if not layers:
        raise ValueError(
            "stratigraphy frame has no aquifer_<L> thickness columns")
    tops, bots = {}, {}
    depth = pd.Series(0.0, index=strat.index)
    for l in layers:
        depth = depth + strat.get(f"aquitard_{l}", 0.0)
        tops[l] = depth.copy()
        depth = depth + strat[f"aquifer_{l}"]
        bots[l] = depth.copy()
    top = pd.DataFrame(tops).set_index(strat["node_id"].values)
    bot = pd.DataFrame(bots).set_index(strat["node_id"].values)
    return top, bot, len(layers)


def _node_weights(nodes_xy, wells, spatial, k) -> "list":
    """[(well_row_pos, [(node_id, weight), ...]), ...]

    Pure-numpy k-nearest search, chunked over wells so the distance
    matrix stays small even for fine grids (no scipy dependency).
    """
    node_ids = nodes_xy["node_id"].values
    nx = nodes_xy["x"].values.astype(float)
    ny = nodes_xy["y"].values.astype(float)
    wx = wells["x"].values.astype(float)
    wy = wells["y"].values.astype(float)
    kk = 1 if spatial == "nearest" else min(k, len(node_ids))
    out = []
    chunk = max(1, int(2e7) // max(len(node_ids), 1))
    for start in range(0, len(wells), chunk):
        sl = slice(start, start + chunk)
        d2 = ((wx[sl, None] - nx[None, :]) ** 2
              + (wy[sl, None] - ny[None, :]) ** 2)
        if kk == 1:
            idx = d2.argmin(axis=1)[:, None]
        else:
            idx = np.argpartition(d2, kk - 1, axis=1)[:, :kk]
            order = np.take_along_axis(d2, idx, axis=1).argsort(axis=1)
            idx = np.take_along_axis(idx, order, axis=1)
        dist = np.sqrt(np.take_along_axis(d2, idx, axis=1))
        for i in range(idx.shape[0]):
            pos = start + i
            if kk == 1 or dist[i, 0] == 0:
                out.append((pos, [(node_ids[idx[i, 0]], 1.0)]))
            else:
                w = 1.0 / dist[i]
                w = w / w.sum()
                out.append((pos, list(zip(node_ids[idx[i]], w))))
    return out


def _vertical_fractions(node, top, bot, n_layers, kh_at, row,
                        default_layer) -> "tuple[np.ndarray, str]":
    layer = row.get("layer")
    if pd.notna(layer) and int(layer) > 0:
        frac = np.zeros(n_layers)
        frac[int(layer) - 1] = 1.0
        return frac, "layer"
    pt, pb = row.get("perf_top"), row.get("perf_bottom")
    if pd.notna(pt) and pd.notna(pb) and pb > pt:
        t = top.loc[node].values
        b = bot.loc[node].values
        intersect = np.clip(np.minimum(pb, b) - np.maximum(pt, t), 0, None)
        kh = kh_at(node)
        trans = kh * intersect
        if trans.sum() > 0:
            return trans / trans.sum(), "perforation"
        frac = np.zeros(n_layers)
        if pt > b[-1]:
            frac[-1] = 1.0
            logger.warning(
                "well %s: perforation below the model bottom at node %s; "
                "assigned deepest layer", row["well_id"], node)
            return frac, "below_model"
        frac[0] = 1.0
        logger.warning(
            "well %s: perforation intersects no aquifer layer at node %s "
            "(aquitard interval?); assigned layer 1", row["well_id"], node)
        return frac, "no_intersect"
    frac = np.zeros(n_layers)
    frac[int(default_layer) - 1] = 1.0
    return frac, "default"


# ------------------------------------------------------------------ result
@dataclass
class WellMapping:
    """Well-to-mesh mapping with per-(node, layer) composite weights.

    Attributes
    ----------
    wells : pandas.DataFrame
        One row per well: ``well_id, x, y, node`` (primary/nearest
        node), ``method`` (``layer / perforation / default /
        below_model / no_intersect``).
    weights : pandas.DataFrame
        Long-form ``well_id, node, layer, weight``; weights sum to 1
        per well.
    n_layers : int
    """

    wells: "pd.DataFrame"
    weights: "pd.DataFrame"
    n_layers: int

    def to_csv(self, path) -> None:
        """Persist as one denormalized CSV (the ``fracs.csv`` role)."""
        merged = self.weights.merge(
            self.wells[["well_id", "x", "y", "method"]], on="well_id")
        merged.insert(0, "n_layers", self.n_layers)
        from iwfm_io._writer import replace_file_text
        replace_file_text(Path(path), merged.to_csv(index=False))

    @classmethod
    def from_csv(cls, path) -> "WellMapping":
        df = pd.read_csv(path)
        weights = df[["well_id", "node", "layer", "weight"]].copy()
        primary = (weights.groupby(["well_id", "node"])["weight"].sum()
                   .reset_index()
                   .sort_values("weight", ascending=False)
                   .drop_duplicates("well_id"))
        wells = (df[["well_id", "x", "y", "method"]]
                 .drop_duplicates("well_id")
                 .merge(primary[["well_id", "node"]], on="well_id"))
        return cls(wells=wells.reset_index(drop=True), weights=weights,
                   n_layers=int(df["n_layers"].iloc[0]))

    # ------------------------------------------------------------ fast path
    def composite(self, heads) -> "pd.DataFrame":
        """Composite per-well heads from node × layer simulated heads.

        Parameters
        ----------
        heads : DataFrame, dict, or model
            Canonical: a DataFrame indexed by datetime whose columns are
            a ``(node, layer)`` MultiIndex. Also accepted: a dict
            ``{layer: DataFrame(time × node)}`` (columns ``node_<id>``
            or plain ints — what ``IOModelAdapter.heads_df(layer)``
            returns), or any object with a ``heads_df(layer=...)``
            method.

        Returns
        -------
        pandas.DataFrame
            time × well_id composite heads.
        """
        h = _canonical_heads(heads, self.n_layers)
        W = self.weights.pivot_table(index=["node", "layer"],
                                     columns="well_id", values="weight",
                                     aggfunc="sum", fill_value=0.0)
        missing = W.index.difference(h.columns)
        if len(missing):
            raise KeyError(
                f"heads are missing {len(missing)} (node, layer) "
                f"column(s) needed by the mapping, e.g. "
                f"{list(missing[:3])}")
        out = h[W.index].to_numpy() @ W.to_numpy()
        return pd.DataFrame(out, index=h.index, columns=W.columns)


def _canonical_heads(heads, n_layers) -> "pd.DataFrame":
    if hasattr(heads, "heads_df"):
        heads = {l: heads.heads_df(layer=l) for l in range(1, n_layers + 1)}
    if isinstance(heads, dict):
        pieces = {}
        for layer, df in heads.items():
            cols = []
            for c in df.columns:
                m = _NODE_RE.match(str(c))
                cols.append(int(m.group(1)) if m else int(c))
            piece = df.copy()
            piece.columns = pd.MultiIndex.from_arrays(
                [cols, [int(layer)] * len(cols)], names=["node", "layer"])
            pieces[layer] = piece
        return pd.concat(pieces.values(), axis=1)
    if isinstance(heads, pd.DataFrame):
        if isinstance(heads.columns, pd.MultiIndex):
            return heads
        parsed = [_NODE_LAYER_RE.match(str(c)) for c in heads.columns]
        if all(parsed):
            out = heads.copy()
            out.columns = pd.MultiIndex.from_tuples(
                [(int(m.group(1)), int(m.group(2))) for m in parsed],
                names=["node", "layer"])
            return out
    raise TypeError(
        "heads must be a (node, layer)-MultiIndex frame, a "
        "{layer: frame} dict, a node_<id>_layer_<L> frame, or a model "
        "with heads_df()")


# ------------------------------------------------------------------- build
def build_well_mapping(model, wells, kh=None, spatial: str = "nearest",
                       k: int = 4, default_layer: int = 1) -> WellMapping:
    """Build the well-to-mesh mapping (the expensive, run-once step).

    Parameters
    ----------
    model : object
        Anything with ``nodes_df()`` and ``stratigraphy_df()``
        (``IOModelAdapter`` or the DLL model).
    wells : pandas.DataFrame
        One row per well: ``well_id, x, y`` plus optional ``layer``
        (>0 pins the well to that layer), ``perf_top, perf_bottom``
        (depths below ground surface).
    kh : pandas.DataFrame, optional
        Horizontal conductivity per ``node_id, layer, kh`` (e.g.
        ``read_gw_main(...).aquifer_params[["node_id", "layer", "kh"]]``).
        Without it, fractions are thickness-weighted (Kh ≡ 1) — noted
        in the log.
    spatial : {"nearest", "idw"}
        Single nearest node, or inverse-distance weights over the *k*
        nearest nodes.
    k : int, default 4
        Neighbor count for ``idw``.
    default_layer : int, default 1
        Layer for wells with neither ``layer`` nor a valid perforated
        interval (see :func:`select_best_layers`).

    Returns
    -------
    WellMapping
    """
    if spatial not in ("nearest", "idw"):
        raise ValueError(f"spatial must be 'nearest' or 'idw', got {spatial!r}")
    wells = wells.copy().reset_index(drop=True)
    if not {"well_id", "x", "y"} <= set(wells.columns):
        raise ValueError("wells needs columns well_id, x, y")

    nodes = model.nodes_df()[["node_id", "x", "y"]]
    top, bot, n_layers = _layer_depths(model.stratigraphy_df())

    if kh is None:
        logger.info("no kh provided — using thickness-only weighting")
        kh_lookup = None
    else:
        kh_lookup = (kh.pivot_table(index="node_id", columns="layer",
                                    values="kh", aggfunc="mean")
                     .reindex(columns=range(1, n_layers + 1)))

    def kh_at(node):
        if kh_lookup is None or node not in kh_lookup.index:
            return np.ones(n_layers)
        return np.nan_to_num(kh_lookup.loc[node].values, nan=1.0)

    spatial_w = _node_weights(nodes, wells, spatial, k)
    weight_rows, meta = [], []
    for pos, node_list in spatial_w:
        row = wells.iloc[pos]
        primary_node = node_list[0][0]
        method = None
        for node, w_node in node_list:
            frac, method_n = _vertical_fractions(
                node, top, bot, n_layers, kh_at, row, default_layer)
            method = method or method_n
            for l in range(n_layers):
                if frac[l] > 0:
                    weight_rows.append(
                        (row["well_id"], node, l + 1, w_node * frac[l]))
        meta.append((row["well_id"], row["x"], row["y"], primary_node,
                     method))
    weights = pd.DataFrame(
        weight_rows, columns=["well_id", "node", "layer", "weight"])
    wells_out = pd.DataFrame(
        meta, columns=["well_id", "x", "y", "node", "method"])
    return WellMapping(wells=wells_out, weights=weights, n_layers=n_layers)


def select_best_layers(mapping: WellMapping, heads, obs, min_n: int = 6,
                       default_layer: int = 1) -> "pd.Series":
    """Pick each well's best single layer by RMSE against observations.

    For wells without completion data: compute the simulated head series
    in *each* layer (at the well's mapped node(s)) and choose the layer
    whose series best matches the observed record. Feed the result back
    as the wells frame's ``layer`` column and rebuild the mapping.

    Parameters
    ----------
    mapping : WellMapping
        Provides each well's spatial node weights.
    heads : any form :meth:`WellMapping.composite` accepts.
    obs : pandas.DataFrame
        Long-form ``site, datetime, value`` observed heads, sites named
        by ``well_id``. Timestamps must align with the simulated index
        (resample both to month-end first for monthly comparisons).
    min_n : int, default 6
        Wells with fewer aligned observations get *default_layer*.
    default_layer : int, default 1

    Returns
    -------
    pandas.Series
        ``well_id → layer`` (int).
    """
    h = _canonical_heads(heads, mapping.n_layers)
    node_w = (mapping.weights.groupby(["well_id", "node"])["weight"]
              .sum().reset_index())
    obs = obs.copy()
    obs["datetime"] = pd.to_datetime(obs["datetime"])
    out = {}
    for well, grp in obs.groupby(obs["site"].astype(str)):
        wn = node_w[node_w["well_id"].astype(str) == well]
        if wn.empty:
            continue
        o = grp.set_index("datetime")["value"].groupby(level=0).mean()
        best, best_rmse = default_layer, np.inf
        n_aligned = 0
        for layer in range(1, mapping.n_layers + 1):
            cols = [(n, layer) for n in wn["node"] if (n, layer) in h.columns]
            if not cols:
                continue
            sim = (h[cols].to_numpy()
                   @ (wn.set_index("node").loc[[c[0] for c in cols],
                                               "weight"].to_numpy()))
            sim = pd.Series(sim, index=h.index)
            joined = pd.concat([o, sim], axis=1, join="inner").dropna()
            n_aligned = max(n_aligned, len(joined))
            if len(joined) < min_n:
                continue
            rmse = float(np.sqrt(((joined.iloc[:, 0]
                                   - joined.iloc[:, 1]) ** 2).mean()))
            if rmse < best_rmse:
                best, best_rmse = layer, rmse
        if n_aligned < min_n:
            logger.warning(
                "well %s: only %d aligned observation(s) (< %d); "
                "assigned default layer %d", well, n_aligned, min_n,
                default_layer)
        out[well] = int(best)
    return pd.Series(out, name="layer")
