"""
PEST SMP (bore sample) file reader/writer.

SMP is the interchange format of the established IWFM calibration
toolchain: DWR's Fortran utilities (IWFM2OBS and relatives) and the
cfbrush/iwfm ``calib`` module both consume and produce it. One record per
line, whitespace-delimited::

    site_id    dd/mm/yyyy    hh:mm:ss    value

:func:`read_smp` returns the package's standard long-form frame
(``site, datetime, value`` — the same columns as
``iwfm_io.collect_hydrographs``); :func:`write_smp` regenerates a file
from it, round-trip safe.

Date convention: the PEST standard is day-first (``dd/mm/yyyy``), but
US-locale toolchains (including DWR workflows) commonly use
month-first (``mm/dd/yyyy``). :func:`read_smp` auto-detects when the data
disambiguates it (any first component > 12 → day-first, any second
component > 12 → month-first) and refuses to guess otherwise — pass
``date_format`` explicitly for genuinely ambiguous files. A wrong guess
here would silently corrupt every date, so ambiguity is an error, not a
warning.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from iwfm_io._writer import replace_file_text

__all__ = ["read_smp", "write_smp"]

logger = logging.getLogger(__name__)

#: accepted ``date_format`` values → strftime equivalents
_DATE_FORMATS = {"dd/mm/yyyy": "%d/%m/%Y", "mm/dd/yyyy": "%m/%d/%Y"}


def _detect_date_format(dates: "pd.Series", path) -> str:
    first = dates.str.split("/").str[0].astype(int)
    second = dates.str.split("/").str[1].astype(int)
    if (first > 12).any():
        return "dd/mm/yyyy"
    if (second > 12).any():
        return "mm/dd/yyyy"
    raise ValueError(
        f"cannot auto-detect the date convention of {path}: every "
        f"day/month component is <= 12; pass "
        f"date_format='dd/mm/yyyy' or 'mm/dd/yyyy' explicitly"
    )


def read_smp(path, date_format: Optional[str] = None) -> "pd.DataFrame":
    """Read a PEST SMP bore-sample file.

    Parameters
    ----------
    path : str or Path
    date_format : {"dd/mm/yyyy", "mm/dd/yyyy"}, optional
        Date convention. Default auto-detects from the data and raises
        if every component is <= 12 (ambiguous).

    Returns
    -------
    pandas.DataFrame
        Long-form ``site, datetime, value``. Non-numeric values (e.g.
        ``dry`` markers) become NaN with a logged warning.
    """
    path = Path(path)
    df = pd.read_csv(
        path, sep=r"\s+", header=None, dtype=str, comment=None,
        names=["site", "date", "time", "value"],
    )
    missing = df[["site", "date", "time"]].isna().any(axis=1)
    if missing.any():
        raise ValueError(
            f"{path}: {int(missing.sum())} malformed line(s) with fewer "
            f"than 4 fields (first at data line {int(missing.idxmax()) + 1})"
        )
    if date_format is None:
        date_format = _detect_date_format(df["date"], path)
    elif date_format not in _DATE_FORMATS:
        raise ValueError(
            f"date_format must be one of {sorted(_DATE_FORMATS)}, "
            f"got {date_format!r}"
        )
    when = pd.to_datetime(
        df["date"] + " " + df["time"],
        format=_DATE_FORMATS[date_format] + " %H:%M:%S",
    )
    values = pd.to_numeric(df["value"], errors="coerce")
    n_bad = int(values.isna().sum() - df["value"].isna().sum())
    if n_bad:
        logger.warning("%s: %d non-numeric value(s) read as NaN", path, n_bad)
    return pd.DataFrame({
        "site": df["site"].str.strip(),
        "datetime": when,
        "value": values,
    })


def write_smp(df, path, date_format: str = "dd/mm/yyyy",
              max_site_len: Optional[int] = 10, sort: bool = True,
              float_format: str = "%15.6E") -> None:
    """Write a PEST SMP bore-sample file.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value`` (extra columns ignored).
    path : str or Path
    date_format : {"dd/mm/yyyy", "mm/dd/yyyy"}, default day-first (PEST
        standard) — use ``"mm/dd/yyyy"`` for DWR/US-locale toolchains.
    max_site_len : int or None, default 10
        Classic PEST utilities limit bore IDs to 10 characters; longer
        names raise. Pass ``None`` to disable the check.
    sort : bool, default True
        Sort by site then time (the ordering SMP consumers expect).
    float_format : str, default ``"%15.6E"``

    Notes
    -----
    Rows with NaN values are dropped (with a logged warning) — SMP has no
    missing-value marker. The file is written atomically (temp + rename),
    preserving the ``create_scenario`` hardlink invariant.
    """
    if date_format not in _DATE_FORMATS:
        raise ValueError(
            f"date_format must be one of {sorted(_DATE_FORMATS)}, "
            f"got {date_format!r}"
        )
    out = pd.DataFrame({
        "site": df["site"].astype(str).str.strip(),
        "datetime": pd.to_datetime(df["datetime"]),
        "value": pd.to_numeric(df["value"]),
    })
    bad_site = out["site"].str.contains(r"\s") | (out["site"] == "")
    if bad_site.any():
        raise ValueError(
            f"{int(bad_site.sum())} site name(s) empty or containing "
            f"whitespace, e.g. {out.loc[bad_site, 'site'].head(3).tolist()}"
        )
    if max_site_len is not None:
        long_names = out["site"].str.len() > max_site_len
        if long_names.any():
            raise ValueError(
                f"{int(long_names.sum())} site name(s) longer than "
                f"{max_site_len} chars (classic PEST limit), e.g. "
                f"{out.loc[long_names, 'site'].drop_duplicates().head(3).tolist()}; "
                f"pass max_site_len=None to allow"
            )
    n_nan = int(out["value"].isna().sum())
    if n_nan:
        logger.warning("%s: dropping %d NaN value row(s)", path, n_nan)
        out = out.dropna(subset=["value"])
    if sort:
        out = out.sort_values(["site", "datetime"], kind="stable")

    width = max(10, int(out["site"].str.len().max()) if len(out) else 10)
    stamp = out["datetime"].dt.strftime(_DATE_FORMATS[date_format] + " %H:%M:%S")
    lines = [
        f"{site:<{width}}  {when}  {float_format % value}"
        for site, when, value in zip(out["site"], stamp, out["value"])
    ]
    replace_file_text(Path(path), "\n".join(lines) + "\n")
