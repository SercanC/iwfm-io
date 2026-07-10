"""IOModelAdapter — wraps IO reader data to present the same DataFrame
interface as IWFMModel._df() methods.

Usage::

    from iwfm_io import read_preprocessor, read_simulation
    from iwfm_io.model_adapter import IOModelAdapter

    pp = read_preprocessor("Preprocessor/PreProcessor_MAIN.IN")
    adapter = IOModelAdapter(preprocessor=pp)
    adapter.nodes_df()      # same GeoDataFrame as IWFMModel.nodes_df()
    adapter.elements_df()   # same GeoDataFrame as IWFMModel.elements_df()
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import geopandas as gpd
    from shapely.geometry import Point
    _HAS_GEO = True
except ImportError:
    _HAS_GEO = False


class IOModelAdapter:
    """Adapter presenting IO-reader data through the same ``_df()`` API
    as :class:`~iwfm_io.dll.model.IWFMModel`.

    Parameters
    ----------
    preprocessor : PreprocessorMain, optional
        Result of ``read_preprocessor()``.  Provides grid geometry,
        stratigraphy, stream network, and lake data.
    simulation : SimulationMain, optional
        Result of ``read_simulation()``.  Provides stream/GW file paths
        for follow-on loading.
    heads_hdf : str or Path, optional
        Path to ``GWHeadAll.hdf``.
    budget_hdfs : dict[str, str or Path], optional
        Mapping of budget name → HDF5 path (e.g. ``{"GW": "GW.hdf"}``).
    hydrograph_hdfs : dict[str, str or Path], optional
        Mapping of hydrograph name → HDF5 path.
    stream_main : StreamMain, optional
        Result of ``read_stream_main()``.
    bypass_specs : BypassSpecsFile, optional
        Result of ``read_bypass_specs()``.
    tile_drain : TileDrainFile, optional
        Result of ``read_tile_drain()``.
    """

    def __init__(
        self,
        preprocessor=None,
        simulation=None,
        heads_hdf=None,
        budget_hdfs=None,
        hydrograph_hdfs=None,
        stream_main=None,
        bypass_specs=None,
        tile_drain=None,
        zbudget_hdfs=None,
        gw_main=None,
        well_spec=None,
        diver_specs=None,
    ):
        self._pp = preprocessor
        self._sim = simulation
        self._heads_hdf = heads_hdf
        self._budget_hdfs = budget_hdfs or {}
        self._hydrograph_hdfs = hydrograph_hdfs or {}
        self._stream_main = stream_main
        self._bypass_specs = bypass_specs
        self._tile_drain_file = tile_drain
        self._zbudget_hdfs = zbudget_hdfs or {}
        self._gw_main = gw_main
        self._well_spec = well_spec
        self._diver_specs = diver_specs
        self._root = None  # set by open_model()
        self._cache: dict[str, Any] = {}

    # -- helpers --------------------------------------------------------

    def _child(self, key):
        """Get a child object from the preprocessor."""
        if self._pp is None:
            raise RuntimeError(
                f"IOModelAdapter: preprocessor data required for '{key}'")
        return self._pp.children.get(key)

    # -- Grid geometry -------------------------------------------------

    def nodes_df(self):
        """Return GeoDataFrame: node_id, x, y, geometry(Point)."""
        if "nodes" in self._cache:
            return self._cache["nodes"]
        node_file = self._child("node")
        if node_file is None:
            raise RuntimeError("No node file loaded in preprocessor")
        df = node_file.data.copy()
        self._cache["nodes"] = df
        return df

    def elements_df(self):
        """Return GeoDataFrame: element_id, node1-4, subregion, geometry(Polygon)."""
        if "elements" in self._cache:
            return self._cache["elements"]
        elem_file = self._child("element")
        if elem_file is None:
            raise RuntimeError("No element file loaded in preprocessor")
        df = elem_file.data.copy()
        self._cache["elements"] = df
        return df

    def subregions_df(self):
        """Return DataFrame: subregion_id, name."""
        if "subregions" in self._cache:
            return self._cache["subregions"]
        elem_file = self._child("element")
        if elem_file is None:
            raise RuntimeError("No element file loaded in preprocessor")
        df = elem_file.subregions.copy()
        self._cache["subregions"] = df
        return df

    def stratigraphy_df(self):
        """Return DataFrame: node_id, elevation, aquitard_1, aquifer_1, ..."""
        if "strata" in self._cache:
            return self._cache["strata"]
        strata_file = self._child("strata")
        if strata_file is None:
            raise RuntimeError("No stratigraphy file loaded in preprocessor")
        df = strata_file.data.copy()
        self._cache["strata"] = df
        return df

    # -- Stream network ------------------------------------------------

    def reaches_df(self):
        """Return DataFrame: reach_id, n_nodes, outflow_dest, name."""
        if "reaches" in self._cache:
            return self._cache["reaches"]
        stream_file = self._child("stream")
        if stream_file is None:
            raise RuntimeError("No stream file loaded in preprocessor")
        df = stream_file.reaches.copy()
        self._cache["reaches"] = df
        return df

    def stream_nodes_df(self):
        """Return GeoDataFrame: stream_node_id, reach_id, gw_node_id, geometry(Point)."""
        if "stream_nodes" in self._cache:
            return self._cache["stream_nodes"]
        stream_file = self._child("stream")
        if stream_file is None:
            raise RuntimeError("No stream file loaded in preprocessor")
        df = stream_file.nodes.copy()
        self._cache["stream_nodes"] = df
        return df

    def stream_rating_tables_df(self):
        """Return DataFrame: stream_node_id, bottom_elev, stage, flow."""
        if "rating_tables" in self._cache:
            return self._cache["rating_tables"]
        stream_file = self._child("stream")
        if stream_file is None:
            raise RuntimeError("No stream file loaded in preprocessor")
        df = stream_file.rating_tables.copy()
        self._cache["rating_tables"] = df
        return df

    # -- Lakes ---------------------------------------------------------

    def lakes_df(self):
        """Return DataFrame: lake_id, n_elements, elements(list)."""
        if "lakes" in self._cache:
            return self._cache["lakes"]
        lake_file = self._child("lake")
        if lake_file is None:
            df = pd.DataFrame(columns=["lake_id", "n_elements", "elements"])
        else:
            df = lake_file.data.copy()
        self._cache["lakes"] = df
        return df

    # -- Bypasses ------------------------------------------------------

    def bypasses_df(self):
        """Return DataFrame: bypass_id, export_node, dest_type, dest, rec_loss, nonrec_loss."""
        if "bypasses" in self._cache:
            return self._cache["bypasses"]
        if self._bypass_specs is None or self._bypass_specs.bypass_data is None:
            df = pd.DataFrame(columns=[
                "bypass_id", "export_node", "dest_type", "dest",
                "rec_loss", "nonrec_loss"])
            self._cache["bypasses"] = df
            return df
        bd = self._bypass_specs.bypass_data
        df = pd.DataFrame({
            "bypass_id": bd["bypass_id"],
            "export_node": bd["stream_node"],
            "dest_type": bd["dest_type"],
            "dest": bd["dest"],
            "rec_loss": bd["divrl"],
            "nonrec_loss": bd["divnl"],
        })
        self._cache["bypasses"] = df
        return df

    # -- Tile drains ---------------------------------------------------

    def tile_drains_df(self):
        """Return GeoDataFrame: id, node, x, y, geometry(Point)."""
        if "tile_drains" in self._cache:
            return self._cache["tile_drains"]
        if self._tile_drain_file is None:
            df = pd.DataFrame(columns=["id", "node", "x", "y"])
            self._cache["tile_drains"] = df
            return df
        td = self._tile_drain_file.data
        ndf = self.nodes_df()
        coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
        rows = []
        for _, row in td.iterrows():
            nid = int(row["node"])
            xy = coord.get(nid, (np.nan, np.nan))
            rows.append({"id": int(row["id"]), "node": nid, "x": xy[0], "y": xy[1]})
        df = pd.DataFrame(rows)
        if _HAS_GEO and len(df) > 0:
            geom = [Point(r["x"], r["y"]) if not np.isnan(r["x"]) else None
                    for _, r in df.iterrows()]
            df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["tile_drains"] = df
        return df

    # -- Wells (placeholder — requires pump file parsing) ---------------

    def wells_df(self):
        """Return GeoDataFrame: well_id, x, y, radius, perf_top, perf_bot,
        name, geometry(Point).

        From the well specification file referenced by the pumping main
        (discovered by ``open_model``). Coordinates are file-native, the
        same system the node file uses. Empty when the model has no well
        file (e.g. the sample model pumps by element only).
        """
        if "wells" in self._cache:
            return self._cache["wells"]
        if self._well_spec is None or self._well_spec.data is None:
            df = pd.DataFrame(columns=[
                "well_id", "x", "y", "radius", "perf_top", "perf_bot", "name"])
        else:
            df = self._well_spec.data.copy()
            if _HAS_GEO and len(df) > 0:
                geom = [Point(x, y) for x, y in zip(df["x"], df["y"])]
                df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["wells"] = df
        return df

    # -- Diversions ------------------------------------------------------

    def diversions_df(self):
        """Return DataFrame: diversion_id, export_node, dest_type,
        dest_id, name, elements, recharge_elements.

        From the diversion specification file. ``export_node`` is the
        diverting stream node (0 = import from outside the model).
        ``elements`` are the delivery destination resolved to element
        ids from TYPDSTDL/DSTDL: element group (type 6) → the group's
        elements, subregion (type 4) → the subregion's elements,
        single element (type 2) → that element, outside (type 0) →
        empty. ``recharge_elements`` are the recharge zone
        (recoverable-loss area) elements; zone ids match diversion ids.
        """
        if "diversions" in self._cache:
            return self._cache["diversions"]
        cols = ["diversion_id", "export_node", "max_col", "max_frac",
                "recov_loss_col", "recov_loss_frac", "nonrecov_loss_col",
                "nonrecov_loss_frac", "spill_col", "spill_frac",
                "dest_type", "dest_id", "delivery_col", "delivery_frac",
                "irig_frac_col", "adjust_col",
                "name", "elements", "recharge_elements"]
        if self._diver_specs is None or self._diver_specs.data is None:
            df = pd.DataFrame(columns=cols)
        else:
            df = self._diver_specs.data.copy()
            dg = {g["group_id"]: g["elements"]
                  for g in self._diver_specs.delivery_groups}
            elems = self.elements_df()
            sub_elems = {
                int(s): elems.loc[elems["subregion"] == s,
                                  "element_id"].astype(int).tolist()
                for s in elems["subregion"].unique()
            }

            def _dest_elements(row):
                t, d = int(row["dest_type"]), int(row["dest_id"])
                if t == 6:
                    return dg.get(d, [])
                if t == 4:
                    return sub_elems.get(d, [])
                if t == 2:
                    return [d]
                return []  # 0 = outside the model

            df["elements"] = df.apply(_dest_elements, axis=1)
            rz = {g["group_id"]: g["elements"]
                  for g in self._diver_specs.recharge_zones}
            df["recharge_elements"] = [rz.get(int(i), [])
                                       for i in df["diversion_id"]]
        self._cache["diversions"] = df
        return df

    # -- Time-series results -------------------------------------------

    def heads_df(self, layer, begin_date=None, end_date=None):
        """Return DataFrame(DatetimeIndex) with one column per node.

        Reads from ``GWHeadAll.hdf`` when available, otherwise from the
        text equivalent ``GWHeadAll.out`` (what a fresh simulation run
        writes) — both are layer-major with identical column ordering.
        """
        if self._heads_hdf is None:
            raise RuntimeError("IOModelAdapter: heads_hdf path required")
        ndf = self.nodes_df()
        n_nodes = len(ndf)
        strata = self._child("strata")
        n_layers = strata.n_layers if strata else 1

        if Path(self._heads_hdf).suffix.lower() == ".out":
            result = self._heads_from_text(layer, n_nodes, n_layers)
        else:
            from iwfm_io.readers.hdf5 import read_head_hdf
            head_df = read_head_hdf(
                self._heads_hdf, n_nodes=n_nodes, n_layers=n_layers)
            # Filter columns for requested layer: node_N_layer_M pattern
            layer_cols = [c for c in head_df.columns
                          if c.endswith(f"_layer_{layer}")]
            result = head_df[layer_cols].copy()
            # Rename to node_N for consistency with IWFMModel.heads_df()
            result.columns = [c.replace(f"_layer_{layer}", "")
                              for c in layer_cols]
        # Filter by date range if specified
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            result = result[result.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            result = result[result.index <= parse_iwfm_date(end_date)]
        return result

    def _strat_node_arrays(self):
        """Per-node x, y, GSE, and layer top/bottom elevations (cached)."""
        if "strat_node_arrays" in self._cache:
            return self._cache["strat_node_arrays"]
        strata = self._child("strata")
        if strata is None:
            raise RuntimeError("No stratigraphy file loaded in preprocessor")
        ndf = self.nodes_df()[["node_id", "x", "y"]]
        df = ndf.merge(strata.data, on="node_id", how="inner")
        nl = strata.n_layers
        gse = df["elevation"].to_numpy(dtype=float)
        tops = np.zeros((len(df), nl))
        bots = np.zeros((len(df), nl))
        elev = gse.copy()
        for k in range(1, nl + 1):
            elev = elev - df[f"aquitard_{k}"].to_numpy(dtype=float)
            tops[:, k - 1] = elev
            elev = elev - df[f"aquifer_{k}"].to_numpy(dtype=float)
            bots[:, k - 1] = elev
        arrays = (
            df["x"].to_numpy(dtype=float),
            df["y"].to_numpy(dtype=float),
            gse, tops, bots,
        )
        self._cache["strat_node_arrays"] = arrays
        return arrays

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

    def _heads_from_text(self, layer, n_nodes, n_layers):
        """Heads for one layer from a GWHeadAll.out text file."""
        full = self._cache.get("heads_text")
        if full is None:
            from iwfm_io._tokens import parse_iwfm_date
            from iwfm_io.readers.text_output import read_head_all_out
            raw = read_head_all_out(self._heads_hdf)
            idx = pd.DatetimeIndex(
                [parse_iwfm_date(d) for d in raw["date"]], name="datetime")
            full = raw.drop(columns="date")
            full.index = idx
            self._cache["heads_text"] = full
        if full.shape[1] != n_nodes * n_layers:
            raise ValueError(
                f"{self._heads_hdf}: {full.shape[1]} head columns but the "
                f"grid has {n_nodes} nodes x {n_layers} layers")
        start = (layer - 1) * n_nodes
        result = full.iloc[:, start:start + n_nodes].copy()
        result.columns = [f"node_{n}" for n in range(1, n_nodes + 1)]
        return result

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

    def budget_df(self, budget_name, location, begin_date=None, end_date=None,
                  interval=None, columns=None, **kwargs):
        """Return DataFrame(DatetimeIndex) of budget time series.

        Parameters
        ----------
        budget_name : str
            Key in ``budget_hdfs`` dict (e.g. ``"GW"``).
        location : int or str
            1-based location index or location name.
        """
        if budget_name not in self._budget_hdfs:
            raise RuntimeError(
                f"IOModelAdapter: no budget HDF for '{budget_name}'")
        from iwfm_io.readers.hdf5 import read_budget_hdf
        bud = read_budget_hdf(self._budget_hdfs[budget_name], interval=interval)
        locs = bud["locations"]
        if isinstance(location, int):
            if location < 1 or location > len(locs):
                raise IndexError(f"Location {location} out of range [1, {len(locs)}]")
            loc_name = locs[location - 1]
        else:
            loc_name = location
        df = bud["data"][loc_name]
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        if columns is not None:
            df = df.iloc[:, [c - 1 for c in columns]]
        return df

    def hydrograph_df(self, hdf_name, column=None, begin_date=None,
                      end_date=None, **kwargs):
        """Return DataFrame(DatetimeIndex) from a hydrograph HDF5.

        Parameters
        ----------
        hdf_name : str
            Key in ``hydrograph_hdfs`` dict.
        column : int, optional
            0-based column to extract as 'value'.  None returns all columns.
        """
        if hdf_name not in self._hydrograph_hdfs:
            raise RuntimeError(
                f"IOModelAdapter: no hydrograph HDF for '{hdf_name}'")
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf
        df = read_hydrograph_hdf(self._hydrograph_hdfs[hdf_name])
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        if column is not None:
            col_name = df.columns[column]
            df = pd.DataFrame({"value": df[col_name]}, index=df.index)
        return df

    # -- Budget-backed state (DLL-free) ---------------------------------

    def _read_full_budget(self, key):
        """Read (and cache) a whole budget HDF: {locations, data, ...}."""
        cache_key = f"_budget_full::{key}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        from iwfm_io.readers.hdf5 import read_budget_hdf
        bud = read_budget_hdf(self._budget_hdfs[key])
        self._cache[cache_key] = bud
        return bud

    def _find_budget_key(self, *tokens):
        """Find a budget key whose normalized name contains any token."""
        for key in self._budget_hdfs:
            norm = key.upper().replace("&", "").replace("_", "").replace("-", "")
            if any(t in norm for t in tokens):
                return key
        return None

    @staticmethod
    def _find_column(df, *substrings):
        """First column whose upper-cased name contains all substrings."""
        for col in df.columns:
            u = col.upper()
            if all(s in u for s in substrings):
                return col
        return None

    def stream_flows_df(self, factor=1.0, stat="mean"):
        """Per-stream-node flow components from the stream node budget HDF.

        DLL-free equivalent of ``IWFMModel.stream_flows_df``. The DLL
        returns a live-timestep snapshot; this reads the stream *node
        budget* output (all simulated timesteps) and aggregates with
        *stat* (``"mean"`` over the run, or ``"last"`` timestep). Nodes
        without budget output get 0.0. Returns an empty DataFrame when
        the model has no stream node budget HDF.
        """
        cache_key = f"stream_flows::{factor}::{stat}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        columns = [
            "stream_node_id", "flow", "stage", "gain_from_gw",
            "gain_from_lakes", "tributary_inflows", "return_flows",
            "tile_drains", "rainfall_runoff", "riparian_et", "evaporation",
        ]
        key = self._find_budget_key("NODEBUD", "NODEBUDGET")
        if key is None:
            logger.warning(
                "stream_flows_df: no stream node budget HDF found — "
                "returning empty DataFrame")
            return pd.DataFrame(columns=columns)
        bud = self._read_full_budget(key)

        sn_ids = self.stream_nodes_df()["stream_node_id"].astype(int).values
        out = {c: np.zeros(len(sn_ids)) for c in columns[1:]}
        col_map = {
            "gain_from_gw": ("GAIN", "GW"),
            "flow": ("DOWNSTREAM", "OUTFLOW"),
            "tributary_inflows": ("TRIBUTARY",),
            "return_flows": ("RETURN",),
            "tile_drains": ("TILE",),
            "rainfall_runoff": ("RUNOFF",),
            "riparian_et": ("RIPARIAN",),
            "evaporation": ("EVAPORATION",),
        }
        pos = {int(sid): i for i, sid in enumerate(sn_ids)}
        for loc_name in bud["locations"]:
            digits = "".join(ch for ch in loc_name if ch.isdigit())
            if not digits or int(digits) not in pos:
                continue
            i = pos[int(digits)]
            df = bud["data"][loc_name]
            row = df.mean() if stat == "mean" else df.iloc[-1]
            for out_col, subs in col_map.items():
                src = self._find_column(df, *subs)
                if src is not None:
                    out[out_col][i] = float(row[src]) * factor
        result = pd.DataFrame({"stream_node_id": sn_ids, **out})
        self._cache[cache_key] = result
        return result

    def subsidence_df(self, factor=1.0):
        """Not available from IO readers without live DLL snapshot.

        Per-node cumulative subsidence exists only as DLL state or at
        hydrograph observation points (``read_hydrograph_out`` on the
        subsidence ``.out`` file).
        """
        return pd.DataFrame(columns=["node_id"])

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
        if "supply_demand" in self._cache:
            df = self._cache["supply_demand"]
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
            self._cache["supply_demand"] = df
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
        if "subregion_depth" in self._cache:
            return self._cache["subregion_depth"]
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
        self._cache["subregion_depth"] = result
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

        cache_key = f"_zbudget_subregions::{key}"
        if cache_key in self._cache:
            z = self._cache[cache_key]
        else:
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
            z = read_zbudget_hdf(self._zbudget_hdfs[key], zone_def=zd)
            self._cache[cache_key] = z

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
        excel = (sub.index - pd.Timestamp("1899-12-30")).days.to_numpy(float)
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

    # -- Convenience properties matching IWFMModel ---------------------

    @property
    def n_nodes(self):
        return len(self.nodes_df())

    @property
    def n_elements(self):
        return len(self.elements_df())

    @property
    def n_layers(self):
        strata = self._child("strata")
        return strata.n_layers if strata else 1

    @property
    def n_subregions(self):
        return len(self.subregions_df())

    @property
    def n_reaches(self):
        return len(self.reaches_df())

    @property
    def n_stream_nodes(self):
        return len(self.stream_nodes_df())

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

    @property
    def n_lakes(self):
        return len(self.lakes_df())

    @property
    def n_diversions(self):
        return len(self.diversions_df())

    @property
    def n_wells(self):
        return len(self.wells_df())

    # -- Model overview -------------------------------------------------

    def describe(self):
        """Return a JSON-serializable summary of the model.

        One call that answers "what is this model and what data can I ask
        it for?" — useful to orient yourself (``print(json.dumps(d,
        indent=2))``) or for an AI agent deciding what to query next.
        Sections that cannot be derived from the loaded files are None.

        Returns
        -------
        dict
            Keys: ``source``, ``model_root``, ``grid``, ``streams``,
            ``lakes``, ``simulation``, ``results``.
        """

        def _try(fn):
            try:
                return fn()
            except Exception:
                return None

        info = {
            "source": "iwfm_io file readers (no DLL)",
            "model_root": str(self._root) if self._root else None,
        }
        info["grid"] = _try(lambda: {
            "n_nodes": int(self.n_nodes),
            "n_elements": int(self.n_elements),
            "n_layers": int(self.n_layers),
            "n_subregions": int(self.n_subregions),
            "subregion_names": {
                int(r.subregion_id): str(r.name)
                for r in self.subregions_df().itertuples()
            },
        })
        info["streams"] = _try(lambda: {
            "n_reaches": int(self.n_reaches),
            "n_stream_nodes": int(self.n_stream_nodes),
        })
        info["lakes"] = _try(lambda: {"n_lakes": int(len(self.lakes_df()))})
        if self._sim is not None:
            info["simulation"] = {
                "begins": self._sim.sim_begin,
                "ends": self._sim.sim_end,
                "timestep": self._sim.time_unit,
            }
        else:
            info["simulation"] = None
        info["results"] = {
            "heads": str(self._heads_hdf) if self._heads_hdf else None,
            "budgets": {
                name: {
                    "path": str(path),
                    "locations": _try(lambda p=path: _hdf_dataset_names(p)),
                }
                for name, path in self._budget_hdfs.items()
            },
            "hydrographs": {
                name: str(path)
                for name, path in self._hydrograph_hdfs.items()
            },
            "zbudgets": {
                name: str(path)
                for name, path in self._zbudget_hdfs.items()
            },
        }
        return info

    def __repr__(self):
        parts = []
        try:
            parts.append(f"{self.n_nodes} nodes")
            parts.append(f"{self.n_elements} elements")
            parts.append(f"{self.n_layers} layers")
        except Exception:
            parts.append("no grid loaded")
        if self._budget_hdfs:
            parts.append(f"{len(self._budget_hdfs)} budgets")
        if self._heads_hdf:
            parts.append("heads")
        return f"<IOModelAdapter: {', '.join(parts)}>"


# ----------------------------------------------------------------------
# open_model() — one-call model opening with file discovery
# ----------------------------------------------------------------------

_MAIN_SUFFIXES = (".in", ".dat")


def _hdf_dataset_names(path):
    """List top-level dataset names in an HDF5 file (cheap — no data read)."""
    import h5py
    with h5py.File(path, "r") as f:
        return [k for k in f.keys() if k != "Attributes"]


def _find_main_file(root, subdir, patterns):
    """Find a main input file under *root* or *root/subdir*.

    Looks for files with a ``.in``/``.dat`` suffix whose name contains one
    of *patterns* (case-insensitive), preferring names that contain "main".
    """
    search_dirs = [root / subdir, root]
    candidates = []
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            name = f.name.lower()
            if (f.is_file() and f.suffix.lower() in _MAIN_SUFFIXES
                    and any(p in name for p in patterns)):
                candidates.append(f)
        if candidates:
            break
    preferred = [f for f in candidates if "main" in f.name.lower()]
    return (preferred or candidates)[0] if candidates else None


def _sniff_simulation_main(path, max_lines=500):
    """Return True if *path* looks like a simulation main file.

    The simulation main is the only input file with a keyed ``/ BDT``
    line (simulation begin date). Only the first *max_lines* lines are
    scanned so large data files are cheap to reject.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    return False
                if line[:1] in ("C", "c", "*", "/") or not line.strip():
                    continue
                if re.search(r"/\s*BDT\b", line):
                    return True
    except OSError:
        return False
    return False


def _find_simulation_main(root):
    """Find the simulation main file under *root*.

    Tries name patterns first, then falls back to sniffing file contents —
    real-world models often use names the patterns miss (e.g. C2VSimFG's
    ``C2VSimFG.in``).
    """
    found = _find_main_file(root, "Simulation", ("simulation", "sim_"))
    if found is not None:
        return found
    for d in (root / "Simulation", root):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir(), key=lambda p: (p.suffix.lower() != ".in", p.name)):
            if (f.is_file() and f.suffix.lower() in _MAIN_SUFFIXES
                    and _sniff_simulation_main(f)):
                return f
    return None


def _classify_hdf(path, n_head_columns=None):
    """Classify a results HDF5 file by its internal structure.

    Returns one of ``"budget"``, ``"hydrograph"``, ``"heads"``,
    ``"zbudget"``, or None if the file cannot be read.
    """
    import h5py
    try:
        with h5py.File(path, "r") as f:
            keys = [k for k in f.keys() if k != "Attributes"]
            if not keys:
                return None
            if any(isinstance(f[k], h5py.Group) for k in keys):
                return "zbudget"
            attrs = f["Attributes"].attrs if "Attributes" in f else {}
            if any("DataColumnTypes" in k for k in attrs):
                return "budget"
            if len(keys) > 1:
                return "budget"
            n_cols = f[keys[0]].shape[1] if f[keys[0]].ndim == 2 else None
            if n_head_columns and n_cols == n_head_columns:
                return "heads"
            if "headall" in path.stem.lower():
                return "heads"
            return "hydrograph"
    except Exception as exc:
        logger.warning("Could not classify %s: %s", path.name, exc)
        return None


def open_model(path, preprocessor=None, simulation=None, results_dir=None):
    """Open an IWFM model from its folder — the simplest way to read a model.

    No DLL required; works on any operating system. Point it at the model's
    root folder and it finds the preprocessor and simulation main files and
    all HDF5 result files automatically::

        from iwfm_io import open_model

        model = open_model("path/to/my_model")
        print(model.describe())          # what does this model contain?
        model.nodes_df()                 # grid nodes as a GeoDataFrame
        model.heads_df(layer=1)          # simulated heads, one column per node
        model.budget_df("GW", location=1)  # groundwater budget time series

    Parameters
    ----------
    path : str or Path
        The model root folder (the one containing ``Preprocessor/``,
        ``Simulation/`` and ``Results/``), or a direct path to the
        preprocessor or simulation main file.
    preprocessor : str or Path, optional
        Explicit path to the preprocessor main file. Overrides discovery.
    simulation : str or Path, optional
        Explicit path to the simulation main file. Overrides discovery.
    results_dir : str or Path, optional
        Explicit results folder. Overrides discovery (default:
        ``<root>/Results``).

    Returns
    -------
    IOModelAdapter
        Ready to use. Call :meth:`~IOModelAdapter.describe` to see what
        was found.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist, or no preprocessor main file can be
        located (the grid geometry is required for everything else).
    """
    from iwfm_io.readers.preprocessor import read_preprocessor_main
    from iwfm_io.readers.simulation import read_simulation_main

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model path does not exist: {path}")

    # Resolve the model root folder
    if path.is_dir():
        root = path
    else:
        # A main file was passed directly — classify it and derive the root
        name = path.name.lower()
        if "preproc" in name and preprocessor is None:
            preprocessor = path
        elif simulation is None:
            simulation = path
        root = path.parent.parent if path.parent.parent.is_dir() else path.parent

    # Discover main files
    if preprocessor is None:
        preprocessor = _find_main_file(root, "Preprocessor", ("preproc",))
    if simulation is None:
        simulation = _find_simulation_main(root)
    if preprocessor is None:
        raise FileNotFoundError(
            f"No preprocessor main file found under {root}.\n"
            "Expected e.g. Preprocessor/PreProcessor_MAIN.IN. Pass the path "
            "explicitly: open_model(root, preprocessor='path/to/main.IN')"
        )

    pp = read_preprocessor_main(preprocessor, follow_references=True)

    sim = None
    if simulation is not None:
        try:
            sim = read_simulation_main(simulation)
        except Exception as exc:
            logger.warning(
                "Could not parse simulation main file %s: %s", simulation, exc)

    # Follow the GW and stream mains for component data that the adapter
    # can serve DLL-free (tile drains, bypasses, aquifer parameters).
    gw_main = None
    stream_main = None
    tile_drain = None
    bypass_specs = None
    well_spec = None
    diver_specs = None
    if sim is not None:
        gw_path = sim.file_paths.get("gw_main")
        if gw_path and Path(gw_path).is_file():
            try:
                from iwfm_io.readers.groundwater import (
                    read_gw_main, read_pump_main, read_tile_drain, read_well_spec)
                gw_main = read_gw_main(gw_path)
                td_path = gw_main.file_paths.get("tile_drain")
                if td_path and Path(td_path).is_file():
                    tile_drain = read_tile_drain(td_path)
                pump_path = gw_main.file_paths.get("pump_main")
                if pump_path and Path(pump_path).is_file():
                    well_path = read_pump_main(pump_path).file_paths.get("well")
                    if well_path and Path(well_path).is_file():
                        well_spec = read_well_spec(well_path)
            except Exception as exc:
                logger.warning("Could not parse GW main/children: %s", exc)
        st_path = sim.file_paths.get("stream_main")
        if st_path and Path(st_path).is_file():
            try:
                from iwfm_io.readers.stream import (
                    read_bypass_specs, read_diver_specs, read_stream_main)
                stream_main = read_stream_main(st_path)
                bp_path = stream_main.file_paths.get("bypass_specs")
                if bp_path and Path(bp_path).is_file():
                    bypass_specs = read_bypass_specs(bp_path)
                dv_path = stream_main.file_paths.get("diver_specs")
                if dv_path and Path(dv_path).is_file():
                    diver_specs = read_diver_specs(dv_path)
            except Exception as exc:
                logger.warning("Could not parse stream main/children: %s", exc)

    # Discover and classify result HDF5 files
    if results_dir is None:
        results_dir = root / "Results"
    else:
        results_dir = Path(results_dir)

    heads_hdf = None
    budget_hdfs = {}
    hydrograph_hdfs = {}
    zbudget_hdfs = {}
    if results_dir.is_dir():
        n_head_columns = None
        try:
            n_nodes = len(pp.nodes)
            n_head_columns = n_nodes * pp.n_layers
        except Exception:
            pass
        for f in sorted(results_dir.glob("*.hdf")):
            kind = _classify_hdf(f, n_head_columns)
            if kind == "heads":
                heads_hdf = f
            elif kind == "budget":
                budget_hdfs[f.stem] = f
            elif kind == "hydrograph":
                hydrograph_hdfs[f.stem] = f
            elif kind == "zbudget":
                zbudget_hdfs[f.stem] = f
        if heads_hdf is None:
            # A fresh simulation run writes text heads (GWHeadAll.out);
            # the HDF equivalent only exists once the DLL has opened the
            # model in inquiry mode. Fall back to the text file.
            for f in sorted(results_dir.glob("*.out")):
                if "headall" in f.stem.lower():
                    heads_hdf = f
                    break

    adapter = IOModelAdapter(
        preprocessor=pp,
        simulation=sim,
        heads_hdf=heads_hdf,
        budget_hdfs=budget_hdfs,
        hydrograph_hdfs=hydrograph_hdfs,
        stream_main=stream_main,
        bypass_specs=bypass_specs,
        tile_drain=tile_drain,
        zbudget_hdfs=zbudget_hdfs,
        gw_main=gw_main,
        well_spec=well_spec,
        diver_specs=diver_specs,
    )
    adapter._root = root
    return adapter
