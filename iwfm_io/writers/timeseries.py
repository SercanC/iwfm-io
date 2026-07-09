"""
Writers for IWFM time-series input files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.timeseries import (
    ETFile,
    IrigFracFile,
    PrecipFile,
    SupplyAdjustFile,
    TimeSeriesFile,
)


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

    ET uses a 4-param header (no DSSFL line).

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

    3-param header: NCOL, NSP, NFQ.

    Parameters
    ----------
    irig : IrigFracFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(irig.header)

    w.write_keyed_value(irig.n_columns, "NCOLIRF")
    w.write_keyed_value(irig.n_steps_update, "NSPIRF")
    w.write_keyed_value(irig.repeat_freq, "NFQIRF")
    w.write_keyed_value("", "DSSFL")

    if irig.data is not None:
        w.write_timeseries_data(irig.data)

    w.flush()


def write_supply_adjust(sa: SupplyAdjustFile, path: str | Path) -> None:
    """Write an IWFM supply adjustment file.

    3-param header: NCOL, NSP, NFQ.

    Parameters
    ----------
    sa : SupplyAdjustFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sa.header)

    w.write_keyed_value(sa.n_columns, "NCOLADJ")
    w.write_keyed_value(sa.n_steps_update, "NSPADJ")
    w.write_keyed_value(sa.repeat_freq, "NFQADJ")
    w.write_keyed_value("", "DSSFL")

    if sa.data is not None:
        w.write_timeseries_data(sa.data)

    w.flush()
