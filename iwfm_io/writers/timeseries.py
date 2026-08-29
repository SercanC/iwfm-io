"""
Writers for IWFM time-series input files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.writers._param_blocks import check_count
from iwfm_io.models.timeseries import (
    ETFile,
    IrigFracFile,
    IrrPeriodFile,
    PrecipFile,
    SupplyAdjustFile,
    TimeSeriesDataFile,
    TimeSeriesFile,
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

    if ts.data is not None:
        check_count(ts.n_columns, len(ts.data.columns) - 1,
                    "Time-series file: NCOL vs data columns")
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
    for i, value in enumerate(values):
        kw = keywords[i] if i < len(keywords) and keywords[i] else defaults[i]
        w.write_keyed_value(value, kw)
    # IWFM's READCH keeps consuming data lines while resolving a blank
    # DSS filename — this terminating comment is load-bearing.
    w.write_comment("C  end of specification")

    if ts.dss_file and ts.dss_pathnames:
        w.write_dss_pathnames(ts.dss_pathnames)
    elif ts.data is not None:
        w.write_timeseries_data(ts.data)

    w.flush()


def write_precip(precip: PrecipFile, path: str | Path) -> None:
    """Write an IWFM precipitation file.

    Parameters
    ----------
    precip : PrecipFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(precip.header)
    w.write_timeseries_spec(
        precip.spec,
        keywords=["NRAIN", "FACTRN", "NSPRN", "NFQRN", "DSSFL"],
    )

    if precip.dss_pathnames:
        w.write_dss_pathnames(precip.dss_pathnames)
    elif precip.data is not None:
        w.write_timeseries_data(precip.data)

    w.flush()


def write_et(et: ETFile, path: str | Path) -> None:
    """Write an IWFM evapotranspiration file.

    Standard 5-param header: NCOLET, FACTET, NSPET, NFQET, DSSFL.

    Parameters
    ----------
    et : ETFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(et.header)

    w.write_timeseries_spec(
        et.spec,
        keywords=["NCOLET", "FACTET", "NSPET", "NFQET", "DSSFL"],
    )

    if et.dss_pathnames:
        w.write_dss_pathnames(et.dss_pathnames)
    elif et.data is not None:
        w.write_timeseries_data(et.data)

    w.flush()


def write_irigfrac(irig: IrigFracFile, path: str | Path) -> None:
    """Write an IWFM irrigation fractions file.

    4-param header: NCOLIRF, NSPIRF, NFQIRF, DSSFL.

    Parameters
    ----------
    irig : IrigFracFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(irig.header)

    if irig.data is not None:
        check_count(irig.n_columns, len(irig.data.columns) - 1,
                    "IrigFrac: NCOL vs data columns")
    w.write_keyed_value(irig.n_columns, "NCOLIRF")
    w.write_keyed_value(irig.n_steps_update, "NSPIRF")
    w.write_keyed_value(irig.repeat_freq, "NFQIRF")
    w.write_keyed_value(irig.dss_file, "DSSFL")
    # IWFM's READCH keeps consuming data lines while resolving a blank
    # DSS filename — this terminating comment is load-bearing.
    w.write_comment("C  end of specification")

    if irig.dss_file and irig.dss_pathnames:
        w.write_dss_pathnames(irig.dss_pathnames)
    elif irig.data is not None:
        w.write_timeseries_data(irig.data)

    w.flush()


def write_irr_period(ip: IrrPeriodFile, path: str | Path) -> None:
    """Write an IWFM irrigation period data file (IPFL).

    4-param header: NCOLIP, NSPIP, NFQIP, DSSFL.

    Parameters
    ----------
    ip : IrrPeriodFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ip.header)

    if ip.data is not None:
        check_count(ip.n_columns, len(ip.data.columns) - 1,
                    "IrrPeriod: NCOL vs data columns")
    w.write_keyed_value(ip.n_columns, "NCOLIP")
    w.write_keyed_value(ip.n_steps_update, "NSPIP")
    w.write_keyed_value(ip.repeat_freq, "NFQIP")
    w.write_keyed_value(ip.dss_file, "DSSFL")
    w.write_comment("C  end of specification")

    if ip.dss_file and ip.dss_pathnames:
        w.write_dss_pathnames(ip.dss_pathnames)
    elif ip.data is not None:
        w.write_timeseries_data(ip.data)

    w.flush()


def write_supply_adjust(sa: SupplyAdjustFile, path: str | Path) -> None:
    """Write an IWFM supply adjustment file.

    4-param header: NCOLADJ, NSPADJ, NFQADJ, DSSFL.

    Parameters
    ----------
    sa : SupplyAdjustFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sa.header)

    if sa.data is not None:
        check_count(sa.n_columns, len(sa.data.columns) - 1,
                    "SupplyAdjust: NCOL vs data columns")
    w.write_keyed_value(sa.n_columns, "NCOLADJ")
    w.write_keyed_value(sa.n_steps_update, "NSPADJ")
    w.write_keyed_value(sa.repeat_freq, "NFQADJ")
    w.write_keyed_value(sa.dss_file, "DSSFL")
    w.write_comment("C  end of specification")

    if sa.dss_file and sa.dss_pathnames:
        w.write_dss_pathnames(sa.dss_pathnames)
    elif sa.data is not None:
        w.write_timeseries_data(sa.data)

    w.flush()
