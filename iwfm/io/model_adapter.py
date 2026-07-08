"""IOModelAdapter — wraps IO reader data to present the same DataFrame
interface as IWFMModel._df() methods.

Usage::

    from iwfm.io import read_preprocessor, read_simulation
    from iwfm.io.model_adapter import IOModelAdapter

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
    as :class:`~iwfm.model.IWFMModel`.

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
        """Return GeoDataFrame: well_id, x, y, perf_top, perf_bot, geometry(Point)."""
        if "wells" in self._cache:
            return self._cache["wells"]
        # IO layer doesn't currently parse individual well specs
        df = pd.DataFrame(columns=["well_id", "x", "y", "perf_top", "perf_bot"])
        self._cache["wells"] = df
        return df

    # -- Diversions (placeholder — DiverSpecs is raw) -------------------

    def diversions_df(self):
        """Return DataFrame: diversion_id, export_node, n_elements, elements(list)."""
        if "diversions" in self._cache:
            return self._cache["diversions"]
        df = pd.DataFrame(
            columns=["diversion_id", "export_node", "n_elements", "elements"])
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
            from iwfm.io.readers.hdf5 import read_head_hdf
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
            from iwfm.io._tokens import parse_iwfm_date
            result = result[result.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm.io._tokens import parse_iwfm_date
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
            from iwfm.io._tokens import parse_iwfm_date
            from iwfm.io.readers.text_output import read_head_all_out
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
        from iwfm.io.readers.hdf5 import read_budget_hdf
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
            from iwfm.io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm.io._tokens import parse_iwfm_date
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
        from iwfm.io.readers.hdf5 import read_hydrograph_hdf
        df = read_hydrograph_hdf(self._hydrograph_hdfs[hdf_name])
        if begin_date is not None:
            from iwfm.io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm.io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        if column is not None:
            col_name = df.columns[column]
            df = pd.DataFrame({"value": df[col_name]}, index=df.index)
        return df

    def stream_flows_df(self, factor=1.0):
        """Not available from IO readers (requires live DLL).

        Returns an empty DataFrame with the expected columns.
        """
        return pd.DataFrame(columns=[
            "stream_node_id", "flow", "stage", "gain_from_gw",
            "gain_from_lakes", "tributary_inflows", "return_flows",
            "tile_drains", "rainfall_runoff", "riparian_et", "evaporation",
        ])

    def subsidence_df(self, factor=1.0):
        """Not available from IO readers without live DLL snapshot."""
        return pd.DataFrame(columns=["node_id"])

    def supply_demand_df(self, location_type=None, locations=None, factor=1.0):
        """Not available from IO readers (requires live DLL)."""
        return pd.DataFrame(columns=[
            "location_id", "ag_requirement", "urban_requirement",
            "ag_shortage", "urban_shortage",
        ])

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
        from iwfm.io._tokens import format_iwfm_date
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
            "source": "iwfm.io file readers (no DLL)",
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

        from iwfm.io import open_model

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
    from iwfm.io.readers.preprocessor import read_preprocessor_main
    from iwfm.io.readers.simulation import read_simulation_main

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
        zbudget_hdfs=zbudget_hdfs,
    )
    adapter._root = root
    return adapter
