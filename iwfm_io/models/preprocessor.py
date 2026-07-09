"""Dataclasses for IWFM preprocessor input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from iwfm_io.models.base import FileHeader, ConversionFactor


@dataclass
class NodeFile:
    """Parsed node coordinate file (e.g. NodeXY.dat).

    Attributes
    ----------
    header : FileHeader
    factor : ConversionFactor
    data : GeoDataFrame
        Columns: node_id (int), x (float), y (float), geometry (Point).
    """

    header: FileHeader = field(default_factory=FileHeader)
    factor: ConversionFactor = field(default_factory=ConversionFactor)
    data: Any = None  # GeoDataFrame at runtime


@dataclass
class ElementFile:
    """Parsed element configuration file (e.g. Element.dat).

    Attributes
    ----------
    header : FileHeader
    subregions : pd.DataFrame
        Columns: subregion_id (int), name (str).
    data : GeoDataFrame
        Columns: element_id, node1, node2, node3, node4, subregion, geometry.
    """

    header: FileHeader = field(default_factory=FileHeader)
    subregions: Any = None  # DataFrame
    data: Any = None  # GeoDataFrame


@dataclass
class StratigraphyFile:
    """Parsed stratigraphy file (e.g. Strata.dat).

    Attributes
    ----------
    header : FileHeader
    n_layers : int
    factor : ConversionFactor
    data : pd.DataFrame
        Columns: node_id, elevation, aquitard_1, aquifer_1, ..., aquitard_N, aquifer_N.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_layers: int = 0
    factor: ConversionFactor = field(default_factory=ConversionFactor)
    data: Any = None  # DataFrame


@dataclass
class StreamGeomFile:
    """Parsed stream geometry file (e.g. Stream.dat).

    Attributes
    ----------
    header : FileHeader
    version : str or None
    n_rating_points : int
        Number of rating table points per stream node (NRTB).
    reaches : pd.DataFrame
        Columns: reach_id, n_nodes, outflow_dest, name.
    nodes : GeoDataFrame
        Columns: stream_node_id, reach_id, gw_node_id, geometry (Point).
    rating_tables : pd.DataFrame
        Columns: stream_node_id, bottom_elev, stage, flow.
    rating_factors : dict
        Keys: factlt, factq, tunit.
    n_partial_interaction : int
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_rating_points: int = 0
    reaches: Any = None
    nodes: Any = None  # GeoDataFrame
    rating_tables: Any = None  # DataFrame
    rating_factors: dict = field(default_factory=dict)
    n_partial_interaction: int = 0


@dataclass
class LakeGeomFile:
    """Parsed lake geometry file (e.g. Lake.dat).

    Attributes
    ----------
    header : FileHeader
    data : pd.DataFrame
        Columns: lake_id, dest_type, dest_id, elements (list[int]).
    """

    header: FileHeader = field(default_factory=FileHeader)
    data: Any = None  # DataFrame


@dataclass
class PreprocessorMain:
    """Parsed preprocessor main file (e.g. PreProcessor_MAIN.IN).

    Attributes
    ----------
    header : FileHeader
    titles : list[str]
        Up to 3 title lines.
    file_paths : dict[str, str or None]
        Keyed by role: binary_output, element, node, strata, stream, lake.
    config : dict
        Non-file settings (KOUT, KDEB, unit conversion factors).
    children : dict
        Loaded child file objects (if follow_references=True).
    """

    header: FileHeader = field(default_factory=FileHeader)
    titles: list[str] = field(default_factory=list)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    children: dict = field(default_factory=dict)

    # -- Direct data access ------------------------------------------------
    #
    # Shortcuts so users can write ``pp.nodes`` instead of
    # ``pp.children["node"].data``.

    def _child_attr(self, key, attr):
        child = self.children.get(key)
        if child is None:
            if not self.file_paths.get(key):
                # The model doesn't include this component (blank file
                # entry, e.g. a model without lakes) — not an error.
                return None
            raise KeyError(
                f"The '{key}' file was not loaded with this preprocessor. "
                "Re-read with read_preprocessor(path, follow_references=True) "
                f"and check that file_paths[{key!r}] points to an existing file."
            )
        return getattr(child, attr)

    @property
    def nodes(self):
        """GeoDataFrame of node coordinates: node_id, x, y, geometry."""
        return self._child_attr("node", "data")

    @property
    def elements(self):
        """GeoDataFrame of elements: element_id, node1-4, subregion, geometry."""
        return self._child_attr("element", "data")

    @property
    def subregions(self):
        """DataFrame of subregions: subregion_id, name."""
        return self._child_attr("element", "subregions")

    @property
    def stratigraphy(self):
        """DataFrame of stratigraphy: node_id, elevation, per-layer thicknesses."""
        return self._child_attr("strata", "data")

    @property
    def n_layers(self):
        """Number of aquifer layers from the stratigraphy file."""
        return self._child_attr("strata", "n_layers")

    @property
    def stream_reaches(self):
        """DataFrame of stream reaches: reach_id, n_nodes, outflow_dest, name."""
        return self._child_attr("stream", "reaches")

    @property
    def stream_nodes(self):
        """GeoDataFrame of stream nodes: stream_node_id, reach_id, gw_node_id, geometry."""
        return self._child_attr("stream", "nodes")

    @property
    def stream_rating_tables(self):
        """DataFrame of rating tables: stream_node_id, bottom_elev, stage, flow."""
        return self._child_attr("stream", "rating_tables")

    @property
    def lakes(self):
        """DataFrame of lakes: lake_id, dest_type, dest_id, elements."""
        return self._child_attr("lake", "data")
