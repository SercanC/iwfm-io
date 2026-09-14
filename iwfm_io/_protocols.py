"""Structural type of "a model" as the plotting, GIS, VTK and calibration
helpers see it.

:class:`ModelLike` documents the methods those consumers rely on — the
DataFrame API shared by :class:`iwfm_io.model_adapter.IOModelAdapter`
(file-based, DLL-free) and :class:`iwfm_io.dll.model.IWFMModel` (live
DLL).  It is a :class:`typing.Protocol` for documentation and static
checking only: nothing performs ``isinstance`` checks against it, and
any object exposing the same methods (duck typing) is accepted
everywhere a model is expected.

Consumers and what they use:

- ``iwfm_io.plots`` — ``nodes_df``, ``elements_df``, ``stratigraphy_df``,
  ``heads_df``, ``budget_df``, ``hydrograph_df``, ``reaches_df``,
  ``stream_nodes_df``, ``stream_rating_tables_df``, ``lakes_df``,
  ``subregions_df``, ``n_layers`` (+ the DLL-shaped getters served by
  :class:`iwfm_io._compat_shims.DllCompatMixin`).
- ``iwfm_io.gis`` — the grid/stream/lake tables plus ``tile_drains_df``,
  ``wells_df``, ``heads_df``.
- ``iwfm_io.vtk`` — ``nodes_df``, ``elements_df``, ``stratigraphy_df``,
  ``heads_df``, ``n_layers``.
- ``iwfm_io.wells`` / ``iwfm_io.gauges`` — ``nodes_df``, ``elements_df``,
  ``stratigraphy_df``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class ModelLike(Protocol):
    """The DataFrame-returning model interface (see the module docstring).

    Tabular results are pandas DataFrames; spatial tables are GeoDataFrames
    when geopandas is installed and plain DataFrames otherwise.
    """

    # -- grid ------------------------------------------------------------
    def nodes_df(self) -> pd.DataFrame:
        """``node_id, x, y[, geometry]`` — one row per grid node."""
        ...

    def elements_df(self) -> pd.DataFrame:
        """``element_id, node1..node4, subregion[, geometry]``
        (``node4 == 0`` marks a triangle)."""
        ...

    def subregions_df(self) -> pd.DataFrame:
        """``subregion_id, name``."""
        ...

    def stratigraphy_df(self) -> pd.DataFrame:
        """``node_id, elevation, aquitard_1, aquifer_1, ...`` per node."""
        ...

    # -- streams and lakes ----------------------------------------------
    def reaches_df(self) -> pd.DataFrame:
        """``reach_id, n_nodes, outflow_dest, name``."""
        ...

    def stream_nodes_df(self) -> pd.DataFrame:
        """``stream_node_id, reach_id, gw_node_id[, geometry]``."""
        ...

    def stream_rating_tables_df(self) -> pd.DataFrame:
        """``stream_node_id, bottom_elev, stage, flow``."""
        ...

    def lakes_df(self) -> pd.DataFrame:
        """``lake_id, n_elements, elements`` (list of element ids)."""
        ...

    # -- point features --------------------------------------------------
    def tile_drains_df(self) -> pd.DataFrame:
        """``id, node, x, y[, geometry]``."""
        ...

    def wells_df(self) -> pd.DataFrame:
        """``well_id, x, y, radius, perf_top, perf_bot, name[, geometry]``."""
        ...

    # -- time series -----------------------------------------------------
    def heads_df(self, layer: int, begin_date: Any = None,
                 end_date: Any = None, day_index: bool = False,
                 ) -> pd.DataFrame:
        """DatetimeIndex x one column per node (``node_<id>``)."""
        ...

    def budget_df(self, budget_name: Any, location: Any,
                  begin_date: Any = None, end_date: Any = None,
                  interval: Any = None, columns: Any = None,
                  day_index: bool = False, **kwargs: Any) -> pd.DataFrame:
        """DatetimeIndex x budget columns for one location."""
        ...

    def hydrograph_df(self, hdf_name: Any, column: Any = None,
                      begin_date: Any = None, end_date: Any = None,
                      day_index: bool = False, **kwargs: Any,
                      ) -> pd.DataFrame:
        """DatetimeIndex x hydrograph columns of one output file."""
        ...

    # -- counts and overview --------------------------------------------
    @property
    def n_nodes(self) -> int: ...

    @property
    def n_elements(self) -> int: ...

    @property
    def n_layers(self) -> int: ...

    @property
    def n_subregions(self) -> int: ...

    @property
    def n_reaches(self) -> int: ...

    @property
    def n_stream_nodes(self) -> int: ...

    def describe(self) -> dict:
        """JSON-serializable overview of the model and its outputs."""
        ...


__all__ = ["ModelLike"]
