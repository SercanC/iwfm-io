"""
Writers for IWFM time-series input files.

Every writer here is a thin caller of
:func:`iwfm_io.writers._timeseries.write_ts_body`, which owns the spec
block, its load-bearing terminating comment and the NCOL checks.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.writers._timeseries import write_ts_body
from iwfm_io.models.timeseries import (
    ETFile,
    IrigFracFile,
    IrrPeriodFile,
    PrecipFile,
    SupplyAdjustFile,
    TimeSeriesDataFile,
)


def write_timeseries_file(ts: TimeSeriesDataFile, path: str | Path) -> None:
    """Write a standard IWFM time-series data file.

    Mirrors :func:`iwfm_io.read_timeseries_file`: the spec block is
    replayed with the file's original keywords (falling back to generic
    ones), followed by the load-bearing end-of-spec comment and the
    inline data or DSS pathname assignments.

    Parameters
    ----------
    ts : TimeSeriesDataFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ts.header)

    values: list = [ts.n_columns]
    defaults = ["NCOL"]
    if ts.factor is not None:
        values.append(ts.factor)
        defaults.append("FACT")
    values.extend([ts.n_steps_update, ts.repeat_freq])
    defaults.extend(["NSP", "NFQ"])
    if ts.has_dssfl:
        values.append(ts.dss_file or "")
        defaults.append("DSSFL")

    keywords = list(ts.keywords)
    fields = []
    for i, value in enumerate(values):
        kw = keywords[i] if i < len(keywords) and keywords[i] else defaults[i]
        fields.append((value, kw))

    write_ts_body(w, fields, ts.data,
                  ts.dss_pathnames if ts.dss_file else None,
                  n_columns=ts.n_columns)
    w.flush()


def _write_5param(ts, path: str | Path, keywords: list[str]) -> None:
    """A 5-parameter (NCOL FACT NSP NFQ DSSFL) time-series file."""
    w = IWFMFileWriter(path)
    w.write_header(ts.header)
    spec = ts.spec
    fields = list(zip(
        [spec.n_columns, spec.factor, spec.n_steps_update,
         spec.repeat_freq, spec.dss_file], keywords))
    write_ts_body(w, fields, ts.data, ts.dss_pathnames,
                  n_columns=spec.n_columns)
    w.flush()


def _write_4param(ts, path: str | Path, keywords: list[str]) -> None:
    """A 4-parameter (NCOL NSP NFQ DSSFL, no factor) time-series file."""
    w = IWFMFileWriter(path)
    w.write_header(ts.header)
    fields = list(zip(
        [ts.n_columns, ts.n_steps_update, ts.repeat_freq, ts.dss_file],
        keywords))
    write_ts_body(w, fields, ts.data,
                  ts.dss_pathnames if ts.dss_file else None,
                  n_columns=ts.n_columns)
    w.flush()


def write_precip(precip: PrecipFile, path: str | Path) -> None:
    """Write an IWFM precipitation file.

    Parameters
    ----------
    precip : PrecipFile
    path : str or Path
    """
    _write_5param(precip, path,
                  ["NRAIN", "FACTRN", "NSPRN", "NFQRN", "DSSFL"])


def write_et(et: ETFile, path: str | Path) -> None:
    """Write an IWFM evapotranspiration file.

    Standard 5-param header: NCOLET, FACTET, NSPET, NFQET, DSSFL.

    Parameters
    ----------
    et : ETFile
    path : str or Path
    """
    _write_5param(et, path, ["NCOLET", "FACTET", "NSPET", "NFQET", "DSSFL"])


def write_irigfrac(irig: IrigFracFile, path: str | Path) -> None:
    """Write an IWFM irrigation fractions file.

    4-param header: NCOLIRF, NSPIRF, NFQIRF, DSSFL.

    Parameters
    ----------
    irig : IrigFracFile
    path : str or Path
    """
    _write_4param(irig, path, ["NCOLIRF", "NSPIRF", "NFQIRF", "DSSFL"])


def write_irr_period(ip: IrrPeriodFile, path: str | Path) -> None:
    """Write an IWFM irrigation period data file (IPFL).

    4-param header: NCOLIP, NSPIP, NFQIP, DSSFL.

    Parameters
    ----------
    ip : IrrPeriodFile
    path : str or Path
    """
    _write_4param(ip, path, ["NCOLIP", "NSPIP", "NFQIP", "DSSFL"])


def write_supply_adjust(sa: SupplyAdjustFile, path: str | Path) -> None:
    """Write an IWFM supply adjustment file.

    4-param header: NCOLADJ, NSPADJ, NFQADJ, DSSFL.

    Parameters
    ----------
    sa : SupplyAdjustFile
    path : str or Path
    """
    _write_4param(sa, path, ["NCOLADJ", "NSPADJ", "NFQADJ", "DSSFL"])
