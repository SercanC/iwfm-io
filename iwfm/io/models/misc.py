"""Dataclasses for miscellaneous IWFM files (SWShed, UnsatZone)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm.io.models.base import FileHeader


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
        Parameters (FACTA, FACTQ, TUNITQ, TOLER, ITERMAX, etc.).
    watershed_data : pd.DataFrame or None
        Per-watershed definitions.
    raw_lines : list[str]
        Remaining unparsed lines.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    n_watersheds: int = 0
    config: dict = field(default_factory=dict)
    watershed_data: Any = None
    raw_lines: list[str] = field(default_factory=list)


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
        Additional parameters.
    raw_lines : list[str]
        Remaining unparsed lines.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_unsat_layers: int = 0
    convergence: float = 0.001
    max_iterations: int = 150
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    raw_lines: list[str] = field(default_factory=list)
