"""Dataclasses for IWFM time-series input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader, TimeSeriesSpec


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
class TimeSeriesDataFile:
    """Generic IWFM time-series data file.

    Covers every input file with the standard layout — a spec block of
    keyed lines (NCOL, optional FACT, NSP, NFQ, optional DSSFL), then
    rows of ``DATE  v1 .. vNCOL`` (or DSS pathname assignments).  Use
    :func:`iwfm_io.read_timeseries_file` for e.g. the root-zone leaf
    files: RootDepthFrac, MinMoist, PondDepth, RiceOps, Population,
    PerCapWaterUse, UrbanWaterUseSpecs, ReturnFlowFrac, ReuseFrac.

    Attributes
    ----------
    header : FileHeader
    keywords : list[str]
        The spec keywords exactly as the file carried them (e.g.
        ``["NCOLRT", "NSPRT", "NFQRT", "DSSFL"]``), replayed on write.
    n_columns : int
    factor : float or None
        Conversion factor; None when the spec has no FACT line
        (4-param files).
    n_steps_update : int
    repeat_freq : int
    dss_file : str
        DSSFL value; empty when data is inline.
    has_dssfl : bool
        Whether the spec block carries a DSSFL line at all.
    data : pd.DataFrame or None
        ``date`` (kept as strings — recurring-year data uses years
        4000/2500) + ``col_1..col_N`` float columns.
    dss_pathnames : list[tuple[int, str]]
    """

    header: FileHeader = field(default_factory=FileHeader)
    keywords: list[str] = field(default_factory=list)
    n_columns: int = 0
    factor: float | None = None
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""
    has_dssfl: bool = True
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class IrigFracFile:
    """Irrigation fractions file (e.g. ``IrigFrac.dat``).

    Has a 4-param spec: NCOLIRF, NSPIRF, NFQIRF, DSSFL (no FACT).

    Attributes
    ----------
    header : FileHeader
    n_columns : int
    n_steps_update : int
    repeat_freq : int
    dss_file : str
        DSSFL — empty when the fractions are inline in this file.
    data : pd.DataFrame
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments when *dss_file* is set.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_columns: int = 0
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class IrrPeriodFile:
    """Irrigation period data file (IPFL, e.g. ``IrigPeriod.dat``).

    Has a 4-param spec: NCOLIP, NSPIP, NFQIP, DSSFL (no FACT).

    Attributes
    ----------
    header : FileHeader
    n_columns : int
        NCOLIP — number of irrigation-period data columns.  The ICIP
        pointer table in the non-ponded ag main file
        (``NonPondedAgFile.irig_period_columns``) maps each
        (element, crop) to one of these 1-based columns.
    n_steps_update : int
    repeat_freq : int
    dss_file : str
        DSSFL — empty when the flags are inline in this file.
    data : pd.DataFrame or None
        Long DataFrame ``date, col_1 .. col_NCOLIP`` of 0/1 flags
        (1 = irrigation period).  Dates are kept as strings because
        recurring-year data uses year 4000.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments when *dss_file* is set.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_columns: int = 0
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class SupplyAdjustFile:
    """Supply adjustment file (e.g. ``SupplyAdjust.dat``).

    Has a 4-param spec: NCOLADJ, NSPADJ, NFQADJ, DSSFL (no FACT).

    Attributes
    ----------
    header : FileHeader
    n_columns : int
    n_steps_update : int
    repeat_freq : int
    dss_file : str
        DSSFL — empty when the adjustment flags are inline.
    data : pd.DataFrame
        KADJ flags are two-digit codes (ag digit, urban digit) stored
        as floats — e.g. ``10`` = adjust ag only, ``1`` = urban only.
    dss_pathnames : list[tuple[int, str]]
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_columns: int = 0
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)
