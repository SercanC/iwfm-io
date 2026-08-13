"""
Residual / calibration statistics for PEST(++) workflows.

Core entry point :func:`residual_stats` computes goodness-of-fit metrics —
count, bias, median residual, mean/max absolute residual, RMSE, R², NSE,
KGE, and (when weights are given) the PEST objective-function contribution
``phi`` — on a long-form frame of observed/simulated pairs, grouped by any
combination of columns (observation type, location, group, iteration,
realization, …).

Adapters cover the two file-shaped sources:

- :func:`rei_stats` — PEST residual files (``.rei`` / ``.res``).
- :func:`ies_stats` — PESTPP-IES observation ensembles via
  :class:`~iwfm_io.pest.ies.IesResults`, computed per
  ``(iteration, realization, group)`` with vectorized column-group
  reductions (no per-group Python loops), so full-scale ensembles
  (hundreds of realizations × 10⁵–10⁶ observations) are practical.

Conventions
-----------
``residual = observed - simulated`` (the PEST ``Measured - Modelled``
convention). Standard deviations in KGE use ``ddof=0``. Metrics that
require variance (R², NSE, KGE) are ``NaN`` for degenerate groups
(fewer than 2 values, or constant observations).
"""

from __future__ import annotations

from typing import Iterable, Optional, Union

import numpy as np
import pandas as pd

__all__ = ["METRICS", "residual_stats", "rei_stats", "ies_stats"]

#: metric columns produced (plus ``phi`` when weights are supplied)
METRICS = ["n", "mean_res", "med_res", "mean_abs_res", "max_abs_res",
           "rmse", "r2", "nse", "kge"]


def _metrics_from_sums(n, sum_o, sum_s, sum_o2, sum_s2, sum_os,
                       sum_res, sum_abs_res, max_abs_res, sum_res2,
                       med_res) -> "pd.DataFrame":
    """Assemble the metric table from per-group sufficient statistics.

    All inputs are aligned Series (or scalars broadcast against them).
    """
    n = n.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_o = sum_o / n
        mean_s = sum_s / n
        var_o = sum_o2 / n - mean_o**2
        var_s = sum_s2 / n - mean_s**2
        # numerical noise can push tiny variances negative
        var_o = var_o.where(var_o > 0)
        var_s = var_s.where(var_s > 0)
        cov = sum_os / n - mean_o * mean_s
        r = cov / np.sqrt(var_o * var_s)
        alpha = np.sqrt(var_s / var_o)
        beta = mean_s / mean_o.where(mean_o != 0)
        out = pd.DataFrame({
            "n": n.astype(int),
            "mean_res": sum_res / n,
            "med_res": med_res,
            "mean_abs_res": sum_abs_res / n,
            "max_abs_res": max_abs_res,
            "rmse": np.sqrt(sum_res2 / n),
            "r2": r**2,
            "nse": 1.0 - sum_res2 / (n * var_o),
            "kge": 1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2
                                 + (beta - 1) ** 2),
        })
    single = n < 2
    out.loc[single, ["r2", "nse", "kge"]] = np.nan
    return out


def residual_stats(df, by=None, observed: str = "observed",
                   simulated: str = "simulated",
                   weight: Optional[str] = None) -> "pd.DataFrame":
    """Goodness-of-fit statistics on a long-form observed/simulated frame.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-form frame with one row per (site, time, …) sample.
    by : str, list of str, or None
        Column(s) to group by (e.g. ``["obs_type", "location"]``).
        ``None`` computes one row for the whole frame.
    observed, simulated : str
        Column names of the observed and simulated values.
    weight : str, optional
        Weight column; adds a ``phi`` column (``Σ (w·residual)²``, the
        PEST objective-function contribution).

    Returns
    -------
    pandas.DataFrame
        One row per group (indexed by ``by``), columns :data:`METRICS`
        (+ ``phi``). Rows with NaN in either value column are dropped
        before computing.

    Examples
    --------
    >>> residual_stats(df, by=["obs_type", "location"])          # doctest: +SKIP
    >>> residual_stats(rei, observed="measured", simulated="modelled",
    ...                by="group", weight="weight")              # doctest: +SKIP
    """
    o = pd.to_numeric(df[observed], errors="coerce")
    s = pd.to_numeric(df[simulated], errors="coerce")
    valid = o.notna() & s.notna()
    o, s = o[valid], s[valid]
    res = o - s
    work = pd.DataFrame({
        "_o": o, "_s": s, "_res": res,
        "_o2": o**2, "_s2": s**2, "_os": o * s,
        "_abs": res.abs(), "_res2": res**2,
    })
    if weight is not None:
        w = pd.to_numeric(df[weight], errors="coerce")[valid]
        work["_wres2"] = (w * res) ** 2

    if by is None:
        keys = [np.zeros(len(work), dtype=int)]
    else:
        by_cols = [by] if isinstance(by, str) else list(by)
        keys = [df.loc[valid, c] for c in by_cols]
    grouped = work.groupby(keys, observed=True, dropna=False)

    agg = grouped.agg(
        n=("_o", "size"),
        sum_o=("_o", "sum"), sum_s=("_s", "sum"),
        sum_o2=("_o2", "sum"), sum_s2=("_s2", "sum"), sum_os=("_os", "sum"),
        sum_res=("_res", "sum"), med_res=("_res", "median"),
        sum_abs_res=("_abs", "sum"), max_abs_res=("_abs", "max"),
        sum_res2=("_res2", "sum"),
    )
    out = _metrics_from_sums(
        agg["n"], agg["sum_o"], agg["sum_s"],
        agg["sum_o2"], agg["sum_s2"], agg["sum_os"],
        agg["sum_res"], agg["sum_abs_res"], agg["max_abs_res"],
        agg["sum_res2"], agg["med_res"],
    )
    if weight is not None:
        out["phi"] = grouped["_wres2"].sum()
    if by is None:
        out.index = pd.Index(["all"], name="group")
    return out


def rei_stats(rei, by: Union[str, list] = "group",
              weighted_only: bool = False) -> "pd.DataFrame":
    """Statistics from a PEST residual file (``.rei``/``.res``).

    Parameters
    ----------
    rei : path or pandas.DataFrame
        Residual file path (read with
        :func:`~iwfm_io.pest.ies.read_rei`) or an already-loaded frame
        with ``measured/modelled/weight`` columns.
    by : str or list, default ``"group"``
        Grouping column(s); pass ``None`` for a single summary row.
    weighted_only : bool, default False
        Drop zero-weight observations first (carried-but-inactive
        observations otherwise dilute the statistics).

    Returns
    -------
    pandas.DataFrame
        Metric table including ``phi`` per group.
    """
    if not isinstance(rei, pd.DataFrame):
        from iwfm_io.pest.ies import read_rei
        rei = read_rei(rei)
    if weighted_only:
        rei = rei[pd.to_numeric(rei["weight"], errors="coerce") > 0]
    return residual_stats(rei, by=by, observed="measured",
                          simulated="modelled", weight="weight")


def _group_labels(names: "pd.Index", by) -> "pd.Series":
    """Resolve a per-observation grouping for ensemble stats."""
    if by is None:
        return pd.Series("all", index=names, name="group")
    if callable(by):
        return pd.Series([by(n) for n in names], index=names, name="group")
    lab = pd.Series(by) if isinstance(by, dict) else by
    lab = lab.reindex(names)
    lab.name = lab.name or "group"
    return lab


def ies_stats(results, observed=None, iterations=None, by=None) -> "pd.DataFrame":
    """Per-``(iteration, realization, group)`` statistics for an IES run.

    Parameters
    ----------
    results : IesResults
        From :func:`~iwfm_io.pest.ies.load_ies_ensembles`.
    observed : pandas.Series, optional
        Observed values indexed by observation name. Defaults to the
        ``"base"`` row of ``results.obs_plus_noise()`` (PESTPP-IES writes
        the noise-free observation values there when ``ies_add_base`` is
        on); raises if neither is available.
    iterations : int, iterable of int, or None
        Iterations to include (default: all with an observation ensemble).
    by : Series, dict, or callable, optional
        Maps observation name → group label (e.g. a decoded ``obs_type``
        column from
        :func:`~iwfm_io.pest.names.decode_obs_names`). Observations that
        map to NaN are excluded; ``None`` puts everything in one group.

    Returns
    -------
    pandas.DataFrame
        Tidy metric table indexed by ``(iteration, real_name, group)``.

    Notes
    -----
    Reductions are computed with column-transposed vectorized groupbys —
    full-scale ensembles (10⁵–10⁶ observations × 10² realizations) are
    processed without per-group Python loops.
    """
    if observed is None:
        noise = results.obs_plus_noise()
        if noise is None or "base" not in noise.index:
            raise ValueError(
                "no observed values: pass observed= (Series indexed by "
                "observation name); the obs+noise 'base' realization is "
                "not available for this run"
            )
        observed = noise.loc["base"]
    observed = pd.Series(observed).astype(float)

    if iterations is None:
        iterations = sorted(results.obs_files)
    elif isinstance(iterations, int):
        iterations = [iterations]

    pieces = {}
    for it in iterations:
        ens = results.obs(it)
        names = ens.columns.intersection(observed.index)
        labels = _group_labels(names, by).dropna()
        names = labels.index
        o = observed[names]

        s_t = ens[names].T  # observations × realizations
        res_t = -s_t.sub(o, axis=0)  # observed - simulated (PEST convention)
        g = labels.values

        def gsum(frame):
            return frame.groupby(g).sum()

        n = pd.Series(1.0, index=names).groupby(g).sum()
        sum_o = o.groupby(g).sum()
        sum_o2 = (o**2).groupby(g).sum()
        sums = {
            "sum_s": gsum(s_t), "sum_s2": gsum(s_t**2),
            "sum_os": gsum(s_t.mul(o, axis=0)),
            "sum_res": gsum(res_t), "sum_abs": gsum(res_t.abs()),
            "sum_res2": gsum(res_t**2),
            "max_abs": res_t.abs().groupby(g).max(),
            "med": res_t.groupby(g).median(),
        }
        # stack (group × realization) → long index, then broadcast the
        # observation-side sums per group
        stacked = {k: v.stack() for k, v in sums.items()}
        idx = stacked["sum_s"].index  # (group, real_name)
        grp = idx.get_level_values(0)
        out = _metrics_from_sums(
            pd.Series(n[grp].values, index=idx),
            pd.Series(sum_o[grp].values, index=idx),
            stacked["sum_s"],
            pd.Series(sum_o2[grp].values, index=idx),
            stacked["sum_s2"], stacked["sum_os"],
            stacked["sum_res"], stacked["sum_abs"], stacked["max_abs"],
            stacked["sum_res2"], stacked["med"],
        )
        out.index.names = ["group", "real_name"]
        pieces[it] = out

    tidy = pd.concat(pieces, names=["iteration"])
    return tidy.reorder_levels(["iteration", "real_name", "group"]).sort_index()
