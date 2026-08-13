"""
Structured PEST observation names: encode/decode ``(obs_type, location, time)``.

Every downstream calibration consumer — residual statistics, diagnostics,
plots, weight balancing — needs to recover *what kind* of observation a PEST
name refers to, *where*, and *when*. Hand-built workflows do this with ad-hoc
string surgery that drifts between scripts; this module makes the naming
scheme an explicit, round-trip-tested object.

The default :class:`StandardScheme` produces names like::

    gwh_w1234_20001031        # type "gwh", location "w1234", 2000-10-31
    stf_105_zcs014_20001031   # locations may contain the separator
    bud_dperc_sr01            # time-aggregated observations have no date

Encoding is ``{obs_type}{sep}{location}[{sep}{date}]`` with a lowercase
result. Decoding splits on the first separator for the type and, when the
final separator-delimited token is an 8-digit date, on the last separator
for the time — so locations containing separators round-trip unambiguously.

Projects with pre-existing (legacy) naming conventions subclass
:class:`NameScheme` and :func:`register_scheme` it; all module functions
then accept the scheme by name.

PEST name limits: PEST++ accepts observation names up to 200 characters;
classic PEST utilities are limited to 20. :func:`validate_obs_names` checks
length, character set, and case-insensitive uniqueness (PEST compares names
case-insensitively).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

import pandas as pd

__all__ = [
    "ObsName",
    "GroupSequenceScheme",
    "NameScheme",
    "StandardScheme",
    "register_scheme",
    "get_scheme",
    "encode_obs_name",
    "decode_obs_name",
    "encode_obs_names",
    "decode_obs_names",
    "validate_obs_names",
]

#: Characters PEST(++) handles safely in observation names (lowercase).
_VALID_NAME_RE = re.compile(r"^[a-z0-9_.\-:]+$")


@dataclass(frozen=True)
class ObsName:
    """Decoded parts of a structured observation name.

    Attributes
    ----------
    obs_type : str
        Short lowercase category token (e.g. ``"gwh"``, ``"stf"``,
        ``"bud"``). Never contains the scheme separator.
    location : str
        Site/entity identifier (well name, stream node, subregion, …).
        May contain the scheme separator.
    time : pandas.Timestamp or None
        Observation timestamp, or ``None`` for time-aggregated
        observations (long-term means, budget summaries, …).
    """

    obs_type: str
    location: str
    time: Optional[pd.Timestamp] = None


class NameScheme:
    """Base class for observation-name schemes.

    Subclasses must implement :meth:`encode` and :meth:`decode`.
    ``encode_many`` / ``decode_many`` have generic loop implementations;
    override them for vectorized performance (see :class:`StandardScheme`).
    """

    def encode(self, parts: ObsName) -> str:
        raise NotImplementedError

    def decode(self, name: str) -> ObsName:
        raise NotImplementedError

    def encode_many(self, parts: Iterable[ObsName]) -> "pd.Series":
        return pd.Series([self.encode(p) for p in parts], dtype=object)

    def decode_many(self, names: Iterable[str]) -> "pd.DataFrame":
        decoded = [self.decode(n) for n in names]
        return pd.DataFrame(
            {
                "obs_type": [d.obs_type for d in decoded],
                "location": [d.location for d in decoded],
                "time": pd.to_datetime([d.time for d in decoded]),
            }
        )


class StandardScheme(NameScheme):
    """Default ``{type}{sep}{location}[{sep}{date}]`` scheme, lowercase.

    Parameters
    ----------
    sep : str, default ``"_"``
        Separator between the three fields. The observation type must not
        contain it; the location may.
    date_format : str, default ``"%Y%m%d"``
        ``strftime`` format for the date token. Must render as exactly
        8 digits (the decoder recognizes date tokens by that shape).

    Notes
    -----
    A *dateless* name whose location has at least one separator and ends
    in an 8-digit token (e.g. location ``"gage_20001031"``) would decode
    with the tail misread as a date; :meth:`encode` raises ``ValueError``
    for such locations instead of emitting an ambiguous name.
    """

    def __init__(self, sep: str = "_", date_format: str = "%Y%m%d"):
        self.sep = sep
        self.date_format = date_format
        self._date_token_re = re.compile(r"^\d{8}$")

    def encode(self, parts: ObsName) -> str:
        obs_type = str(parts.obs_type).lower()
        location = str(parts.location).lower()
        if not obs_type or not location:
            raise ValueError("obs_type and location must be non-empty")
        if self.sep in obs_type:
            raise ValueError(
                f"obs_type {obs_type!r} must not contain separator {self.sep!r}"
            )
        if parts.time is None:
            tail = location.rsplit(self.sep, 1)[-1]
            if self.sep in location and self._date_token_re.match(tail):
                raise ValueError(
                    f"ambiguous dateless name: location {location!r} ends in "
                    f"an 8-digit token that would decode as a date"
                )
            return f"{obs_type}{self.sep}{location}"
        stamp = pd.Timestamp(parts.time).strftime(self.date_format)
        if not self._date_token_re.match(stamp):
            raise ValueError(
                f"date_format {self.date_format!r} must render as 8 digits, "
                f"got {stamp!r}"
            )
        return f"{obs_type}{self.sep}{location}{self.sep}{stamp}"

    def decode(self, name: str) -> ObsName:
        tokens = str(name).lower().split(self.sep)
        if len(tokens) < 2 or not tokens[0] or not tokens[-1]:
            raise ValueError(f"cannot decode observation name {name!r}")
        obs_type = tokens[0]
        if len(tokens) >= 3 and self._date_token_re.match(tokens[-1]):
            time = pd.to_datetime(tokens[-1], format=self.date_format)
            location = self.sep.join(tokens[1:-1])
        else:
            time = None
            location = self.sep.join(tokens[1:])
        if not location:
            raise ValueError(f"cannot decode observation name {name!r}")
        return ObsName(obs_type, location, time)

    def decode_many(self, names: Iterable[str]) -> "pd.DataFrame":
        s = pd.Series(list(names), dtype=object).astype(str).str.lower()
        sep = re.escape(self.sep)
        pat = re.compile(
            rf"^(?P<obs_type>[^{sep}]+){sep}(?P<location>.+?)"
            rf"(?:{sep}(?P<date>\d{{8}}))?$"
        )
        out = s.str.extract(pat)
        bad = s[out["obs_type"].isna() | out["location"].isna()]
        if len(bad):
            raise ValueError(
                f"cannot decode {len(bad)} observation name(s), "
                f"e.g. {bad.head(5).tolist()}"
            )
        out["time"] = pd.to_datetime(out.pop("date"), format=self.date_format)
        out.index = pd.Index(names)
        return out


class GroupSequenceScheme(NameScheme):
    """Legacy-style ``{type}{group:02d}{seq:04d}_{date}`` names.

    Encodes a well's spatial group and within-group sequence directly
    into the location token (e.g. group 67, seq 1 -> ``670001``), so
    observation names — and therefore hydrograph figures sorted by
    name — order by location. Pair with
    :func:`iwfm_io.assign_sequences`.

    Parameters
    ----------
    type_len : int, default 3
        Length of the observation-type token (no separator between
        type and location).
    date_format : str, default ``"%y%m%d"``
        The legacy 2-digit-year stamp; use ``"%Y%m%d"`` for
        unambiguous new setups.
    """

    def __init__(self, type_len: int = 3, date_format: str = "%y%m%d"):
        self.type_len = int(type_len)
        self.date_format = date_format

    @staticmethod
    def location(group, seq, group_digits: int = 2,
                 seq_digits: int = 4) -> str:
        """Build the location token from (group, seq)."""
        return f"{int(group):0{group_digits}d}{int(seq):0{seq_digits}d}"

    def encode(self, parts: ObsName) -> str:
        obs_type = str(parts.obs_type).lower()
        location = str(parts.location).lower()
        if len(obs_type) != self.type_len:
            raise ValueError(
                f"obs_type {obs_type!r} must be exactly "
                f"{self.type_len} characters in this scheme")
        if not location:
            raise ValueError("location must be non-empty")
        if parts.time is None:
            return f"{obs_type}{location}"
        stamp = pd.Timestamp(parts.time).strftime(self.date_format)
        return f"{obs_type}{location}_{stamp}"

    def decode(self, name: str) -> ObsName:
        s = str(name).lower()
        head, sep, stamp = s.rpartition("_")
        time = None
        if sep and stamp.isdigit():
            try:
                time = pd.to_datetime(stamp, format=self.date_format)
            except ValueError:
                head = s
        else:
            head = s
        if len(head) <= self.type_len:
            raise ValueError(f"cannot decode observation name {name!r}")
        return ObsName(head[:self.type_len], head[self.type_len:], time)


_SCHEMES: dict = {"standard": StandardScheme(),
                  "grouped": GroupSequenceScheme()}


def register_scheme(name: str, scheme: NameScheme) -> None:
    """Register a (project-specific) naming scheme under ``name``.

    Registered schemes can then be passed by name to every codec function
    in this module. Re-registering a name replaces the previous scheme.
    """
    if not isinstance(scheme, NameScheme):
        raise TypeError("scheme must be a NameScheme instance")
    _SCHEMES[name] = scheme


def get_scheme(scheme: Union[str, NameScheme]) -> NameScheme:
    """Resolve a scheme by registry name, or pass an instance through."""
    if isinstance(scheme, NameScheme):
        return scheme
    try:
        return _SCHEMES[scheme]
    except KeyError:
        raise KeyError(
            f"unknown name scheme {scheme!r}; registered: {sorted(_SCHEMES)}"
        ) from None


def encode_obs_name(obs_type, location, time=None, scheme="standard") -> str:
    """Encode one observation name.

    Parameters
    ----------
    obs_type : str
        Short category token (e.g. ``"gwh"``). Lowercased on output.
    location : str
        Site identifier. Lowercased on output.
    time : datetime-like or None
        Timestamp; ``None`` for time-aggregated observations.
    scheme : str or NameScheme, default ``"standard"``

    Returns
    -------
    str

    Examples
    --------
    >>> encode_obs_name("gwh", "W1234", "2000-10-31")
    'gwh_w1234_20001031'
    >>> encode_obs_name("bud", "dperc_sr01")
    'bud_dperc_sr01'
    """
    t = None if time is None else pd.Timestamp(time)
    return get_scheme(scheme).encode(ObsName(obs_type, location, t))


def decode_obs_name(name, scheme="standard") -> ObsName:
    """Decode one observation name into an :class:`ObsName`.

    Examples
    --------
    >>> decode_obs_name("gwh_w1234_20001031")
    ObsName(obs_type='gwh', location='w1234', time=Timestamp('2000-10-31 00:00:00'))
    """
    return get_scheme(scheme).decode(name)


def encode_obs_names(obs_types, locations, times=None, scheme="standard") -> "pd.Series":
    """Encode many observation names (vectorized-friendly).

    Parameters
    ----------
    obs_types, locations : str or sequence of str
        Scalars broadcast against the longest input.
    times : datetime-like, sequence, or None
        ``None`` (or ``None`` elements) → dateless names.
    scheme : str or NameScheme, default ``"standard"``

    Returns
    -------
    pandas.Series of str
    """
    sch = get_scheme(scheme)
    df = pd.DataFrame(
        {
            "obs_type": obs_types,
            "location": locations,
            "time": pd.to_datetime(times) if times is not None else None,
        }
    )
    parts = (
        ObsName(r.obs_type, r.location, None if pd.isnull(r.time) else r.time)
        for r in df.itertuples()
    )
    return sch.encode_many(parts)


def decode_obs_names(names, scheme="standard") -> "pd.DataFrame":
    """Decode many observation names into a DataFrame.

    Parameters
    ----------
    names : sequence of str (list, Series, or Index)
    scheme : str or NameScheme, default ``"standard"``

    Returns
    -------
    pandas.DataFrame
        Columns ``obs_type``, ``location``, ``time`` (``NaT`` for dateless
        names), indexed by the input names.

    Examples
    --------
    >>> decode_obs_names(["gwh_w1_20001031", "bud_dperc_sr01"])["obs_type"].tolist()
    ['gwh', 'bud']
    """
    sch = get_scheme(scheme)
    out = sch.decode_many(list(names))
    out.index = pd.Index(names)
    return out


def validate_obs_names(names, max_len: int = 200) -> list:
    """Check observation names for PEST-compatibility problems.

    Checks case-insensitive uniqueness (PEST compares names
    case-insensitively), length (``max_len``: 200 for PEST++, use 20 for
    classic PEST utilities), and character set
    (``a-z 0-9 _ . - :`` after lowercasing).

    Returns
    -------
    list of str
        Human-readable problem descriptions; empty when all names pass
        (same convention as ``iwfm_io._validation``).
    """
    problems = []
    s = pd.Series(list(names), dtype=object).astype(str)
    lower = s.str.lower()

    dups = lower[lower.duplicated()].unique()
    if len(dups):
        problems.append(
            f"{len(dups)} duplicate name(s) (case-insensitive), "
            f"e.g. {list(dups[:5])}"
        )
    too_long = s[s.str.len() > max_len]
    if len(too_long):
        problems.append(
            f"{len(too_long)} name(s) longer than {max_len} chars, "
            f"e.g. {too_long.head(5).tolist()}"
        )
    bad = s[~lower.str.match(_VALID_NAME_RE)]
    if len(bad):
        problems.append(
            f"{len(bad)} name(s) with invalid characters "
            f"(allowed: a-z 0-9 _ . - :), e.g. {bad.head(5).tolist()}"
        )
    return problems
