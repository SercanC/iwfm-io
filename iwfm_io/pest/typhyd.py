"""
Typical (cluster-average) hydrographs — a CalcTypHyd equivalent.

DWR's CalcTypHyd Fortran utility condenses many noisy observation-well
records into a few "typical hydrographs", one per well cluster — smooth,
representative series that make robust calibration targets (C2VSim used
them as PEST observation groups alongside the raw well records).

The algorithm, per cluster:

1. Bin each well's observations into period-year slots (default: the
   four seasons of each year) and average within each slot.
2. Compute each well's mean as the mean of its *slot averages* — not of
   its raw observations — so densely sampled seasons don't dominate.
3. De-mean each slot average by its well's mean, so wells at different
   absolute water levels contribute comparable anomalies.
4. Average the de-meaned slot values across the cluster's wells,
   weighted by membership weight (fuzzy clustering supported), at each
   period-year. The value is stamped at the period's representative
   date in that year.

:func:`typical_hydrographs` is a pure transform on the package's
standard long-form ``site, datetime, value`` layout, and its output is
the same layout (``site`` = cluster label) — so the identical call
derives the observed series (from field data) and the simulated series
(from model output at the same wells), and the two align
point-for-point for :func:`~iwfm_io.pest.stats.residual_stats`,
:func:`~iwfm_io.pest.smp.write_smp`, or observation-file generation.
Because each side is de-meaned by its *own* well means, the comparison
targets the shape and seasonal dynamics of the water-level record, not
its absolute elevation.

Periods spanning the calendar-year boundary are handled by nearest
representative date: with the default winter period (Dec–Feb,
representative Jan 15), a December 2000 measurement counts toward the
winter *2001* slot.

Typical pairing workflow::

    typ_obs = typical_hydrographs(obs, clusters)
    typ_sim = typical_hydrographs(sim, clusters)
    paired = match_sim_to_obs(typ_sim.series, typ_obs.series,
                              method="nearest")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

__all__ = ["Period", "PERIODS_QUARTERLY", "PERIODS_SPRING_FALL",
           "TypicalHydrographs", "typical_hydrographs"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Period:
    """One averaging period of the typical-hydrograph year.

    Attributes
    ----------
    name : str
        Period label, carried into the output's ``period`` column.
    months : tuple
        Calendar months (1–12) whose observations the period averages.
    rep : str
        Representative date, ``"MM/DD"`` — the timestamp the period's
        value is stamped at (in the slot's year). Keep the day <= 28 so
        every year is valid.
    """

    name: str
    months: "tuple"
    rep: str

    def rep_month_day(self) -> "tuple":
        month, day = (int(p) for p in self.rep.split("/"))
        if not (1 <= month <= 12 and 1 <= day <= 28):
            raise ValueError(
                f"period {self.name!r}: rep must be MM/DD with day <= 28 "
                f"(valid in every year), got {self.rep!r}")
        bad = [m for m in self.months if not 1 <= int(m) <= 12]
        if bad or not self.months:
            raise ValueError(
                f"period {self.name!r}: months must be 1-12, got "
                f"{tuple(self.months)}")
        return month, day


#: The classic CalcTypHyd quarterly seasons.
PERIODS_QUARTERLY = (
    Period("winter", (12, 1, 2), "01/15"),
    Period("spring", (3, 4, 5), "04/15"),
    Period("summer", (6, 7, 8), "07/15"),
    Period("fall", (9, 10, 11), "10/15"),
)

#: Biannual spring-high / fall-low periods (the CASGEM/CNRA measurement
#: seasons commonly used for California groundwater-level data).
PERIODS_SPRING_FALL = (
    Period("spring", (1, 2, 3, 4), "03/01"),
    Period("fall", (8, 9, 10, 11), "10/01"),
)


@dataclass
class TypicalHydrographs:
    """Result of :func:`typical_hydrographs`.

    Attributes
    ----------
    series : pandas.DataFrame
        Long-form ``site, datetime, value`` (``site`` = cluster label
        as a string) plus ``period`` and ``n_wells`` (wells that
        contributed to the point).
    well_means : pandas.Series
        Per-well mean of slot averages (the de-meaning offsets),
        indexed by well site.
    wells : pandas.DataFrame
        One row per contributing (cluster, well): ``cluster, site,
        weight, n_slots``.
    """

    series: "pd.DataFrame"
    well_means: "pd.Series"
    wells: "pd.DataFrame"

    def summary(self) -> dict:
        return {
            "n_clusters": int(self.series["site"].nunique()),
            "n_points": int(len(self.series)),
            "n_wells": int(self.wells["site"].nunique()),
        }


def _cluster_table(clusters) -> "pd.DataFrame":
    """Normalize cluster membership to long-form site, cluster, weight."""
    if isinstance(clusters, Mapping):
        clusters = pd.Series(clusters)
    if isinstance(clusters, pd.Series):
        out = pd.DataFrame({"site": clusters.index.astype(str),
                            "cluster": clusters.values,
                            "weight": 1.0})
    elif isinstance(clusters, pd.DataFrame):
        cols = set(clusters.columns)
        id_col = ("site" if "site" in cols
                  else "well_id" if "well_id" in cols else None)
        if id_col is not None and "cluster" in cols:
            out = clusters.rename(columns={id_col: "site"})
            out = out[["site", "cluster"]
                      + (["weight"] if "weight" in cols else [])].copy()
            if "weight" not in out.columns:
                out["weight"] = 1.0
        else:  # wide: index = site, columns = cluster labels, values = weights
            out = clusters.stack().rename("weight").reset_index()
            out.columns = ["site", "cluster", "weight"]
    else:
        raise TypeError(
            "clusters must be a site->cluster mapping/Series, a long "
            "frame (site/well_id, cluster[, weight]), or a wide frame "
            "(site index x cluster columns of weights)")
    out["site"] = out["site"].astype(str).str.strip()
    out["weight"] = pd.to_numeric(out["weight"])
    if (out["weight"] < 0).any():
        raise ValueError("cluster weights must be non-negative")
    out = out[out["weight"] > 0].reset_index(drop=True)
    dup = out.duplicated(subset=["site", "cluster"])
    if dup.any():
        raise ValueError(
            f"duplicate (site, cluster) membership row(s), e.g. "
            f"{out.loc[dup, ['site', 'cluster']].head(3).to_dict('records')}")
    return out


def typical_hydrographs(df, clusters, periods: Optional[Sequence] = None,
                        start=None, end=None, min_obs: int = 1,
                        demean: bool = True) -> TypicalHydrographs:
    """Compute cluster-average typical hydrographs (CalcTypHyd).

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form ``site, datetime, value`` well records (observed or
        simulated). Rows flagged in an ``excluded`` column (as written
        by :func:`~iwfm_io.pest.smp.read_smp`) are dropped.
    clusters : Series, mapping, or DataFrame
        Cluster membership. A ``site -> cluster`` mapping/Series (crisp,
        weight 1), a long frame with ``site`` (or ``well_id``),
        ``cluster`` and optional ``weight`` columns, or a wide frame of
        fuzzy weights (site index x one column per cluster). Zero
        weights drop the membership.
    periods : sequence of :class:`Period`, optional
        Averaging periods; default :data:`PERIODS_QUARTERLY`
        (:data:`PERIODS_SPRING_FALL` fits spring/fall measurement
        programs).
    start, end : datetime-like, optional
        Limit the record: observations outside ``[start, end]`` are
        dropped, and slots whose representative month falls outside the
        range are not emitted. Defaults to the data's span.
    min_obs : int, default 1
        Minimum observations a (well, period, year) slot needs to
        produce a slot average.
    demean : bool, default True
        Subtract each well's mean of slot averages before combining
        (the CalcTypHyd anomaly convention). ``False`` averages
        absolute values — only meaningful for clusters of wells at
        comparable water levels.

    Returns
    -------
    TypicalHydrographs
        ``.series`` is the package's standard long-form layout with the
        cluster label as ``site``, ready for ``write_smp``,
        ``match_sim_to_obs``, and ``residual_stats``.
    """
    if min_obs < 1:
        raise ValueError(f"min_obs must be >= 1, got {min_obs}")
    period_list = list(periods) if periods is not None \
        else list(PERIODS_QUARTERLY)
    rep_md = [p.rep_month_day() for p in period_list]

    work = df.copy()
    if "excluded" in work.columns:
        excl = work["excluded"].fillna(False).astype(bool)
        if excl.any():
            logger.info("dropping %d excluded observation(s)",
                        int(excl.sum()))
        work = work[~excl]
    work = pd.DataFrame({
        "site": work["site"].astype(str).str.strip(),
        "datetime": pd.to_datetime(work["datetime"]),
        "value": pd.to_numeric(work["value"], errors="coerce"),
    }).dropna(subset=["value"])
    if start is not None:
        work = work[work["datetime"] >= pd.Timestamp(start)]
    if end is not None:
        work = work[work["datetime"] <= pd.Timestamp(end)]

    cl = _cluster_table(clusters)
    have = set(work["site"])
    no_data = sorted(set(cl["site"]) - have)
    if no_data:
        logger.warning(
            "%d clustered well(s) have no observations, e.g. %s",
            len(no_data), no_data[:5])

    empty = pd.DataFrame(
        columns=["site", "datetime", "period", "value", "n_wells"])
    if not len(work):
        return TypicalHydrographs(
            series=empty, well_means=pd.Series(dtype=float),
            wells=pd.DataFrame(
                columns=["cluster", "site", "weight", "n_slots"]))

    # slot-validity bounds, in absolute months (year*12 + month)
    t0 = pd.Timestamp(start) if start is not None else work["datetime"].min()
    t1 = pd.Timestamp(end) if end is not None else work["datetime"].max()
    lo, hi = t0.year * 12 + t0.month, t1.year * 12 + t1.month

    month = work["datetime"].dt.month
    total = work["datetime"].dt.year * 12 + month
    slot_frames = []
    for p, (rep_month, rep_day) in zip(period_list, rep_md):
        sel = month.isin([int(m) for m in p.months])
        if not sel.any():
            continue
        # nearest slot year: December belongs to the following January's
        # winter (circular distance to the representative month)
        slot_year = (total[sel] - rep_month + 6) // 12
        g = (work[sel].groupby([work.loc[sel, "site"], slot_year])["value"]
             .agg(avg="mean", n_obs="count"))
        g.index.names = ["site", "slot_year"]
        g = g[g["n_obs"] >= min_obs].reset_index()
        rep_total = g["slot_year"] * 12 + rep_month
        g = g[(rep_total >= lo) & (rep_total <= hi)]
        if not len(g):
            continue
        g["period"] = p.name
        g["datetime"] = pd.to_datetime(pd.DataFrame({
            "year": g["slot_year"], "month": rep_month, "day": rep_day}))
        slot_frames.append(g)

    if not slot_frames:
        return TypicalHydrographs(
            series=empty, well_means=pd.Series(dtype=float),
            wells=pd.DataFrame(
                columns=["cluster", "site", "weight", "n_slots"]))
    slots = pd.concat(slot_frames, ignore_index=True)

    # per-well mean of slot averages (the CalcTypHyd convention -- NOT
    # the mean of raw observations)
    well_means = slots.groupby("site")["avg"].mean()
    well_means.name = "well_mean"
    slots["anom"] = slots["avg"] - slots["site"].map(well_means) \
        if demean else slots["avg"]

    merged = slots.merge(cl, on="site")
    if not len(merged):
        logger.warning("no clustered well has any usable slot average")
        return TypicalHydrographs(
            series=empty, well_means=well_means,
            wells=pd.DataFrame(
                columns=["cluster", "site", "weight", "n_slots"]))
    merged["wsum"] = merged["weight"] * merged["anom"]
    g = (merged.groupby(["cluster", "datetime", "period"])
         .agg(value=("wsum", "sum"), weight=("weight", "sum"),
              n_wells=("site", "nunique")).reset_index())
    g["value"] = g["value"] / g["weight"]
    series = pd.DataFrame({
        "site": g["cluster"].astype(str),
        "datetime": g["datetime"],
        "period": g["period"],
        "value": g["value"],
        "n_wells": g["n_wells"],
    }).sort_values(["site", "datetime"]).reset_index(drop=True)

    wells = (merged.groupby(["cluster", "site"])
             .agg(weight=("weight", "first"), n_slots=("anom", "count"))
             .reset_index())
    result = TypicalHydrographs(series=series, well_means=well_means,
                                wells=wells)
    logger.info("typical_hydrographs: %s", result.summary())
    return result
