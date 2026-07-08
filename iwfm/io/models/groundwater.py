"""Dataclasses for IWFM groundwater component input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm.io.models.base import FileHeader, TimeSeriesSpec


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
    aquifer_param_raw : list[str]
        Raw lines for the aquifer parameter section (NGROUP block),
        stored verbatim for round-trip writing.
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
    aquifer_param_raw: list[str] = field(default_factory=list)


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
    groups_raw : list[str]
        Raw lines for element group definitions, stored verbatim.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_sinks: int = 0
    data: Any = None  # DataFrame
    n_groups: int = 0
    groups_raw: list[str] = field(default_factory=list)


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
    hyd_raw : list[str]
        Raw lines for the hydrograph output section, stored verbatim.
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
    hyd_raw: list[str] = field(default_factory=list)


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
    subsidence_param_raw : list[str]
        Raw lines for the subsidence parameter section (NGROUP block),
        stored verbatim for round-trip writing.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    n_hydrographs: int = 0
    hydrograph_factxy: float = 1.0
    hydrograph_out_file: str | None = None
    hydrographs: Any = None  # DataFrame
    subsidence_param_raw: list[str] = field(default_factory=list)
