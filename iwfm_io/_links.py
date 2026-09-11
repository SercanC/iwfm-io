"""Cross-file relationship registry and resolution engine (INTERNAL).

IWFM input files reference each other constantly: pointer columns hold
1-based column numbers into a time-series file referenced by role
(``et_columns`` -> the ET file, ``icolwl`` -> TSPumping, ...), ID
columns reference rows of the grid tables, and ``(TYPDST, DST)`` pairs
select a destination whose meaning depends on a per-file code table.

This module is the single source of truth for those relationships:

- ``COMPONENTS`` — how each component/sub-file is reached from the
  model root (parent component + ``file_paths`` key + reader).
- ``TS_TARGETS`` — every time-series file role a pointer can reference
  (component, path key, reader, where its conversion factor lives).
- ``TS_LINKS`` — every pointer-column -> time-series-column reference.
- ``ID_LINKS`` — every entity-ID reference (element / node / stream
  node / subregion / lake).
- ``DEST_LINKS`` — every polymorphic ``(type, dest)`` reference with
  its code table.

The engine functions (``load_component``, ``load_timeseries``,
``series``, ``column_usage``, ``validate_references``) take an
``IOModelAdapter`` and are surfaced as methods on it.  Everything here
is internal API — names and shapes may change between releases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------------
# Registry data structures
# ------------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    """How to reach a parsed component from the model root."""

    parent: str | None      # parent component name (None = model root)
    path_key: str | None    # key into the parent's file_paths
    reader: str             # function name in iwfm_io


@dataclass(frozen=True)
class TsTarget:
    """A time-series file role that pointer columns can reference."""

    component: str          # component whose file_paths holds the path
    path_key: str           # key in that component's file_paths
    reader: str             # function name in iwfm_io
    factor: str | None      # "spec" (obj.spec.factor), "obj"
                            # (obj.factor, may be None), or None
    kind: str = "series"    # "series" | "flags" | "dest_pairs"


@dataclass(frozen=True)
class TsLink:
    """A pointer-column reference into a time-series file."""

    source: str                       # component name
    table: str                        # attribute on the parsed object
    pointers: tuple[str, ...] | str   # column names, or "*" = all
                                      # non-key/non-text columns
    keys: tuple[str, ...]             # identifying columns
    target: str                       # role in TS_TARGETS
    scale: str | None = None          # sibling column multiplying the
                                      # referenced series (e.g. fracwl)
    note: str = ""


@dataclass(frozen=True)
class IdLink:
    """An entity-ID reference into a grid/entity table."""

    source: str
    table: str
    column: str
    entity: str            # "element"|"node"|"stream_node"|"subregion"|"lake"
    zero_ok: bool = True   # 0 = none / all-elements sentinel


@dataclass(frozen=True)
class DestLink:
    """A polymorphic (type, dest) reference with a per-file code table."""

    source: str
    table: str
    type_col: str
    dest_col: str
    codes: dict = field(hash=False, default_factory=dict)
    # codes: {type code: entity name or None (no dest id) or
    #         "group:<component>" (element group of that file)}


# ------------------------------------------------------------------
# Component graph
# ------------------------------------------------------------------

COMPONENTS: dict[str, Component] = {
    "gw_main":      Component(None, "gw_main", "read_gw_main"),
    "stream_main":  Component(None, "stream_main", "read_stream_main"),
    "lake_main":    Component(None, "lake_main", "read_lake_main"),
    "rootzone":     Component(None, "rootzone_main", "read_rootzone_main"),
    "swshed":       Component(None, "swshed", "read_swshed"),
    "unsatzone":    Component(None, "unsatzone", "read_unsatzone"),
    "bc_main":      Component("gw_main", "bc_main", "read_bc_main"),
    "pump_main":    Component("gw_main", "pump_main", "read_pump_main"),
    "tile_drain":   Component("gw_main", "tile_drain", "read_tile_drain"),
    "subsidence":   Component("gw_main", "subsidence", "read_subsidence"),
    "spec_head":    Component("bc_main", "sp_head", "read_spec_head_bc"),
    "spec_flow":    Component("bc_main", "sp_flow", "read_spec_flow_bc"),
    "ghbc":         Component("bc_main", "ghbc", "read_general_head_bc"),
    "con_ghbc":     Component("bc_main", "con_ghbc",
                              "read_constrained_head_bc"),
    "well_spec":    Component("pump_main", "well", "read_well_spec"),
    "elem_pump":    Component("pump_main", "elem_pump", "read_elem_pump"),
    "diver_specs":  Component("stream_main", "diver_specs",
                              "read_diver_specs"),
    "bypass_specs": Component("stream_main", "bypass_specs",
                              "read_bypass_specs"),
    "nonponded_ag": Component("rootzone", "nonponded_ag",
                              "read_nonponded_ag_main"),
    "ponded_ag":    Component("rootzone", "ponded_ag",
                              "read_ponded_ag_main"),
    "urban":        Component("rootzone", "urban", "read_urban_main"),
    "native_veg":   Component("rootzone", "native_veg",
                              "read_native_veg_main"),
}

#: Adapter attributes that may already hold a parsed component
PRELOADED = {
    "gw_main": "_gw_main",
    "stream_main": "_stream_main",
    "well_spec": "_well_spec",
    "diver_specs": "_diver_specs",
    "bypass_specs": "_bypass_specs",
    "tile_drain": "_tile_drain_file",
}


# ------------------------------------------------------------------
# Time-series targets
# ------------------------------------------------------------------

TS_TARGETS: dict[str, TsTarget] = {
    "precip":            TsTarget("__sim__", "precip", "read_precip", "spec"),
    "et":                TsTarget("__sim__", "et", "read_et", "spec"),
    "irigfrac":          TsTarget("__sim__", "irigfrac",
                                  "read_irigfrac", None),
    "supply_adjust":     TsTarget("__sim__", "supply_adjust",
                                  "read_supply_adjust", None),
    "return_flow":       TsTarget("rootzone", "return_flow",
                                  "read_timeseries_file", "obj"),
    "reuse_frac":        TsTarget("rootzone", "reuse_frac",
                                  "read_timeseries_file", "obj"),
    "irig_period":       TsTarget("rootzone", "irig_period",
                                  "read_irr_period", None, "flags"),
    "ag_water_demand":   TsTarget("rootzone", "ag_water_demand",
                                  "read_timeseries_file", "obj"),
    "moisture_src":      TsTarget("rootzone", "moisture_src",
                                  "read_timeseries_file", "obj"),
    "surface_flow_dest": TsTarget("rootzone", "surface_flow_dest",
                                  "read_surface_flow_dest", None,
                                  "dest_pairs"),
    "root_depth_fracs":  TsTarget("nonponded_ag", "root_depth_fracs",
                                  "read_timeseries_file", "obj"),
    "min_soil_moisture": TsTarget("nonponded_ag", "min_soil_moisture",
                                  "read_timeseries_file", "obj"),
    "target_soil_moisture": TsTarget("nonponded_ag",
                                     "target_soil_moisture",
                                     "read_timeseries_file", "obj"),
    "min_perc":          TsTarget("nonponded_ag", "min_perc",
                                  "read_timeseries_file", "obj"),
    "ponding_depth":     TsTarget("ponded_ag", "ponding_depth",
                                  "read_timeseries_file", "obj"),
    "rice_refuge_ops":   TsTarget("ponded_ag", "rice_refuge_ops",
                                  "read_timeseries_file", "obj"),
    "population":        TsTarget("urban", "population",
                                  "read_timeseries_file", "obj"),
    "per_capita_use":    TsTarget("urban", "per_capita_use",
                                  "read_timeseries_file", "obj"),
    "water_use_specs":   TsTarget("urban", "water_use_specs",
                                  "read_timeseries_file", "obj"),
    "ts_pumping":        TsTarget("pump_main", "ts_pump",
                                  "read_ts_pumping", "spec"),
    "boundary_ts":       TsTarget("bc_main", "ts_bc",
                                  "read_boundary_ts", "spec"),
    "diversions":        TsTarget("stream_main", "diversions",
                                  "read_diversions", "spec"),
    "stream_inflow":     TsTarget("stream_main", "inflow",
                                  "read_stream_inflow", "spec"),
    "max_lake_elev":     TsTarget("lake_main", "__max_elev_file__",
                                  "read_max_lake_elev", "spec"),
}


# ------------------------------------------------------------------
# Pointer-column links
# ------------------------------------------------------------------

_E = ("element_id",)

TS_LINKS: tuple[TsLink, ...] = (
    # non-ponded crops
    TsLink("nonponded_ag", "et_columns", "*", _E, "et"),
    TsLink("nonponded_ag", "supply_req_columns", "*", _E,
           "ag_water_demand", note="0 = computed internally"),
    TsLink("nonponded_ag", "irig_period_columns", "*", _E, "irig_period"),
    TsLink("nonponded_ag", "min_moisture_columns", "*", _E,
           "min_soil_moisture"),
    TsLink("nonponded_ag", "target_moisture_columns", "*", _E,
           "target_soil_moisture"),
    TsLink("nonponded_ag", "return_flow_columns", "*", _E, "return_flow"),
    TsLink("nonponded_ag", "reuse_columns", "*", _E, "reuse_frac"),
    TsLink("nonponded_ag", "min_perc_columns", "*", _E, "min_perc"),
    TsLink("nonponded_ag", "root_depths", ("icroot",), ("crop",),
           "root_depth_fracs"),
    # ponded crops
    TsLink("ponded_ag", "et_columns", "*", _E, "et"),
    TsLink("ponded_ag", "supply_req_columns", "*", _E, "ag_water_demand"),
    TsLink("ponded_ag", "irig_period_columns", "*", _E, "irig_period"),
    TsLink("ponded_ag", "ponding_depth_columns", "*", _E, "ponding_depth"),
    TsLink("ponded_ag", "app_depth_columns", ("icdwri_nfl",), _E,
           "rice_refuge_ops"),
    TsLink("ponded_ag", "return_flow_columns", "*", _E, "rice_refuge_ops"),
    TsLink("ponded_ag", "reuse_columns", "*", _E, "rice_refuge_ops"),
    # urban
    TsLink("urban", "element_params", ("icpopul",), _E, "population"),
    TsLink("urban", "element_params", ("icwtruse",), _E, "per_capita_use"),
    TsLink("urban", "element_params", ("iceturb",), _E, "et"),
    TsLink("urban", "element_params", ("icrtfurb",), _E, "return_flow"),
    TsLink("urban", "element_params", ("icrufurb",), _E, "reuse_frac"),
    TsLink("urban", "element_params", ("icurbspec",), _E,
           "water_use_specs"),
    # native/riparian vegetation
    TsLink("native_veg", "element_params", ("icetnv", "icetrv"), _E, "et"),
    # root zone main soil table
    TsLink("rootzone", "element_params", ("irne",), _E, "precip"),
    TsLink("rootzone", "element_params", ("imsrc",), _E, "moisture_src",
           note="0 = precipitation is the moisture source"),
    TsLink("rootzone", "element_params",
           ("icdstag", "icdsturbin", "icdsturbout", "icdstnvrv"), _E,
           "surface_flow_dest", note="v4.12+ only"),
    # small watersheds
    TsLink("swshed", "rootzone_params", ("irns",), ("id",), "precip"),
    TsLink("swshed", "rootzone_params", ("icets",), ("id",), "et"),
    # lakes
    TsLink("lake_main", "lake_params", ("max_elev_col",), ("lake_id",),
           "max_lake_elev"),
    TsLink("lake_main", "lake_params", ("et_col",), ("lake_id",), "et"),
    TsLink("lake_main", "lake_params", ("precip_col",), ("lake_id",),
           "precip"),
    # stream evaporation (icarst -> STARFL has no reader; not linked)
    TsLink("stream_main", "evaporation", ("icetst",), ("stream_node",),
           "et"),
    # wells
    TsLink("well_spec", "pump_config", ("icolwl",), ("id",),
           "ts_pumping", scale="fracwl"),
    TsLink("well_spec", "pump_config", ("icwlmax",), ("id",),
           "ts_pumping", note="maximum-pumping column"),
    TsLink("well_spec", "pump_config", ("icfirigwl",), ("id",),
           "irigfrac"),
    TsLink("well_spec", "pump_config", ("icadjwl",), ("id",),
           "supply_adjust"),
    # element pumping
    TsLink("elem_pump", "data", ("icolsk",), ("id",), "ts_pumping",
           scale="fracsk"),
    TsLink("elem_pump", "data", ("icskmax",), ("id",), "ts_pumping",
           note="maximum-pumping column"),
    TsLink("elem_pump", "data", ("icfirigsk",), ("id",), "irigfrac"),
    TsLink("elem_pump", "data", ("icadjsk",), ("id",), "supply_adjust"),
    # boundary conditions
    TsLink("spec_head", "data", ("itscol",), ("node_id", "layer"),
           "boundary_ts", note="0 = constant head"),
    TsLink("spec_flow", "data", ("itscol",), ("node_id", "layer"),
           "boundary_ts"),
    TsLink("ghbc", "data", ("itscol",), ("node_id", "layer"),
           "boundary_ts"),
    TsLink("con_ghbc", "data", ("itscol", "itscolf"),
           ("node_id", "layer"), "boundary_ts"),
    # diversions
    TsLink("diver_specs", "data", ("max_col",), ("diversion_id",),
           "diversions", scale="max_frac"),
    TsLink("diver_specs", "data", ("recov_loss_col",), ("diversion_id",),
           "diversions", scale="recov_loss_frac"),
    TsLink("diver_specs", "data", ("nonrecov_loss_col",),
           ("diversion_id",), "diversions", scale="nonrecov_loss_frac"),
    TsLink("diver_specs", "data", ("delivery_col",), ("diversion_id",),
           "diversions", scale="delivery_frac"),
    TsLink("diver_specs", "data", ("spill_col",), ("diversion_id",),
           "diversions", note="older spill-pair layouts only"),
    TsLink("diver_specs", "data", ("irig_frac_col",), ("diversion_id",),
           "irigfrac"),
    TsLink("diver_specs", "data", ("adjust_col",), ("diversion_id",),
           "supply_adjust"),
)

#: Columns never treated as pointers by the "*" expansion
_NON_POINTER_COLS = {"notes", "name"}


# ------------------------------------------------------------------
# Entity-ID links
# ------------------------------------------------------------------

ID_LINKS: tuple[IdLink, ...] = (
    IdLink("rootzone", "element_params", "element_id", "element"),
    IdLink("urban", "element_params", "element_id", "element"),
    IdLink("native_veg", "element_params", "element_id", "element"),
    IdLink("unsatzone", "element_params", "element_id", "element"),
    IdLink("elem_pump", "data", "id", "element", zero_ok=False),
    IdLink("gw_main", "kh_anomalies", "element_id", "element",
           zero_ok=False),
    IdLink("gw_main", "aquifer_params", "node_id", "node",
           zero_ok=False),
    IdLink("gw_main", "initial_heads", "node_id", "node", zero_ok=False),
    IdLink("spec_head", "data", "node_id", "node", zero_ok=False),
    IdLink("spec_flow", "data", "node_id", "node", zero_ok=False),
    IdLink("ghbc", "data", "node_id", "node", zero_ok=False),
    IdLink("con_ghbc", "data", "node_id", "node", zero_ok=False),
    IdLink("tile_drain", "data", "node", "node", zero_ok=False),
    IdLink("swshed", "watershed_nodes", "gw_node", "node",
           zero_ok=False),
    IdLink("swshed", "watershed_data", "stream_node", "stream_node"),
    IdLink("stream_main", "reach_params", "stream_node_id",
           "stream_node", zero_ok=False),
    IdLink("stream_main", "evaporation", "stream_node", "stream_node",
           zero_ok=False),
    # export_node 0 = water imported from outside the model
    IdLink("diver_specs", "data", "export_node", "stream_node",
           zero_ok=True),
    IdLink("bypass_specs", "bypass_data", "stream_node", "stream_node",
           zero_ok=False),
)


# ------------------------------------------------------------------
# Polymorphic destination links
# ------------------------------------------------------------------

DEST_LINKS: tuple[DestLink, ...] = (
    DestLink("diver_specs", "data", "dest_type", "dest_id",
             {0: None, 2: "element", 4: "subregion",
              6: "group:diver_specs"}),
    DestLink("lake_geom", "data", "dest_type", "dest_id",
             {0: None, 1: "stream_node", 3: "lake"}),
    DestLink("gw_main", "return_flow", "dest_type", "dest",
             {0: None, 1: "stream_node", 3: "lake"}),
    DestLink("well_spec", "pump_config", "typdstwl", "dstwl",
             {-1: None, 0: None, 2: "element", 4: "subregion",
              6: "group:well_spec"}),
    DestLink("elem_pump", "data", "typdstsk", "dstsk",
             {-1: None, 0: None, 2: "element", 4: "subregion",
              6: "group:elem_pump"}),
)


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------


def _reader(name: str):
    import iwfm_io
    return getattr(iwfm_io, name)


def load_component(model, name: str):
    """Parse (and cache) a component by registry name, or None when the
    model does not reference it."""
    attr = PRELOADED.get(name)
    if attr is not None and getattr(model, attr, None) is not None:
        return getattr(model, attr)
    comp = COMPONENTS[name]
    path = _component_path(model, comp)
    if path is None or not Path(path).exists():
        return None
    cached = getattr(model, "_cached_file", None)
    if cached is None:                      # duck-typed model without the cache
        return _read_component(model, comp, path)
    return cached(f"_component::{name}", [path],
                  lambda: _read_component(model, comp, path))


def _component_path(model, comp):
    if comp.parent is None:
        parent = model._sim
    else:
        parent = load_component(model, comp.parent)
    paths = getattr(parent, "file_paths", {}) if parent else {}
    return paths.get(comp.path_key)


def _read_component(model, comp, path):
    fn = _reader(comp.reader)
    kwargs = {}
    if "n_elements" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
        try:
            kwargs["n_elements"] = int(len(model.elements_df()))
        except Exception:
            pass
    return fn(path, **kwargs)


def _target_path(model, target: TsTarget):
    if target.component == "__sim__":
        parent = model._sim
        paths = getattr(parent, "file_paths", {}) if parent else {}
        return paths.get(target.path_key)
    parent = load_component(model, target.component)
    if parent is None:
        return None
    if target.path_key == "__max_elev_file__":
        return getattr(parent, "max_elev_file", None)
    return getattr(parent, "file_paths", {}).get(target.path_key)


def load_timeseries(model, role: str):
    """Parse (and cache) the time-series file for a registry role."""
    if role not in TS_TARGETS:
        raise KeyError(
            f"unknown time-series role {role!r}; known roles: "
            f"{sorted(TS_TARGETS)}")
    target = TS_TARGETS[role]
    path = _target_path(model, target)
    if not path or not Path(path).exists():
        return None
    cached = getattr(model, "_cached_file", None)
    if cached is None:
        return _reader(target.reader)(path)
    return cached(f"_timeseries::{role}", [path],
                  lambda: _reader(target.reader)(path))


def _ts_meta(obj, target: TsTarget):
    """(data DataFrame, n_columns, factor) for a parsed TS object."""
    data = getattr(obj, "data", None)
    if hasattr(obj, "spec") and obj.spec is not None:
        ncol = obj.spec.n_columns
    else:
        ncol = getattr(obj, "n_columns", None)
    factor = None
    if target.factor == "spec":
        factor = obj.spec.factor
    elif target.factor == "obj":
        factor = getattr(obj, "factor", None)
    return data, ncol, factor


def series(model, role: str, column: int, raw: bool = False,
           expand: bool = True) -> pd.DataFrame:
    """One referenced time-series column as a two-column DataFrame.

    Returns ``date`` + ``value``; the file's conversion factor is
    applied unless ``raw=True``, and recurring-year data (sentinel
    years 2500/4000) is expanded onto the simulation period unless
    ``expand=False``.
    """
    target = TS_TARGETS[role]
    if target.kind == "dest_pairs":
        raise ValueError(
            f"{role!r} holds (type, dest) tuples, not a numeric series — "
            "use model.timeseries(role) and the type_i/dest_i columns")
    obj = load_timeseries(model, role)
    if obj is None:
        raise FileNotFoundError(
            f"the model does not reference a {role!r} file")
    data, ncol, factor = _ts_meta(obj, target)
    if data is None:
        raise ValueError(
            f"{role!r} is DSS-backed (no inline data); read the DSS "
            "records via iwfm_io.read_dss_timeseries with "
            f"model.timeseries({role!r}).dss_pathnames")
    if not (1 <= int(column) <= (ncol or 0)):
        raise IndexError(
            f"{role!r} has columns 1..{ncol}; got {column}")
    col = f"col_{int(column)}"
    out = data[["date", col]].rename(columns={col: "value"}).copy()
    if not raw and factor is not None and target.kind != "flags":
        out["value"] = out["value"] * factor
    if expand and model._sim is not None:
        from iwfm_io._tokens import expand_recurring
        out = expand_recurring(out, model._sim.sim_begin,
                               model._sim.sim_end)
    return out.reset_index(drop=True)


def _pointer_columns(link: TsLink, df: pd.DataFrame) -> list[str]:
    if link.pointers == "*":
        return [c for c in df.columns
                if c not in link.keys and c not in _NON_POINTER_COLS]
    return [c for c in link.pointers if c in df.columns]


def _iter_ts_links(model):
    """Yield (link, table DataFrame, pointer columns) for present data."""
    for link in TS_LINKS:
        comp = load_component(model, link.source)
        if comp is None:
            continue
        df = getattr(comp, link.table, None)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            continue
        cols = _pointer_columns(link, df)
        if cols:
            yield link, df, cols


def column_usage(model, role: str) -> pd.DataFrame:
    """Who references each column of a time-series file.

    Long DataFrame: ``column``, ``source``, ``table``,
    ``pointer_column``, ``n_refs``, ``examples`` (up to three key
    tuples).  This is the reverse lookup that gives the otherwise
    anonymous ``col_N`` columns their meaning.
    """
    rows = []
    for link, df, cols in _iter_ts_links(model):
        if link.target != role:
            continue
        for col in cols:
            vals = pd.to_numeric(df[col], errors="coerce")
            for column, group in df[vals > 0].groupby(vals[vals > 0]):
                keys = group[list(link.keys)].astype(str).agg(
                    "/".join, axis=1)
                rows.append({
                    "column": int(column),
                    "source": link.source,
                    "table": link.table,
                    "pointer_column": col,
                    "n_refs": len(group),
                    "examples": ", ".join(keys.head(3)),
                })
    out = pd.DataFrame(
        rows, columns=["column", "source", "table", "pointer_column",
                       "n_refs", "examples"])
    return out.sort_values(["column", "source", "table"]).reset_index(
        drop=True)


# ------------------------------------------------------------------
# Reference validation
# ------------------------------------------------------------------


def _entity_ids(model, entity: str, group_source: str | None = None):
    """The set of known ids for *entity*.

    Empty only when the entity's file is genuinely absent (a model
    without streams or lakes, a component the model does not
    reference); a parse failure propagates as ``IWFMParseError``.
    """
    cache = model._cache.setdefault("_entity_ids", {})
    key = entity if group_source is None else f"group:{group_source}"
    if key in cache:
        return cache[key]
    ids: set = set()
    pp = getattr(model, "_pp", None)
    children = getattr(pp, "children", {}) if pp is not None else {}
    if entity == "element":
        ids = set(model.elements_df()["element_id"].astype(int))
    elif entity == "node":
        ids = set(model.nodes_df()["node_id"].astype(int))
    elif entity == "stream_node":
        if children.get("stream") is not None:
            ids = set(model.stream_nodes_df()["stream_node_id"]
                      .astype(int))
    elif entity == "subregion":
        ids = set(model.subregions_df()["subregion_id"].astype(int))
    elif entity == "lake":
        if children.get("lake") is not None:
            lakes = model.lakes_df()
            if lakes is not None and "lake_id" in lakes.columns:
                ids = set(lakes["lake_id"].astype(int))
    elif entity == "group":
        comp = load_component(model, group_source)
        groups = (getattr(comp, "element_groups", None)
                  or getattr(comp, "delivery_groups", None)) if comp \
            else None
        ids = {g["group_id"] for g in groups} if groups else set()
    else:
        raise KeyError(f"unknown entity {entity!r}")
    cache[key] = ids
    return ids


def _numeric_values(rows, severity_src, table, column, raw,
                    what="pointer"):
    """Numeric, integral values of a column; non-numeric text and
    non-integral numbers are reported as findings (never coerced away).
    Missing values (NaN/None) are skipped — they are legitimate blanks
    (e.g. the spill pair of a no-spill diversion layout)."""
    present = raw[raw.notna()]
    num = pd.to_numeric(present, errors="coerce")
    bad_text = present[num.isna()]
    if len(bad_text):
        _finding(rows, "error", severity_src, table, column,
                 f"non-numeric {what} value(s)",
                 sorted({str(v) for v in bad_text}))
    num = num.dropna().astype(float)
    frac = num[num != num.round()]
    if len(frac):
        _finding(rows, "error", severity_src, table, column,
                 f"non-integral {what} value(s)",
                 sorted(frac.unique().tolist()))
    return num[num == num.round()].astype(int)


def _finding(rows, severity, source, table, column, issue, bad):
    rows.append({
        "severity": severity,
        "source": source,
        "table": table,
        "column": column,
        "issue": issue,
        "count": len(bad),
        "examples": ", ".join(str(v) for v in bad[:5]),
    })


def validate_references(model) -> pd.DataFrame:
    """Validate every cross-file reference the registry knows about.

    Checks pointer columns against the referenced file's declared
    column count (0 = none is always legal), entity IDs against the
    grid tables, and ``(type, dest)`` pairs against their code tables.
    Returns a findings DataFrame (empty = everything resolves);
    missing optional components are skipped, but a pointer into a file
    the model does not reference is an error.
    """
    rows: list[dict] = []

    # ---- pointer -> TS column ----
    for link, df, cols in _iter_ts_links(model):
        target = TS_TARGETS[link.target]
        obj = load_timeseries(model, link.target)
        ncol = None
        if obj is not None:
            _, ncol, _ = _ts_meta(obj, target)
        for col in cols:
            vals = _numeric_values(rows, link.source, link.table, col,
                                   df[col])
            used = vals[vals != 0]
            if used.empty:
                continue
            if obj is None:
                _finding(rows, "error", link.source, link.table, col,
                         f"points into {link.target!r} but the model "
                         "references no such file",
                         sorted(used.unique().astype(int).tolist()))
                continue
            neg = sorted(used[used < 0].unique().astype(int).tolist())
            if neg:
                _finding(rows, "warning", link.source, link.table, col,
                         f"negative pointer values into {link.target!r}",
                         neg)
            if ncol is not None:
                over = sorted(used[used > ncol].unique().astype(int)
                              .tolist())
                if over:
                    _finding(rows, "error", link.source, link.table, col,
                             f"pointer beyond {link.target!r} column "
                             f"count ({ncol})", over)

    # ---- entity IDs ----
    for link in ID_LINKS:
        comp = load_component(model, link.source)
        if comp is None:
            continue
        df = getattr(comp, link.table, None)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty \
                or link.column not in df.columns:
            continue
        ids = _entity_ids(model, link.entity)
        if not ids:
            continue
        vals = _numeric_values(rows, link.source, link.table, link.column,
                               df[link.column], what=f"{link.entity} id")
        if link.zero_ok:
            vals = vals[vals != 0]
        bad = sorted(set(vals) - ids)
        if bad:
            _finding(rows, "error", link.source, link.table, link.column,
                     f"unknown {link.entity} id(s)", bad)

    # ---- (type, dest) pairs ----
    for link in DEST_LINKS:
        if link.source == "lake_geom":
            lake_child = model._pp.children.get("lake") if model._pp \
                else None
            df = getattr(lake_child, "data", None)
        else:
            comp = load_component(model, link.source)
            df = getattr(comp, link.table, None) if comp else None
        if df is None or not isinstance(df, pd.DataFrame) or df.empty \
                or link.type_col not in df.columns:
            continue
        types = pd.to_numeric(df[link.type_col], errors="coerce")
        _numeric_values(rows, link.source, link.table, link.type_col,
                        df[link.type_col], what="destination type")
        unknown = sorted(set(types.dropna().astype(int))
                         - set(link.codes))
        if unknown:
            _finding(rows, "warning", link.source, link.table,
                     link.type_col, "unknown destination type code(s)",
                     unknown)
        for code, entity in link.codes.items():
            if entity is None:
                continue
            sel = df[types == code]
            if sel.empty:
                continue
            dests = _numeric_values(rows, link.source, link.table,
                                    link.dest_col, sel[link.dest_col],
                                    what=f"type {code} destination")
            if entity.startswith("group:"):
                ids = _entity_ids(model, "group",
                                  entity.split(":", 1)[1])
            else:
                ids = _entity_ids(model, entity)
            if not ids:
                continue
            bad = sorted(set(dests) - ids)
            if bad:
                _finding(rows, "error", link.source, link.table,
                         link.dest_col,
                         f"type {code} destination not a known "
                         f"{entity.split(':', 1)[-1]}", bad)

    return pd.DataFrame(
        rows, columns=["severity", "source", "table", "column", "issue",
                       "count", "examples"])


# ------------------------------------------------------------------
# Convenience accessors
# ------------------------------------------------------------------
#
# Each accessor answers one modeling question ("what ET series drives
# crop TO at element 12?") by combining: the consumer row (honoring
# the element_id=0 "all elements" sentinel), the registry's pointer ->
# role mapping, per-consumer scale columns, and series() resolution
# (factor + recurring-year expansion).

#: kind -> (pointer table, target role), per land-use component
_NONPONDED_KINDS = {
    "et": ("et_columns", "et"),
    "irrigation_period": ("irig_period_columns", "irig_period"),
    "supply_requirement": ("supply_req_columns", "ag_water_demand"),
    "min_moisture": ("min_moisture_columns", "min_soil_moisture"),
    "target_moisture": ("target_moisture_columns",
                        "target_soil_moisture"),
    "return_flow": ("return_flow_columns", "return_flow"),
    "reuse": ("reuse_columns", "reuse_frac"),
    "min_perc": ("min_perc_columns", "min_perc"),
}
_PONDED_KINDS = {
    "et": ("et_columns", "et"),
    "irrigation_period": ("irig_period_columns", "irig_period"),
    "supply_requirement": ("supply_req_columns", "ag_water_demand"),
    "ponding_depth": ("ponding_depth_columns", "ponding_depth"),
    # ponded return/reuse pointers reference FLOWFL, not RFFL/RUFL
    "return_flow": ("return_flow_columns", "rice_refuge_ops"),
    "reuse": ("reuse_columns", "rice_refuge_ops"),
}
_PONDED_TYPES = ("rice_fl", "rice_nfl", "rice_ndc",
                 "refuge_sl", "refuge_pr")
_URBAN_KINDS = {
    "population": ("icpopul", "population"),
    "per_capita_use": ("icwtruse", "per_capita_use"),
    "water_use_specs": ("icurbspec", "water_use_specs"),
    "et": ("iceturb", "et"),
    "return_flow": ("icrtfurb", "return_flow"),
    "reuse": ("icrufurb", "reuse_frac"),
}
_NATIVE_ET_COLS = {"native": "icetnv", "riparian": "icetrv"}


def _element_row(df: pd.DataFrame, element, what: str,
                 key: str = "element_id") -> pd.Series:
    """The row applying to *element*, honoring the id-0 sentinel."""
    ids = df[key].astype(int)
    if element is None:
        if len(df) == 1:
            return df.iloc[0]
        zero = df[ids == 0]
        if len(zero):
            return zero.iloc[0]
        raise ValueError(
            f"{what}: the table has per-element rows — pass element=")
    hit = df[ids == int(element)]
    if len(hit):
        return hit.iloc[0]
    zero = df[ids == 0]
    if len(zero):  # id 0 = the values apply to all elements
        return zero.iloc[0]
    raise KeyError(f"{what}: no row for element {element}")


def _pointer(row, col: str, what: str) -> int:
    value = row[col]
    value = int(value) if pd.notna(value) else 0
    if value <= 0:
        raise ValueError(
            f"{what} has no data column (pointer is {value}; 0 means "
            "none / computed internally)")
    return value


def crop_series(model, kind: str, crop: str, element=None,
                raw: bool = False, expand: bool = True) -> pd.DataFrame:
    """A land-use driver series for one crop/land-use at one element."""
    what = f"{kind} for {crop!r}" + (
        f" at element {element}" if element is not None else "")

    if crop in _NATIVE_ET_COLS:
        if kind != "et":
            raise ValueError(
                f"native/riparian vegetation only has kind='et' "
                f"(got {kind!r})")
        comp = load_component(model, "native_veg")
        if comp is None or comp.element_params is None:
            raise FileNotFoundError(
                "the model references no native vegetation main file")
        row = _element_row(comp.element_params, element, what)
        return series(model, "et",
                      _pointer(row, _NATIVE_ET_COLS[crop], what),
                      raw=raw, expand=expand)

    np_ag = load_component(model, "nonponded_ag")
    if np_ag is not None and crop in np_ag.crop_codes:
        comp, kinds, col = np_ag, _NONPONDED_KINDS, crop
    elif crop in _PONDED_TYPES:
        comp = load_component(model, "ponded_ag")
        if comp is None:
            raise FileNotFoundError(
                "the model references no ponded crops main file")
        kinds, col = _PONDED_KINDS, crop
    else:
        known = (list(np_ag.crop_codes) if np_ag else []) \
            + list(_PONDED_TYPES) + list(_NATIVE_ET_COLS)
        raise KeyError(f"unknown crop {crop!r}; known: {known}")

    if kind not in kinds:
        raise ValueError(
            f"unknown kind {kind!r} for {crop!r}; choose from "
            f"{sorted(kinds)}")
    table_name, role = kinds[kind]
    table = getattr(comp, table_name, None)
    if table is None:
        raise FileNotFoundError(
            f"the model has no {kind} table (the referenced file is "
            "not configured)")
    row = _element_row(table, element, what)
    return series(model, role, _pointer(row, col, what),
                  raw=raw, expand=expand)


def urban_series(model, kind: str, element=None, raw: bool = False,
                 expand: bool = True) -> pd.DataFrame:
    """An urban driver series (population, per-capita use, ...) at one
    element."""
    if kind not in _URBAN_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; choose from {sorted(_URBAN_KINDS)}")
    comp = load_component(model, "urban")
    if comp is None or comp.element_params is None:
        raise FileNotFoundError(
            "the model references no urban main file")
    col, role = _URBAN_KINDS[kind]
    what = f"urban {kind}" + (
        f" at element {element}" if element is not None else "")
    row = _element_row(comp.element_params, element, what)
    return series(model, role, _pointer(row, col, what),
                  raw=raw, expand=expand)


def well_pumping(model, well_id: int, kind: str = "pumping",
                 scaled: bool = True, raw: bool = False,
                 expand: bool = True) -> pd.DataFrame:
    """A well's pumping (or maximum-pumping) series from TSPumping,
    scaled by the well's FRACWL share unless ``scaled=False``."""
    ws = load_component(model, "well_spec")
    if ws is None or ws.pump_config is None:
        raise FileNotFoundError(
            "the model references no well specification file")
    hit = ws.pump_config[ws.pump_config["id"].astype(int) == int(well_id)]
    if not len(hit):
        raise KeyError(f"no well with id {well_id}")
    row = hit.iloc[0]
    if kind == "pumping":
        col_field, scale = "icolwl", "fracwl"
    elif kind == "max":
        col_field, scale = "icwlmax", None
    else:
        raise ValueError(
            f"unknown kind {kind!r}; choose 'pumping' or 'max'")
    out = series(model, "ts_pumping",
                 _pointer(row, col_field, f"well {well_id} {kind}"),
                 raw=raw, expand=expand)
    if scaled and scale is not None:
        out = out.copy()
        out["value"] = out["value"] * float(row[scale])
    return out


def element_pumping(model, element_id: int, kind: str = "pumping",
                    scaled: bool = True, raw: bool = False,
                    expand: bool = True) -> pd.DataFrame:
    """An element's pumping (or maximum-pumping) series from TSPumping,
    scaled by the element's FRACSK share unless ``scaled=False``."""
    ep = load_component(model, "elem_pump")
    if ep is None or ep.data is None:
        raise FileNotFoundError(
            "the model references no element pumping file")
    hit = ep.data[ep.data["id"].astype(int) == int(element_id)]
    if not len(hit):
        raise KeyError(f"no element pumping for element {element_id}")
    if len(hit) > 1:
        raise ValueError(
            f"element {element_id} has {len(hit)} pumping rows — use "
            "model.component('elem_pump').data directly")
    row = hit.iloc[0]
    if kind == "pumping":
        col_field, scale = "icolsk", "fracsk"
    elif kind == "max":
        col_field, scale = "icskmax", None
    else:
        raise ValueError(
            f"unknown kind {kind!r}; choose 'pumping' or 'max'")
    out = series(model, "ts_pumping",
                 _pointer(row, col_field,
                          f"element {element_id} {kind}"),
                 raw=raw, expand=expand)
    if scaled and scale is not None:
        out = out.copy()
        out["value"] = out["value"] * float(row[scale])
    return out


#: BC components searched by bc_series, with their constant-value
#: column and the attribute holding its conversion factor
_BC_SOURCES = (
    ("spec_head", "head", "factor"),
    ("spec_flow", "flow", "factor"),
    ("ghbc", "head", "facth"),
    ("con_ghbc", "head", "facth"),
)


def bc_series(model, node: int, layer=None, raw: bool = False,
              expand: bool = True) -> pd.DataFrame:
    """The boundary-condition series at a GW node (and layer).

    Searches the specified-head, specified-flow, general-head, and
    constrained-head BC files.  A time-series-driven BC resolves its
    ITSCOL column of the time-series BC file; a constant BC (ITSCOL=0)
    returns its constant value as a single stamp at the simulation
    start (factor applied unless ``raw=True``).
    """
    matches = []
    for name, value_col, factor_attr in _BC_SOURCES:
        comp = load_component(model, name)
        df = getattr(comp, "data", None) if comp else None
        if df is None or df.empty:
            continue
        sel = df[df["node_id"].astype(int) == int(node)]
        if layer is not None:
            sel = sel[sel["layer"].astype(int) == int(layer)]
        for _, row in sel.iterrows():
            matches.append((name, value_col, factor_attr, comp, row))
    if not matches:
        where = f"node {node}" + (f", layer {layer}"
                                  if layer is not None else "")
        raise KeyError(f"no boundary condition at {where}")
    if len(matches) > 1:
        found = ", ".join(f"{m[0]} (layer {int(m[4]['layer'])})"
                          for m in matches)
        raise ValueError(
            f"multiple boundary conditions at node {node}: {found} — "
            "pass layer= (or read the BC components directly)")
    name, value_col, factor_attr, comp, row = matches[0]
    itscol = int(row["itscol"]) if pd.notna(row["itscol"]) else 0
    if itscol > 0:
        return series(model, "boundary_ts", itscol, raw=raw,
                      expand=expand)
    value = float(row[value_col])
    if not raw:
        value *= float(getattr(comp, factor_attr, 1.0) or 1.0)
    begin = None
    if model._sim is not None:
        from iwfm_io._tokens import parse_iwfm_date
        try:
            begin = pd.Timestamp(parse_iwfm_date(model._sim.sim_begin))
        except (TypeError, ValueError):
            begin = None
    return pd.DataFrame({"date": [begin], "value": [value]})


_DIVERSION_KINDS = {
    "delivery": ("delivery_col", "delivery_frac"),
    "max": ("max_col", "max_frac"),
    "recoverable_loss": ("recov_loss_col", "recov_loss_frac"),
    "nonrecoverable_loss": ("nonrecov_loss_col", "nonrecov_loss_frac"),
    "spill": ("spill_col", "spill_frac"),
}


def diversion_series(model, diversion_id: int, kind: str = "delivery",
                     scaled: bool = True, raw: bool = False,
                     expand: bool = True) -> pd.DataFrame:
    """One diversion's series from the Diversions file — its delivery,
    maximum, loss, or spill column — scaled by the matching fraction
    unless ``scaled=False``."""
    if kind not in _DIVERSION_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; choose from "
            f"{sorted(_DIVERSION_KINDS)}")
    ds = load_component(model, "diver_specs")
    if ds is None or ds.data is None:
        raise FileNotFoundError(
            "the model references no diversion specification file")
    hit = ds.data[ds.data["diversion_id"].astype(int)
                  == int(diversion_id)]
    if not len(hit):
        raise KeyError(f"no diversion with id {diversion_id}")
    row = hit.iloc[0]
    col_field, frac_field = _DIVERSION_KINDS[kind]
    out = series(model, "diversions",
                 _pointer(row, col_field,
                          f"diversion {diversion_id} {kind}"),
                 raw=raw, expand=expand)
    if scaled:
        out = out.copy()
        out["value"] = out["value"] * float(row[frac_field])
    return out


def lake_max_elevation(model, lake_id=None, raw: bool = False,
                       expand: bool = True) -> pd.DataFrame:
    """A lake's maximum-elevation series from MaxLakeElev."""
    lk = load_component(model, "lake_main")
    if lk is None or lk.lake_params is None:
        raise FileNotFoundError(
            "the model references no lake main file")
    df = lk.lake_params
    if lake_id is None:
        if len(df) > 1:
            raise ValueError(
                f"the model has {len(df)} lakes — pass lake_id=")
        row = df.iloc[0]
    else:
        hit = df[df["lake_id"].astype(int) == int(lake_id)]
        if not len(hit):
            raise KeyError(f"no lake with id {lake_id}")
        row = hit.iloc[0]
    what = f"lake {int(row['lake_id'])} maximum elevation"
    return series(model, "max_lake_elev",
                  _pointer(row, "max_elev_col", what),
                  raw=raw, expand=expand)
