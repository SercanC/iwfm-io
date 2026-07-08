"""
Line classification and date parsing for IWFM text files.

IWFM conventions:
- Comment lines start with C, c, *, or / in column 1
- Date format: MM/DD/YYYY_HH:MM (hour 24:00 = end of day)
- Version headers: lines starting with # (e.g., #4.0)
- Key-value: VALUE / KEYWORD description
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Characters that mark a comment line when in column 1
_COMMENT_CHARS = frozenset("Cc*/")

# Pattern for IWFM date strings: MM/DD/YYYY_HH:MM
_DATE_RE = re.compile(
    r"(\d{2})/(\d{2})/(\d{4})_(\d{2}):(\d{2})"
)


def is_comment(line: str) -> bool:
    """Return True if *line* is a comment or blank line in IWFM format.

    IWFM comment characters (C, c, *, /) must appear in **column 1**
    of the raw line (no leading whitespace).  Lines that start with
    whitespace are data lines even if a comment character appears later.
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
    which is equivalent to 00:00 of the next day.

    Parameters
    ----------
    date_str : str
        Date string in ``MM/DD/YYYY_HH:MM`` format.

    Returns
    -------
    datetime
    """
    m = _DATE_RE.search(date_str)
    if m is None:
        raise ValueError(f"Cannot parse IWFM date: {date_str!r}")
    month, day, year, hour, minute = (int(g) for g in m.groups())
    if hour == 24:
        # 24:00 means end of day → start of next day
        return datetime(year, month, day) + timedelta(days=1)
    return datetime(year, month, day, hour, minute)


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


# Pattern to find the keyword separator: whitespace followed by /
# This distinguishes from slashes inside dates (09/30/1990)
_KEYED_SEP_RE = re.compile(r"\s+/")


def split_keyed_line(line: str) -> tuple[str, str]:
    """Split a key-value line on the keyword ``/`` separator.

    The separator is identified as ``/`` preceded by whitespace,
    distinguishing it from slashes inside IWFM date strings.

    Returns ``(value_part, keyword_part)`` with leading/trailing
    whitespace stripped from both.  If there is no separator, the
    keyword part is an empty string.
    """
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
    being careful not to split on slashes inside IWFM dates.
    """
    m = _KEYED_SEP_RE.search(line)
    if m:
        line = line[: m.start()]
    return line.split()
