"""
Observation weight balancing by phi budget.

Standard PEST(++) practice: run once at ``noptmax=0``, inspect how the
objective function (phi) is distributed over observation groups, then
rescale weights so each *category* of observations contributes a chosen
target — otherwise plentiful-but-cheap observations (e.g. 10⁵ monthly
heads) silently drown out scarce-but-important ones (e.g. budget terms).

:func:`balance_weights` implements the rescale on plain DataFrames: for
each group matched by a budget pattern, weights are multiplied by
``sqrt(target_phi / current_phi)`` so the group's phi lands on target.
It needs only the observation-data table (``obsnme, weight, obgnme`` —
in PEST++ v2 control files this is already an external CSV) and residuals
from any source (a ``.rei``/``.res`` file, a base-realization
:meth:`~iwfm_io.pest.ies.IesResults.base_rei`, or a Series). No pyemu
required; :func:`balance_pst_weights` is a thin adapter that applies the
same core to a classic ``.pst`` through pyemu when it is installed.

Per-observation 1/σ weighting composes naturally: set ``weight = 1/σ``
per observation first, then balance categories on top — the rescale is
uniform within each group, so relative 1/σ weighting is preserved.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

__all__ = ["WeightBalance", "balance_weights", "balance_pst_weights"]

logger = logging.getLogger(__name__)


@dataclass
class WeightBalance:
    """Result of :func:`balance_weights`.

    Attributes
    ----------
    obs_data : pandas.DataFrame
        Copy of the input observation data with the ``weight`` column
        rescaled.
    report : pandas.DataFrame
        One row per observation group: ``pattern, n_obs, n_nonzero,
        phi_before, target, factor, phi_after, share_before,
        share_after``. Groups not matched by any budget pattern have
        ``pattern = NaN`` and ``factor = 1``.
    """

    obs_data: "pd.DataFrame"
    report: "pd.DataFrame"


def _match_groups(groups, budgets) -> "pd.Series":
    """Map each group to the budget pattern it matches.

    A pattern matches a group by exact name, by regex fullmatch, or as a
    prefix (checked in that order). A group matching two different
    patterns is an error — overlapping budgets would be ambiguous.
    """
    assigned = {}
    for pattern in budgets:
        try:
            rx = re.compile(pattern)
        except re.error:
            rx = None
        for g in groups:
            hit = (g == pattern
                   or (rx is not None and rx.fullmatch(g) is not None)
                   or g.startswith(pattern))
            if not hit:
                continue
            if g in assigned and assigned[g] != pattern:
                raise ValueError(
                    f"observation group {g!r} matches two budget patterns: "
                    f"{assigned[g]!r} and {pattern!r}"
                )
            assigned[g] = pattern
    return pd.Series(assigned, dtype=object)


def _residual_series(residuals) -> "pd.Series":
    """Accept a Series (obsnme → residual) or a rei-style DataFrame."""
    if isinstance(residuals, pd.DataFrame):
        if not {"name", "residual"} <= set(residuals.columns):
            raise ValueError(
                "residuals DataFrame needs 'name' and 'residual' columns "
                "(as returned by read_rei / IesResults.base_rei)"
            )
        s = residuals.set_index("name")["residual"]
    else:
        s = pd.Series(residuals)
    s.index = s.index.astype(str).str.lower()
    return pd.to_numeric(s, errors="coerce")


def balance_weights(obs_data, residuals, budgets: Dict[str, float],
                    split: str = "even",
                    min_weight: Optional[float] = None,
                    max_weight: Optional[float] = None) -> WeightBalance:
    """Rescale observation weights so group phi hits per-category targets.

    Parameters
    ----------
    obs_data : pandas.DataFrame
        Observation data with columns ``obsnme, weight, obgnme`` (the
        PEST++ v2 external observation-data layout; extra columns pass
        through untouched).
    residuals : Series, DataFrame, or path-like
        Residuals (``measured - modelled``) per observation name: a
        Series, a frame from
        :func:`~iwfm_io.pest.ies.read_rei` /
        :meth:`~iwfm_io.pest.ies.IesResults.base_rei`, or a ``.rei`` path.
    budgets : dict
        ``{pattern: target_phi}``. A pattern matches groups by exact
        name, regex fullmatch, or prefix — e.g. ``{"gwh": 1500}``
        matches every group starting with ``gwh``. A group matching two
        patterns raises.
    split : {"even", "proportional"}
        How a pattern's target is divided among its matched groups:
        equal shares, or proportional to each group's current phi
        (preserving relative balance within the category).
    min_weight, max_weight : float, optional
        Clip rescaled weights (zero weights always stay zero). Clipping
        moves ``phi_after`` off target; the report shows the realized
        value.

    Returns
    -------
    WeightBalance

    Raises
    ------
    ValueError
        On overlapping budget patterns, a pattern matching no group,
        or residuals missing for weighted observations.
    """
    if split not in ("even", "proportional"):
        raise ValueError(f"split must be 'even' or 'proportional', got {split!r}")
    obs = obs_data.copy()
    for col in ("obsnme", "weight", "obgnme"):
        if col not in obs.columns:
            raise ValueError(f"obs_data is missing required column {col!r}")

    if not isinstance(residuals, (pd.Series, pd.DataFrame)):
        from iwfm_io.pest.ies import read_rei
        residuals = read_rei(residuals)
    res = _residual_series(residuals)

    names = obs["obsnme"].astype(str).str.lower()
    weight = pd.to_numeric(obs["weight"], errors="coerce").fillna(0.0)
    group = obs["obgnme"].astype(str).str.lower()

    aligned = res.reindex(names)
    missing = weight.gt(0).values & aligned.isna().values
    if missing.any():
        raise ValueError(
            f"residuals missing for {int(missing.sum())} weighted "
            f"observation(s), e.g. {names[missing].head(3).tolist()}"
        )

    contrib = pd.Series((weight.values * aligned.values) ** 2, index=group.values)
    phi_before = contrib.groupby(level=0).sum()
    counts = group.value_counts()
    nonzero_counts = group[weight > 0].value_counts()

    matched = _match_groups(phi_before.index, budgets)
    unmatched_patterns = set(budgets) - set(matched.values)
    if unmatched_patterns:
        raise ValueError(
            f"budget pattern(s) matched no observation group: "
            f"{sorted(unmatched_patterns)}; groups present: "
            f"{sorted(phi_before.index)}"
        )

    factor = pd.Series(1.0, index=phi_before.index)
    target = pd.Series(np.nan, index=phi_before.index)
    for pattern, total in budgets.items():
        members = matched[matched == pattern].index
        phis = phi_before[members]
        # a zero-phi group (all-zero weights or residuals) cannot be
        # scaled to a target — split the budget over scalable groups only
        zero = phis.index[phis == 0]
        if len(zero):
            logger.warning(
                "pattern %r: %d matched group(s) have zero phi and are "
                "left unchanged (e.g. %s)", pattern, len(zero),
                ", ".join(zero[:3]))
        scalable = phis.index[phis > 0]
        if not len(scalable):
            continue
        if split == "even":
            targets = pd.Series(total / len(scalable), index=scalable)
        else:
            targets = total * phis[scalable] / phis[scalable].sum()
        for g in scalable:
            target[g] = targets[g]
            factor[g] = np.sqrt(targets[g] / phi_before[g])

    new_weight = weight.values * factor[group.values].values
    if min_weight is not None or max_weight is not None:
        clipped = np.clip(new_weight, min_weight, max_weight)
        clipped[weight.values == 0] = 0.0  # zero stays zero despite min_weight
        new_weight = clipped
    obs["weight"] = new_weight

    phi_after = (pd.Series((new_weight * aligned.values) ** 2,
                           index=group.values).groupby(level=0).sum())
    total_before, total_after = phi_before.sum(), phi_after.sum()
    report = pd.DataFrame({
        "pattern": matched.reindex(phi_before.index),
        "n_obs": counts.reindex(phi_before.index).fillna(0).astype(int),
        "n_nonzero": nonzero_counts.reindex(phi_before.index).fillna(0).astype(int),
        "phi_before": phi_before,
        "target": target,
        "factor": factor,
        "phi_after": phi_after,
        "share_before": phi_before / total_before if total_before else np.nan,
        "share_after": phi_after / total_after if total_after else np.nan,
    }).sort_values(["pattern", "phi_before"], ascending=[True, False])
    report.index.name = "obgnme"
    return WeightBalance(obs_data=obs, report=report)


def balance_pst_weights(pst_path, budgets: Dict[str, float],
                        residuals=None, **kwargs) -> "WeightBalance":
    """Balance weights of a classic ``.pst`` control file via pyemu.

    Thin adapter over :func:`balance_weights`: loads the control file
    with pyemu, takes residuals from ``residuals`` (any form the core
    accepts) or the control file's own residual file (``pst.res``),
    applies the rescaled weights back onto ``pst.observation_data``, and
    returns the :class:`WeightBalance` with the modified ``pyemu.Pst``
    attached as ``.pst``. Writing the updated file is left to the caller
    (``wb.pst.write(...)``).

    Requires pyemu (``pip install pyemu``).
    """
    try:
        import pyemu
    except ImportError:
        raise RuntimeError(
            "balance_pst_weights requires pyemu (pip install pyemu); "
            "for PEST++ v2 external-CSV control files, use "
            "balance_weights on the observation-data CSV directly"
        ) from None
    pst = pyemu.Pst(str(pst_path))
    obs = pst.observation_data[["obsnme", "weight", "obgnme"]].copy()
    if residuals is None:
        res = pst.res
        if res is None:
            raise ValueError(
                "no residuals: pass residuals= or place the .rei/.res "
                "file next to the control file"
            )
        residuals = res["residual"] if "residual" in res else res
    wb = balance_weights(obs, residuals, budgets, **kwargs)
    new_w = wb.obs_data.set_index("obsnme")["weight"]
    pst.observation_data.loc[new_w.index, "weight"] = new_w
    wb.pst = pst
    return wb
