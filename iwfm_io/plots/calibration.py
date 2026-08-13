"""PEST(++) calibration figures for IWFM models.

The standard figure set for reviewing an ensemble calibration, built on
the ``iwfm_io.pest`` data structures:

- :func:`plot_phi_convergence` — phi distribution per iteration
- :func:`plot_phi_by_group` — top phi-contributing groups, first vs last
- :func:`plot_residual_butterfly` — diverging mean-residual bars by group
- :func:`plot_obs_vs_sim` — observed vs simulated 1:1
- :func:`plot_parameter_histograms` — prior vs posterior distributions
- :func:`plot_parameter_railing` — % of ensemble at parameter bounds
- :func:`plot_ensemble_hydrograph` — ensemble band + base + observations
- :func:`plot_residual_map` — residual statistics at x/y locations

All functions follow the package plotting interface: optional *ax*,
*figsize*, *save_path*, *dpi*; return ``(fig, ax)``.

Color conventions: categorical series use the shared package palette;
diverging quantities (residuals) use a fixed blue/red pair around a
neutral zero; magnitude (density) uses a single perceptual ramp.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from . import savefig, build_element_polygons

__all__ = [
    "plot_phi_convergence",
    "plot_phi_by_group",
    "plot_residual_butterfly",
    "plot_obs_vs_sim",
    "plot_parameter_histograms",
    "plot_parameter_railing",
    "plot_ensemble_hydrograph",
    "plot_residual_map",
]

# diverging pair (negative / positive) + neutral — colorblind-safe RdBu poles
_NEG_COLOR = "#2166ac"
_POS_COLOR = "#b2182b"
_NEUTRAL = "#666666"
_BASE_COLOR = "#1f77b4"
_ORIG_COLOR = "#ff7f0e"
_PRIOR_COLOR = "#999999"
_POST_COLOR = "#1f77b4"


def _prepare_axes(ax, figsize):
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    return fig, ax


def _finish(fig, save_path, dpi):
    fig.tight_layout()
    if save_path:
        savefig(fig, save_path, dpi=dpi)


def _tidy_phi(source, kind):
    """Accept an IesResults or an already-tidy phi frame."""
    if isinstance(source, pd.DataFrame):
        return source
    return source.phi(kind)


def plot_phi_convergence(source, kind="composite", log=True, ax=None,
                         figsize=(8, 5), save_path=None, dpi=150):
    """Box-plot the ensemble phi distribution per IES iteration.

    Parameters
    ----------
    source : IesResults or DataFrame
        Results handle, or a tidy phi frame
        (``iteration, real_name, phi``).
    kind : str, default "composite"
        Phi flavor when *source* is an ``IesResults``.
    log : bool, default True
        Log-scale the phi axis.

    Returns
    -------
    (fig, ax)
    """
    phi = _tidy_phi(source, kind)
    fig, ax = _prepare_axes(ax, figsize)
    iterations = sorted(phi["iteration"].unique())
    data = [phi.loc[phi["iteration"] == it, "phi"].values
            for it in iterations]
    ax.boxplot(data, positions=range(len(iterations)),
               medianprops=dict(color=_BASE_COLOR, linewidth=1.5),
               flierprops=dict(marker=".", markersize=4, alpha=0.5))
    means = [d.mean() for d in data]
    ax.plot(range(len(iterations)), means, "-o", color=_POS_COLOR,
            markersize=5, linewidth=1.5, label="mean")
    ax.set_xticks(range(len(iterations)))
    ax.set_xticklabels([str(it) for it in iterations])
    if log:
        ax.set_yscale("log")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Phi")
    ax.set_title("Ensemble phi convergence")
    ax.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax.legend(loc="best", fontsize="small", framealpha=0.8)
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_phi_by_group(source, n_top=20, iterations=None, ax=None,
                      figsize=(8, 7), save_path=None, dpi=150):
    """Horizontal bars of mean per-group phi, first vs last iteration.

    Parameters
    ----------
    source : IesResults or DataFrame
        Results handle, or a tidy per-group phi frame
        (``iteration, real_name, group, phi``).
    n_top : int, default 20
        Groups shown, ranked by last-iteration phi.
    iterations : (int, int), optional
        Explicit (first, last) pair; default min/max present.

    Returns
    -------
    (fig, ax)
    """
    g = source if isinstance(source, pd.DataFrame) else source.phi_groups()
    first, last = iterations or (g["iteration"].min(), g["iteration"].max())
    mean = (g[g["iteration"].isin([first, last])]
            .groupby(["iteration", "group"])["phi"].mean().unstack(0))
    mean = mean.sort_values(last, ascending=False).head(n_top).iloc[::-1]
    fig, ax = _prepare_axes(ax, figsize)
    y = np.arange(len(mean))
    h = 0.38
    ax.barh(y + h / 2, mean[first], height=h, color=_PRIOR_COLOR,
            label=f"iteration {first}")
    ax.barh(y - h / 2, mean[last], height=h, color=_POST_COLOR,
            label=f"iteration {last}")
    ax.set_yticks(y)
    ax.set_yticklabels(mean.index, fontsize="small")
    ax.set_xlabel("Mean phi")
    ax.set_title(f"Top {len(mean)} phi-contributing observation groups")
    ax.grid(True, linestyle="--", alpha=0.4, axis="x")
    ax.legend(loc="best", fontsize="small", framealpha=0.8)
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_residual_butterfly(stats, metric="mean_res", n_top=30, ax=None,
                            figsize=(8, 7), save_path=None, dpi=150):
    """Diverging horizontal bars of a residual metric by group.

    Positive residuals (observed > simulated, i.e. the model is low)
    plot to the right in red; negative to the left in blue.

    Parameters
    ----------
    stats : DataFrame
        Metric table indexed by group — e.g. from
        :func:`iwfm_io.pest.residual_stats` or
        :func:`iwfm_io.pest.rei_stats`.
    metric : str, default "mean_res"
    n_top : int, default 30
        Groups shown, ranked by absolute metric value.

    Returns
    -------
    (fig, ax)
    """
    vals = stats[metric].dropna()
    vals = vals.reindex(vals.abs().sort_values(ascending=False).index)
    vals = vals.head(n_top).iloc[::-1]
    fig, ax = _prepare_axes(ax, figsize)
    colors = [_POS_COLOR if v > 0 else _NEG_COLOR for v in vals]
    ax.barh(np.arange(len(vals)), vals.values, color=colors, height=0.7)
    ax.axvline(0, color=_NEUTRAL, linewidth=1)
    ax.set_yticks(np.arange(len(vals)))
    ax.set_yticklabels([str(i) for i in vals.index], fontsize="small")
    ax.set_xlabel(metric)
    ax.set_title(f"{metric} by group (obs − sim; red: model low, "
                 f"blue: model high)")
    ax.grid(True, linestyle="--", alpha=0.4, axis="x")
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_obs_vs_sim(data, observed="observed", simulated="simulated",
                    hexbin_threshold=5000, ax=None, figsize=(6.5, 6.5),
                    save_path=None, dpi=150):
    """Observed vs simulated 1:1 plot with fit statistics.

    Scatter for small datasets; hexbin density above *hexbin_threshold*
    points. Annotates N, RMSE, R², and NSE (via
    :func:`iwfm_io.pest.residual_stats`).

    Parameters
    ----------
    data : DataFrame
        Long-form frame with *observed* and *simulated* columns (e.g. a
        ``read_rei`` frame with ``observed="measured",
        simulated="modelled"``).

    Returns
    -------
    (fig, ax)
    """
    from iwfm_io.pest import residual_stats

    o = pd.to_numeric(data[observed], errors="coerce")
    s = pd.to_numeric(data[simulated], errors="coerce")
    ok = o.notna() & s.notna()
    o, s = o[ok], s[ok]
    fig, ax = _prepare_axes(ax, figsize)
    if len(o) > hexbin_threshold:
        hb = ax.hexbin(o, s, gridsize=60, cmap="cividis", mincnt=1,
                       bins="log")
        fig.colorbar(hb, ax=ax, label="count (log)")
    else:
        ax.plot(o, s, ".", color=_BASE_COLOR, markersize=4, alpha=0.5)
    lo = min(o.min(), s.min())
    hi = max(o.max(), s.max())
    ax.plot([lo, hi], [lo, hi], "-", color=_NEUTRAL, linewidth=1,
            label="1:1")
    st = residual_stats(pd.DataFrame({"observed": o, "simulated": s})).iloc[0]
    ax.annotate(
        f"N = {int(st['n'])}\nRMSE = {st['rmse']:.3g}\n"
        f"R² = {st['r2']:.3f}\nNSE = {st['nse']:.3f}",
        xy=(0.03, 0.97), xycoords="axes fraction", va="top",
        fontsize="small",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                  edgecolor="gray", alpha=0.85))
    ax.set_xlabel("Observed")
    ax.set_ylabel("Simulated")
    ax.set_title("Observed vs simulated")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="lower right", fontsize="small", framealpha=0.8)
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_parameter_histograms(results, parameters=None, group=None,
                              par_data=None, iterations=None, max_pars=20,
                              ncols=4, bins=20, figsize=None,
                              save_path=None, dpi=150):
    """Prior-vs-posterior histograms, one panel per parameter.

    Parameters
    ----------
    results : IesResults
    parameters : list of str, optional
        Parameter names to plot. Default: all (capped at *max_pars*).
    group : str, optional
        Restrict to one parameter group (needs *par_data* with
        ``parnme``/``pargp``).
    par_data : DataFrame or path, optional
        Parameter-data table; adds bound lines and log-x scaling for
        log-transformed parameters.
    iterations : (int, int), optional
        (prior, posterior) iterations; default first/last available.

    Returns
    -------
    (fig, axes)
    """
    if par_data is not None and not isinstance(par_data, pd.DataFrame):
        par_data = pd.read_csv(par_data)
    if par_data is not None:
        par_data = par_data.copy()
        par_data.columns = [c.lower() for c in par_data.columns]
        par_data = par_data.set_index(
            par_data["parnme"].astype(str).str.lower())

    first, last = iterations or (min(results.par_files),
                                 max(results.par_files))
    prior, post = results.par(first), results.par(last)
    cols = list(parameters) if parameters is not None else list(prior.columns)
    if group is not None:
        if par_data is None:
            raise ValueError("group= filtering requires par_data=")
        members = par_data.index[par_data["pargp"].astype(str) == group]
        cols = [c for c in cols if c.lower() in set(members)]
    if not cols:
        raise ValueError("no parameters selected")
    if len(cols) > max_pars:
        cols = cols[:max_pars]

    n = len(cols)
    ncols = min(ncols, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=figsize or (3.2 * ncols, 2.6 * nrows),
                             squeeze=False)
    for i, name in enumerate(cols):
        ax = axes[i // ncols][i % ncols]
        pv = pd.to_numeric(prior[name], errors="coerce").dropna()
        sv = pd.to_numeric(post[name], errors="coerce").dropna()
        log_x = False
        if par_data is not None and name.lower() in par_data.index:
            row = par_data.loc[name.lower()]
            log_x = str(row.get("partrans", "")).lower() == "log"
            for b in ("parlbnd", "parubnd"):
                if b in row:
                    ax.axvline(float(row[b]), color=_NEUTRAL,
                               linestyle=":", linewidth=1)
        if log_x and (pv > 0).all() and (sv > 0).all():
            lo = min(pv.min(), sv.min())
            hi = max(pv.max(), sv.max())
            edges = np.logspace(np.log10(lo), np.log10(hi), bins + 1)
            ax.set_xscale("log")
        else:
            lo = min(pv.min(), sv.min())
            hi = max(pv.max(), sv.max())
            edges = np.linspace(lo, hi, bins + 1) if hi > lo else bins
        ax.hist(pv, bins=edges, color=_PRIOR_COLOR, alpha=0.6,
                label=f"iter {first}")
        ax.hist(sv, bins=edges, color=_POST_COLOR, alpha=0.6,
                label=f"iter {last}")
        ax.set_title(name, fontsize="small")
        ax.tick_params(labelsize="x-small")
    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].set_visible(False)
    axes[0][0].legend(fontsize="x-small", framealpha=0.8)
    fig.suptitle("Parameter distributions: prior vs posterior")
    _finish(fig, save_path, dpi)
    return fig, axes


def plot_parameter_railing(source, n_top=25, ax=None, figsize=(8, 6),
                           save_path=None, dpi=150):
    """Stacked horizontal bars: % of ensemble values at bounds, per group.

    Parameters
    ----------
    source : IesDiagnostics or dict
        A diagnostics result (its ``bound_railing`` section is used) or
        the section dict itself.

    Returns
    -------
    (fig, ax)
    """
    state = source if isinstance(source, dict) else source.state
    section = state.get("bound_railing", state)
    by_group = section.get("by_group")
    if not by_group:
        raise ValueError(
            "no railing data — run diagnose_ies with par_data= (bounds)")
    df = pd.DataFrame(by_group).T
    df["pct_low"] = 100.0 * df["at_low"] / df["n_values"]
    df["pct_high"] = 100.0 * df["at_high"] / df["n_values"]
    df = df.sort_values("pct_railed", ascending=False).head(n_top).iloc[::-1]
    fig, ax = _prepare_axes(ax, figsize)
    y = np.arange(len(df))
    ax.barh(y, df["pct_low"], color=_NEG_COLOR, height=0.7,
            label="at lower bound")
    ax.barh(y, df["pct_high"], left=df["pct_low"], color=_POS_COLOR,
            height=0.7, label="at upper bound")
    flag = section.get("flag_threshold_pct")
    if flag:
        ax.axvline(flag, color=_NEUTRAL, linestyle="--", linewidth=1,
                   label=f"flag threshold ({flag}%)")
    ax.set_yticks(y)
    ax.set_yticklabels(df.index, fontsize="small")
    ax.set_xlabel("% of parameter × realization values at a bound")
    ax.set_title("Parameter bound railing")
    ax.grid(True, linestyle="--", alpha=0.4, axis="x")
    ax.legend(loc="best", fontsize="small", framealpha=0.8)
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_ensemble_hydrograph(ensemble, observed=None, base="base",
                             original=None, quantiles=(0.05, 0.95),
                             ylabel="Value", title=None, ax=None,
                             figsize=(10, 5), save_path=None, dpi=150):
    """Ensemble time-series band with base realization and observations.

    Parameters
    ----------
    ensemble : DataFrame
        Time series indexed by datetime, one column per realization
        (transpose of an ``IesResults`` ensemble slice reshaped by the
        caller to one site).
    observed : Series, optional
        Observed values indexed by datetime (plotted as points).
    base : str, optional
        Column highlighted as the base realization (skipped if absent).
    original : Series, optional
        A reference model run (e.g. pre-calibration) for comparison.
    quantiles : (float, float), default (0.05, 0.95)
        Ensemble envelope.

    Returns
    -------
    (fig, ax)
    """
    fig, ax = _prepare_axes(ax, figsize)
    ens = ensemble.sort_index()
    lo = ens.quantile(quantiles[0], axis=1)
    hi = ens.quantile(quantiles[1], axis=1)
    ax.fill_between(ens.index, lo, hi, color=_BASE_COLOR, alpha=0.20,
                    linewidth=0,
                    label=f"ensemble {quantiles[0]:.0%}–{quantiles[1]:.0%}")
    ax.plot(ens.index, ens.median(axis=1), color=_BASE_COLOR,
            linewidth=1, alpha=0.8, label="ensemble median")
    if base is not None and base in ens.columns:
        ax.plot(ens.index, ens[base], color="black", linewidth=1.5,
                label="base realization")
    if original is not None:
        orig = pd.Series(original).sort_index()
        ax.plot(orig.index, orig.values, color=_ORIG_COLOR, linewidth=1.2,
                linestyle="--", label="original model")
    if observed is not None:
        obs = pd.Series(observed).sort_index()
        ax.plot(obs.index, obs.values, "o", color=_POS_COLOR,
                markersize=3.5, linestyle="none", label="observed")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Date")
    if title:
        ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="best", fontsize="small", framealpha=0.8)
    _finish(fig, save_path, dpi)
    return fig, ax


def plot_residual_map(stats, x="x", y="y", metric="mean_res", model=None,
                      vlim=None, size=25, ax=None, figsize=(8, 9),
                      save_path=None, dpi=150):
    """Map a residual metric at observation locations.

    Parameters
    ----------
    stats : DataFrame
        Per-location metric table with coordinate columns — e.g.
        ``residual_stats(..., by="location")`` joined to well x/y.
    x, y : str
        Coordinate column names.
    metric : str, default "mean_res"
        Colored with the diverging residual palette, symmetric around 0.
    model : optional
        Anything with ``nodes_df()``/``elements_df()`` — draws the model
        mesh as a light background.
    vlim : float, optional
        Symmetric color limit (default: robust 98th percentile of |val|).

    Returns
    -------
    (fig, ax)
    """
    fig, ax = _prepare_axes(ax, figsize)
    if model is not None:
        from matplotlib.collections import PolyCollection
        polys = build_element_polygons(model)
        ax.add_collection(PolyCollection(
            polys, facecolor="none", edgecolor="#cccccc", linewidth=0.3))
    vals = pd.to_numeric(stats[metric], errors="coerce")
    ok = vals.notna() & stats[x].notna() & stats[y].notna()
    v = vals[ok]
    if vlim is None:
        vlim = float(np.nanpercentile(v.abs(), 98)) or 1.0
    sc = ax.scatter(stats.loc[ok, x], stats.loc[ok, y], c=v, s=size,
                    cmap="RdBu_r", vmin=-vlim, vmax=vlim,
                    edgecolors="#444444", linewidths=0.3)
    fig.colorbar(sc, ax=ax, shrink=0.7, label=metric)
    ax.set_aspect("equal", adjustable="datalim")
    ax.autoscale_view()
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(f"{metric} at observation locations")
    _finish(fig, save_path, dpi)
    return fig, ax
