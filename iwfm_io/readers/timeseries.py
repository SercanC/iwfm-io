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
from iwfm_io.models.timeseries import (
    ETFile,
    IrigFracFile,
    PrecipFile,
    SupplyAdjustFile,
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

    The ET file has a 4-param spec (NCOL, FACT, NSP, NFQ) with no DSSFL line,
    followed by inline monthly ET data.

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

    Has a 3-param spec: NCOL, NSP, NFQ (no FACT, no DSSFL).

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
    # Consume optional DSSFL line
    _dss_file, _ = reader.read_keyed_value()

    data = _read_ts_data_to_eof(reader, n_columns)

    return IrigFracFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        data=data,
    )


def read_supply_adjust(path: str | Path) -> SupplyAdjustFile:
    """Read an IWFM supply adjustment file (e.g. ``SupplyAdjust.dat``).

    Has a 3-param spec: NCOL, NSP, NFQ (no FACT, no DSSFL).

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
    # Consume optional DSSFL line
    _dss_file, _ = reader.read_keyed_value()

    data = _read_ts_data_to_eof(reader, n_columns)

    return SupplyAdjustFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        data=data,
    )
