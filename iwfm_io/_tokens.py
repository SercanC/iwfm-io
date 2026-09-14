"""
Line classification and date parsing for IWFM text files.

IWFM conventions:
- Comment lines start with C, c, or * in column 1 (IWFM's
  ``f_cCommentIndicators = 'Cc*'``).  A ``/`` is NOT a comment marker:
  a line whose first non-blank character is ``/`` is a DATA line whose
  value is empty — IWFM consumes it as one (blank) entry, e.g.
  C2VSimFG disables optional outputs with ``/  path  / HTPOUTFL``.
- Date format: MM/DD/YYYY_HH:MM (hour 24:00 = end of day)
- Version headers: lines starting with # (e.g., #4.0)
- Key-value: VALUE / KEYWORD description (Fortran list-directed reads
  stop at the /, which is why trailing comments are transparent)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Characters that mark a comment line when in column 1
_COMMENT_CHARS = frozenset("Cc*")

# Pattern for IWFM date strings: MM/DD/YYYY_HH:MM
_DATE_RE = re.compile(
    r"(\d{2})/(\d{2})/(\d{4})_(\d{2}):(\d{2})"
)


def is_comment(line: str) -> bool:
    """Return True if *line* is a comment or blank line in IWFM format.

    IWFM comment characters (C, c, *) must appear in **column 1** of
    the raw line (no leading whitespace).  Lines that start with
    whitespace are data lines even if a comment character appears
    later.  A line whose first non-blank character is ``/`` is NOT a
    comment — it is a data line with an empty value (see module doc).
    """
    if not line or not line.strip():
        return True
    return line[0] in _COMMENT_CHARS


def is_version_header(line: str) -> bool:
    """Return True if *line* is a version header (e.g., ``#4.0``)."""
    return line.lstrip().startswith("#")


def parse_version_header(line: str) -> str:
    """Extract version string from a header line like ``#4.0``."""
    return line.strip().lstrip("#").strip()


def parse_iwfm_date(date_str: str) -> datetime:
    """Parse an IWFM date string ``MM/DD/YYYY_HH:MM`` into a datetime.

    IWFM uses hour 24:00 to mean midnight at the *end* of the given day,
    which is equivalent to 00:00 of the next day.  The whole string must
    be a date (surrounding whitespace is ignored); ``24:MM`` with a
    nonzero minute and hours above 24 are rejected rather than silently
    rounded.

    Parameters
    ----------
    date_str : str
        Date string in ``MM/DD/YYYY_HH:MM`` format.

    Returns
    -------
    datetime
    """
    if not isinstance(date_str, str):
        raise TypeError(
            f"IWFM date must be a string, got {type(date_str).__name__}")
    m = _DATE_RE.fullmatch(date_str.strip())
    if m is None:
        raise ValueError(f"Cannot parse IWFM date: {date_str!r} "
                         "(expected MM/DD/YYYY_HH:MM)")
    month, day, year, hour, minute = (int(g) for g in m.groups())
    if hour > 24 or minute > 59:
        raise ValueError(f"Invalid time of day in IWFM date: {date_str!r}")
    if hour == 24:
        if minute != 0:
            raise ValueError(
                f"Hour 24 must be 24:00 in IWFM date: {date_str!r}")
        # 24:00 means end of day -> start of next day
        return datetime(year, month, day) + timedelta(days=1)
    return datetime(year, month, day, hour, minute)


def is_iwfm_date(text) -> bool:
    """True when *text* is a complete, valid IWFM date (``MM/DD/YYYY_HH:MM``).

    Sentinel years used by recurring data (2500, 4000) are valid dates.
    """
    try:
        parse_iwfm_date(text)
    except (TypeError, ValueError):
        return False
    return True


def format_iwfm_date(dt: datetime) -> str:
    """Format a datetime as an IWFM date string ``MM/DD/YYYY_HH:MM``.

    If the time is midnight (00:00), this is formatted as 24:00 of the
    *previous* day to follow IWFM convention.

    Parameters
    ----------
    dt : datetime

    Returns
    -------
    str
    """
    if dt.hour == 0 and dt.minute == 0:
        prev = dt - timedelta(days=1)
        return f"{prev.month:02d}/{prev.day:02d}/{prev.year:04d}_24:00"
    return f"{dt.month:02d}/{dt.day:02d}/{dt.year:04d}_{dt.hour:02d}:{dt.minute:02d}"


def iwfm_day(times):
    """The day each timestamp *belongs to* under the ``24:00`` convention.

    IWFM stamps a period at the first instant after it ends, so a value
    for ``09/30/2024_24:00`` parses to ``10/01/2024 00:00`` — the
    correct instant, but the value belongs to September 30. This helper
    returns that owning day: midnight stamps map to the **previous**
    day, any other time of day maps to its own day.

    Use it (not the raw index) whenever you group IWFM output by day,
    month, or year; :func:`water_year` builds on it.

    Parameters
    ----------
    times : str, datetime, pandas Series, DatetimeIndex, or array-like
        A single IWFM date string / datetime, or a vector of datetimes.

    Returns
    -------
    Normalized (midnight) timestamp(s) of the owning day — a
    ``pd.Timestamp`` for scalar input, a Series for Series input, a
    ``DatetimeIndex`` otherwise.
    """
    import pandas as pd

    if isinstance(times, str):
        times = parse_iwfm_date(times)
    if isinstance(times, datetime):  # includes pd.Timestamp
        return (pd.Timestamp(times) - pd.Timedelta(seconds=1)).normalize()
    if isinstance(times, pd.Series):
        return (pd.to_datetime(times)
                - pd.Timedelta(seconds=1)).dt.normalize()
    idx = pd.DatetimeIndex(pd.to_datetime(times))
    return (idx - pd.Timedelta(seconds=1)).normalize()


def _maybe_day_index(df, day_index):
    """Optionally re-index a DatetimeIndex frame by the owning day.

    IWFM stamps each value at the first instant after its period ends
    (``24:00`` = next-day midnight); with ``day_index=True`` the frame
    is re-indexed by :func:`iwfm_day` so calendar idioms —
    ``resample("YE-SEP")``, ``.dt.year``, ``.dt.month`` — label periods
    correctly. The underlying timestamps are unchanged elsewhere.
    Shared by ``IOModelAdapter`` and the DLL ``IWFMModel`` ``*_df``
    methods.
    """
    if not day_index:
        return df
    out = df.copy(deep=False)
    out.index = iwfm_day(df.index)
    return out


def water_year(times):
    """Water year each timestamp belongs to (Oct 1 – Sep 30, labeled by
    the ending year), honoring the ``24:00`` convention via
    :func:`iwfm_day` — so a ``09/30_24:00`` stamp closes the water year
    ending that day, and an ``10/01_24:00`` stamp opens the next one.

    Parameters
    ----------
    times : str, datetime, pandas Series, DatetimeIndex, or array-like

    Returns
    -------
    ``int`` for scalar input, an integer Series/Index otherwise.
    """
    import pandas as pd

    d = iwfm_day(times)
    if isinstance(d, pd.Timestamp):
        return int(d.year + (1 if d.month >= 10 else 0))
    if isinstance(d, pd.Series):
        return d.dt.year + (d.dt.month >= 10).astype(int)
    return pd.Index(d.year + (d.month >= 10).astype(int))


#: Years at or above this are IWFM recurring-data sentinels
#: (2500 = constant / recurring, 4000 = recurring pattern). Real
#: simulations reaching 2100 (end-of-century climate runs) stay real.
_RECURRING_YEAR = 2500


def is_recurring_year(year) -> bool:
    """True when *year* is an IWFM recurring-data sentinel (2500, 4000, ...)."""
    return int(year) >= _RECURRING_YEAR


def expand_recurring(data, begin, end):
    """Expand IWFM recurring-year time-series data onto a real period.

    IWFM marks non-time-tracked, recurring data with sentinel years
    (4000 for e.g. a repeating monthly pattern, 2500 for a single
    constant entry).  This maps such data onto the calendar between
    *begin* and *end*: each pattern stamp recurs in every simulation
    year (day 29 February entries fall back to 28 February in
    non-leap years), and a single-entry table becomes one stamp at
    *begin* whatever its date (decks mark constants with 2100, 2500 or
    4000 alike).  Multi-row data whose dates are real calendar years is
    returned unchanged.  Values are step functions: each value applies from its
    stamp until the next one, matching IWFM semantics.

    Parameters
    ----------
    data : pd.DataFrame
        With a ``date`` column of IWFM date strings (as produced by the
        time-series readers).
    begin, end : str or datetime
        Period bounds — IWFM date strings (e.g. ``SimulationMain
        .sim_begin`` / ``.sim_end``) or datetimes.

    Returns
    -------
    pd.DataFrame
        Same value columns, ``date`` as real ``pd.Timestamp``s within
        ``[begin, end]``, sorted.
    """
    import pandas as pd

    if isinstance(begin, str):
        begin = parse_iwfm_date(begin)
    if isinstance(end, str):
        end = parse_iwfm_date(end)

    parsed = [parse_iwfm_date(d) for d in data["date"]]
    if not parsed:
        return data.copy()
    value_cols = [c for c in data.columns if c != "date"]
    if len(data) == 1:
        # a single record is a constant for the whole period whatever
        # its stamp (decks use 2100, 2500 or 4000 as "far future")
        out = pd.DataFrame({"date": [pd.Timestamp(begin)]})
        for c in value_cols:
            out[c] = data[c].iloc[0]
        return out
    if not any(is_recurring_year(p.year) for p in parsed):
        out = data.copy()
        out["date"] = pd.to_datetime(parsed)
        return out[(out["date"] >= begin) & (out["date"] <= end)]             .sort_values("date").reset_index(drop=True)

    rows = []
    for year in range(begin.year - 1, end.year + 1):
        for stamp, (_, row) in zip(parsed, data.iterrows()):
            day = stamp.day
            while True:
                try:
                    t = pd.Timestamp(year=year, month=stamp.month,
                                     day=day, hour=stamp.hour,
                                     minute=stamp.minute)
                    break
                except ValueError:  # e.g. 29 Feb in a non-leap year
                    if day <= 28:
                        raise
                    day -= 1
            rows.append([t] + [row[c] for c in value_cols])
    out = pd.DataFrame(rows, columns=["date"] + value_cols)
    out = out.sort_values("date").reset_index(drop=True)
    begin_ts, end_ts = pd.Timestamp(begin), pd.Timestamp(end)
    # step-function semantics: the pattern value in effect at *begin*
    # (the last stamp at or before it) applies from *begin* onward
    before = out[out["date"] <= begin_ts]
    inside = out[(out["date"] > begin_ts) & (out["date"] <= end_ts)]
    if len(before):
        carry = before.iloc[[-1]].copy()
        carry["date"] = begin_ts
        inside = carry if inside.empty else pd.concat([carry, inside],
                                                       ignore_index=True)
    return inside.reset_index(drop=True)


# Pattern to find the keyword separator: whitespace followed by /, or a /
# glued to a number and followed by whitespace (``441/ ND``,
# ``31745/ Carrier Canal`` -- Fortran list-directed reads stop at the
# slash regardless). Slashes inside dates (09/30/1990) and inside paths
# (``../Results/GW.hdf``, ``v1.5/Simulation``) never match.
_KEYED_SEP_RE = re.compile(r"\s+/|(?<=\d)/(?=\s)")


def split_keyed_line(line: str) -> tuple[str, str]:
    """Split a key-value line on the keyword ``/`` separator.

    The separator is a ``/`` preceded by whitespace, or one glued to a
    number and followed by whitespace (``441/ ND``); slashes inside IWFM
    date strings and paths are never separators.

    Returns ``(value_part, keyword_part)`` with leading/trailing
    whitespace stripped from both.  If there is no separator, the
    keyword part is an empty string.

    A line whose first non-blank character is ``/`` is a disabled /
    blank entry (IWFM reads it as an empty value): the value is ``""``
    and the keyword is taken from the remainder — after a further
    ``/`` separator when one exists (``/  old-path  / HTPOUTFL``),
    else the remainder itself (``/ DSSFL``).
    """
    stripped = line.lstrip()
    if stripped.startswith("/"):
        rest = stripped[1:]
        m = _KEYED_SEP_RE.search(rest)
        if m:
            return "", rest[m.end():].strip()
        return "", rest.strip()
    m = _KEYED_SEP_RE.search(line)
    if m:
        sep_start = m.start()
        slash_pos = m.end() - 1  # position of the /
        value_part = line[:sep_start].strip()
        keyword_part = line[slash_pos + 1 :].strip()
        return value_part, keyword_part
    return line.strip(), ""


def tokenize_data_line(line: str) -> list[str]:
    """Split a whitespace-delimited data line into tokens.

    Strips any trailing ``<whitespace>/ comment`` portion first,
    being careful not to split on slashes inside IWFM dates.  A line
    whose first non-blank character is ``/`` carries no data tokens
    (Fortran list-directed reads stop at the slash).
    """
    if line.lstrip().startswith("/"):
        return []
    m = _KEYED_SEP_RE.search(line)
    if m:
        line = line[: m.start()]
    return line.split()
