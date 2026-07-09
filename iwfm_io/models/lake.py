"""Dataclasses for IWFM lake component files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader, TimeSeriesSpec


@dataclass
class LakeMain:
    """Parsed lake component main file (e.g. ``Lake_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    budget_file : str or None
    final_elev_file : str or None
    n_lakes : int
    lake_params : pd.DataFrame
        Per-lake parameters: lake_id, max_elev_col, precip_col, et_col,
        outflow_type, outflow_dest.
    max_elev_spec : TimeSeriesSpec
    max_elev_data : pd.DataFrame or None
    """

    header: FileHeader = field(default_factory=FileHeader)
    budget_file: str | None = None
    final_elev_file: str | None = None
    n_lakes: int = 0
    lake_params: Any = None  # DataFrame
    max_elev_spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    max_elev_data: Any = None  # DataFrame
    max_elev_file: str | None = None
