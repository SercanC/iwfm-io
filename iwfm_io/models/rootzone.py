"""Dataclasses for IWFM root zone component files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader


@dataclass
class RootZoneMain:
    """Parsed root zone component main file (e.g. ``RootZone_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    convergence : float
        RZCONV convergence criterion.
    max_iterations : int
        RZITERMX maximum iterations.
    factor_cn : float
        FACTCN conversion factor (e.g., in→ft).
    gw_uptake : int
        GWUPTK flag.
    file_paths : dict[str, str or None]
        References to sub-component files.
    config : dict
        Soil parameters, conversion factors, etc.
    element_params : pd.DataFrame or None
        Per-element soil parameters.
    raw_lines : list[str]
        Remaining unparsed lines (for round-trip).
    """

    header: FileHeader = field(default_factory=FileHeader)
    convergence: float = 0.001
    max_iterations: int = 150
    factor_cn: float = 1.0
    gw_uptake: int = 0
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    element_params: Any = None
    raw_lines: list[str] = field(default_factory=list)
