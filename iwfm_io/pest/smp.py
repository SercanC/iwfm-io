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

Two DWR-toolchain extensions are supported: an optional trailing ``x``
field flags a record as excluded (returned as a boolean ``excluded``
column and written back), and ``fixed_width=True`` reads the IWFM2OBS
fixed-column layout (site 1–25, date 26–37, time 38–49, value 50–60,
flag 61+) — required when site names contain spaces.

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

import numpy as np
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


def _read_fixed_width(path) -> "pd.DataFrame":
    """Read the IWFM2OBS fixed-column SMP layout into string columns."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            rows.append((line[:25].strip(), line[25:37].strip(),
                         line[37:49].strip(), line[49:60].strip(),
                         line[60:].strip()))
    df = pd.DataFrame(rows, columns=["site", "date", "time", "value",
                                     "flag"])
    return df.mask(df == "")  # empty fields -> NaN, like the split reader


def read_smp(path, date_format: Optional[str] = None,
             fixed_width: bool = False) -> "pd.DataFrame":
    """Read a PEST SMP bore-sample file.

    Parameters
    ----------
    path : str or Path
    date_format : {"dd/mm/yyyy", "mm/dd/yyyy"}, optional
        Date convention. Default auto-detects from the data and raises
        if every component is <= 12 (ambiguous).
    fixed_width : bool, default False
        Read by the IWFM2OBS column layout (site 1–25, date 26–37,
        time 38–49, value 50–60, flag 61+) instead of splitting on
        whitespace. Required when site names contain spaces.

    Returns
    -------
    pandas.DataFrame
        Long-form ``site, datetime, value, excluded``. Non-numeric
        values (e.g. ``dry`` markers) become NaN with a logged warning;
        ``excluded`` is True for records carrying the trailing ``x``
        flag.
    """
    path = Path(path)
    if fixed_width:
        df = _read_fixed_width(path)
    else:
        df = pd.read_csv(
            path, sep=r"\s+", header=None, dtype=str, comment=None,
            names=["site", "date", "time", "value", "flag"],
        )
    missing = df[["site", "date", "time"]].isna().any(axis=1)
    if missing.any():
        raise ValueError(
            f"{path}: {int(missing.sum())} malformed line(s) with fewer "
            f"than 4 fields (first at data line {int(missing.idxmax()) + 1})"
        )
    flag = df["flag"].fillna("").str.strip()
    bad_flag = ~flag.str.casefold().isin(("", "x"))
    if bad_flag.any():
        raise ValueError(
            f"{path}: {int(bad_flag.sum())} record(s) with an unrecognized "
            f"trailing field (expected the 'x' exclusion flag), e.g. "
            f"{sorted(set(flag[bad_flag]))[:3]}"
        )
    if date_format is None:
        date_format = _detect_date_format(df["date"], path)
    elif date_format not in _DATE_FORMATS:
        raise ValueError(
            f"date_format must be one of {sorted(_DATE_FORMATS)}, "
            f"got {date_format!r}"
        )
    # IWFM's end-of-day stamp "24:00:00" is the next day's midnight
    time = df["time"].str.strip()
    is_2400 = time.str.match(r"^24:00(:00)?$")
    time = time.where(~is_2400, "00:00:00")
    when = pd.to_datetime(
        df["date"] + " " + time,
        format=_DATE_FORMATS[date_format] + " %H:%M:%S",
    )
    if is_2400.any():
        when = when + pd.to_timedelta(is_2400.astype(int), unit="D")
    values = pd.to_numeric(df["value"], errors="coerce")
    n_bad = int(values.isna().sum() - df["value"].isna().sum())
    if n_bad:
        logger.warning("%s: %d non-numeric value(s) read as NaN", path, n_bad)
    return pd.DataFrame({
        "site": df["site"].str.strip(),
        "datetime": when,
        "value": values,
        "excluded": flag.str.casefold() == "x",
    })


def write_smp(df, path, date_format: str = "dd/mm/yyyy",
              max_site_len: Optional[int] = 10, sort: bool = True,
              float_format: str = "%15.6E") -> None:
    """Write a PEST SMP bore-sample file.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value``; a boolean ``excluded``
        column writes the trailing ``x`` flag on flagged records.
        Other extra columns are ignored.
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
    SMP has no missing-value marker: records with a NaN value are dropped
    (logged), while an infinite value or a missing datetime raises
    ``ValueError``. The file is
    written atomically (temp + rename), preserving the
    ``create_scenario`` hardlink invariant.
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
        "excluded": (df["excluded"].fillna(False).astype(bool).values
                     if "excluded" in df.columns else False),
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
    vals = out["value"].to_numpy(dtype=float)
    if np.isinf(vals).any():
        idx = int(np.argmax(np.isinf(vals)))
        raise ValueError(
            f"{int(np.isinf(vals).sum())} infinite value(s) (SMP has no "
            f"marker for them), e.g. site {out['site'].iloc[idx]!r}")
    nan_value = np.isnan(vals)
    if nan_value.any():
        # missing readings are normal in observation records: drop them
        # (logged) rather than writing a literal 'nan'
        logger.warning("write_smp: dropping %d record(s) with NaN values",
                       int(nan_value.sum()))
        out = out[~nan_value].reset_index(drop=True)
    bad_time = out["datetime"].isna()
    if bad_time.any():
        idx = int(np.argmax(bad_time.to_numpy()))
        raise ValueError(
            f"{int(bad_time.sum())} row(s) have a missing datetime, e.g. "
            f"site {out['site'].iloc[idx]!r} -- drop those rows first")
    if sort:
        out = out.sort_values(["site", "datetime"], kind="stable")

    width = max(10, int(out["site"].str.len().max()) if len(out) else 10)
    stamp = out["datetime"].dt.strftime(_DATE_FORMATS[date_format] + " %H:%M:%S")
    lines = [
        f"{site:<{width}}  {when}  {float_format % value}"
        + ("  x" if excluded else "")
        for site, when, value, excluded in zip(
            out["site"], stamp, out["value"], out["excluded"])
    ]
    replace_file_text(Path(path), "\n".join(lines) + "\n")
