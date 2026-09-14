"""DLL-API compatibility shims for :class:`~iwfm_io.model_adapter.IOModelAdapter`.

The plot library (and older user code) was written against the numpy /
dict-returning getters of :class:`iwfm_io.dll.model.IWFMModel`
(``get_budget_timeseries``, ``get_hydrograph``, ``get_node_ids``, ...).
:class:`DllCompatMixin` serves the same shapes from the parsed files and
result outputs so that every plot renders DLL-free.  It is mixed into
``IOModelAdapter`` and relies on the adapter's core DataFrame API
(``nodes_df``, ``elements_df``, ``heads_df``, ``budget_df``,
``hydrograph_df``, ``_read_full_budget``, ``_cached_file``, ...) plus its
private handles (``_sim``, ``_gw_main``, ``_cache``, ...).  Nothing here
is public API on its own — import ``IOModelAdapter`` instead.

Dates come back as Excel serial days (float days since 1899-12-30), the
DLL's convention.
"""

from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BUDGET_TYPE_CODES = {
    # IWFM DLL budget type ids (IW_GetBudgetTypeIDs, 2025.0.1747)
    1001: "StrmNode", 1002: "StrmReach", 1003: "DiverDetail",
    2001: "Lake", 3001: "GW", 4001: "LWU", 4002: "RootZone",
    4003: "NonPondedCrop_LWU", 4004: "NonPondedCrop_RZ",
    4005: "PondedCrop_LWU", 4006: "PondedCrop_RZ",
    5001: "UnsatZone", 6001: "SWShed",
}

#: keyword arguments the DLL wrapper's DataFrame methods take; accepted
#: (and, where meaningful, applied) so DLL-written code runs unchanged
_DLL_COMPAT_KWARGS = frozenset({"fact_lt", "fact_ar", "fact_vl",
                                "length_unit", "area_unit", "volume_unit"})


def _as_index(value, what, lo, hi):
    """Validate an integer-like index (numpy ints ok, bools not) in
    ``[lo, hi]`` and return it as ``int``."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)):
        raise TypeError(f"{what} must be an integer, got {value!r}")
    value = int(value)
    if not lo <= value <= hi:
        raise IndexError(f"{what} {value} out of range [{lo}, {hi}]")
    return value


def _check_compat_kwargs(kwargs, what):
    unknown = set(kwargs) - _DLL_COMPAT_KWARGS
    if unknown:
        raise TypeError(
            f"{what}() got unexpected keyword argument(s) "
            f"{sorted(unknown)}")
    return float(kwargs.get("fact_vl", 1.0))


def _excel_serials(index) -> np.ndarray:
    """DatetimeIndex -> Excel serial days (fractional; the DLL convention)."""
    base = pd.Timestamp("1899-12-30")
    return ((pd.DatetimeIndex(index) - base)
            / pd.Timedelta(days=1)).to_numpy(dtype=float)


def _file_sig(path):
    """(mtime_ns, size) of *path*, or None when it cannot be stat'ed --
    the cheap fingerprint that tells a cached table its source changed."""
    if path is None:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class DllCompatMixin:
    """Mixin providing ``IWFMModel``-shaped getters on top of the
    adapter's DataFrame API (see the module docstring)."""

    def get_stratigraphy_at_xy(self, x, y):
        """Compatibility method matching ``IWFMModel.get_stratigraphy_at_xy``.

        Layer elevations are derived from the stratigraphy file (ground
        surface minus cumulative aquitard/aquifer thicknesses) and
        interpolated linearly between grid nodes; points outside the mesh
        use the nearest node.

        Returns
        -------
        dict
            Keys ``GSElev`` (float), ``TopElevs`` and ``BottomElevs``
            (arrays of length ``n_layers``).
        """
        xs, ys, gse, tops, bots = self._strat_node_arrays()
        nl = tops.shape[1]
        vals = np.column_stack([gse[:, None], tops, bots])
        out = np.empty(vals.shape[1])
        interpolated = False
        try:
            from matplotlib.tri import Triangulation, LinearTriInterpolator
            tri = self._cache.get("strat_tri")
            if tri is None:
                tri = Triangulation(xs, ys)
                self._cache["strat_tri"] = tri
            for j in range(vals.shape[1]):
                r = LinearTriInterpolator(tri, vals[:, j])(x, y)
                if np.ma.is_masked(r):
                    break
                out[j] = float(r)
            else:
                interpolated = True
        except Exception:
            pass
        if not interpolated:
            i = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
            out = vals[i].astype(float)
        return {
            "GSElev": float(out[0]),
            "TopElevs": out[1:1 + nl],
            "BottomElevs": out[1 + nl:],
        }

    def get_gw_heads_for_layer(self, layer, begin_date, end_date, factor=1.0):
        """Compatibility method matching ``IWFMModel.get_gw_heads_for_layer``.

        Returns ``(dates, heads)`` in the DLL wrapper's convention —
        *dates* as Excel serial numbers (float days since 1899-12-30) and
        *heads* with shape ``(n_nodes, n_times)`` — so plot functions
        written against the legacy interface also work with file-based
        models.
        """
        df = self.heads_df(layer, begin_date=begin_date, end_date=end_date)
        base = pd.Timestamp("1899-12-30")
        dates = ((df.index - base) / pd.Timedelta(days=1)).to_numpy(dtype=float)
        heads = df.to_numpy(dtype=float).T * factor
        return dates, heads

    def _budget_key(self, budget_type):
        """Resolve a budget name, DLL type code or loose name to a key."""
        keys = list(self._budget_hdfs) + [k for k in self._budget_texts
                                          if k not in self._budget_hdfs]
        if isinstance(budget_type, (bool, np.bool_)):
            raise TypeError("budget name must be a string or a DLL type code")
        if isinstance(budget_type, (int, np.integer)):
            name = _BUDGET_TYPE_CODES.get(int(budget_type))
            if name is None:
                raise KeyError(
                    f"unknown DLL budget type code {int(budget_type)}; "
                    f"known: {sorted(_BUDGET_TYPE_CODES)}")
            budget_type = name
        if budget_type in keys:
            return budget_type
        key = self._find_budget_key(str(budget_type))
        if key is None:
            raise RuntimeError(
                f"IOModelAdapter: no budget named {budget_type!r}; "
                f"available: {keys}")
        return key

    # -- DLL-API budget / hydrograph shims -----------------------------
    # The plot functions were written against IWFMModel's getters; these
    # serve the same shapes from the result files so every plot renders
    # DLL-free. Dates come back as Excel serial days like the DLL.

    def _budget_frame(self, budget_type, location, begin_date=None,
                      end_date=None, interval=None, fact_vl=1.0):
        native = (self._sim.time_unit if self._sim else "") or ""
        if interval is not None and str(interval).upper() in (
                "", native.upper()):
            interval = None
        return self.budget_df(budget_type, location, begin_date=begin_date,
                              end_date=end_date, interval=interval,
                              fact_vl=fact_vl)

    def get_budget_n_columns(self, budget_type, location):
        return int(self._budget_frame(budget_type, location).shape[1])

    def get_budget_column_titles(self, budget_type, location,
                                 length_unit="FT", area_unit="SQ FT",
                                 volume_unit="CU FT"):
        """Column titles of a budget (the file's own names; the unit
        arguments are accepted for DLL compatibility)."""
        return [str(c) for c in self._budget_frame(budget_type,
                                                   location).columns]

    def get_budget_timeseries(self, budget_type, location, columns,
                              begin_date, end_date, interval,
                              fact_lt=1.0, fact_ar=1.0, fact_vl=1.0):
        df = self._budget_frame(budget_type, location, begin_date,
                                end_date, interval, fact_vl)
        ncol = df.shape[1]
        sel = [_as_index(c, "column", 1, ncol) - 1 for c in columns]
        sub = df.iloc[:, sel]
        return {"dates": _excel_serials(sub.index),
                "values": sub.to_numpy(dtype=float),
                "data_types": [str(c) for c in sub.columns]}

    def get_budget_monthly_average(self, budget_type, location,
                                   begin_date, end_date, fact_vl=1.0,
                                   lu_type=0, swshed_comp=0):
        """Mean and standard deviation of each column by calendar month
        (Jan..Dec) over the window, from monthly aggregation."""
        from iwfm_io._tokens import iwfm_day
        df = self._budget_frame(budget_type, location, begin_date,
                                end_date, "1MON", fact_vl)
        months = iwfm_day(df.index).month
        g = df.groupby(np.asarray(months))
        mean = g.mean().reindex(range(1, 13))
        std = g.std(ddof=0).reindex(range(1, 13))
        return {"names": [str(c) for c in df.columns],
                "flows": mean.to_numpy(dtype=float).T,
                "std_devs": std.to_numpy(dtype=float).T}

    def get_budget_annual(self, budget_type, location, begin_date,
                          end_date, fact_vl=1.0, lu_type=0, swshed_comp=0):
        """Annual (water-year) values of each column: ``flows`` is
        ``(n_columns, n_years)`` and ``years`` labels each window by the
        year it ends in."""
        from iwfm_io._tokens import iwfm_day
        df = self._budget_frame(budget_type, location, begin_date,
                                end_date, "1YEAR", fact_vl)
        years = iwfm_day(df.index).year.to_numpy(dtype=np.int32)
        return {"names": [str(c) for c in df.columns],
                "flows": df.to_numpy(dtype=float).T,
                "years": years}

    def get_budget_cum_gw_storage_change(self, subregion, begin_date,
                                         end_date, interval, fact_vl=1.0):
        """Cumulative change in groundwater storage for a subregion
        (``(dates, values)`` like the DLL)."""
        df = self._budget_frame("GW", subregion, begin_date, end_date,
                                interval, fact_vl)
        beg = self._find_column(df, "BEGINNING STORAGE")
        end = self._find_column(df, "ENDING STORAGE")
        if beg is not None and end is not None:
            change = df[end] - df[beg]
        else:
            col = (self._find_column(df, "CHANGE IN STORAGE")
                   or self._find_column(df, "STORAGE", "CHANGE"))
            if col is None:
                raise KeyError(
                    "GW budget has no storage columns; columns: "
                    f"{list(df.columns)}")
            change = df[col]
        cum = change.cumsum()
        return _excel_serials(cum.index), cum.to_numpy(dtype=float)

    def get_hydrograph_type_list(self):
        """Hydrograph output kinds available from the result files, as
        ``[{"name", "location_type"}]`` where ``location_type`` is the
        adapter's hydrograph key (used as the DLL's type id)."""
        out = []
        for key in sorted(self._hydrograph_hdfs):
            k = key.lower()
            if "strm" in k or "stream" in k:
                name = "Stream flow hydrograph"
            elif "subs" in k:
                name = "Subsidence hydrograph"
            elif "tile" in k:
                name = "Tile drain hydrograph"
            else:
                name = "Groundwater head hydrograph"
            out.append({"name": name, "location_type": key})
        return out

    def get_n_hydrographs(self, location_type):
        return int(self.hydrograph_df(location_type).shape[1])

    def get_hydrograph_ids(self, location_type):
        return np.arange(1, self.get_n_hydrographs(location_type) + 1,
                         dtype=np.int32)

    def get_hydrograph(self, hyd_type, index, layer, begin_date, end_date,
                       interval=None, fact_lt=1.0, fact_vl=1.0):
        """``(dates, values)`` for hydrograph *index* (1-based id) of the
        hydrograph file *hyd_type* (an adapter key). Only the native
        output interval is served; ``layer`` is accepted for DLL
        compatibility."""
        native = (self._sim.time_unit if self._sim else "") or ""
        n = self.get_n_hydrographs(hyd_type)
        idx = _as_index(index, "hydrograph index", 1, n)
        df = self.hydrograph_df(hyd_type, column=idx - 1,
                                begin_date=begin_date, end_date=end_date)
        if (interval not in (None, "") and str(interval).upper()
                != native.upper() and len(df)):
            # instantaneous quantity: the value at each window end
            # (complete windows only), DLL-anchored windows
            from iwfm_io._budget_agg import window_end_labels
            labels, complete = window_end_labels(df.index, str(interval),
                                                 native or None)
            keep = df[complete]
            df = keep.groupby(np.asarray(labels[complete])).last()
            df.index = pd.DatetimeIndex(df.index)
        vals = df["value"].to_numpy(dtype=float) * float(fact_vl)
        return _excel_serials(df.index), vals

    def _lwu_budget(self):
        key = self._find_budget_key("LWU")
        return self._read_full_budget(key) if key else None

    def supply_demand_df(self, location_type=None, locations=None, factor=1.0):
        """Period-total ag/urban supply requirement and shortage per
        subregion, from the Land & Water Use budget HDF.

        DLL-free equivalent of ``IWFMModel.supply_demand_df``; the DLL
        reports a live-timestep snapshot, this reports totals over the
        simulated period. *location_type* is accepted for interface
        compatibility (locations are the budget's subregions).
        """
        lwu_key = self._find_budget_key("LWU")
        df = self._cache.get("supply_demand")
        if df is not None and df[0] == _file_sig(self._budget_path(lwu_key)):
            df = df[1]
        else:
            bud = self._lwu_budget()
            if bud is None:
                logger.warning(
                    "supply_demand_df: no L&WU budget HDF found — "
                    "returning empty DataFrame")
                return pd.DataFrame(columns=[
                    "location_id", "ag_requirement", "urban_requirement",
                    "ag_shortage", "urban_shortage",
                ])
            import re as _re
            rows = []
            fallback_id = 0
            for loc_name in bud["locations"]:
                if "ENTIRE" in loc_name.upper():
                    continue
                fallback_id += 1
                # HDF locations list alphabetically (SR1, SR10, SR11, …,
                # SR2), so take the id from the name, not the position
                m = _re.search(r"\d+", loc_name)
                loc_id = int(m.group()) if m else fallback_id
                df_loc = bud["data"][loc_name]
                total = df_loc.sum()

                def col_total(*subs, _df=df_loc, _total=total):
                    col = self._find_column(_df, *subs)
                    return float(_total[col]) if col is not None else np.nan

                rows.append({
                    "location_id": loc_id,
                    "ag_requirement": col_total("AG", "SUPPLY REQUIREMENT"),
                    "urban_requirement": col_total("URBAN", "SUPPLY REQUIREMENT"),
                    "ag_shortage": col_total("AG", "SHORTAGE"),
                    "urban_shortage": col_total("URBAN", "SHORTAGE"),
                })
            df = pd.DataFrame(rows).sort_values("location_id").reset_index(drop=True)
            self._cache["supply_demand"] = (
                _file_sig(self._budget_path(lwu_key)), df)
        if locations is not None:
            df = df[df["location_id"].isin([int(x) for x in np.atleast_1d(locations)])]
        if factor != 1.0:
            df = df.copy()
            for c in ("ag_requirement", "urban_requirement",
                      "ag_shortage", "urban_shortage"):
                df[c] = df[c] * factor
        return df.reset_index(drop=True)

    def _supply_column(self, column, locations, factor):
        df = self.supply_demand_df(locations=locations, factor=factor)
        return df[column].to_numpy()

    def get_supply_requirement_ag(self, location_type=None, locations=None, factor=1.0):
        """Period-total ag supply requirement per subregion (see supply_demand_df)."""
        return self._supply_column("ag_requirement", locations, factor)

    def get_supply_requirement_urban(self, location_type=None, locations=None, factor=1.0):
        """Period-total urban supply requirement per subregion."""
        return self._supply_column("urban_requirement", locations, factor)

    def get_supply_short_at_origin_ag(self, supply_type=None, supplies=None, factor=1.0):
        """Period-total ag shortage per subregion. The DLL variant reports
        per-supply (diversion/well) shortages; budgets only resolve to
        subregions, so *supplies* are treated as subregion ids."""
        return self._supply_column("ag_shortage", supplies, factor)

    def get_supply_short_at_origin_urban(self, supply_type=None, supplies=None, factor=1.0):
        """Period-total urban shortage per subregion (see ag variant)."""
        return self._supply_column("urban_shortage", supplies, factor)

    def get_subregion_ag_pumping_avg_depth_to_gw(self):
        """Average depth to groundwater (GSE − layer-1 head, end of run)
        per subregion, computed from the heads output and stratigraphy."""
        hit = self._cache.get("subregion_depth")
        if hit is not None and hit[0] == _file_sig(self._heads_hdf):
            return hit[1]
        heads = self.heads_df(layer=1).iloc[-1].to_numpy()
        strat = self.stratigraphy_df()
        gse_col = (self._find_column(strat, "ELEVATION")
                   or self._find_column(strat, "GSE") or strat.columns[1])
        gse = strat[gse_col].to_numpy()
        depth = gse - heads

        # node -> subregion via the first element that references it
        elems = self.elements_df()
        node_sub = {}
        node_cols = [c for c in ("node1", "node2", "node3", "node4")
                     if c in elems.columns]
        for _, e in elems.iterrows():
            sub = int(e["subregion"])
            for c in node_cols:
                nid = int(e[c])
                if nid > 0 and nid not in node_sub:
                    node_sub[nid] = sub
        node_ids = self.nodes_df()["node_id"].astype(int).values
        subs = sorted(self.subregions_df()["subregion_id"].astype(int)) \
            if "subregion_id" in self.subregions_df().columns else \
            sorted(set(node_sub.values()))
        sums = {s: [0.0, 0] for s in subs}
        for i, nid in enumerate(node_ids):
            s = node_sub.get(int(nid))
            if s in sums and np.isfinite(depth[i]):
                sums[s][0] += depth[i]
                sums[s][1] += 1
        result = np.array([sums[s][0] / sums[s][1] if sums[s][1] else np.nan
                           for s in subs])
        self._cache["subregion_depth"] = (_file_sig(self._heads_hdf), result)
        return result

    # -- Land use (from the budget outputs) -----------------------------

    def get_n_ag_crops(self):
        """Budget-backed land use resolves a single aggregate Ag category."""
        return 1

    def get_land_use_areas(self, begin_date=None, end_date=None,
                           lu_type="AG", lu=1, fact_area=1.0):
        """Land-use area time series per subregion from the RZ/L&WU budget.

        DLL-free equivalent of ``IWFMModel.get_land_use_areas``: returns
        an array of shape ``(n_locations, n_times)``. The DLL variant is
        element-level and per-crop; budgets resolve subregion-level
        aggregate Ag / Urban / Native-Riparian areas (sum over axis 0 for
        the model total, as the plotting code does).
        """
        key = self._find_budget_key("RZ", "ROOTZONE") or self._find_budget_key("LWU")
        if key is None:
            raise RuntimeError("get_land_use_areas: no RootZone or L&WU "
                               "budget HDF found")
        bud = self._read_full_budget(key)
        subs = {
            "AG": ("AG", "AREA"),
            "URBAN": ("URBAN", "AREA"),
            "NATIVERIPARIAN": ("NATIVE", "AREA"),
        }.get(str(lu_type).upper().replace("&", "").replace("_", ""))
        if subs is None:
            raise ValueError(f"Unknown lu_type: {lu_type!r}")
        series = []
        for loc_name in bud["locations"]:
            if "ENTIRE" in loc_name.upper():
                continue
            df = bud["data"][loc_name]
            if begin_date is not None:
                from iwfm_io._tokens import parse_iwfm_date
                df = df[df.index >= parse_iwfm_date(begin_date)]
            if end_date is not None:
                from iwfm_io._tokens import parse_iwfm_date
                df = df[df.index <= parse_iwfm_date(end_date)]
            col = self._find_column(df, *subs)
            series.append(df[col].to_numpy() * fact_area if col is not None
                          else np.zeros(len(df)))
        return np.asarray(series)

    def get_zbudget_timeseries(self, zbudget_type, zone_id, columns,
                               zone_extent=None, elements=None, layers=None,
                               zone_ids=None, begin_date=None, end_date=None,
                               interval="1MON", fact_ar=1.0, fact_vl=1.0):
        """DLL-free zone-budget time series from a Z-Budget HDF file.

        Mirrors ``IWFMModel.get_zbudget_timeseries`` closely enough for
        the plotting functions: zones are the model's subregions (every
        element is assigned to its subregion), *zone_id* is a subregion
        id, and *columns* are 0-based column indices into that zone's
        aggregated DataFrame. Extra DLL-specific arguments
        (*zone_extent*, *elements*, *layers*, *zone_ids*) are accepted
        and ignored.

        Returns ``{"dates": excel_serials, "values": (n_times, n_cols),
        "data_types": names}``.
        """
        # Fuzzy-match the requested type against discovered zbudget HDFs
        key = None
        if zbudget_type in self._zbudget_hdfs:
            key = zbudget_type
        else:
            want = str(zbudget_type).upper().replace("&", "").replace("_", "")
            for k in self._zbudget_hdfs:
                if want in k.upper().replace("&", "").replace("_", ""):
                    key = k
                    break
        if key is None:
            raise RuntimeError(
                f"No zone-budget HDF matching {zbudget_type!r}; available: "
                f"{sorted(self._zbudget_hdfs)}")

        if float(fact_ar) != 1.0:
            raise ValueError("get_zbudget_timeseries: fact_ar is not "
                             "supported by the file-based adapter")
        interval = None if interval in (None, "") else str(interval).upper()
        def build():
            from iwfm_io.models.base import ZoneDefinition
            from iwfm_io.readers.hdf5 import read_zbudget_hdf
            elems = self.elements_df()
            zd = ZoneDefinition(
                extent="horizontal",
                zones={int(s): f"Subregion {int(s)}"
                       for s in sorted(elems["subregion"].unique())},
                element_zones=pd.DataFrame({
                    "element_id": elems["element_id"].astype(int),
                    "zone_id": elems["subregion"].astype(int),
                }),
            )
            return read_zbudget_hdf(self._zbudget_hdfs[key], zone_def=zd,
                                    interval=interval)
        z = self._cached_file(f"_zbudget_subregions::{key}::{interval}",
                              [self._zbudget_hdfs[key]], build)

        df = z["data"][f"Subregion {int(zone_id)}"]
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        cols = list(columns)
        sub = df.iloc[:, cols]
        # Plotting code converts dates with excel_date_to_datetime
        excel = _excel_serials(sub.index)
        return {
            "dates": excel,
            "values": sub.to_numpy() * fact_vl,
            "data_types": list(sub.columns),
        }

    # -- Aquifer parameters (from the GW main file, NGROUP=0) -----------

    def _aquifer_params(self):
        """Per-node aquifer parameters from the GW main's parsed block.

        Only the NGROUP=0 layout (values listed at every node) is
        supported; parametric-grid models (NGROUP>0) require the grid
        interpolation the DLL performs.
        """
        if "aquifer_params" in self._cache:
            return self._cache["aquifer_params"]
        if self._gw_main is None:
            raise RuntimeError(
                "Aquifer parameters need the GW main file — open the model "
                "with open_model() so it is discovered, or check that the "
                "simulation main references it.")
        if self._gw_main.ngroup:
            raise NotImplementedError(
                f"Aquifer parameter block uses a parametric grid "
                f"(NGROUP={self._gw_main.ngroup}); only per-node values "
                "(NGROUP=0) can be read without the DLL.")
        df = self._gw_main.aquifer_params
        if df is None:
            raise RuntimeError(
                "The GW main's aquifer parameter table could not be parsed.")
        f = self._gw_main.param_factors

        n_layers = self.n_layers
        node_ids = self.nodes_df()["node_id"].astype(int).values
        pos = {int(nid): i for i, nid in enumerate(node_ids)}
        shape = (len(node_ids), n_layers)
        params = {name: np.full(shape, np.nan)
                  for name in ("kh", "ss", "sy", "kv_aquitard", "kv")}
        factor_of = {"kh": "fkh", "ss": "fs", "sy": "fn",
                     "kv_aquitard": "fv", "kv": "fl"}
        col_of = {"kv_aquitard": "aquitard_kv"}

        rows = df["node_id"].map(pos).values
        cols = df["layer"].values - 1
        ok = ~pd.isna(rows) & (cols < n_layers)
        for name, arr in params.items():
            values = df[col_of.get(name, name)].values * f.get(
                factor_of[name], 1.0)
            arr[rows[ok].astype(int), cols[ok].astype(int)] = values[ok]

        self._cache["aquifer_params"] = params
        return params

    def get_aquifer_horizontal_k(self):
        """(n_nodes, n_layers) horizontal hydraulic conductivity (PKH·FKH)."""
        return self._aquifer_params()["kh"]

    def get_aquifer_vertical_k(self):
        """(n_nodes, n_layers) aquifer vertical hydraulic conductivity (PL·FL)."""
        return self._aquifer_params()["kv"]

    def get_aquitard_vertical_k(self):
        """(n_nodes, n_layers) aquitard vertical hydraulic conductivity (PV·FV)."""
        return self._aquifer_params()["kv_aquitard"]

    def get_aquifer_specific_yield(self):
        """(n_nodes, n_layers) specific yield (PN·FN)."""
        return self._aquifer_params()["sy"]

    def get_aquifer_specific_storage(self):
        """(n_nodes, n_layers) specific storage (PS·FS)."""
        return self._aquifer_params()["ss"]

    # -- Legacy compatibility (IWFMModel numpy interface) ----------------
    #
    # The plot library was originally written against IWFMModel's numpy
    # getters. These shims return the same shapes/types derived from the
    # parsed files, so every grid/stream/stratigraphy plot function works
    # with file-based models too. Solver-state getters (stream flows,
    # supply/demand, land use) have no file equivalent and are
    # intentionally absent.

    def get_node_ids(self):
        return self.nodes_df()["node_id"].to_numpy(dtype=np.int32)

    def get_node_coordinates(self):
        ndf = self.nodes_df()
        return (ndf["x"].to_numpy(dtype=np.float64),
                ndf["y"].to_numpy(dtype=np.float64))

    def get_element_ids(self):
        return self.elements_df()["element_id"].to_numpy(dtype=np.int32)

    def get_element_config(self, element):
        edf = self.elements_df()
        row = edf[edf["element_id"] == element]
        if row.empty:  # fall back to 1-based positional index
            row = edf.iloc[[element - 1]]
        return row.iloc[0][["node1", "node2", "node3", "node4"]].to_numpy(
            dtype=np.int32)

    def get_element_subregions(self):
        return self.elements_df()["subregion"].to_numpy(dtype=np.int32)

    def get_subregion_ids(self):
        return self.subregions_df()["subregion_id"].to_numpy(dtype=np.int32)

    def get_subregion_name(self, subregion):
        sdf = self.subregions_df()
        row = sdf[sdf["subregion_id"] == subregion]
        return str(row.iloc[0]["name"]) if not row.empty else f"Subregion {subregion}"

    def get_ground_surface_elevation(self):
        _, _, gse, _, _ = self._strat_node_arrays()
        return gse

    def get_aquifer_top_elevation(self):
        """Shape (n_nodes, n_layers), matching IWFMModel."""
        _, _, _, tops, _ = self._strat_node_arrays()
        return tops

    def get_aquifer_bottom_elevation(self):
        _, _, _, _, bots = self._strat_node_arrays()
        return bots

    def get_time_specs(self):
        """Return dict with 'dates' (IWFM strings) and 'interval'."""
        from iwfm_io._tokens import format_iwfm_date
        interval = self._sim.time_unit if self._sim else ""
        if self._heads_hdf is not None:
            df = self.heads_df(layer=1)
            dates = [format_iwfm_date(d) for d in df.index.to_pydatetime()]
        elif self._sim is not None:
            dates = [self._sim.sim_begin, self._sim.sim_end]
        else:
            raise RuntimeError(
                "IOModelAdapter: need heads_hdf or simulation for time specs")
        return {"dates": dates, "interval": interval}

    def get_stream_node_ids(self):
        return self.stream_nodes_df()["stream_node_id"].to_numpy(dtype=np.int32)

    def get_reach_ids(self):
        return self.reaches_df()["reach_id"].to_numpy(dtype=np.int32)

    def get_reach_stream_nodes(self, reach):
        sdf = self.stream_nodes_df()
        return sdf[sdf["reach_id"] == reach]["stream_node_id"].to_numpy(
            dtype=np.int32)

    def get_reach_gw_nodes(self, reach):
        sdf = self.stream_nodes_df()
        return sdf[sdf["reach_id"] == reach]["gw_node_id"].to_numpy(
            dtype=np.int32)

    def get_stream_bottom_elevations(self):
        rt = self.stream_rating_tables_df()
        elevs = rt.groupby("stream_node_id", sort=True)["bottom_elev"].first()
        order = self.stream_nodes_df()["stream_node_id"]
        return elevs.reindex(order).to_numpy(dtype=np.float64)

    def get_stream_rating_table(self, stream_node):
        rt = self.stream_rating_tables_df()
        rows = rt[rt["stream_node_id"] == stream_node]
        return (rows["stage"].to_numpy(dtype=np.float64),
                rows["flow"].to_numpy(dtype=np.float64))

    def get_lake_ids(self):
        return self.lakes_df()["lake_id"].to_numpy(dtype=np.int32)

    def get_elements_in_lake(self, lake):
        ldf = self.lakes_df()
        row = ldf[ldf["lake_id"] == lake]
        return np.asarray(row.iloc[0]["elements"], dtype=np.int32)
