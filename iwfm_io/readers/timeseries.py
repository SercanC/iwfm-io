"""
Readers for IWFM time-series input files (Precip, ET, IrigFrac, SupplyAdjust).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import parse_iwfm_date, tokenize_data_line
from iwfm_io.models.base import TimeSeriesSpec
from iwfm_io._tokens import split_keyed_line
from iwfm_io.models.timeseries import (
    ETFile,
    IrigFracFile,
    IrrPeriodFile,
    PrecipFile,
    SupplyAdjustFile,
    TimeSeriesDataFile,
    TimeSeriesFile,
)


def _read_ts_data_to_eof(
    reader: IWFMFileReader,
    n_columns: int,
    col_names: list[str] | None = None,
) -> pd.DataFrame:
    """Read time-series data rows until EOF.

    Each row: ``DATE  val1  val2  ...``

    The date strings are stored as-is in the ``date`` column because IWFM
    uses special years (4000, 2500) for repeating/cyclic data that are
    outside pandas Timestamp range.
    """
    if col_names is None:
        col_names = [f"col_{i+1}" for i in range(n_columns)]

    date_strs: list[str] = []
    values: list[list[float]] = []

    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if not tokens:
            break
        # Check first token is an IWFM date
        if "/" not in tokens[0] or "_" not in tokens[0]:
            break
        reader.next_data_line()
        row_vals = [float(v) for v in tokens[1 : n_columns + 1]]
        date_strs.append(tokens[0])
        values.append(row_vals)

    if not date_strs:
        return pd.DataFrame(columns=["date"] + col_names)

    df = pd.DataFrame(values, columns=col_names)
    df.insert(0, "date", date_strs)
    return df


def read_timeseries_file(
    path: str | Path,
    has_factor: bool | None = None,
    has_dssfl: bool | None = None,
    columns: list[str] | None = None,
) -> TimeSeriesDataFile:
    """Read any standard IWFM time-series data file.

    Handles all three spec-block shapes found across IWFM inputs:

    - 5-param: NCOL, FACT, NSP, NFQ, DSSFL (e.g. PondDepth, RiceOps,
      PerCapWaterUse, MaxLakeElev)
    - 4-param: NCOL, NSP, NFQ, DSSFL (e.g. RootDepthFrac, MinMoist,
      Population, UrbanWaterUseSpecs, ReturnFlowFrac, ReuseFrac)
    - 3-param: NCOL, NSP, NFQ with no DSSFL line

    The shape is detected from the ``/ KEYWORD`` comments (a FACT* line
    marks the factor, a DSS* line the DSS file); pass *has_factor*
    explicitly for a deck without keyword comments.  Values are stored
    file-native — apply ``factor`` for model units.

    Parameters
    ----------
    path : str or Path
    has_factor : bool, optional
        Whether the spec block carries a FACT line.  Auto-detected from
        the keyword when omitted.
    has_dssfl : bool, optional
        Whether the spec block carries a DSSFL line.  Auto-detected
        when omitted; pass explicitly for keyword-less decks (a truly
        blank DSSFL line without a ``/ DSSFL`` tag is otherwise
        indistinguishable from a blank line).
    columns : list[str], optional
        Names for the data columns (default ``col_1..col_N``).

    Returns
    -------
    TimeSeriesDataFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    keywords: list[str] = []

    def _keyed():
        value, kw = reader.read_keyed_value()
        keywords.append(kw.split()[0] if kw else "")
        return value

    n_columns = int(_keyed())

    # FACT line: detect by keyword unless the caller decided
    if has_factor is None:
        line = reader.peek_data_line()
        _, kw = split_keyed_line(line) if line is not None else ("", "")
        has_factor = bool(kw) and kw.split()[0].upper().startswith("FACT")
    factor = float(_keyed()) if has_factor else None

    n_steps_update = int(_keyed())
    repeat_freq = int(_keyed())

    # DSSFL line: present in most layouts, absent in a few (e.g.
    # SurfaceFlowDest).  A data row starts with an IWFM date, which a
    # DSSFL value never resembles.
    dss_file = ""
    if has_dssfl is None:
        has_dssfl = False
        line = reader.peek_data_line()
        if line is not None:
            value, kw = split_keyed_line(line)
            kw1 = kw.split()[0].upper() if kw else ""
            first_tok = value.split()[0] if value.split() else ""
            looks_like_date = "/" in first_tok and "_" in first_tok
            if kw1.startswith("DSS") or (not kw and not looks_like_date):
                has_dssfl = True
    if has_dssfl:
        dss_file = _keyed()

    result = TimeSeriesDataFile(
        header=header,
        keywords=keywords,
        n_columns=n_columns,
        factor=factor,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
        has_dssfl=has_dssfl,
    )

    if dss_file:
        spec = TimeSeriesSpec(n_columns=n_columns, dss_file=dss_file)
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = _read_ts_data_to_eof(reader, n_columns,
                                           col_names=columns)

    return result


def read_precip(path: str | Path) -> PrecipFile:
    """Read an IWFM precipitation file (e.g. ``Precip.dat``).

    The precip file has a 5-param time-series spec (NCOL, FACT, NSP, NFQ, DSSFL).
    If DSSFL is non-empty, DSS pathnames follow instead of inline data.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    PrecipFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    spec = reader.read_timeseries_spec()

    result = PrecipFile(header=header, spec=spec)

    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = _read_ts_data_to_eof(reader, spec.n_columns)

    return result


def read_et(path: str | Path) -> ETFile:
    """Read an IWFM evapotranspiration file (e.g. ``ET.dat``).

    The ET file has the standard 5-param spec (NCOLET, FACTET, NSPET,
    NFQET, DSSFL), followed by inline monthly ET data (or DSS pathnames
    when DSSFL is set).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    ETFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    # ET uses the standard 5-param time-series spec
    spec = reader.read_timeseries_spec()

    if spec.dss_file:
        data = None
        dss_pathnames = reader.read_dss_pathnames(spec)
        return ETFile(header=header, spec=spec, data=data, dss_pathnames=dss_pathnames)

    data = _read_ts_data_to_eof(reader, spec.n_columns)
    return ETFile(header=header, spec=spec, data=data)


def read_irigfrac(path: str | Path) -> IrigFracFile:
    """Read an IWFM irrigation fractions file (e.g. ``IrigFrac.dat``).

    Has a 4-param spec: NCOLIRF, NSPIRF, NFQIRF, DSSFL (no FACT).  When
    DSSFL is set, the DSS pathname assignments are read instead of
    inline data.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    IrigFracFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_columns, _ = reader.read_keyed_int()
    n_steps_update, _ = reader.read_keyed_int()
    repeat_freq, _ = reader.read_keyed_int()
    dss_file, _ = reader.read_keyed_value()

    result = IrigFracFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
    )
    if dss_file:
        spec = TimeSeriesSpec(n_columns=n_columns, dss_file=dss_file)
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = _read_ts_data_to_eof(reader, n_columns)
    return result


def read_irr_period(path: str | Path) -> IrrPeriodFile:
    """Read an IWFM irrigation period data file (IPFL, e.g. ``IrigPeriod.dat``).

    Has a 4-param spec: NCOLIP, NSPIP, NFQIP, DSSFL (no FACT), then rows
    of ``DATE  flag1 .. flagNCOLIP`` 0/1 flags (1 = irrigation period),
    usually a recurring year-4000 pattern.  The root-zone main exposes
    this file's path as ``file_paths['irig_period']``; the ICIP pointer
    table (``NonPondedAgFile.irig_period_columns``) maps each
    (element, crop) to one of the 1-based flag columns.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    IrrPeriodFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_columns, _ = reader.read_keyed_int()
    n_steps_update, _ = reader.read_keyed_int()
    repeat_freq, _ = reader.read_keyed_int()
    dss_file, _ = reader.read_keyed_value()

    result = IrrPeriodFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
    )

    if dss_file:
        spec = TimeSeriesSpec(n_columns=n_columns, dss_file=dss_file)
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        data = _read_ts_data_to_eof(reader, n_columns)
        for col in data.columns[1:]:
            data[col] = data[col].astype(int)
        result.data = data

    return result


def read_supply_adjust(path: str | Path) -> SupplyAdjustFile:
    """Read an IWFM supply adjustment file (e.g. ``SupplyAdjust.dat``).

    Has a 4-param spec: NCOLADJ, NSPADJ, NFQADJ, DSSFL (no FACT).  When
    DSSFL is set, the DSS pathname assignments are read instead of
    inline data.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SupplyAdjustFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_columns, _ = reader.read_keyed_int()
    n_steps_update, _ = reader.read_keyed_int()
    repeat_freq, _ = reader.read_keyed_int()
    dss_file, _ = reader.read_keyed_value()

    result = SupplyAdjustFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
    )
    if dss_file:
        spec = TimeSeriesSpec(n_columns=n_columns, dss_file=dss_file)
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = _read_ts_data_to_eof(reader, n_columns)
    return result
