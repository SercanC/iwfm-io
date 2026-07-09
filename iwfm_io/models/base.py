"""Base dataclasses shared across all IWFM file models."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class FileHeader:
    """Metadata from the top of an IWFM file.

    Attributes
    ----------
    version : str or None
        Version string from a ``#4.0`` header, or None.
    comment_lines : list[str]
        Comment lines preceding the first data, preserved for round-trip.
    """

    version: str | None = None
    comment_lines: list[str] = field(default_factory=list)


@dataclass
class ConversionFactor:
    """A conversion factor with its keyword and optional unit label.

    Attributes
    ----------
    value : float
        The numeric factor (e.g. 3.2808 for m→ft).
    keyword : str
        The keyword from the file (e.g. "FACT", "FACTLTOU").
    unit_label : str
        Optional unit string (e.g. "FEET").
    """

    value: float = 1.0
    keyword: str = ""
    unit_label: str = ""


@dataclass
class TimeSeriesSpec:
    """Header parameters for an IWFM time-series data section.

    Attributes
    ----------
    n_columns : int
        Number of data columns (NCOL).
    factor : float
        Conversion factor applied to all values (FACT).
    n_steps_update : int
        Number of timesteps between updates (NSP). 0 or 1 = every step.
    repeat_freq : int
        Repetition frequency flag (NFQ). 0 = no repeat.
    dss_file : str
        Path to HEC-DSS file, or empty string if data is inline.
    """

    n_columns: int = 0
    factor: float = 1.0
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""


@dataclass
class ZoneDefinition:
    """Zone definition for IWFM Z-Budget aggregation.

    Attributes
    ----------
    extent : str
        ``"horizontal"`` (same zones for all layers) or ``"vertical"``
        (layer-specific zone assignments).
    zones : dict[int, str]
        Mapping of zone ID to zone name.
    element_zones : pandas.DataFrame
        Element-to-zone assignments.  Columns are ``[element_id, zone_id]``
        when *extent* is ``"horizontal"``, or ``[element_id, layer, zone_id]``
        when *extent* is ``"vertical"``.
    """

    extent: str = "horizontal"
    zones: dict[int, str] = field(default_factory=dict)
    element_zones: pd.DataFrame = field(default_factory=pd.DataFrame)
