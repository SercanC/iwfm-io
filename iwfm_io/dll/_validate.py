"""Argument validation for the DLL wrapper.

The Fortran side does not validate its inputs: a malformed date string
makes it execute ``STOP`` (the Python process exits with code 0 and no
exception), a location index of 0 corrupts the heap, and an
out-of-range id reads uninitialised memory. Every wrapper method
therefore checks its arguments here before crossing the boundary.
"""

from __future__ import annotations

import re

import numpy as np

from iwfm_io._tokens import is_iwfm_date, parse_iwfm_date
from iwfm_io.dll._errors import IWFMError

_INTERVAL_RE = re.compile(r"^\d+(MIN|HOUR|DAY|WEEK|MON|YEAR)$")
#: the intervals IWFM recognises (TimeSeriesUtilities.f90); anything
#: else -- e.g. "3MON" -- counts as zero intervals inside the Fortran
RECOGNIZED_INTERVALS = (
    "1MIN", "2MIN", "3MIN", "4MIN", "5MIN", "10MIN", "15MIN", "20MIN",
    "30MIN", "1HOUR", "2HOUR", "3HOUR", "4HOUR", "6HOUR", "8HOUR",
    "12HOUR", "1DAY", "1WEEK", "1MON", "1YEAR",
)


def check_int(name: str, value) -> int:
    """An integer-like scalar (numpy ints ok; bools, floats and strings
    are rejected)."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer, got {value!r}")
    return int(value)


def check_range(name: str, value, n: int, lo: int = 1) -> int:
    """An integer index in ``[lo, n]`` (1-based by default)."""
    v = check_int(name, value)
    if not lo <= v <= n:
        raise IndexError(f"{name} {v} out of range [{lo}, {n}]")
    return v


def check_ids(name: str, values, n: int, lo: int = 1) -> np.ndarray:
    """A non-empty sequence of integer ids in ``[lo, n]``."""
    arr = np.asarray(list(values))
    if arr.size == 0:
        raise ValueError(f"{name} must not be empty")
    if arr.dtype.kind == "b" or not np.issubdtype(arr.dtype, np.integer):
        raise TypeError(f"{name} must be integers, got {arr.dtype}")
    if (arr < lo).any() or (arr > n).any():
        bad = arr[(arr < lo) | (arr > n)][:3].tolist()
        raise IndexError(f"{name} contains ids outside [{lo}, {n}]: {bad}")
    return arr.astype(np.int32)


def check_same_length(**arrays) -> int:
    lengths = {k: len(v) for k, v in arrays.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"lengths differ: {lengths}")
    return next(iter(lengths.values())) if lengths else 0


def check_date(name: str, value) -> str:
    """A complete IWFM date string ``MM/DD/YYYY_HH:MM``.

    A plain date, an ISO date, or garbage would reach the Fortran
    date parser, which STOPs the process.
    """
    if not isinstance(value, str) or not is_iwfm_date(value):
        raise ValueError(
            f"{name} must be an IWFM date string MM/DD/YYYY_HH:MM, "
            f"got {value!r}")
    return value.strip()


def check_window(begin: str, end: str, sim_dates=None) -> tuple[str, str]:
    """Validate a ``begin``/``end`` pair: both IWFM dates, ordered, and
    within the simulation output dates when *sim_dates* (first, last
    IWFM stamps) is given — the DLL fills windows outside the run with
    zeros or uninitialised values."""
    b = check_date("begin_date", begin)
    e = check_date("end_date", end)
    if parse_iwfm_date(b) > parse_iwfm_date(e):
        raise ValueError(f"begin_date {b} is after end_date {e}")
    if sim_dates:
        first, last = sim_dates[0], sim_dates[-1]
        if (parse_iwfm_date(b) < parse_iwfm_date(first)
                or parse_iwfm_date(e) > parse_iwfm_date(last)):
            raise ValueError(
                f"window {b} .. {e} lies outside the simulation output "
                f"{first} .. {last}")
    return b, e


def check_interval(value, allowed=None) -> str:
    """An IWFM interval string (``1DAY``, ``1MON``, ``1YEAR`` ...),
    optionally restricted to the model's output intervals."""
    if not isinstance(value, str):
        raise TypeError(f"interval must be a string, got {value!r}")
    iv = value.strip().upper()
    if not _INTERVAL_RE.match(iv) or iv not in RECOGNIZED_INTERVALS:
        raise ValueError(
            f"interval {value!r} is not an IWFM interval; recognised: "
            f"{', '.join(RECOGNIZED_INTERVALS)}")
    if allowed is not None:
        allowed_u = [a.strip().upper() for a in allowed]
        if iv not in allowed_u:
            raise ValueError(
                f"interval {value!r} is not an output interval of this "
                f"model; available: {allowed_u}")
    return iv


def closed(what: str) -> IWFMError:
    return IWFMError(f"{what} is closed", -1)
