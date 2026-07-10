"""Dataclasses for IWFM groundwater component input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader, TimeSeriesSpec


@dataclass
class GWMain:
    """Parsed groundwater component main file (e.g. ``GW_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        Keyed by role: bc_main, tile_drain, pump_main, subsidence,
        overwrite, vel_out, vflow_out, gwhead_all, htp_out, vtp_out,
        gw_budget, zbudget, final_heads.
    config : dict
        Non-file settings: factltou, unitltou, factvlou, unitvlou,
        factvrou, unitvrou, ihtpflag, kdeb.
    n_hydrographs : int
        Number of GW hydrograph output locations (NOUTH).
    hydrograph_factxy : float
        Coordinate conversion factor for hydrograph x-y locations.
    hydrograph_out_file : str or None
        Output file for GW hydrographs.
    hydrographs : pd.DataFrame or None
        Columns: id, hydtyp, layer, x, y, node, name.
    n_face_flows : int
        Number of element face flow output specs (NOUTF).
    face_flow_out_file : str or None
        Output file for face flow hydrographs.
    face_flows : pd.DataFrame or None
        Columns: id, layer, node_a, node_b, name.
    ngroup : int or None
        Number of parametric grid groups (0 = parameters listed at
        every GW node).
    param_factors : dict
        Aquifer parameter conversion factors: fx, fkh, fs, fn, fv, fl.
        Parameter DataFrames store file-native values — apply these
        factors for model units.
    param_time_units : dict
        Time units keyed by keyword (TUNITKH, TUNITV, TUNITL).
    aquifer_params : pd.DataFrame or None
        NGROUP=0 only.  Long format, one row per node-layer:
        node_id, layer, kh, ss, sy, aquitard_kv, kv.
    parametric_grids : list[dict]
        NGROUP>0 only.  One dict per group: node_range (str), nodes
        (list[int]), ndp, nep, elements (DataFrame or None), params
        (DataFrame: node_id, x, y, layer, kh, ss, sy, aquitard_kv, kv).
    anomaly_nebk : int
        Number of hydraulic-conductivity anomaly elements (NEBK).
    anomaly_factor : float
        Conversion factor for anomaly Kh values (FACT).
    anomaly_time_unit : str
        Time unit for anomaly Kh values (TUNITH).
    kh_anomalies : pd.DataFrame or None
        Columns: ic, element_id, kh_layer_1..kh_layer_NL.
    iflagrf : int or None
        Groundwater return-flow simulation flag (IFLAGRF); None when
        the file variant has no return-flow section.
    return_flow : pd.DataFrame or None
        Columns: node_id, dest_type (0=outside, 1=stream node,
        3=lake), dest.
    facthp : float or None
        Conversion factor for initial heads (FACTHP).
    initial_heads : pd.DataFrame or None
        Columns: node_id, head_layer_1..head_layer_NL.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    n_hydrographs: int = 0
    hydrograph_factxy: float = 1.0
    hydrograph_out_file: str | None = None
    hydrographs: Any = None  # DataFrame
    n_face_flows: int = 0
    face_flow_out_file: str | None = None
    face_flows: Any = None  # DataFrame
    ngroup: int | None = None
    param_factors: dict = field(default_factory=dict)
    param_time_units: dict = field(default_factory=dict)
    aquifer_params: Any = None  # DataFrame
    parametric_grids: list = field(default_factory=list)
    anomaly_nebk: int = 0
    anomaly_factor: float = 1.0
    anomaly_time_unit: str = ""
    kh_anomalies: Any = None  # DataFrame
    iflagrf: int | None = None
    return_flow: Any = None  # DataFrame
    facthp: float | None = None
    initial_heads: Any = None  # DataFrame


@dataclass
class BCMain:
    """Parsed boundary conditions main file (e.g. ``BC_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        Keyed by role: sp_flow, sp_head, ghbc, con_ghbc, ts_bc.
    n_bc_hydrographs : int
        Number of boundary node flow hydrograph outputs (NOUTB).
    bc_hyd_out_file : str or None
        Output file for boundary flow hydrographs.
    bc_hydrographs : pd.DataFrame or None
        Columns: id, layer, node, name.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    n_bc_hydrographs: int = 0
    bc_hyd_out_file: str | None = None
    bc_hydrographs: Any = None  # DataFrame


@dataclass
class SpecifiedHeadFile:
    """Parsed specified head boundary conditions file (e.g. ``SpecHeadBC.dat``).

    Attributes
    ----------
    header : FileHeader
    n_nodes : int
        Number of specified-head nodes (NHB).
    factor : float
        Conversion factor for head values (FACT).
    data : pd.DataFrame or None
        Columns: node_id, layer, ibctyp, head.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_nodes: int = 0
    factor: float = 1.0
    data: Any = None  # DataFrame


@dataclass
class SpecifiedFlowBCFile:
    """Parsed specified flow boundary conditions file.

    Attributes
    ----------
    header : FileHeader
    n_nodes : int
        Number of specified-flow nodes (NQB).
    factor : float
        Conversion factor for flow values (FACT).
    time_unit : str
        Time unit of the flows (TUNIT).
    data : pd.DataFrame or None
        Columns: node_id, layer, itscol (column in the time-series BC
        file; 0 = constant), flow.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_nodes: int = 0
    factor: float = 1.0
    time_unit: str = ""
    data: Any = None  # DataFrame


@dataclass
class GeneralHeadBCFile:
    """Parsed general head boundary conditions file.

    Attributes
    ----------
    header : FileHeader
    n_nodes : int
        Number of general-head BC nodes (NGB).
    facth : float
        Conversion factor for boundary heads (FACTH).
    factc : float
        Conversion factor for conductances (FACTC).
    time_unit : str
        Time unit of the conductance (TUNITC).
    data : pd.DataFrame or None
        Columns: node_id, layer, itscol (column in the time-series BC
        file; 0 = constant), head, conductance.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_nodes: int = 0
    facth: float = 1.0
    factc: float = 1.0
    time_unit: str = ""
    data: Any = None  # DataFrame


@dataclass
class ConstrainedHeadBCFile:
    """Parsed constrained general head boundary conditions file.

    Attributes
    ----------
    header : FileHeader
    n_nodes : int
        Number of constrained general-head BC nodes (NCGB).
    facth : float
        Conversion factor for boundary and limiting heads (FACTH).
    factvl : float
        Conversion factor for maximum boundary flows (FACTVL).
    tunitvl : str
        Time unit of the maximum boundary flows.
    factc : float
        Conversion factor for conductances (FACTC).
    tunitc : str
        Time unit of the conductances.
    data : pd.DataFrame or None
        Columns: node_id, layer, itscol (boundary-head column in the
        time-series BC file; 0 = constant), head, conductance,
        limiting_head, itscolf (max-flow column in the time-series BC
        file; 0 = constant), max_flow, name.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_nodes: int = 0
    facth: float = 1.0
    factvl: float = 1.0
    tunitvl: str = ""
    factc: float = 1.0
    tunitc: str = ""
    data: Any = None  # DataFrame


@dataclass
class BoundaryTSFile:
    """Parsed time-series boundary condition file (e.g. ``BoundTSD.dat``).

    Attributes
    ----------
    header : FileHeader
    spec : TimeSeriesSpec
        Standard 5-param time-series spec (NBTSD, FACTHTS, FACTQTS, NSPHTS, NFQHTS, DSSFL).
        n_columns stores NBTSD; factor stores FACTHTS.
        The FACTQTS is stored separately in config.
    config : dict
        Additional spec values: factqts.
    data : pd.DataFrame or None
        DataFrame with ``date`` column and value columns.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments if using DSS input.
    """

    header: FileHeader = field(default_factory=FileHeader)
    spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    config: dict = field(default_factory=dict)
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class PumpMain:
    """Parsed pumping component main file (e.g. ``Pump_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        Keyed by role: well, elem_pump, ts_pump, pump_out.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)


@dataclass
class ElemPumpFile:
    """Parsed element pumping specification file (e.g. ``ElemPump.dat``).

    Attributes
    ----------
    header : FileHeader
    n_sinks : int
        Number of pumping elements (NSINK).
    data : pd.DataFrame or None
        Columns: id, icolsk, fracsk, ioptsk, fracskl_1, fracskl_2,
        typdstsk, dstsk, icfirigsk, icadjsk, icskmax, fskmax.
    n_groups : int
        Number of element groups for delivery (NGRP).
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_sinks: int = 0
    data: Any = None  # DataFrame
    n_groups: int = 0
    #: Parsed delivery element groups: [{group_id, elements: [int]}, …]
    element_groups: list = field(default_factory=list)

    @property
    def element_groups_df(self):
        """Delivery element groups as a long-format DataFrame
        (columns: group_id, element_id)."""
        from iwfm_io.readers._element_groups import element_groups_to_df
        return element_groups_to_df(self.element_groups)


@dataclass
class WellSpecFile:
    """Parsed well specification file (e.g. ``WellSpec.dat``).

    Attributes
    ----------
    header : FileHeader
    n_wells : int
        Number of wells (NWELL).
    factors : dict
        Conversion factors: factxy (coordinates), factrw (radius),
        factlt (perforation depths). ``data`` stores file-native values;
        apply factors for model units.
    data : pd.DataFrame or None
        Columns: well_id, x, y, radius, perf_top, perf_bot, name.
    pump_config : pd.DataFrame or None
        Per-well pumping configuration, one row per well.  Columns use
        the IWFM variable names: id, icolwl (column in the time-series
        pumping file; 0 = none), fracwl (fraction of that column),
        ioptwl (distribution option), typdstwl (-1=same element,
        0=outside, 2=element, 4=subregion, 6=element group), dstwl
        (destination id), icfirigwl (column in the irrigation fractions
        file), icadjwl (column in the supply adjustment file), icwlmax
        (max-pumping column in the time-series pumping file), fwlmax.
    n_groups : int
        Number of delivery element groups (NGRP).
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_wells: int = 0
    factors: dict = field(default_factory=dict)
    data: Any = None  # DataFrame
    pump_config: Any = None  # DataFrame
    n_groups: int = 0
    #: Parsed delivery element groups: [{group_id, elements: [int]}, …]
    element_groups: list = field(default_factory=list)

    @property
    def element_groups_df(self):
        """Delivery element groups as a long-format DataFrame
        (columns: group_id, element_id)."""
        from iwfm_io.readers._element_groups import element_groups_to_df
        return element_groups_to_df(self.element_groups)


@dataclass
class TSPumpingFile:
    """Parsed time-series pumping data file (e.g. ``TSPumping.dat``).

    Attributes
    ----------
    header : FileHeader
    spec : TimeSeriesSpec
        Standard 5-param time-series spec (NCOLPUMP, FACTPUMP, NSPPUMP, NFQPUMP, DSSFL).
    data : pd.DataFrame or None
        DataFrame with ``date`` column and value columns.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments if using DSS input.
    """

    header: FileHeader = field(default_factory=FileHeader)
    spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class TileDrainFile:
    """Parsed tile drain parameter file (e.g. ``TileDrain.dat``).

    Attributes
    ----------
    header : FileHeader
    n_tile_drains : int
        Number of tile drain nodes (NTD).
    facth : float
        Conversion factor for tile drain elevations (FACTH).
    factcdc : float
        Conversion factor for tile drain conductances (FACTCDC).
    tunit_dr : str
        Time unit for tile drain conductance (TUNITDR).
    data : pd.DataFrame or None
        Columns: id, node, elev, conductance, dest_type, dest.
    n_sub_irrig : int
        Number of subsurface irrigation nodes (NSI).
    facthsi : float
        Conversion factor for subsurface irrigation elevations (FACTHSI).
    factcdcsi : float
        Conversion factor for subsurface irrigation conductances (FACTCDCSI).
    tunit_si : str
        Time unit for subsurface irrigation conductance (TUNITSI).
    sub_irrig_data : pd.DataFrame or None
        Columns: id, node, elev, conductance.
    n_hydrographs : int
        Number of tile drain hydrograph outputs (NOUTTD).
    hyd_factvlou : float
        Flow output conversion factor (FACTVLOU).
    hyd_unitvlou : str
        Flow output unit (UNITVLOU).
    hyd_out_file : str or None
        Hydrograph output file (TDOUTFL), file-native path string.
    hydrographs : pd.DataFrame or None
        Columns: id, idtyp (1=tile drain, 2=subsurface irrigation), name.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_tile_drains: int = 0
    facth: float = 1.0
    factcdc: float = 1.0
    tunit_dr: str = "1day"
    data: Any = None  # DataFrame
    n_sub_irrig: int = 0
    facthsi: float = 1.0
    factcdcsi: float = 1.0
    tunit_si: str = "1day"
    sub_irrig_data: Any = None  # DataFrame
    n_hydrographs: int = 0
    hyd_factvlou: float = 1.0
    hyd_unitvlou: str = ""
    hyd_out_file: str | None = None
    hydrographs: Any = None  # DataFrame


@dataclass
class SubsidenceFile:
    """Parsed subsidence component main file (e.g. ``Subsidence.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        Keyed by role: ini_sub, tps_out, fn_sub.
    config : dict
        Conversion and unit settings: factltou, unitltou.
    n_hydrographs : int
        Number of subsidence hydrograph outputs (NOUTS).
    hydrograph_factxy : float
        Coordinate conversion factor (FACTXY).
    hydrograph_out_file : str or None
        Output file for subsidence hydrographs.
    hydrographs : pd.DataFrame or None
        Columns: id, subtyp, layer, x, y, node, name.
    ngroup : int or None
        Number of parametric grid groups (0 = parameters listed at
        every GW node).
    param_factors : dict
        Conversion factors: fx, fsce, fsci, fdc, fdcmin, fhc.
        ``subsidence_params`` stores file-native values — apply these
        factors for model units.
    subsidence_params : pd.DataFrame or None
        NGROUP=0 only.  Long format, one row per node-layer: node_id,
        layer, sce (elastic storage), sci (inelastic storage), dc
        (interbed thickness), dcmin (min interbed thickness), hc
        (pre-compaction head; 99999 = use initial heads).
    parametric_grids : list[dict]
        NGROUP>0 only.  One dict per group: node_range (str), nodes
        (list[int]), ndp, nep, elements (DataFrame or None), params
        (DataFrame: node_id, x, y, layer, sce, sci, dc, dcmin, hc).
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    n_hydrographs: int = 0
    hydrograph_factxy: float = 1.0
    hydrograph_out_file: str | None = None
    hydrographs: Any = None  # DataFrame
    ngroup: int | None = None
    param_factors: dict = field(default_factory=dict)
    subsidence_params: Any = None  # DataFrame
    parametric_grids: list = field(default_factory=list)
