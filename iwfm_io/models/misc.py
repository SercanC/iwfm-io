"""Dataclasses for miscellaneous IWFM files (SWShed, UnsatZone)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader


@dataclass
class SWShedFile:
    """Parsed small watershed file (e.g. ``SWShed.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict
        Output file paths (SWBUDFL, FNSWFL).
    n_watersheds : int
    config : dict
        Parameters and conversion factors: facta, factq, tunitq, toler,
        itermax, factl, factcn, factk, tunitk, factgw, factt, tunitt,
        fact_ic.
    watershed_data : pd.DataFrame or None
        Per-watershed definitions.  Columns: id, area, stream_node
        (receives the surface runoff), n_gw_nodes.
    watershed_nodes : pd.DataFrame or None
        Groundwater nodes receiving baseflow, one row per node.
        Columns: watershed_id, gw_node, qmax (max recharge rate;
        negative values encode the receiving layer number).
    rootzone_params : pd.DataFrame or None
        Per-watershed root zone parameters.  Columns: id, irns (column
        in the Precipitation data file), frns, icets (column in the ET
        data file), wp, fc, porosity, lambda, root_depth, soil_k, rhc,
        cn.
    aquifer_params : pd.DataFrame or None
        Columns: id, gw_threshold_depth, gw_max_depth,
        surface_flow_recession, baseflow_recession.
    initial_conditions : pd.DataFrame or None
        Columns: id, soil_moisture, gw_storage.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    n_watersheds: int = 0
    config: dict = field(default_factory=dict)
    watershed_data: Any = None
    watershed_nodes: Any = None
    rootzone_params: Any = None
    aquifer_params: Any = None
    initial_conditions: Any = None


@dataclass
class UnsatZoneFile:
    """Parsed unsaturated zone file (e.g. ``UnsatZone.dat``).

    Attributes
    ----------
    header : FileHeader
    n_unsat_layers : int
    convergence : float
    max_iterations : int
    file_paths : dict
        Output file paths (UZBUDFL, UZZBUDFL, UZFNFL).
    config : dict
        Conversion factors and units: fx, fd, fk, tunitz.
    ngroup : int or None
        Number of parametric grid groups (0 = parameters listed at
        every element).
    element_params : pd.DataFrame or None
        NGROUP=0 only.  Long format, one row per element-layer:
        element_id, layer, thickness, porosity, pore_size_index, k,
        rhc (1=Campbell, 2=van Genuchten-Mualem).  File-native values —
        apply the config factors for model units.
    initial_moisture : pd.DataFrame or None
        Columns: element_id, moisture_layer_1..moisture_layer_N.
        element_id 0 means the values apply to all elements.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_unsat_layers: int = 0
    convergence: float = 0.001
    max_iterations: int = 150
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    ngroup: int | None = None
    element_params: Any = None  # DataFrame
    initial_moisture: Any = None  # DataFrame
