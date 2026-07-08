"""Dataclasses for IWFM time-series input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm.io.models.base import FileHeader, TimeSeriesSpec


@dataclass
class TimeSeriesFile:
    """Generic time-series file container.

    Attributes
    ----------
    header : FileHeader
    spec : TimeSeriesSpec
    data : pd.DataFrame or None
        DataFrame with DatetimeIndex if inline data.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments if reading from DSS.
    """

    header: FileHeader = field(default_factory=FileHeader)
    spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


# Typed aliases for documentation clarity
PrecipFile = TimeSeriesFile
ETFile = TimeSeriesFile


@dataclass
class IrigFracFile:
    """Irrigation fractions file (e.g. ``IrigFrac.dat``).

    Has a 3-param spec: NCOL, NSP, NFQ (no FACT, no DSSFL).

    Attributes
    ----------
    header : FileHeader
    n_columns : int
    n_steps_update : int
    repeat_freq : int
    data : pd.DataFrame
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_columns: int = 0
    n_steps_update: int = 1
    repeat_freq: int = 0
    data: Any = None  # DataFrame


@dataclass
class SupplyAdjustFile:
    """Supply adjustment file (e.g. ``SupplyAdjust.dat``).

    Has a 3-param spec: NCOL, NSP, NFQ (no FACT, no DSSFL).

    Attributes
    ----------
    header : FileHeader
    n_columns : int
    n_steps_update : int
    repeat_freq : int
    data : pd.DataFrame
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_columns: int = 0
    n_steps_update: int = 1
    repeat_freq: int = 0
    data: Any = None  # DataFrame
