"""
Sim-to-obs time matching — a Python IWFM2OBS equivalent.

Pairs simulated hydrograph series (GW head, stream flow, subsidence, …)
with observed records by interpolating the simulation to each
observation's timestamp — the role DWR's IWFM2OBS Fortran utility plays
in the classic IWFM calibration workflow.

Both inputs use the package's standard long-form layout
(``site, datetime, value`` — what :func:`~iwfm_io.pest.smp.read_smp`,
``iwfm_io.collect_hydrographs`` and the hydrograph readers produce);
wide frames (datetime index × site columns) are also accepted for the
simulation side. The output is a long-form paired frame
(``site, datetime, observed, simulated``) that feeds directly into
:func:`~iwfm_io.pest.stats.residual_stats`,
:func:`~iwfm_io.pest.smp.write_smp`, and (later) instruction-file
generation.

IWFM's end-of-timestep convention: a monthly value stamped
``10/31/2000_24:00`` parses to ``11/01 00:00`` — one second into the
*next* month. :func:`resample_month_end` accounts for this by default so
month-end aggregation buckets such values into the month they belong to.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

import numpy as np
import pandas as pd

__all__ = ["match_sim_to_obs", "resample_month_end"]

logger = logging.getLogger(__name__)


def _to_wide(sim) -> "pd.DataFrame":
    """Normalize the simulated input to datetime-index × site columns."""
    if {"site", "datetime", "value"} <= set(getattr(sim, "columns", [])):
        wide = sim.pivot_table(index="datetime", columns="site",
                               values="value", aggfunc="mean")
    else:
        wide = sim.copy()
        wide.index = pd.to_datetime(wide.index)
    return wide.sort_index()


def match_sim_to_obs(sim, obs, method: str = "linear",
                     max_gap=None) -> "pd.DataFrame":
    """Interpolate simulated series to observation timestamps.

    Parameters
    ----------
    sim : pandas.DataFrame
        Simulated series: long-form ``site, datetime, value`` or wide
        (datetime index, one column per site).
    obs : pandas.DataFrame
        Observations, long-form ``site, datetime, value`` (e.g. from
        :func:`~iwfm_io.pest.smp.read_smp`).
    method : {"linear", "nearest"}
        ``linear`` interpolates in time between the bracketing simulated
        values (never extrapolates — observations outside the simulated
        period get NaN). ``nearest`` takes the closest simulated value.
    max_gap : str, Timedelta, or None
        Data-gap guard. For ``linear``, both bracketing simulated points
        must lie within ``max_gap`` of the observation time; for
        ``nearest``, the closest point must. Violations yield NaN
        rather than silently interpolating across a gap.

    Returns
    -------
    pandas.DataFrame
        Long-form ``site, datetime, observed, simulated``. Observation
        sites absent from the simulation are dropped (logged); rows the
        interpolation could not fill keep ``simulated = NaN`` so
        downstream statistics can drop or count them.

    Examples
    --------
    >>> paired = match_sim_to_obs(sim, read_smp("heads.smp"),
    ...                           max_gap="45D")             # doctest: +SKIP
    >>> residual_stats(paired, by="site")                    # doctest: +SKIP
    """
    if method not in ("linear", "nearest"):
        raise ValueError(f"method must be 'linear' or 'nearest', got {method!r}")
    gap_ns = None
    if max_gap is not None:
        gap_ns = pd.Timedelta(max_gap).value

    wide = _to_wide(sim)
    obs = obs.copy()
    obs["datetime"] = pd.to_datetime(obs["datetime"])
    obs_sites = obs["site"].astype(str)

    known = set(map(str, wide.columns))
    missing = sorted(set(obs_sites) - known)
    if missing:
        logger.warning(
            "%d observation site(s) have no simulated series and are "
            "dropped, e.g. %s", len(missing), missing[:5])
    keep = obs_sites.isin(known)
    obs = obs[keep]
    obs_sites = obs_sites[keep]

    pieces = []
    for site, group in obs.groupby(obs_sites):
        s = wide[site].dropna() if site in wide.columns else wide[
            [c for c in wide.columns if str(c) == site][0]].dropna()
        t_obs = group["datetime"].values.astype("datetime64[ns]").astype(np.int64)
        simulated = np.full(len(group), np.nan)
        if len(s):
            t_sim = s.index.values.astype("datetime64[ns]").astype(np.int64)
            v_sim = s.values.astype(float)
            if method == "nearest":
                idx = np.searchsorted(t_sim, t_obs)
                idx_lo = np.clip(idx - 1, 0, len(t_sim) - 1)
                idx_hi = np.clip(idx, 0, len(t_sim) - 1)
                d_lo = np.abs(t_obs - t_sim[idx_lo])
                d_hi = np.abs(t_sim[idx_hi] - t_obs)
                nearest = np.where(d_lo <= d_hi, idx_lo, idx_hi)
                dist = np.minimum(d_lo, d_hi)
                simulated = v_sim[nearest].copy()
                if gap_ns is not None:
                    simulated[dist > gap_ns] = np.nan
            else:
                inside = (t_obs >= t_sim[0]) & (t_obs <= t_sim[-1])
                interp = np.interp(t_obs, t_sim, v_sim)
                simulated = np.where(inside, interp, np.nan)
                if gap_ns is not None and inside.any():
                    hi = np.searchsorted(t_sim, t_obs, side="left")
                    lo = np.clip(hi - 1, 0, len(t_sim) - 1)
                    hi = np.clip(hi, 0, len(t_sim) - 1)
                    exact = np.isin(t_obs, t_sim)
                    d_lo = t_obs - t_sim[lo]
                    d_hi = t_sim[hi] - t_obs
                    bad = ((d_lo > gap_ns) | (d_hi > gap_ns)) & ~exact
                    simulated[bad] = np.nan
        pieces.append(pd.DataFrame({
            "site": site,
            "datetime": group["datetime"].values,
            "observed": pd.to_numeric(group["value"], errors="coerce").values,
            "simulated": simulated,
        }))
    if not pieces:
        return pd.DataFrame(columns=["site", "datetime", "observed",
                                     "simulated"])
    out = pd.concat(pieces, ignore_index=True)
    return out.sort_values(["site", "datetime"]).reset_index(drop=True)


def resample_month_end(df, how: str = "mean",
                       iwfm_convention: bool = True) -> "pd.DataFrame":
    """Aggregate a long-form series to month-end timestamps.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value``.
    how : str, default "mean"
        Aggregation (any pandas groupby aggregation name).
    iwfm_convention : bool, default True
        Treat exact-midnight timestamps as end-of-previous-timestep
        (IWFM's 24:00 convention): a value stamped ``11/01 00:00``
        (i.e. ``10/31 24:00``) buckets into October. Disable for data
        whose midnight stamps genuinely mean start-of-day.

    Returns
    -------
    pandas.DataFrame
        Long-form ``site, datetime, value`` with month-end timestamps.
    """
    work = df.copy()
    t = pd.to_datetime(work["datetime"])
    if iwfm_convention:
        t = t - pd.Timedelta(seconds=1)
    period = t.dt.to_period("M")
    out = (work.assign(_p=period)
           .groupby(["site", "_p"])["value"].agg(how).reset_index())
    out["datetime"] = out.pop("_p").dt.to_timestamp("M")
    return out[["site", "datetime", "value"]].sort_values(
        ["site", "datetime"]).reset_index(drop=True)
