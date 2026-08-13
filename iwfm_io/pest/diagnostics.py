"""
IES run-health diagnostics: distill a PESTPP-IES run into a compact state.

:func:`diagnose_ies` reads a run through
:class:`~iwfm_io.pest.ies.IesResults` and produces an
:class:`IesDiagnostics` — a few-KB JSON-serializable dict of metrics and
boolean *signals*, plus a human-readable summary. The design target is
the same as ``IOModelAdapter.describe()``: small enough to hand to a
person or an LLM reasoning layer without ever exposing the raw
multi-hundred-MB ensembles.

Sections (each individually fault-tolerant — a missing file yields a
``note``/``error`` entry, never an exception):

- **phi** — per-iteration mean/min/max/std, total and last-step relative
  reduction, ensemble std collapse ratio. Signals: ``phi_stalled``,
  ``ensemble_collapsed``.
- **prior_data_conflict** — count and rate of observations PESTPP-IES
  flagged as prior-data conflicts, by observation category. Signal:
  ``conflict_systemic``.
- **bound_railing** — % of (parameter × realization) values within
  tolerance of a bound in the last ensemble, per parameter group,
  log-transform aware. Needs the parameter-data table (bounds). Signal:
  ``railing_present``.
- **residuals** — base-realization residuals by observation group: bias,
  absolute mean, and (when observation names decode to dates) a linear
  time trend per year. Flags structurally suspect groups.
- **outliers** — weighted observations with |residual| over a threshold.
- **objective_balance** — last-iteration phi share by category. Signals:
  ``objective_imbalance``, ``dominant_category``.

Example::

    from iwfm_io.pest import load_ies_ensembles, diagnose_ies

    diag = diagnose_ies(load_ies_ensembles("master/case.pst"),
                        par_data="master/case_par_data.csv")
    print(diag.summary())
    diag.to_json("diag_state.json")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

__all__ = ["DiagThresholds", "IesDiagnostics", "diagnose_ies"]

logger = logging.getLogger(__name__)


@dataclass
class DiagThresholds:
    """Cut-offs that turn metrics into boolean signals.

    Defaults follow common PEST practice (and the values proven on a
    C2VSimCG-scale IES calibration); override any of them per call.
    """

    #: relative last-step phi reduction below this → ``phi_stalled``
    phiredstp: float = 0.01
    #: last/first ensemble phi std below this → ``ensemble_collapsed``
    collapse_ratio: float = 0.30
    #: conflicts / nonzero obs above this → ``conflict_systemic``
    conflict_systemic: float = 0.40
    #: within this fraction of the (transformed) bound span = railed
    rail_tol: float = 0.02
    #: a group with more than this fraction railed is flagged
    rail_flag: float = 0.25
    #: |residual| above this → outlier (model units)
    outlier_threshold: float = 100.0
    #: |group mean residual| above this → biased group
    bias_threshold: float = 15.0
    #: |residual trend| (units/year) above this → drifting group
    trend_threshold: float = 1.0
    #: rows kept in top-N tables
    top_n: int = 20


@dataclass
class IesDiagnostics:
    """Result of :func:`diagnose_ies`.

    ``state`` is a JSON-serializable nested dict (one key per section,
    plus ``signals`` aggregating every boolean signal); :meth:`summary`
    renders a short human-readable digest; :meth:`to_json` writes the
    state to disk.
    """

    case: str
    state: dict = field(default_factory=dict)

    @property
    def signals(self) -> dict:
        """All boolean signals from all sections, flattened."""
        out = {}
        for section, content in self.state.items():
            if isinstance(content, dict):
                for k, v in content.get("signals", {}).items():
                    out[k] = v
        return out

    def to_json(self, path=None) -> str:
        text = json.dumps({"case": self.case, **self.state},
                          indent=2, default=str)
        if path is not None:
            Path(path).write_text(text)
        return text

    def summary(self) -> str:
        lines = [f"PESTPP-IES diagnostics — {self.case}"]
        phi = self.state.get("phi", {})
        if "per_iteration" in phi:
            means = [round(p["mean"]) for p in phi["per_iteration"]]
            lines.append(
                f"  phi mean by iteration: {means}"
                f" (total reduction {phi.get('total_phi_reduction_frac')})")
        pdc = self.state.get("prior_data_conflict", {})
        if "total_conflicts" in pdc:
            lines.append(
                f"  prior-data conflict: {pdc['total_conflicts']} obs"
                f" (rate {pdc.get('conflict_rate')})")
        rail = self.state.get("bound_railing", {})
        if "flagged_groups" in rail:
            lines.append(
                f"  railed parameter groups (>"
                f"{rail.get('flag_threshold_pct')}%):"
                f" {list(rail['flagged_groups']) or 'none'}")
        res = self.state.get("residuals", {})
        if "flagged_groups" in res:
            lines.append(
                f"  structurally suspect obs groups:"
                f" {list(res['flagged_groups']) or 'none'}")
        outl = self.state.get("outliers", {})
        if "n_over_threshold" in outl:
            lines.append(
                f"  |residual| > {outl['threshold']}:"
                f" {outl['n_over_threshold']} obs")
        obj = self.state.get("objective_balance", {})
        if "category_share" in obj:
            dom = obj["signals"].get("dominant_category")
            share = obj["category_share"].get(dom)
            lines.append(f"  dominant phi category: {dom} ({share})")
        active = [k for k, v in self.signals.items() if v]
        lines.append(f"  active signals: {active or 'none'}")
        return "\n".join(lines)


def _default_category(name: str) -> str:
    return str(name)[:3]


def _sec_phi(results, t: DiagThresholds) -> dict:
    kind = "actual" if "actual" in results.phi_files else "composite"
    summary = results.phi_summary(kind)
    tidy = results.phi(kind)
    n_reals = tidy.groupby("iteration")["phi"].size()
    per = [
        {"iteration": int(it), "mean": float(r["mean"]),
         "min": float(r["min"]), "max": float(r["max"]),
         "std": float(r["standard_deviation"]),
         "n_reals": int(n_reals.get(it, 0))}
        for it, r in summary.iterrows()
    ]
    means = [p["mean"] for p in per]
    stds = [p["std"] for p in per]
    total_red = ((means[0] - means[-1]) / means[0]
                 if means and means[0] else None)
    last_red = ((means[-2] - means[-1]) / means[-2]
                if len(means) > 1 and means[-2] else None)
    collapse = stds[-1] / stds[0] if len(stds) > 1 and stds[0] else None
    return {
        "source": f"phi.{kind}",
        "n_iterations": len(per),
        "per_iteration": per,
        "total_phi_reduction_frac": _r(total_red, 4),
        "last_phi_reduction_frac": _r(last_red, 4),
        "phi_std_collapse_ratio": _r(collapse, 4),
        "signals": {
            "phi_stalled": bool(last_red is not None
                                and last_red < t.phiredstp),
            "ensemble_collapsed": bool(collapse is not None
                                       and collapse < t.collapse_ratio),
        },
    }


def _sec_conflict(results, t: DiagThresholds, category_of) -> dict:
    pdc = results.pdc()
    if pdc is None:
        return {"note": "no .pdc.csv (prior-data conflict not reported)"}
    cats = pdc.index.astype(str).map(category_of)
    by_cat = pdc.groupby(cats).size().sort_values(ascending=False)
    total = int(len(pdc))
    nz = None
    if results.rei_files:
        rei = results.base_rei()
        nz = int((pd.to_numeric(rei["weight"], errors="coerce") > 0).sum())
    rate = total / nz if nz else None
    return {
        "total_conflicts": total,
        "nonzero_obs": nz,
        "conflict_rate": _r(rate, 4),
        "by_category": {str(k): int(v) for k, v in by_cat.items()},
        "signals": {"conflict_systemic": bool(rate is not None
                                              and rate > t.conflict_systemic)},
    }


def _sec_railing(results, par_data, t: DiagThresholds) -> dict:
    if par_data is None:
        return {"note": "no parameter data (bounds) provided; pass "
                        "par_data= to enable railing checks"}
    if not isinstance(par_data, pd.DataFrame):
        par_data = pd.read_csv(par_data)
    par_data = par_data.copy()
    par_data.columns = [c.lower() for c in par_data.columns]
    name_col = "parnme" if "parnme" in par_data.columns else par_data.columns[0]
    adjustable = par_data[
        par_data["partrans"].astype(str).str.lower().isin(["none", "log"])]
    ens = results.par()
    names = pd.Index(adjustable[name_col].astype(str).str.lower())
    common = ens.columns.str.lower().intersection(names)
    if not len(common):
        return {"note": "no adjustable parameters found in the ensemble"}

    ens = ens.copy()
    ens.columns = ens.columns.str.lower()
    vals = ens[common].astype(float)
    meta = adjustable.assign(_n=names).set_index("_n").loc[common]
    lb = pd.to_numeric(meta["parlbnd"]).values
    ub = pd.to_numeric(meta["parubnd"]).values
    is_log = meta["partrans"].astype(str).str.lower().eq("log").values

    v = vals.values.astype(float).copy()
    lo_b, hi_b = lb.astype(float).copy(), ub.astype(float).copy()
    with np.errstate(invalid="ignore", divide="ignore"):
        v[:, is_log] = np.log10(np.where(v[:, is_log] > 0, v[:, is_log], np.nan))
        lo_b[is_log] = np.log10(lo_b[is_log])
        hi_b[is_log] = np.log10(hi_b[is_log])
        span = hi_b - lo_b
        frac = (v - lo_b) / np.where(span > 0, span, np.nan)
    at_low = frac <= t.rail_tol
    at_high = frac >= 1 - t.rail_tol
    cells = pd.DataFrame({
        "group": meta["pargp"].astype(str).values,
        "n": np.isfinite(frac).sum(axis=0),
        "lo": at_low.sum(axis=0),
        "hi": at_high.sum(axis=0),
    })
    per_group = cells.groupby("group").sum()
    per_group["pct_railed"] = (100.0 * (per_group["lo"] + per_group["hi"])
                               / per_group["n"].where(per_group["n"] > 0))
    per_group = per_group[per_group["pct_railed"] > 0].sort_values(
        "pct_railed", ascending=False)
    by_group = {
        g: {"n_values": int(r["n"]), "pct_railed": _r(r["pct_railed"], 1),
            "at_low": int(r["lo"]), "at_high": int(r["hi"]),
            "direction": "low" if r["lo"] >= r["hi"] else "high"}
        for g, r in per_group.iterrows()
    }
    flagged = {g: v for g, v in by_group.items()
               if v["pct_railed"] >= 100 * t.rail_flag}
    return {
        "iteration": max(results.par_files),
        "n_parameters": int(len(common)),
        "n_realizations": int(len(vals)),
        "flag_threshold_pct": _r(100 * t.rail_flag, 1),
        "by_group": by_group,
        "flagged_groups": flagged,
        "signals": {"railing_present": bool(flagged)},
    }


def _sec_residuals(results, t: DiagThresholds, scheme) -> dict:
    if not results.rei_files:
        return {"note": "no .base.rei residual files"}
    rei = results.base_rei()
    w = pd.to_numeric(rei["weight"], errors="coerce").fillna(0)
    r = rei[w > 0].copy()
    if r.empty:
        return {"note": "no weighted observations in residuals"}
    times = None
    try:
        from iwfm_io.pest.names import decode_obs_names
        times = decode_obs_names(r["name"], scheme=scheme)["time"]
        times.index = r.index
    except Exception as exc:  # undecodable names → no trends
        logger.debug("obs names not decodable for trends: %s", exc)

    out, flagged = {}, {}
    for g, s in r.groupby(r["group"].astype(str)):
        rec = {"n_obs": int(len(s)),
               "mean_res": _r(s["residual"].mean(), 2),
               "abs_mean_res": _r(s["residual"].abs().mean(), 2)}
        if times is not None:
            yrs = times.loc[s.index].dropna().dt.year
            if yrs.nunique() > 2:
                yearly = s.loc[yrs.index, "residual"].groupby(yrs).mean()
                rec["trend_per_yr"] = _r(
                    np.polyfit(yearly.index, yearly.values, 1)[0], 2)
        out[g] = rec
        biased = abs(rec["mean_res"]) > t.bias_threshold
        drifting = abs(rec.get("trend_per_yr", 0.0)) > t.trend_threshold
        if biased and drifting:
            flagged[g] = {**rec, "likely": "systematic drift"}
        elif biased:
            flagged[g] = {**rec, "likely": "bias"}
    top = dict(sorted(flagged.items(),
                      key=lambda kv: -abs(kv[1]["mean_res"]))[:t.top_n])
    return {"iteration": max(results.rei_files),
            "n_groups": len(out), "by_group": out, "flagged_groups": top}


def _sec_outliers(results, t: DiagThresholds) -> dict:
    if not results.rei_files:
        return {"note": "no .base.rei residual files"}
    rei = results.base_rei()
    w = pd.to_numeric(rei["weight"], errors="coerce").fillna(0)
    r = rei[w > 0]
    big = r[r["residual"].abs() > t.outlier_threshold]
    top = big.reindex(
        big["residual"].abs().sort_values(ascending=False).index
    ).head(t.top_n)
    return {
        "threshold": t.outlier_threshold,
        "n_over_threshold": int(len(big)),
        "top": [
            {"obs": str(row["name"]), "group": str(row["group"]),
             "measured": _r(row["measured"], 2),
             "modelled": _r(row["modelled"], 2),
             "residual": _r(row["residual"], 2)}
            for _, row in top.iterrows()
        ],
    }


def _sec_objective(results, t: DiagThresholds, category_of) -> dict:
    if results.group_phi_file is None:
        return {"note": "no phi.group.csv"}
    g = results.phi_groups()
    last = g[g["iteration"] == g["iteration"].max()]
    mean_by_group = last.groupby("group")["phi"].mean()
    cats = mean_by_group.groupby(
        mean_by_group.index.astype(str).map(category_of)).sum()
    total = cats.sum() or 1.0
    share = {str(k): _r(v / total, 3)
             for k, v in cats.sort_values(ascending=False).items()}
    top = mean_by_group.sort_values(ascending=False).head(t.top_n)
    max_share = max(share.values()) if share else 0.0
    return {
        "iteration": int(g["iteration"].max()),
        "category_share": share,
        "top_groups": {str(k): _r(float(v), 1) for k, v in top.items()},
        "signals": {
            "objective_imbalance": bool(max_share > 0.5),
            "dominant_category": (max(share, key=share.get)
                                  if share else None),
        },
    }


def _r(x, nd):
    return None if x is None else round(float(x), nd)


def diagnose_ies(results, par_data=None, scheme="standard",
                 category_of: Optional[Callable] = None,
                 thresholds: Optional[DiagThresholds] = None) -> IesDiagnostics:
    """Distill a PESTPP-IES run into metrics, signals, and a summary.

    Parameters
    ----------
    results : IesResults
        From :func:`~iwfm_io.pest.ies.load_ies_ensembles`.
    par_data : DataFrame or path, optional
        Parameter-data table with ``parnme, partrans, parlbnd, parubnd,
        pargp`` (the PEST++ v2 external parameter-data layout). Enables
        the bound-railing section.
    scheme : str or NameScheme, default "standard"
        Observation-name scheme used to decode dates for residual
        trends; undecodable names simply skip the trend metric.
    category_of : callable, optional
        Maps a group/observation name to a category label for the
        conflict and objective-balance rollups (default: first three
        characters).
    thresholds : DiagThresholds, optional
        Signal cut-offs (see :class:`DiagThresholds` defaults).

    Returns
    -------
    IesDiagnostics
        ``.state`` (JSON-serializable), ``.signals`` (flattened booleans),
        ``.summary()`` (short text digest), ``.to_json(path)``.

    Notes
    -----
    Every section is individually fault-tolerant: a missing input turns
    into a ``note``/``error`` entry rather than an exception, so partial
    runs still produce a useful report.
    """
    t = thresholds or DiagThresholds()
    cat = category_of or _default_category
    sections = [
        ("phi", lambda: _sec_phi(results, t)),
        ("prior_data_conflict", lambda: _sec_conflict(results, t, cat)),
        ("bound_railing", lambda: _sec_railing(results, par_data, t)),
        ("residuals", lambda: _sec_residuals(results, t, scheme)),
        ("outliers", lambda: _sec_outliers(results, t)),
        ("objective_balance", lambda: _sec_objective(results, t, cat)),
    ]
    state = {}
    for name, fn in sections:
        try:
            state[name] = fn()
        except Exception as exc:
            logger.warning("diagnostics section %r failed: %s", name, exc)
            state[name] = {"error": f"{type(exc).__name__}: {exc}"}
    state["signals"] = {}
    diag = IesDiagnostics(case=results.case, state=state)
    state["signals"] = diag.signals
    return diag
