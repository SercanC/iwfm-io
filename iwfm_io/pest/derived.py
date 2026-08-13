"""
Derived observation types: transforms that regularize calibrations.

Raw heads and flows underconstrain a groundwater model. The proven
DWR-style remedy is *derived* observations that isolate specific
processes:

- temporal head changes (:func:`head_changes`) — successive
  month-to-month change constrains storage; year-over-year seasonal
  change and within-year drawdown separate climate signal from pumping
  response;
- vertical head differences at multi-completion well pairs
  (:func:`vertical_head_difference`) — constrain aquitard vertical
  conductivity;
- stream accretion/depletion between gauge pairs
  (:func:`accretion_depletion`) — constrain streambed conductance;
- long-term statistics (:func:`long_term_stats`) — constrain the
  overall water balance without chasing month-to-month noise.

Every function is a pure transform on the package's long-form
``site, datetime, value`` layout and returns the same layout — so the
identical call derives the observed series (from field data) and the
simulated series (from model output), guaranteeing the two are
comparable. Pass ``obs_type=`` to add codec-encoded observation names.

Typical pairing workflow::

    obs_del = head_changes(obs, "successive")
    sim_del = head_changes(sim_matched, "successive")
    paired = obs_del.merge(sim_del, on=["site", "datetime"],
                           suffixes=("_obs", "_sim"))
"""

from __future__ import annotations

import logging
from typing import Iterable, Mapping, Optional, Union

import pandas as pd

from iwfm_io.pest.names import encode_obs_names

__all__ = ["head_changes", "vertical_head_difference",
           "accretion_depletion", "long_term_stats"]

logger = logging.getLogger(__name__)


def _named(out, obs_type, scheme, dateless=False) -> "pd.DataFrame":
    if obs_type is not None and len(out):
        times = None if dateless else out["datetime"]
        out = out.copy()
        out.insert(0, "obsnme", encode_obs_names(
            obs_type, out["site"], times, scheme=scheme).values)
    return out


def _monthly(df) -> "pd.DataFrame":
    """Site × month-mean table with year/month helper columns."""
    work = df.copy()
    work["datetime"] = pd.to_datetime(work["datetime"])
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["value"])
    ym = work["datetime"].dt.to_period("M")
    g = (work.assign(_p=ym).groupby(["site", "_p"])
         .agg(value=("value", "mean"), datetime=("datetime", "max"))
         .reset_index())
    g["year"] = g["_p"].dt.year
    g["month"] = g["_p"].dt.month
    return g


def head_changes(df, kind: str, month: int = 3, from_month: int = 3,
                 to_month: int = 9, max_gap=None,
                 obs_type: Optional[str] = None,
                 scheme="standard") -> "pd.DataFrame":
    """Temporal head-change series from a long-form head record.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value``. Multiple values within a
        month are averaged first.
    kind : {"successive", "seasonal", "drawdown"}
        ``successive`` — change from the previous record
        (``v[t] − v[t−1]``, stamped at ``t``);
        ``seasonal`` — year-over-year change of the *month* mean
        (``v[year, month] − v[year−1, month]``);
        ``drawdown`` — within-year difference
        (``v[year, from_month] − v[year, to_month]``, stamped at the
        *to_month* record; positive = seasonal decline).
    month : int, default 3
        Month compared for ``seasonal`` (March by convention).
    from_month, to_month : int, defaults 3 and 9
        Months differenced for ``drawdown`` (spring minus fall).
    max_gap : str or Timedelta, optional
        For ``successive``: drop changes computed across a data gap
        longer than this.
    obs_type : str, optional
        Adds an ``obsnme`` column via the observation-name codec.

    Returns
    -------
    pandas.DataFrame
        Long-form ``site, datetime, value`` (plus ``obsnme`` when
        *obs_type* is given).
    """
    if kind not in ("successive", "seasonal", "drawdown"):
        raise ValueError(
            f"kind must be 'successive', 'seasonal', or 'drawdown', "
            f"got {kind!r}")
    m = _monthly(df)

    if kind == "successive":
        m = m.sort_values(["site", "datetime"])
        prev_v = m.groupby("site")["value"].shift(1)
        prev_t = m.groupby("site")["datetime"].shift(1)
        out = pd.DataFrame({
            "site": m["site"], "datetime": m["datetime"],
            "value": m["value"] - prev_v,
        })
        if max_gap is not None:
            gap = m["datetime"] - prev_t
            out.loc[gap > pd.Timedelta(max_gap), "value"] = pd.NA
        out = out.dropna(subset=["value"])
    elif kind == "seasonal":
        s = m[m["month"] == month].sort_values(["site", "year"])
        prev_v = s.groupby("site")["value"].shift(1)
        prev_y = s.groupby("site")["year"].shift(1)
        out = pd.DataFrame({
            "site": s["site"], "datetime": s["datetime"],
            "value": (s["value"] - prev_v).where(s["year"] - prev_y == 1),
        }).dropna(subset=["value"])
    else:  # drawdown
        a = m[m["month"] == from_month][["site", "year", "value"]]
        b = m[m["month"] == to_month][["site", "year", "value", "datetime"]]
        j = a.merge(b, on=["site", "year"], suffixes=("_from", "_to"))
        out = pd.DataFrame({
            "site": j["site"], "datetime": j["datetime"],
            "value": j["value_from"] - j["value_to"],
        }).dropna(subset=["value"])

    out = out.reset_index(drop=True)
    out["value"] = out["value"].astype(float)
    return _named(out, obs_type, scheme)


def _pair_difference(df, pairs, sep: str) -> "pd.DataFrame":
    """``first − second`` per pair at common timestamps."""
    if isinstance(pairs, Mapping):
        items = list(pairs.items())
    else:
        items = [(None, tuple(p)) for p in pairs]
    work = df.copy()
    work["datetime"] = pd.to_datetime(work["datetime"])
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    by_site = {s: g.set_index("datetime")["value"].dropna()
               for s, g in work.groupby(work["site"].astype(str))}
    pieces = []
    for label, (first, second) in items:
        a, b = by_site.get(str(first)), by_site.get(str(second))
        if a is None or b is None:
            missing = [s for s, v in ((first, a), (second, b)) if v is None]
            logger.warning("pair (%s, %s): site(s) %s absent — skipped",
                           first, second, missing)
            continue
        a = a.groupby(level=0).mean()
        b = b.groupby(level=0).mean()
        common = a.index.intersection(b.index)
        if not len(common):
            logger.warning("pair (%s, %s): no common timestamps — skipped",
                           first, second)
            continue
        pieces.append(pd.DataFrame({
            "site": label or f"{first}{sep}{second}",
            "datetime": common,
            "value": (a[common] - b[common]).values,
        }))
    if not pieces:
        return pd.DataFrame(columns=["site", "datetime", "value"])
    return pd.concat(pieces, ignore_index=True)


def vertical_head_difference(df, pairs, obs_type: Optional[str] = None,
                             scheme="standard") -> "pd.DataFrame":
    """Head difference between paired completions: ``shallow − deep``.

    Positive values indicate a downward vertical gradient. Timestamps
    must match exactly — resample both series first (e.g. with
    :func:`~iwfm_io.pest.sim2obs.resample_month_end`) when the two
    completions are not measured on the same dates.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value`` containing both completions.
    pairs : iterable of (shallow, deep) or mapping label → (shallow, deep)
        Pairs to difference. Without labels, the derived site is
        ``{shallow}_{deep}``. Pairs with absent sites or no common
        timestamps are skipped with a warning.
    obs_type : str, optional
        Adds codec-encoded ``obsnme`` (e.g. ``"vhd"``).
    """
    out = _pair_difference(df, pairs, sep="_")
    return _named(out, obs_type, scheme)


def accretion_depletion(df, pairs, obs_type: Optional[str] = None,
                        scheme="standard") -> "pd.DataFrame":
    """Stream gain between gauges: ``downstream − upstream``.

    Positive values = accretion (the reach gains from the aquifer);
    negative = depletion. Intervening tributaries or diversions must be
    netted out of the input series by the caller.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value`` of gauge flows.
    pairs : iterable of (upstream, downstream) or mapping label → pair
        Gauge pairs. Without labels, the derived site is
        ``{upstream}_{downstream}``.
    obs_type : str, optional
        Adds codec-encoded ``obsnme`` (e.g. ``"acc"``).
    """
    if isinstance(pairs, Mapping):
        flipped = {k: (v[1], v[0]) for k, v in pairs.items()}
    else:
        flipped = [(p[1], p[0]) for p in pairs]
    out = _pair_difference(df, flipped, sep="_")
    if not isinstance(pairs, Mapping) and len(out):
        # keep upstream-first labels despite the flipped arithmetic
        relabel = {f"{d}_{u}": f"{u}_{d}" for u, d in pairs}
        out["site"] = out["site"].map(lambda s: relabel.get(s, s))
    return _named(out, obs_type, scheme)


def long_term_stats(df, stat: str = "mean", min_n: int = 1,
                    obs_type: Optional[str] = None,
                    scheme="standard") -> "pd.DataFrame":
    """One whole-record statistic per site (dateless observations).

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value``.
    stat : str, default "mean"
        Any pandas groupby aggregation (``"mean"``, ``"median"``, …).
    min_n : int, default 1
        Sites with fewer valid samples are dropped.
    obs_type : str, optional
        Adds dateless codec-encoded ``obsnme`` (e.g. ``"ltm"``).

    Returns
    -------
    pandas.DataFrame
        ``site, datetime (NaT), value``.
    """
    work = df.copy()
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["value"])
    g = work.groupby(work["site"].astype(str))["value"]
    out = g.agg(value=stat, _n="size").reset_index()
    out = out[out["_n"] >= min_n].drop(columns="_n")
    out["datetime"] = pd.NaT
    out = out[["site", "datetime", "value"]].reset_index(drop=True)
    return _named(out, obs_type, scheme, dateless=True)
