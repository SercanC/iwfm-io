"""
HEC-DSS time series + CalSim channel-flow linking and extraction.

Reads value data out of HEC-DSS files (the package already parses DSS
*pathname assignments* inside IWFM inputs; this module reads the
records themselves), and layers the CalSim stream-calibration path on
top: link ``gauge_metadata`` rows to CalSim channel arcs and extract
per-gauge flow series, mirroring :mod:`iwfm_io.gauges`.

Requires the optional ``pydsstools`` dependency (``pip install
iwfm-io[dss]``); the import is deferred to call time, so importing
``iwfm_io`` never pays for it. pydsstools >= 3 reads both DSS-6 and
DSS-7 files (auto-detected).

CalSim conventions handled here:

- streamflows are monthly ``PER-AVER`` records in the DV ``.dss`` file,
  one per channel arc (B part, e.g. ``C_SAC041``), period-average CFS;
- DSS stamps a period value at the end-of-period instant, which reads
  back as the *next* day's midnight (January -> Feb 1 00:00) — the same
  convention as IWFM's ``24:00`` stamps, so CalSim and IWFM series
  align without shifting.

Workflow::

    link = link_calsim_channels(gauge_metadata, "DV.dss")
    flows = calsim_streamflow_series(link, "DV.dss", units="taf")

Downstream the calibration machinery applies unchanged (the point of
the ``gauge_id`` pivot): ``match_sim_to_obs``, ``residual_stats``,
``accretion_depletion`` for arc pairs, and the ``"grouped"`` naming
scheme.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from iwfm_io.gauges import validate_gauge_metadata

__all__ = ["dss_catalog", "read_dss_timeseries", "cfs_to_taf",
           "CalSimLink", "link_calsim_channels",
           "calsim_streamflow_series"]

logger = logging.getLogger(__name__)

#: acre-feet per (1 cfs flowing for 1 day): 86400 s/day / 43560 ft2/acre
AF_PER_CFS_DAY = 86400.0 / 43560.0


def _open_dss(dss_file, mode: str = "r"):
    """Open a DSS file via pydsstools (lazy import, quiet heclib log)."""
    try:
        from pydsstools.heclib.dss.HecDss import Open
    except ImportError as exc:
        raise ImportError(
            "reading HEC-DSS files requires pydsstools — "
            "pip install iwfm-io[dss] (or pip install pydsstools)"
        ) from exc
    try:  # silence heclib's per-open console chatter; best-effort
        from pydsstools.heclib.logging import get_dss_logger, Level, Method
        get_dss_logger(Method.GLOBAL).set_level(Level.NONE)
    except Exception:
        pass
    return Open(str(dss_file), mode=mode)


def _require_dss_file(dss_file) -> None:
    """heclib silently creates a new empty file for a missing path."""
    if not Path(dss_file).is_file():
        raise FileNotFoundError(f"DSS file not found: {dss_file}")


def _split_pathname(pathname: str) -> "list[str]":
    """``/A/B/C/D/E/F/`` -> ``[A, B, C, D, E, F]``."""
    parts = str(pathname).split("/")
    if len(parts) < 8:
        parts = parts + [""] * (8 - len(parts))
    return parts[1:7]


def dss_catalog(dss_file, pattern: str = "") -> "pd.DataFrame":
    """Catalog the time-series records of a HEC-DSS file.

    Parameters
    ----------
    dss_file : str or Path
    pattern : str, optional
        Pathname pattern with ``*`` wildcards (all records by default).

    Returns
    -------
    pandas.DataFrame
        One row per stored record (data blocks appear individually):
        ``pathname, a, b, c, d, e, f, condensed`` — *condensed* is the
        pathname with the D (date-block) part blanked, the stable
        record identity to read with.
    """
    _require_dss_file(dss_file)
    with _open_dss(dss_file) as fid:
        paths = fid.search_path(pattern, sort=True) if pattern else \
            fid.search_path(sort=True)
    rows = []
    for p in paths:
        a, b, c, d, e, f = _split_pathname(p)
        rows.append({"pathname": p, "a": a, "b": b, "c": c, "d": d,
                     "e": e, "f": f,
                     "condensed": f"/{a}/{b}/{c}//{e}/{f}/"})
    return pd.DataFrame(
        rows, columns=["pathname", "a", "b", "c", "d", "e", "f",
                       "condensed"])


def read_dss_timeseries(dss_file, paths) -> "pd.DataFrame":
    """Read regular time-series records into a wide DataFrame.

    Parameters
    ----------
    dss_file : str or Path
    paths : str or sequence of str
        Record pathnames — condensed (empty D part) reads the whole
        record across data blocks; a block pathname reads that block.

    Returns
    -------
    pandas.DataFrame
        datetime index × one column per requested pathname (missing
        values as NaN, leading/trailing missing trimmed). Per-column
        record units and data type are kept in ``df.attrs["units"]``
        and ``df.attrs["data_type"]``.
    """
    if isinstance(paths, (str, Path)):
        paths = [str(paths)]
    else:
        paths = [str(p) for p in paths]
    series, units, dtypes = {}, {}, {}
    _require_dss_file(dss_file)
    with _open_dss(dss_file) as fid:
        for p in paths:
            ts = fid.read_ts(p, trim_missing=True)
            vals = np.array(ts.values, dtype=float)   # own copy: written below
            mask = np.asarray(ts.nodata, dtype=bool)
            vals[mask] = np.nan
            # second resolution: IWFM's recurring-year records (year
            # 4000) are outside pandas' nanosecond range
            when = pd.DatetimeIndex(np.array(
                [t.datetime() for t in ts.times], dtype="datetime64[s]"))
            series[p] = pd.Series(vals, index=when)
            units[p] = (ts.data_units or "").strip()
            dtypes[p] = (ts.data_type or "").strip()
    out = pd.DataFrame(series)
    out.index.name = "datetime"
    out.attrs["units"] = units
    out.attrs["data_type"] = dtypes
    return out


def cfs_to_taf(frame) -> "pd.DataFrame":
    """Convert period-average CFS to TAF per period (pure function).

    Uses the DSS/IWFM end-of-period timestamp convention: each stamp is
    the first instant *after* its period, so the period's month is the
    month of ``stamp - 1 day`` and the conversion uses that month's day
    count. Monthly data only (the CalSim case).
    """
    idx = pd.DatetimeIndex(frame.index)
    days = (idx - pd.Timedelta(days=1)).days_in_month.values
    return frame.mul(days * AF_PER_CFS_DAY / 1000.0, axis=0)


@dataclass
class CalSimLink:
    """Result of :func:`link_calsim_channels`.

    Attributes
    ----------
    links : pandas.DataFrame
        One row per matched gauge: ``gauge_id, bpart, pathname``
        (condensed).
    unmatched_gauges : list
        ``gauge_id`` values with no matching DSS record.
    orphan_arcs : list
        Channel-arc B parts (``arc_prefix``-filtered) with no metadata
        row.
    """

    links: "pd.DataFrame"
    unmatched_gauges: "list"
    orphan_arcs: "list"

    def summary(self) -> dict:
        return {
            "n_gauges_linked": int(len(self.links)),
            "n_unmatched_gauges": len(self.unmatched_gauges),
            "n_orphan_arcs": len(self.orphan_arcs),
        }


def link_calsim_channels(gauge_metadata, dss,
                         on: str = "calsim_bpart",
                         cpart: Optional[str] = None,
                         epart: Optional[str] = None,
                         fpart: Optional[str] = None,
                         arc_prefix: str = "C_") -> CalSimLink:
    """Link gauge metadata to CalSim channel arcs in a DSS file.

    Parameters
    ----------
    gauge_metadata : pandas.DataFrame
        Needs ``gauge_id`` plus the *on* column (channel-arc name, e.g.
        ``C_SAC041``). An optional ``dss_path`` column overrides the
        catalog match per row (full condensed pathname).
    dss : str, Path, or pandas.DataFrame
        DSS file to catalog, or an existing :func:`dss_catalog` frame.
    on : str, default "calsim_bpart"
        Metadata column matched against B parts (case-insensitive,
        whitespace-stripped). Duplicate non-null values are an error.
    cpart, epart, fpart : str, optional
        Filter the catalog to one C part (e.g. ``CHANNEL`` /
        ``FLOW-CHANNEL``), E part (e.g. ``1MON``), or F part (the
        scenario) before matching — required when a B part appears
        under several of them (the ambiguity error says so).
    arc_prefix : str, default "C_"
        B-part prefix defining "channel arc" for orphan reporting
        (CalSim3 convention; use ``"C"`` for CalSim II).

    Returns
    -------
    CalSimLink
    """
    problems = validate_gauge_metadata(gauge_metadata)
    if problems:
        raise ValueError("invalid gauge_metadata: " + "; ".join(problems))
    if on not in gauge_metadata.columns:
        raise ValueError(f"gauge_metadata has no column {on!r}")

    cat = dss if isinstance(dss, pd.DataFrame) else dss_catalog(dss)
    if cat.empty:
        raise ValueError("DSS catalog is empty")
    for col, want in (("c", cpart), ("e", epart), ("f", fpart)):
        if want is not None:
            cat = cat[cat[col].str.casefold() == want.casefold()]
    if cat.empty:
        raise ValueError("no DSS records left after C/E/F-part filters")
    # one row per record identity (blocks collapse onto the condensed path)
    cat = cat.drop_duplicates(subset="condensed")

    key = gauge_metadata[on].astype(str).str.strip()
    nonnull = key[gauge_metadata[on].notna()]
    dup = nonnull[nonnull.str.casefold().duplicated()]
    if len(dup):
        raise ValueError(
            f"gauge_metadata[{on!r}] has duplicate value(s): "
            f"{sorted(set(dup))[:5]} — ambiguous join")

    by_bpart = {}   # casefolded B -> (original B, [condensed paths])
    for b, condensed in zip(cat["b"].astype(str).str.strip(),
                            cat["condensed"]):
        by_bpart.setdefault(b.casefold(), (b, []))[1].append(condensed)

    overrides = gauge_metadata["dss_path"] \
        if "dss_path" in gauge_metadata.columns else None
    rows, unmatched = [], []
    for i in gauge_metadata.index:
        gid = gauge_metadata.at[i, "gauge_id"]
        if overrides is not None and pd.notna(overrides.at[i]) \
                and str(overrides.at[i]).strip():
            path = str(overrides.at[i]).strip()
            rows.append({"gauge_id": gid,
                         "bpart": _split_pathname(path)[1],
                         "pathname": path})
            continue
        b = str(key.at[i]).strip().casefold() \
            if pd.notna(gauge_metadata.at[i, on]) else ""
        orig_b, hits = by_bpart.get(b, ("", []))
        if not hits:
            unmatched.append(gid)
        elif len(hits) > 1:
            raise ValueError(
                f"B part {gauge_metadata.at[i, on]!r} matches "
                f"{len(hits)} records (e.g. {hits[:3]}) — narrow with "
                f"cpart=/epart=/fpart=")
        else:
            rows.append({"gauge_id": gid, "bpart": orig_b,
                         "pathname": hits[0]})

    matched_b = {r["bpart"].casefold() for r in rows}
    arcs = cat["b"].astype(str).str.strip()
    is_arc = arcs.str.casefold().str.startswith(arc_prefix.casefold())
    orphans = sorted({a for a in arcs[is_arc]
                      if a.casefold() not in matched_b})

    link = CalSimLink(
        links=pd.DataFrame(rows, columns=["gauge_id", "bpart", "pathname"]),
        unmatched_gauges=unmatched,
        orphan_arcs=orphans,
    )
    logger.info("link_calsim_channels: %s", link.summary())
    return link


def calsim_streamflow_series(link: CalSimLink, dss_file,
                             units: str = "cfs") -> "pd.DataFrame":
    """Extract per-gauge CalSim channel-flow series from a DV DSS file.

    Parameters
    ----------
    link : CalSimLink
    dss_file : str or Path
    units : {"cfs", "taf"}, default "cfs"
        ``cfs`` returns the records as stored (period-average CFS);
        ``taf`` converts to TAF per month via :func:`cfs_to_taf`
        (raises if the DSS record units are not CFS).

    Returns
    -------
    pandas.DataFrame
        time × gauge_id (timestamps follow the shared end-of-period
        convention — a January value is stamped Feb 1 00:00, matching
        IWFM's ``24:00`` handling).
    """
    if units not in ("cfs", "taf"):
        raise ValueError("units must be 'cfs' or 'taf'")
    if link.links.empty:
        raise ValueError("link has no matched gauges")
    frame = read_dss_timeseries(dss_file, list(link.links["pathname"]))
    if units == "taf":
        rec_units = frame.attrs.get("units", {})
        bad = {p: u for p, u in rec_units.items()
               if u and u.casefold() != "cfs"}
        if bad:
            raise ValueError(
                f"units='taf' expects CFS records; found "
                f"{sorted(set(bad.values()))} (e.g. {next(iter(bad))})")
        blank = [p for p, u in rec_units.items() if not u]
        if blank:
            logger.warning(
                "%d record(s) have blank units — assuming CFS",
                len(blank))
        frame = cfs_to_taf(frame)
    out = frame[list(link.links["pathname"])]
    out.columns = list(link.links["gauge_id"])
    return out
