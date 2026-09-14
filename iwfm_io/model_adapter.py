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
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _geo():
    """``(geopandas, Point)`` when the ``[geo]`` extra is installed, else
    ``None``.  Imported at call time so ``import iwfm_io`` never pays the
    geopandas/shapely import cost."""
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError:
        return None
    return gpd, Point


from iwfm_io._compat_shims import (  # noqa: F401  (shared helpers)
    DllCompatMixin,
    _as_index,
    _check_compat_kwargs,
    _excel_serials,
    _file_sig,
)
from iwfm_io._tokens import _maybe_day_index

__all__ = ["IOModelAdapter", "open_model"]


def _hdf_dataset_names(path):
    """List top-level dataset names in an HDF5 file (cheap — no data read)."""
    import h5py
    with h5py.File(path, "r") as f:
        return [k for k in f.keys() if k != "Attributes"]


class IOModelAdapter(DllCompatMixin):
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
    budget_texts : dict[str, str or Path], optional
        Mapping of budget name → text ``.bud`` path.  Text budgets are
        the fallback for packaged/older models whose Results carry no
        budget HDF files; where a name exists in both mappings the HDF
        wins.
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
        budget_texts=None,
        strict=True,
    ):
        self._pp = preprocessor
        self._sim = simulation
        self._strict = bool(strict)
        self._heads_hdf = heads_hdf
        self._budget_hdfs = budget_hdfs or {}
        self._budget_texts = budget_texts or {}
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

    def _reader_mode(self):
        """Context manager applying this adapter's reader mode to the
        files it reads lazily (components, time series)."""
        from iwfm_io._strict import strict_mode
        return strict_mode(self._strict)

    # -- public handles on the parsed inputs / discovered outputs --------

    @property
    def model_root(self):
        """Root folder :func:`open_model` discovered the model in (``None``
        for an adapter built from explicit file objects)."""
        return self._root

    @property
    def simulation(self):
        """The parsed simulation main (``SimulationMain``) or ``None``."""
        return self._sim

    @property
    def preprocessor(self):
        """The parsed preprocessor main (``PreprocessorMain``) or ``None``."""
        return self._pp

    @property
    def gw_main(self):
        """The parsed groundwater main (``GWMain``) or ``None``."""
        return self._gw_main

    @property
    def stream_main(self):
        """The parsed stream main (``StreamMain``) or ``None``."""
        return self._stream_main

    @property
    def heads_file(self):
        """Path of the head output this adapter serves (HDF or text), or
        ``None``."""
        return self._heads_hdf

    @property
    def available_budgets(self):
        """Sorted budget names this adapter can serve -- HDF and text
        (``.bud``) sources alike."""
        return sorted({*self._budget_hdfs, *self._budget_texts})

    @property
    def available_zbudgets(self):
        """Sorted zone-budget names with an HDF source."""
        return sorted(self._zbudget_hdfs)

    def _cached_file(self, key, paths, builder):
        """Return ``builder()`` cached under *key* until any of *paths*
        changes on disk (mtime or size).  Every table the adapter reads
        lazily from a file goes through here, so an edited input or a
        re-run model is picked up without re-opening the adapter."""
        sig = tuple(_file_sig(p) for p in paths)
        hit = self._cache.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1]
        value = builder()
        self._cache[key] = (sig, value)
        return value

    def reload(self):
        """Drop every cached table so the next access re-reads the files.

        Tables read lazily from disk (components, time series, budgets,
        heads, stream flows) already refresh themselves when their source
        file changes; ``reload()`` forces it -- e.g. after a run that
        rewrote outputs in place with the same size and timestamp.  The
        grid tables come from the preprocessor deck parsed at open; use
        ``open_model`` again after editing that.
        """
        self._cache.clear()
        return self

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
        geo = _geo() if len(df) > 0 else None
        if geo is not None:
            gpd, Point = geo
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
            geo = _geo() if len(df) > 0 else None
            if geo is not None:
                gpd, Point = geo
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

    def heads_df(self, layer, begin_date=None, end_date=None,
                 day_index=False):
        """Return DataFrame(DatetimeIndex) with one column per node.

        Reads from ``GWHeadAll.hdf`` when available, otherwise from the
        text equivalent ``GWHeadAll.out`` (what a fresh simulation run
        writes) — both are layer-major with identical column ordering.

        ``day_index=True`` re-indexes by :func:`iwfm_io.iwfm_day` — the
        day each ``24:00`` stamp belongs to — so calendar idioms like
        ``resample("YE-SEP")`` and ``.dt.year`` label periods correctly.
        """
        if self._heads_hdf is None:
            raise RuntimeError("IOModelAdapter: heads_hdf path required")
        ndf = self.nodes_df()
        n_nodes = len(ndf)
        strata = self._child("strata")
        n_layers = strata.n_layers if strata else 1
        layer = _as_index(layer, "layer", 1, n_layers)

        if Path(self._heads_hdf).suffix.lower() == ".out":
            result = self._heads_from_text(layer, n_nodes, n_layers)
        else:
            from iwfm_io.readers.hdf5 import read_head_hdf
            head_df = read_head_hdf(
                self._heads_hdf, n_nodes=n_nodes, n_layers=n_layers)
            # Filter columns for requested layer: node_N_layer_M pattern
            layer_cols = [c for c in head_df.columns
                          if c.endswith(f"_layer_{layer}")]
            if len(layer_cols) != n_nodes:
                raise ValueError(
                    f"{self._heads_hdf}: {len(layer_cols)} head columns "
                    f"for layer {layer} but the grid has {n_nodes} nodes")
            result = head_df[layer_cols].copy()
        # Columns are labelled by the model's node IDs (the file is in
        # node order); positional node_1..N labels would mislabel any
        # grid whose IDs are not contiguous
        result.columns = [f"node_{int(n)}" for n in ndf["node_id"]]
        # Filter by date range if specified
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            result = result[result.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            result = result[result.index <= parse_iwfm_date(end_date)]
        return _maybe_day_index(result, day_index)

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


    def _heads_from_text(self, layer, n_nodes, n_layers):
        """Heads for one layer from a GWHeadAll.out text file."""
        def build():
            from iwfm_io._tokens import parse_iwfm_date
            from iwfm_io.readers.text_output import read_head_all_out
            raw = read_head_all_out(self._heads_hdf)
            if raw.empty or "date" not in raw.columns:
                raise ValueError(
                    f"{self._heads_hdf} holds no head records (an empty or "
                    "truncated GWHeadAll.out -- did the simulation finish?)")
            idx = pd.DatetimeIndex(
                [parse_iwfm_date(d) for d in raw["date"]], name="datetime")
            full = raw.drop(columns="date")
            full.index = idx
            return full
        full = self._cached_file("heads_text", [self._heads_hdf], build)
        if full.shape[1] != n_nodes * n_layers:
            raise ValueError(
                f"{self._heads_hdf}: {full.shape[1]} head columns but the "
                f"grid has {n_nodes} nodes x {n_layers} layers")
        layer = _as_index(layer, "layer", 1, n_layers)
        start = (layer - 1) * n_nodes
        return full.iloc[:, start:start + n_nodes].copy()


    def budget_df(self, budget_name, location, begin_date=None, end_date=None,
                  interval=None, columns=None, day_index=False, **kwargs):
        """Return DataFrame(DatetimeIndex) of budget time series.

        Parameters
        ----------
        budget_name : str
            Key in ``budget_hdfs`` dict (e.g. ``"GW"``), or a text
            ``.bud`` budget discovered by ``open_model``.
        location : int or str
            1-based location index or location name.
        interval : str, optional
            ``"1MON"`` / ``"1YEAR"`` aggregate with the DLL's exact
            semantics (windows anchored to the data begin — ``"1YEAR"``
            is the water year for October-start models — type-aware
            rules, LWU carry-over, trailing partial window dropped);
            ``"1CALYEAR"`` aggregates over calendar years.  ``None``
            serves the native output interval.
        day_index : bool
            Re-index by :func:`iwfm_io.iwfm_day` (the day each ``24:00``
            stamp belongs to) so ``resample("YE-SEP")``/``.dt.year``
            label periods correctly. For water-year aggregation prefer
            :func:`iwfm_io.aggregate_budget`, which also handles the
            storage stocks.
        """
        fact_vl = _check_compat_kwargs(kwargs, "budget_df")
        budget_name = self._budget_key(budget_name)
        bud = self._read_budget_source(budget_name, interval=interval)
        locs = list(bud["locations"])
        if isinstance(location, str):
            if location not in locs:
                raise KeyError(
                    f"budget {budget_name!r} has no location "
                    f"{location!r}; available: {locs}")
            loc_name = location
        else:
            loc_name = locs[_as_index(location, "location", 1, len(locs)) - 1]
        df = bud["data"][loc_name]
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        if columns is not None:
            ncol = df.shape[1]
            sel = [_as_index(c, "column", 1, ncol) - 1 for c in columns]
            df = df.iloc[:, sel]
        else:
            df = df.copy()
        if fact_vl != 1.0:
            df = df * fact_vl
        return _maybe_day_index(df, day_index)


    def hydrograph_df(self, hdf_name, column=None, begin_date=None,
                      end_date=None, day_index=False, **kwargs):
        """Return DataFrame(DatetimeIndex) from a hydrograph HDF5.

        Parameters
        ----------
        hdf_name : str
            Key in ``hydrograph_hdfs`` dict.
        column : int, optional
            0-based column to extract as 'value'.  None returns all columns.
        """
        fact_vl = _check_compat_kwargs(kwargs, "hydrograph_df")
        if hdf_name not in self._hydrograph_hdfs:
            raise RuntimeError(
                f"IOModelAdapter: no hydrograph HDF for '{hdf_name}'; "
                f"available: {sorted(self._hydrograph_hdfs)}")
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf
        df = read_hydrograph_hdf(self._hydrograph_hdfs[hdf_name])
        if begin_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index >= parse_iwfm_date(begin_date)]
        if end_date is not None:
            from iwfm_io._tokens import parse_iwfm_date
            df = df[df.index <= parse_iwfm_date(end_date)]
        if column is not None:
            column = _as_index(column, "column", 0, df.shape[1] - 1)
            col_name = df.columns[column]
            df = pd.DataFrame({"value": df[col_name]}, index=df.index)
        if fact_vl != 1.0:
            df = df * fact_vl
        return _maybe_day_index(df, day_index)

    # -- Budget-backed state (DLL-free) ---------------------------------

    def _read_budget_source(self, key, interval=None):
        """Read a budget by name from its HDF or text ``.bud`` source.

        Returns the ``read_budget_hdf`` shape either way:
        ``{"locations": [...], "data": {location: DataFrame}}`` with a
        DatetimeIndex per location.  Text budgets carry the file's
        native output interval; requesting a different ``interval``
        from a text source raises (HDF budgets resample via the reader).
        """
        if key in self._budget_hdfs:
            from iwfm_io.readers.hdf5 import read_budget_hdf
            return read_budget_hdf(self._budget_hdfs[key],
                                   interval=interval)
        if key in self._budget_texts:
            if interval is not None:
                raise ValueError(
                    f"text budget '{key}' serves only its native output "
                    "interval — resample the returned DataFrame instead")
            from iwfm_io._tokens import parse_iwfm_date
            from iwfm_io.readers.text_output import read_budget_text

            def build():
                sections = read_budget_text(self._budget_texts[key])
                data = {}
                for loc, df in sections.items():
                    df = df.copy()
                    idx = pd.DatetimeIndex(
                        [parse_iwfm_date(d) for d in df.pop("date")])
                    df.index = idx
                    data[loc] = df
                return {"locations": list(data), "data": data}
            return self._cached_file(f"_budget_text::{key}",
                                     [self._budget_texts[key]], build)
        available = sorted({*self._budget_hdfs, *self._budget_texts})
        raise RuntimeError(
            f"IOModelAdapter: no budget source for '{key}' "
            f"(available: {available})")

    def _read_full_budget(self, key):
        """Read (and cache) a whole budget: {locations, data, ...}."""
        return self._cached_file(f"_budget_full::{key}",
                                 [self._budget_path(key)],
                                 lambda: self._read_budget_source(key))

    def _budget_path(self, key):
        """Source file of a budget key (HDF preferred, else text)."""
        return self._budget_hdfs.get(key) or self._budget_texts.get(key)

    def _find_budget_key(self, *tokens):
        """Find a budget key whose normalized name contains any token."""
        for key in (*self._budget_hdfs, *self._budget_texts):
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
        return self._cached_file(
            f"stream_flows::{factor}::{stat}", [self._budget_path(key)],
            lambda: self._stream_flows(key, columns, factor, stat))

    def _stream_flows(self, key, columns, factor, stat):
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
        return pd.DataFrame({"stream_node_id": sn_ids, **out})

    def subsidence_df(self, factor=1.0):
        """Not available from IO readers without live DLL snapshot.

        Per-node cumulative subsidence exists only as DLL state or at
        hydrograph observation points (``read_hydrograph_out`` on the
        subsidence ``.out`` file).
        """
        return pd.DataFrame(columns=["node_id"])


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


    @property
    def n_lakes(self):
        return len(self.lakes_df())

    @property
    def n_diversions(self):
        return len(self.diversions_df())

    @property
    def n_wells(self):
        return len(self.wells_df())

    # -- GIS export -----------------------------------------------------

    def to_gis(self, path, layers=None, crs=None,
               node_data=None, element_data=None):
        """Write the model's spatial layers to a GeoPackage or shapefiles.

        Convenience wrapper around :func:`iwfm_io.export_gis` — see it
        for parameters. Requires the ``[geo]`` extra.

        >>> m = open_model("path/to/model")
        >>> m.to_gis("model.gpkg", crs="EPSG:26910")
        """
        from iwfm_io.gis import export_gis
        return export_gis(self, path, layers=layers, crs=crs,
                          node_data=node_data, element_data=element_data)

    def to_vtk(self, path, point_data=None, cell_data=None,
               z_scale=1.0, layers=None):
        """Write the model as a 3D layered mesh to a VTK ``.vtu`` file.

        Convenience wrapper around :func:`iwfm_io.export_vtk` — see it
        for parameters (and :func:`iwfm_io.export_vtk_timeseries` for
        animated heads). No VTK library needed.

        >>> m = open_model("path/to/model")
        >>> m.to_vtk("model.vtu", z_scale=20)
        """
        from iwfm_io.vtk import export_vtk
        return export_vtk(self, path, point_data=point_data,
                          cell_data=cell_data, z_scale=z_scale,
                          layers=layers)

    # -- Cross-file relationships ---------------------------------------
    #
    # IWFM files reference each other: pointer columns hold 1-based
    # column numbers into role-referenced time-series files, ID columns
    # reference the grid tables, and (type, dest) pairs pick a
    # destination.  The registry in ``iwfm_io._links`` (internal) knows
    # every such relationship; these methods surface it.

    def component(self, name):
        """A parsed component/sub-file by registry name, lazily read
        and cached (e.g. ``"rootzone"``, ``"nonponded_ag"``,
        ``"well_spec"``, ``"bc_main"``).  Returns None when the model
        does not reference it."""
        from iwfm_io._links import load_component
        with self._reader_mode():
            return load_component(self, name)

    def timeseries(self, role):
        """The parsed time-series file for a pointer-target role,
        lazily read and cached (e.g. ``"et"``, ``"irig_period"``,
        ``"ts_pumping"``, ``"return_flow"``).  Returns None when the
        model does not reference it."""
        from iwfm_io._links import load_timeseries
        with self._reader_mode():
            return load_timeseries(self, role)

    def series(self, role, column, raw=False, expand=True):
        """One referenced time-series column as a ``date``/``value``
        DataFrame — the thing a pointer column points at.

        The file's conversion factor is applied (pass ``raw=True`` for
        file-native values) and recurring-year data (sentinel years
        2500/4000) is expanded onto the simulation period (pass
        ``expand=False`` for the raw pattern).  Values are step
        functions: each applies from its stamp until the next.

        Example: the ET series driving crop TO at element 12::

            col = m.component("nonponded_ag").et_columns
            n = col.loc[col.element_id == 12, "TO"].iloc[0]
            et = m.series("et", n)
        """
        from iwfm_io._links import series
        with self._reader_mode():
            return series(self, role, column, raw=raw, expand=expand)

    def column_usage(self, role):
        """Reverse lookup: who references each column of a time-series
        file.  Long DataFrame (column, source, table, pointer_column,
        n_refs, examples) — the way to answer "what is ``col_5`` of
        the ET file?"."""
        from iwfm_io._links import column_usage
        with self._reader_mode():
            return column_usage(self, role)

    def validate_references(self):
        """Validate every cross-file reference: pointer columns within
        the target file's column count, entity IDs present in the grid
        tables, (type, dest) pairs valid under their code tables.
        Returns a findings DataFrame (empty = everything resolves)."""
        from iwfm_io._links import validate_references
        with self._reader_mode():
            return validate_references(self)

    # -- Convenience accessors ------------------------------------------
    #
    # One-call answers to common modeling questions, built on series():
    # the consumer row is looked up (honoring the element_id=0
    # "all elements" sentinel), per-consumer share fractions are
    # applied where they exist, factors are applied (raw=True for
    # file-native values), and recurring-year data is expanded onto
    # the simulation period (expand=False for the raw pattern).

    def crop_series(self, kind, crop, element=None, raw=False,
                    expand=True):
        """A land-use driver series for one crop/land-use at an element.

        *crop* is a non-ponded crop code (``"TO"``), a ponded type
        (``"rice_fl"``, ``"rice_nfl"``, ``"rice_ndc"``, ``"refuge_sl"``,
        ``"refuge_pr"``), or ``"native"`` / ``"riparian"``.  *kind* is
        ``"et"``, ``"irrigation_period"``, ``"supply_requirement"``,
        ``"min_moisture"``, ``"target_moisture"``, ``"return_flow"``,
        ``"reuse"``, ``"min_perc"`` (non-ponded) or ``"ponding_depth"``
        (ponded).  Example::

            m.crop_series("et", "TO", element=12)
            m.crop_series("irrigation_period", "rice_fl")
        """
        from iwfm_io._links import crop_series
        with self._reader_mode():
            return crop_series(self, kind, crop, element=element, raw=raw,
                               expand=expand)

    def urban_series(self, kind, element=None, raw=False, expand=True):
        """An urban driver series at an element: ``"population"``,
        ``"per_capita_use"``, ``"water_use_specs"``, ``"et"``,
        ``"return_flow"``, or ``"reuse"``."""
        from iwfm_io._links import urban_series
        with self._reader_mode():
            return urban_series(self, kind, element=element, raw=raw,
                                expand=expand)

    def well_pumping(self, well_id, kind="pumping", scaled=True,
                     raw=False, expand=True):
        """A well's pumping series from the time-series pumping file —
        its ICOLWL column times its FRACWL share (``scaled=False`` for
        the unscaled column; ``kind="max"`` for the maximum-pumping
        column)."""
        from iwfm_io._links import well_pumping
        with self._reader_mode():
            return well_pumping(self, well_id, kind=kind, scaled=scaled,
                                raw=raw, expand=expand)

    def element_pumping(self, element_id, kind="pumping", scaled=True,
                        raw=False, expand=True):
        """An element's pumping series from the time-series pumping
        file — its ICOLSK column times its FRACSK share."""
        from iwfm_io._links import element_pumping
        with self._reader_mode():
            return element_pumping(self, element_id, kind=kind,
                                   scaled=scaled, raw=raw, expand=expand)

    def bc_series(self, node, layer=None, raw=False, expand=True):
        """The boundary condition at a GW node (and layer), searching
        all four BC files.  Time-series-driven BCs resolve their
        column of the time-series BC file; constant BCs (ITSCOL=0)
        return their value as a single stamp at the simulation start."""
        from iwfm_io._links import bc_series
        with self._reader_mode():
            return bc_series(self, node, layer=layer, raw=raw,
                             expand=expand)

    def diversion_series(self, diversion_id, kind="delivery",
                         scaled=True, raw=False, expand=True):
        """One diversion's series from the Diversions file — its
        ``"delivery"``, ``"max"``, ``"recoverable_loss"``,
        ``"nonrecoverable_loss"``, or ``"spill"`` column times the
        matching fraction (``scaled=False`` for the bare column)."""
        from iwfm_io._links import diversion_series
        with self._reader_mode():
            return diversion_series(self, diversion_id, kind=kind,
                                    scaled=scaled, raw=raw, expand=expand)

    def lake_max_elevation(self, lake_id=None, raw=False, expand=True):
        """A lake's maximum-elevation series from the MaxLakeElev
        file (``lake_id`` optional for single-lake models)."""
        from iwfm_io._links import lake_max_elevation
        with self._reader_mode():
            return lake_max_elevation(self, lake_id=lake_id, raw=raw,
                                      expand=expand)

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
                **{
                    name: {
                        "path": str(path),
                        "locations": _try(
                            lambda p=path: _hdf_dataset_names(p)),
                    }
                    for name, path in self._budget_hdfs.items()
                },
                **{
                    name: {
                        "path": str(path),
                        "format": "text",
                        "locations": _try(
                            lambda n=name: self._read_budget_source(
                                n)["locations"]),
                    }
                    for name, path in self._budget_texts.items()
                },
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
        errors = list(getattr(self, "_results_errors", []) or [])
        if errors:
            # result files that exist but could not be read (zero-byte,
            # truncated, locked): never silently absent
            info["results"]["errors"] = errors
        return info

    def __repr__(self):
        parts = []
        try:
            parts.append(f"{self.n_nodes} nodes")
            parts.append(f"{self.n_elements} elements")
            parts.append(f"{self.n_layers} layers")
        except Exception:
            parts.append("no grid loaded")
        n_budgets = len(self._budget_hdfs) + len(self._budget_texts)
        if n_budgets:
            parts.append(f"{n_budgets} budgets")
        if self._heads_hdf:
            parts.append("heads")
        return f"<IOModelAdapter: {', '.join(parts)}>"



# ----------------------------------------------------------------------
# open_model() and its discovery helpers live in iwfm_io._discovery;
# they are re-exported here so ``iwfm_io.model_adapter.open_model`` (and
# the private discovery helpers other modules import) keep working.
# ----------------------------------------------------------------------

from iwfm_io import _discovery as _discovery  # noqa: E402

open_model = _discovery.open_model
_open_model = _discovery._open_model
_find_main_file = _discovery._find_main_file
_find_simulation_main = _discovery._find_simulation_main
_sniff_simulation_main = _discovery._sniff_simulation_main
_classify_hdf = _discovery._classify_hdf
_UnreadableResult = _discovery._UnreadableResult
_MAIN_SUFFIXES = _discovery._MAIN_SUFFIXES
