"""Dataclasses for the IWFM simulation main file."""

from __future__ import annotations

from dataclasses import dataclass, field

from iwfm_io.models.base import FileHeader


@dataclass
class SimulationMain:
    """Parsed simulation main file (e.g. ``Simulation_MAIN.IN``).

    Attributes
    ----------
    header : FileHeader
    titles : list[str]
        Up to 3 title lines.
    file_paths : dict[str, str or None]
        Keyed by role: preprocessor_bin, gw_main, stream_main, lake_main,
        rootzone_main, swshed, unsatzone, irigfrac, supply_adjust, precip, et,
        crop_coeff.
    sim_begin : str
        Simulation start date (IWFM format).
    sim_end : str
        Simulation end date (IWFM format).
    time_unit : str
        Timestep specification (e.g. ``1DAY``).
    restart : int
        Restart flag.
    solver : dict
        Solver parameters: msolve, relax, mxiter, mxitersp, stopc, stopcvl,
        stopcsp.
    output : dict
        Output settings: istrt, kdeb, cache.
    supply_adjust_flag : int
        KOPTDV flag.
    children : dict
        Loaded child file objects (if follow_references=True).
    """

    header: FileHeader = field(default_factory=FileHeader)
    titles: list[str] = field(default_factory=list)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    sim_begin: str = ""
    sim_end: str = ""
    time_unit: str = ""
    restart: int = 0
    solver: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    supply_adjust_flag: int = 0
    children: dict = field(default_factory=dict)
