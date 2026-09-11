"""
Pilot-point parameterization on the IWFM finite-element mesh.

Pilot points are the standard spatial parameterization for
C2VSim-scale models: PEST estimates values at a few dozen points, and
kriging spreads them to every model node. The expensive part — solving
the kriging systems — depends only on geometry, so it is computed once
at setup (:func:`compute_kriging_factors`) and persisted; the forward
run applies the factors with a sparse multiply
(:func:`apply_kriging_factors`, the ``FAC2REAL`` role).

Self-contained pure-numpy ordinary kriging (no scipy or pyemu):
variogram models :class:`ExpVariogram`, :class:`SphVariogram`,
:class:`GauVariogram` with optional geometric anisotropy, exact
interpolation at pilot-point locations, weights summing to 1.

Helpers: :func:`place_pilot_points_grid` lays out a regular grid of
pilot points clipped to the model's node cloud (optionally per zone).

Example::

    pps = place_pilot_points_grid(model, spacing=20_000.0)
    fac = compute_kriging_factors(pps, model.nodes_df(),
                                  ExpVariogram(a=40_000.0), max_points=12)
    fac.to_csv("pp_factors.csv", index=False)
    # forward run:
    kh_nodes = apply_kriging_factors(fac, pp_values, log=True)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

__all__ = ["ExpVariogram", "SphVariogram", "GauVariogram",
           "place_pilot_points_grid", "compute_kriging_factors",
           "apply_kriging_factors"]

logger = logging.getLogger(__name__)


# ------------------------------------------------------------- variograms
@dataclass
class _Variogram:
    """Base variogram: ``a`` = range, ``sill`` = 1, ``nugget`` optional.

    ``anisotropy`` stretches the *minor* axis by the given ratio after
    rotating by ``bearing`` degrees (clockwise from north, the PEST
    convention) — distances along the bearing use the full range,
    across it ``range / anisotropy``.
    """

    a: float
    nugget: float = 0.0
    anisotropy: float = 1.0
    bearing: float = 0.0

    def _h(self, dx, dy):
        if self.anisotropy != 1.0 or self.bearing != 0.0:
            b = np.deg2rad(self.bearing)
            # rotate so the major axis lies along y (north at bearing 0)
            u = dx * np.cos(b) - dy * np.sin(b)
            v = dx * np.sin(b) + dy * np.cos(b)
            return np.hypot(u * self.anisotropy, v)
        return np.hypot(dx, dy)

    def gamma(self, dx, dy):
        h = self._h(dx, dy)
        g = self.nugget + (1.0 - self.nugget) * self._model(h / self.a)
        return np.where(h == 0, 0.0, g)


class ExpVariogram(_Variogram):
    """Exponential: ``γ = 1 − exp(−3h/a)``."""

    def _model(self, hr):
        return 1.0 - np.exp(-3.0 * hr)


class SphVariogram(_Variogram):
    """Spherical: reaches the sill exactly at ``h = a``."""

    def _model(self, hr):
        hr = np.minimum(hr, 1.0)
        return 1.5 * hr - 0.5 * hr**3


class GauVariogram(_Variogram):
    """Gaussian: ``γ = 1 − exp(−3(h/a)²)`` (very smooth near origin)."""

    def _model(self, hr):
        return 1.0 - np.exp(-3.0 * hr**2)


# ------------------------------------------------------------- placement
def place_pilot_points_grid(model_or_nodes, spacing: float,
                            zones=None, buffer: Optional[float] = None
                            ) -> "pd.DataFrame":
    """Regular pilot-point grid clipped to the model's node cloud.

    Parameters
    ----------
    model_or_nodes : model or DataFrame
        Anything with ``nodes_df()``, or a frame with ``x, y`` columns.
    spacing : float
        Grid spacing in model length units.
    zones : Series, optional
        Zone label per node (same index as the nodes frame); pilot
        points inherit the zone of their nearest node.
    buffer : float, optional
        Keep grid points within this distance of some node (default:
        *spacing* — drops points outside the model footprint).

    Returns
    -------
    pandas.DataFrame
        ``pp_id, x, y`` (+ ``zone``), ``pp_id`` like ``pp0001``.
    """
    nodes = (model_or_nodes.nodes_df()
             if hasattr(model_or_nodes, "nodes_df") else model_or_nodes)
    nx = nodes["x"].values.astype(float)
    ny = nodes["y"].values.astype(float)
    buffer = spacing if buffer is None else buffer

    gx = np.arange(nx.min(), nx.max() + spacing, spacing)
    gy = np.arange(ny.min(), ny.max() + spacing, spacing)
    XX, YY = np.meshgrid(gx, gy)
    pts = np.column_stack([XX.ravel(), YY.ravel()])

    keep, nearest = [], []
    for px, py in pts:
        d2 = (nx - px) ** 2 + (ny - py) ** 2
        j = int(d2.argmin())
        if d2[j] <= buffer**2:
            keep.append((px, py))
            nearest.append(j)
    if not keep:
        raise ValueError(
            "no pilot points inside the model footprint — spacing or "
            "buffer too small?")
    out = pd.DataFrame(keep, columns=["x", "y"])
    out.insert(0, "pp_id", [f"pp{i + 1:04d}" for i in range(len(out))])
    if zones is not None:
        z = pd.Series(zones).reset_index(drop=True)
        out["zone"] = z.iloc[nearest].values
    return out


# --------------------------------------------------------------- factors
def compute_kriging_factors(pilot_points, targets, variogram,
                            max_points: int = 12,
                            search_radius: Optional[float] = None,
                            same_zone_only: bool = False) -> "pd.DataFrame":
    """Ordinary-kriging weights from pilot points to target locations.

    The setup-time step (PPK2FAC role): one small linear solve per
    target using its nearest pilot points.

    Parameters
    ----------
    pilot_points : pandas.DataFrame
        ``pp_id, x, y`` (+ ``zone`` when *same_zone_only*).
    targets : pandas.DataFrame
        Target locations: ``node_id`` (or ``pp_id``-style id column
        named ``node_id``) with ``x, y`` (+ ``zone``). Typically
        ``model.nodes_df()``.
    variogram : ExpVariogram / SphVariogram / GauVariogram
    max_points : int, default 12
        Pilot points used per target (the nearest ones).
    search_radius : float, optional
        Ignore pilot points farther than this; targets with none in
        range raise.
    same_zone_only : bool, default False
        Restrict each target to pilot points of its own ``zone``
        (hard zone boundaries).

    Returns
    -------
    pandas.DataFrame
        Long-form ``node_id, pp_id, weight`` — weights per target sum
        to 1 (ordinary-kriging unbiasedness).
    """
    pp = pilot_points.reset_index(drop=True)
    tg = targets.reset_index(drop=True)
    if same_zone_only and ("zone" not in pp.columns
                           or "zone" not in tg.columns):
        raise ValueError("same_zone_only requires 'zone' in both frames")

    px = pp["x"].values.astype(float)
    py = pp["y"].values.astype(float)
    rows = []
    for _, t in tg.iterrows():
        dx, dy = px - float(t["x"]), py - float(t["y"])
        cand = np.arange(len(pp))
        if same_zone_only:
            cand = cand[pp["zone"].values == t["zone"]]
        if search_radius is not None:
            d = np.hypot(dx[cand], dy[cand])
            cand = cand[d <= search_radius]
        if len(cand) == 0:
            raise ValueError(
                f"target {t.get('node_id', '?')}: no pilot point in "
                f"range/zone")
        d2 = dx[cand] ** 2 + dy[cand] ** 2
        sel = cand[np.argsort(d2)[:max_points]]

        n = len(sel)
        A = np.ones((n + 1, n + 1))
        A[n, n] = 0.0
        A[:n, :n] = variogram.gamma(
            px[sel][:, None] - px[sel][None, :],
            py[sel][:, None] - py[sel][None, :])
        b = np.ones(n + 1)
        b[:n] = variogram.gamma(px[sel] - float(t["x"]),
                                py[sel] - float(t["y"]))
        try:
            w = np.linalg.solve(A, b)[:n]
        except np.linalg.LinAlgError:
            w = np.linalg.lstsq(A, b, rcond=None)[0][:n]
        for j, wj in zip(sel, w):
            rows.append((t["node_id"], pp.at[j, "pp_id"], float(wj)))
    out = pd.DataFrame(rows, columns=["node_id", "pp_id", "weight"])
    return out


def apply_kriging_factors(factors, pp_values, log: bool = False
                          ) -> "pd.Series":
    """Interpolate pilot-point values to targets (the FAC2REAL role).

    Parameters
    ----------
    factors : pandas.DataFrame
        From :func:`compute_kriging_factors` (or its CSV re-read).
    pp_values : Series or dict
        Value per ``pp_id``. Missing pilot points raise.
    log : bool, default False
        Krige in log10 space (standard for conductivities): weights are
        applied to ``log10(value)`` and the result exponentiated.

    Returns
    -------
    pandas.Series
        Value per ``node_id``.
    """
    vals = pd.Series(pp_values).astype(float)
    vals.index = vals.index.astype(str)
    if not np.isfinite(vals.to_numpy()).all():
        bad = vals.index[~np.isfinite(vals.to_numpy())].tolist()
        raise ValueError(
            f"pp_values has NaN/inf for pilot point(s) {bad[:3]}")
    pp_ids = factors["pp_id"].astype(str)
    missing = set(pp_ids) - set(vals.index)
    if missing:
        raise KeyError(
            f"pp_values missing for {len(missing)} pilot point(s), "
            f"e.g. {sorted(missing)[:3]}")
    if log:
        if (vals <= 0).any():
            raise ValueError("log kriging requires positive pilot values")
        vals = np.log10(vals)
    wsum = factors.groupby("node_id")["weight"].sum()
    off = wsum[(wsum - 1.0).abs() > 1e-6]
    if len(off):
        raise ValueError(
            f"kriging weights do not sum to 1 for {len(off)} node(s), "
            f"e.g. {off.head(3).to_dict()}")
    v = pp_ids.map(vals).astype(float) * factors["weight"]
    out = v.groupby(factors["node_id"]).sum()
    if log:
        out = 10.0**out
    out.name = "value"
    return out
