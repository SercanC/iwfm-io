"""
Wells: metadata, hydrograph linking, mesh mapping, and multi-layer
compositing of simulated heads.

Core model-evaluation functionality (moved from ``iwfm_io.pest``, which
re-exports it): map real wells onto the IWFM mesh and composite
simulated heads across layers.

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

__all__ = ["WellMapping", "build_well_mapping", "select_best_layers",
           "GWL_METADATA_KNOWN", "validate_gwl_metadata", "HydrographLink",
           "link_hydrographs", "assign_sequences",
           "composite_well_hydrographs", "enrich_gwl_metadata",
           "gwl_metadata_from_legacy"]

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


# ═══════════════════════════════════════════════════════════════════════
# GWL metadata: the DataFrame-first replacement for hand-maintained
# well-configuration files
# ═══════════════════════════════════════════════════════════════════════
#
# The ``gwl_metadata`` frame is a documented schema, not a file format:
# one row per groundwater-level observation well, primary facts only.
#
#   well_id          stable user identity (required, unique)
#   group, seq       user spatial identifier + within-group order
#   site_code        e.g. state well number (the usual hydrograph link)
#   hydrograph_name  explicit link override when it differs from site_code
#   perf_top, perf_bottom   perforation depths below ground surface
#   layer            explicit single-layer override
#
# Extra columns pass through untouched. Persist with plain pandas
# (``df.to_csv``) if a file is wanted — no function here reads or
# writes one.

GWL_METADATA_REQUIRED = ("well_id",)
GWL_METADATA_KNOWN = ("well_id", "group", "seq", "site_code",
                      "hydrograph_name", "perf_top", "perf_bottom",
                      "layer", "x", "y")


def validate_gwl_metadata(df) -> "list":
    """Check a gwl_metadata frame; returns problem strings (empty = OK)."""
    problems = []
    for col in GWL_METADATA_REQUIRED:
        if col not in df.columns:
            problems.append(f"missing required column {col!r}")
    if "well_id" in df.columns:
        ids = df["well_id"]
        if ids.isna().any():
            problems.append(f"{int(ids.isna().sum())} null well_id value(s)")
        dup = ids[ids.notna() & ids.astype(str).duplicated()]
        if len(dup):
            problems.append(
                f"duplicate well_id(s): {sorted(set(dup.astype(str)))[:5]}")
    if "seq" in df.columns:
        has_seq = df["seq"].notna()
        if "group" not in df.columns and has_seq.any():
            problems.append("seq present but no group column")
        elif has_seq.any():
            grouped = df.loc[has_seq]
            dup = grouped.duplicated(subset=["group", "seq"])
            if dup.any():
                problems.append(
                    f"{int(dup.sum())} duplicate (group, seq) pair(s)")
    if {"perf_top", "perf_bottom"} <= set(df.columns):
        both = df["perf_top"].notna() & df["perf_bottom"].notna()
        bad = both & (df["perf_top"] >= df["perf_bottom"])
        if bad.any():
            problems.append(
                f"{int(bad.sum())} row(s) with perf_top >= perf_bottom")
    if "layer" in df.columns:
        lay = pd.to_numeric(df["layer"], errors="coerce")
        bad = df["layer"].notna() & (lay.isna() | (lay < 1))
        if bad.any():
            problems.append(
                f"{int(bad.sum())} row(s) with non-positive/non-numeric "
                f"layer (use NaN, not legacy 0/-1 codes)")
    return problems


@dataclass
class HydrographLink:
    """Result of :func:`link_hydrographs`.

    Attributes
    ----------
    links : pandas.DataFrame
        One row per matched (well, layer): ``well_id, hyd_id, layer,
        x, y, stem``.
    unmatched_wells : list
        ``well_id`` values with no hydrograph stem.
    orphan_stems : list
        Hydrograph stems with no metadata row.
    layer_mismatches : pandas.DataFrame
        Rows whose parsed ``%layer`` suffix disagrees with the
        hydrograph section's own LAYER field (the LAYER field is
        trusted; the name is reported).
    """

    links: "pd.DataFrame"
    unmatched_wells: "list"
    orphan_stems: "list"
    layer_mismatches: "pd.DataFrame"

    def summary(self) -> dict:
        return {
            "n_wells_linked": int(self.links["well_id"].nunique()),
            "n_hydrographs_linked": int(len(self.links)),
            "n_unmatched_wells": len(self.unmatched_wells),
            "n_orphan_stems": len(self.orphan_stems),
            "n_layer_mismatches": int(len(self.layer_mismatches)),
        }


def _hydrograph_frame(gw_main) -> "pd.DataFrame":
    if isinstance(gw_main, pd.DataFrame):
        return gw_main
    if hasattr(gw_main, "hydrographs"):
        return gw_main.hydrographs
    from iwfm_io.readers.groundwater import read_gw_main
    return read_gw_main(gw_main).hydrographs


def link_hydrographs(gwl_metadata, gw_main, on: str = "site_code",
                     name_sep: str = "%") -> HydrographLink:
    """Link metadata wells to the GW main's hydrograph entries by name.

    The hydrograph section conventionally names entries
    ``{well_identifier}{name_sep}{layer}`` (one entry per layer at the
    well's location). This parses the stems, groups per-layer rows into
    wells, and joins the stems against ``gwl_metadata[on]``.

    Parameters
    ----------
    gwl_metadata : pandas.DataFrame
    gw_main : GWMain, path, or hydrographs DataFrame
    on : str, default "site_code"
        Metadata column matched against the parsed stems
        (case-insensitive, whitespace-stripped). Duplicate non-null
        values in this column are an error (ambiguous join).
    name_sep : str, default "%"
        Separator between well identifier and layer suffix. Names
        without it are treated as single-layer entries whose whole
        name is the stem.

    Returns
    -------
    HydrographLink
    """
    problems = validate_gwl_metadata(gwl_metadata)
    if problems:
        raise ValueError("invalid gwl_metadata: " + "; ".join(problems))
    if on not in gwl_metadata.columns:
        raise ValueError(f"gwl_metadata has no column {on!r}")
    hyd = _hydrograph_frame(gw_main).copy()
    for col in ("id", "layer", "name"):
        if col not in hyd.columns:
            raise ValueError(f"hydrograph frame has no column {col!r}")

    names = hyd["name"].astype(str).str.strip()
    has_sep = names.str.contains(re.escape(name_sep), regex=True)
    stem = names.where(~has_sep,
                       names.str.rsplit(name_sep, n=1).str[0]).str.strip()
    suffix = names.str.rsplit(name_sep, n=1).str[1].where(has_sep)

    declared = pd.to_numeric(hyd["layer"], errors="coerce")
    parsed = pd.to_numeric(suffix, errors="coerce")
    mism = has_sep & parsed.notna() & declared.notna() & (parsed != declared)
    layer_mismatches = pd.DataFrame({
        "hyd_id": hyd.loc[mism, "id"].values,
        "name": names[mism].values,
        "parsed_layer": parsed[mism].values,
        "declared_layer": declared[mism].values,
    })
    if len(layer_mismatches):
        logger.warning(
            "%d hydrograph name(s) disagree with their LAYER field -- "
            "LAYER field trusted", len(layer_mismatches))

    key = gwl_metadata[on].astype(str).str.strip()
    nonnull = key[gwl_metadata[on].notna()]
    dup = nonnull[nonnull.str.casefold().duplicated()]
    if len(dup):
        raise ValueError(
            f"gwl_metadata[{on!r}] has duplicate value(s): "
            f"{sorted(set(dup))[:5]} -- ambiguous join")
    lookup = {k.casefold(): w for k, w in
              zip(nonnull, gwl_metadata.loc[nonnull.index, "well_id"])}

    matched_well = stem.str.casefold().map(lookup)
    ok = matched_well.notna()
    hyd_ids = pd.to_numeric(hyd["id"], errors="coerce")
    if hyd_ids.notna().all():
        hyd_ids = hyd_ids.astype(int)
    else:  # non-numeric ids — keep as given
        hyd_ids = hyd["id"]
    links = pd.DataFrame({
        "well_id": matched_well[ok].values,
        "hyd_id": hyd_ids[ok].values,
        "layer": declared[ok].astype("Int64").values,
        "x": (pd.to_numeric(hyd.loc[ok, "x"], errors="coerce").values
              if "x" in hyd.columns else np.nan),
        "y": (pd.to_numeric(hyd.loc[ok, "y"], errors="coerce").values
              if "y" in hyd.columns else np.nan),
        "stem": stem[ok].values,
    }).sort_values(["well_id", "layer"]).reset_index(drop=True)

    linked_ids = set(links["well_id"])
    unmatched_wells = [w for w in gwl_metadata["well_id"]
                       if w not in linked_ids]
    orphan_stems = sorted(set(stem[~ok]))
    link = HydrographLink(links=links, unmatched_wells=unmatched_wells,
                          orphan_stems=orphan_stems,
                          layer_mismatches=layer_mismatches)
    logger.info("link_hydrographs: %s", link.summary())
    return link


def assign_sequences(gwl_metadata, link: Optional[HydrographLink] = None,
                     order: str = "north_to_south") -> "pd.DataFrame":
    """Fill missing within-group sequence numbers (pure function).

    Existing ``seq`` values are never changed and new ones start after
    each group's current maximum, so adding wells later cannot renumber
    earlier ones — **provided the caller persists the returned frame
    and passes it back next time** (the ledger lives in the frame, not
    in any file this function manages).

    Parameters
    ----------
    gwl_metadata : pandas.DataFrame
        Needs ``group``; ``seq`` is created if absent.
    link : HydrographLink, optional
        Supplies well coordinates (model x/y) when the metadata has no
        ``x``/``y`` columns.
    order : str
        ``north_to_south`` (default), ``south_to_north``,
        ``west_to_east``, or ``east_to_west`` — the spatial ordering of
        newly assigned numbers within each group.

    Returns
    -------
    pandas.DataFrame
        Copy with ``seq`` filled (nullable integer).
    """
    orders = {"north_to_south": ("y", False), "south_to_north": ("y", True),
              "west_to_east": ("x", True), "east_to_west": ("x", False)}
    if order not in orders:
        raise ValueError(f"order must be one of {sorted(orders)}")
    if "group" not in gwl_metadata.columns:
        raise ValueError("gwl_metadata needs a 'group' column")
    out = gwl_metadata.copy()
    if "seq" not in out.columns:
        out["seq"] = pd.array([pd.NA] * len(out), dtype="Int64")
    out["seq"] = out["seq"].astype("Int64")

    coord_col, ascending = orders[order]
    if coord_col in out.columns \
            and pd.to_numeric(out[coord_col], errors="coerce").notna().any():
        coords = pd.to_numeric(out[coord_col], errors="coerce")
    elif link is not None:
        per_well = link.links.groupby("well_id")[coord_col].first()
        coords = out["well_id"].map(per_well)
    else:
        raise ValueError(
            f"no {coord_col!r} available: add x/y columns or pass link=")

    n_assigned = 0
    for group, idx in out.groupby("group").groups.items():
        rows = out.loc[idx]
        todo = rows.index[rows["seq"].isna()]
        if not len(todo):
            continue
        start = int(rows["seq"].max()) + 1 if rows["seq"].notna().any() else 1
        c = coords.loc[todo]
        no_coord = c.isna()
        if no_coord.any():
            logger.warning(
                "group %s: %d well(s) without coordinates appended in "
                "well_id order", group, int(no_coord.sum()))
        ordered = list(c[~no_coord].sort_values(ascending=ascending).index)
        ordered += list(out.loc[todo][no_coord.values]
                        .sort_values("well_id").index)
        for k, i in enumerate(ordered):
            out.at[i, "seq"] = start + k
        n_assigned += len(ordered)
    logger.info("assign_sequences: %d new sequence number(s)", n_assigned)
    return out


def composite_well_hydrographs(link: HydrographLink, hyd_output,
                               fractions) -> "pd.DataFrame":
    """Composite per-layer hydrograph series into per-well series.

    Uses IWFM's own finite-element-interpolated hydrograph output for
    the spatial part and transmissivity layer fractions for the
    vertical part.

    Parameters
    ----------
    link : HydrographLink
    hyd_output : pandas.DataFrame
        Time-indexed hydrograph output; columns may be hydrograph ids
        (ints) or the readers' positional ``col_N`` labels (``col_N``
        is taken as hydrograph id ``N``, the file order).
    fractions : WellMapping or DataFrame
        Layer fractions: a :class:`WellMapping` (node dimension is
        summed out) or a frame with ``well_id, layer`` and a
        ``fraction``/``weight`` column.

    Returns
    -------
    pandas.DataFrame
        time × well_id composite heads. A well whose nonzero-fraction
        layer has no linked hydrograph raises (silent gaps would bias
        the composite).
    """
    h = hyd_output.copy()
    for time_col in ("datetime", "date", "time"):
        if time_col in h.columns:
            try:
                when = pd.to_datetime(h[time_col])
            except (ValueError, TypeError):
                # raw IWFM stamps ("09/30/2000_24:00")
                from iwfm_io._tokens import parse_iwfm_date
                when = pd.to_datetime(
                    [parse_iwfm_date(str(v)) for v in h[time_col]])
            h = h.set_index(when).drop(columns=time_col)
            h.index.name = "datetime"
            break
    cols = []
    for c in h.columns:
        m = re.match(r"^col_(\d+)$", str(c))
        cols.append(int(m.group(1)) if m else int(c))
    h.columns = cols

    if isinstance(fractions, WellMapping):
        frac = (fractions.weights.groupby(["well_id", "layer"])["weight"]
                .sum().reset_index().rename(columns={"weight": "fraction"}))
    else:
        frac = fractions.rename(columns={"weight": "fraction"})[
            ["well_id", "layer", "fraction"]].copy()
    frac = frac[frac["fraction"] > 0]

    idx = link.links.set_index(["well_id", "layer"])["hyd_id"]
    dup = idx.index[idx.index.duplicated()]
    if len(dup):
        raise ValueError(
            f"link has multiple hydrographs for {len(set(dup))} "
            f"(well, layer) pair(s), e.g. {list(dup[:3])}")
    merged = frac.merge(idx.rename("hyd_id").reset_index(),
                        on=["well_id", "layer"], how="left")
    missing = merged[merged["hyd_id"].isna()]
    if len(missing):
        raise KeyError(
            f"{len(missing)} (well, layer) fraction(s) have no linked "
            f"hydrograph, e.g. "
            f"{missing[['well_id', 'layer']].head(3).to_dict('records')}")
    absent = set(merged["hyd_id"].astype(int)) - set(h.columns)
    if absent:
        raise KeyError(
            f"hydrograph output is missing {len(absent)} column(s), "
            f"e.g. {sorted(absent)[:3]}")

    W = merged.assign(hyd_id=merged["hyd_id"].astype(int)).pivot_table(
        index="hyd_id", columns="well_id", values="fraction",
        aggfunc="sum", fill_value=0.0)
    out = pd.DataFrame(h[list(W.index)].to_numpy() @ W.to_numpy(),
                       index=h.index, columns=W.columns)
    return out


def enrich_gwl_metadata(model, gwl_metadata,
                        link: Optional[HydrographLink] = None,
                        obs=None) -> "pd.DataFrame":
    """Add derived columns to a gwl_metadata frame (never required).

    Adds, where inputs allow: ``subregion`` (subregion of an element
    touching the nearest node), ``gse`` (ground surface at the nearest
    node), and — when *obs* (long-form ``site, datetime, value`` keyed
    by ``well_id``) is given — ``n_obs, first_date, last_date``.

    Coordinates come from metadata ``x``/``y`` or from *link*.
    """
    out = gwl_metadata.copy()
    if {"x", "y"} <= set(out.columns) \
            and pd.to_numeric(out["x"], errors="coerce").notna().any():
        wx = pd.to_numeric(out["x"], errors="coerce")
        wy = pd.to_numeric(out["y"], errors="coerce")
    elif link is not None:
        per_well = link.links.groupby("well_id")[["x", "y"]].first()
        wx = out["well_id"].map(per_well["x"])
        wy = out["well_id"].map(per_well["y"])
    else:
        wx = wy = None
        logger.warning("no coordinates: subregion/gse not derived")

    if wx is not None:
        nodes = model.nodes_df()
        nx = nodes["x"].values.astype(float)
        ny = nodes["y"].values.astype(float)
        ok = wx.notna() & wy.notna()
        nearest = pd.Series(pd.NA, index=out.index, dtype="Int64")
        if ok.any():
            d2 = ((wx[ok].values[:, None] - nx[None, :]) ** 2
                  + (wy[ok].values[:, None] - ny[None, :]) ** 2)
            nearest.loc[ok] = nodes["node_id"].values[d2.argmin(axis=1)]
        strat = model.stratigraphy_df().set_index("node_id")["elevation"]
        out["gse"] = nearest.map(strat)
        elems = model.elements_df()
        node_cols = [c for c in elems.columns if re.match(r"^node\d+$", c)]
        node_sub = {}
        for _, e in elems.iterrows():
            for c in node_cols:
                n = e[c]
                if pd.notna(n) and n != 0:
                    node_sub.setdefault(int(n), e["subregion"])
        out["subregion"] = nearest.map(node_sub)

    if obs is not None:
        stats = (obs.assign(_t=pd.to_datetime(obs["datetime"]))
                 .groupby(obs["site"].astype(str))
                 .agg(n_obs=("value", "count"), first_date=("_t", "min"),
                      last_date=("_t", "max")))
        key = out["well_id"].astype(str)
        out["n_obs"] = key.map(stats["n_obs"]).fillna(0).astype(int)
        out["first_date"] = key.map(stats["first_date"])
        out["last_date"] = key.map(stats["last_date"])
    return out


def gwl_metadata_from_legacy(df) -> "pd.DataFrame":
    """Convert a legacy well-keys frame to the gwl_metadata schema.

    Maps the historical column layout (SITE, HYDID, GRP, perft/perfb,
    X/Y, and the ``layer`` code convention where ``-1`` meant
    "use perforations" and ``0`` meant "unknown") onto the schema this
    module documents. The caller reads the legacy CSV with pandas and
    persists the result however they like.
    """
    cols = {str(c).casefold(): c for c in df.columns}

    def take(name):
        return df[cols[name]] if name in cols else None

    hydid = take("hydid")
    if hydid is None:
        raise ValueError("legacy frame has no HYDID column")
    out = pd.DataFrame({"well_id": hydid.values})
    for src, dst in [("site", "site_code"), ("grp", "group"),
                     ("x", "x"), ("y", "y"), ("gse", "gse"),
                     ("sr", "subregion")]:
        v = take(src)
        if v is not None:
            out[dst] = v.values
    if "site_code" in out.columns:
        out["hydrograph_name"] = out["site_code"]
    perft, perfb = take("perft"), take("perfb")
    layer = (pd.to_numeric(take("layer"), errors="coerce")
             if take("layer") is not None
             else pd.Series(np.nan, index=df.index))
    if perft is not None and perfb is not None:
        pt = pd.to_numeric(perft, errors="coerce")
        pb = pd.to_numeric(perfb, errors="coerce")
        use_perf = (layer.values == -1) & (pb.values > pt.values)
        out["perf_top"] = np.where(use_perf, pt.values, np.nan)
        out["perf_bottom"] = np.where(use_perf, pb.values, np.nan)
    out["layer"] = pd.array(
        np.where(layer.values > 0, layer.values, np.nan), dtype="float"
    )
    out["layer"] = out["layer"].astype("Int64")
    return out.reset_index(drop=True)
