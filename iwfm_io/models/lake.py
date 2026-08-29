"""Dataclasses for IWFM lake component files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader


@dataclass
class LakeMain:
    """Parsed lake component main file (e.g. ``Lake_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    max_elev_file : str or None
        MXLKELVFL — maximum lake elevations time-series file (read it
        with :func:`iwfm_io.read_max_lake_elev`).
    budget_file : str or None
        LKBUDFL — lake budget HDF5 output.
    final_elev_file : str or None
        FNLKELVFL — end-of-simulation lake elevations output.
    factk : float
        Conversion factor for lake bed hydraulic conductivity (FACTK).
    tunitk : str
        Time unit of the lake bed conductivity (TUNITK).
    factl : float
        Conversion factor for lake bed thickness (FACTL).
    n_lakes : int
    lake_params : pd.DataFrame
        One row per lake: lake_id, conductance (CLAKE), bed_thickness
        (DLAKE), max_elev_col (ICHLMAX — column in MXLKELVFL), et_col
        (ICETLK — column in the ET file), precip_col (ICPCPLK — column
        in the precipitation file), name (NAMELK).
    init_elev_factor : float
        FACT for the initial lake elevations.
    initial_elevations : pd.DataFrame or None
        One row per lake: lake_id (ILAKE), elevation (HLAKE) —
        file-native values; apply ``init_elev_factor`` for model units.
    """

    header: FileHeader = field(default_factory=FileHeader)
    max_elev_file: str | None = None
    budget_file: str | None = None
    final_elev_file: str | None = None
    factk: float = 1.0
    tunitk: str = "1day"
    factl: float = 1.0
    n_lakes: int = 0
    lake_params: Any = None  # DataFrame
    init_elev_factor: float = 1.0
    initial_elevations: Any = None  # DataFrame
