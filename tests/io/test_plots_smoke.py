"""DLL-free smoke test for every public plot function in ``iwfm_io.plots``.

Every ``plot_*`` / ``animate_*`` callable defined in each plotting module
is enumerated programmatically and called once against the sample model
through :class:`IOModelAdapter` (no DLL) with the minimal arguments in
``KWARGS``. Each call must return ``(Figure, ...)`` (or a
``FuncAnimation`` for the animations) and, when a ``save_path`` was
given, write that file.

``test_kwargs_table_is_complete`` fails loudly when a plot function is
added without a ``KWARGS`` entry (or an entry goes stale).

Known limitations are ``xfail(strict=True)`` so a fix shows up as an
unexpected pass:

* thirteen budget/hydrograph plots call DLL-only ``IWFMModel`` methods
  (``get_budget_column_titles``, ``get_budget_timeseries``, ...) that the
  adapter does not provide;
* the two aquifer-parameter plots cannot be served on NGROUP>0 models
  such as the sample (parameters live in parametric grids).
"""
from __future__ import annotations

import importlib
import inspect

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.animation import FuncAnimation
from matplotlib.figure import Figure

pytestmark = pytest.mark.sample_model

# The plotting modules whose public plot functions are covered. The
# package itself ("") holds the two shared primitives.
MODULES = [
    "",
    "animations",
    "calibration",
    "connectivity",
    "cross_sections",
    "maps",
    "profiles",
    "seasonal",
    "spatial_patterns",
    "stream_analysis",
    "subsidence",
    "summary",
    "supply_demand",
    "timeseries",
    "trends",
    "water_balance",
]

# Sample model: daily timestep, 09/30/1990_24:00 -> 09/30/2000_24:00.
# Two water years keep the head reads small; animations get one week.
BD, ED = "10/01/1990_24:00", "09/30/1992_24:00"
ANIM_BD, ANIM_ED = "09/25/1992_24:00", "09/30/1992_24:00"

DLL_ONLY = pytest.mark.xfail(
    strict=True, reason="H6: DLL-only plot fails on IOModelAdapter")
NO_AQUIFER_PARAMS = pytest.mark.xfail(
    strict=True, reason="aquifer params unavailable on NGROUP>0 adapter")

KNOWN_MARKS = {
    "plot_aquifer_parameter": NO_AQUIFER_PARAMS,
    "plot_aquifer_parameter_histograms": NO_AQUIFER_PARAMS,
}

# Functions whose return is not the ``(fig, ax)`` pair.
MULTI_RETURN = {"plot_element_map", "plot_contour_map"}  # (fig, ax, coll, cb)


# ---------------------------------------------------------------------------
# Synthetic inputs for the data-only functions
# ---------------------------------------------------------------------------

def _transect(m):
    nodes = m.nodes_df()
    x, y = nodes["x"].to_numpy(float), nodes["y"].to_numpy(float)
    return [(float(x.min()), float(y.mean())), (float(x.max()), float(y.mean()))]


def _node_series(m):
    """(dates, values) of layer-1 head at the first node over BD..ED."""
    hdf = m.heads_df(1, BD, ED)
    return list(hdf.index), hdf.iloc[:, 0].to_numpy(float)


def _monthly_means(m):
    dates, values = _node_series(m)
    s = pd.Series(values, index=pd.DatetimeIndex(dates))
    return [float(v) for v in s.groupby(s.index.month).mean().reindex(range(1, 13)).fillna(0.0)]


def _balance_names_values():
    names = ["Deep Percolation (+)", "Stream Recharge (+)", "Pumping (-)", "Outflow (-)"]
    values = [120.0, 80.0, -150.0, -50.0]
    return names, values


def _phi_frame():
    rng = np.random.default_rng(0)
    rows = [(it, f"r{r}", float(1000 / (it + 1) * rng.uniform(0.8, 1.2)))
            for it in range(3) for r in range(10)]
    return pd.DataFrame(rows, columns=["iteration", "real_name", "phi"])


def _phi_group_frame():
    rng = np.random.default_rng(1)
    rows = [(it, f"r{r}", g, float(100 / (it + 1) * rng.uniform(0.5, 1.5)))
            for it in range(3) for r in range(5) for g in ("hds_a", "hds_b", "flow")]
    return pd.DataFrame(rows, columns=["iteration", "real_name", "group", "phi"])


class _FakeIesResults:
    """Minimal stand-in for ``IesResults`` (``par_files`` + ``par(it)``)."""

    par_files = {0: None, 3: None}

    def par(self, iteration):
        rng = np.random.default_rng(iteration)
        return pd.DataFrame({
            "kh_1": rng.lognormal(0.0, 0.5 if iteration == 0 else 0.1, 30),
            "sy_1": rng.uniform(0.05, 0.3, 30),
        })


def _railing_state():
    return {"bound_railing": {
        "flag_threshold_pct": 10.0,
        "by_group": {
            "kh": {"at_low": 3, "at_high": 5, "n_values": 60, "pct_railed": 13.3},
            "sy": {"at_low": 0, "at_high": 1, "n_values": 60, "pct_railed": 1.7},
        }}}


def _ensemble_frame(m):
    dates, values = _node_series(m)
    rng = np.random.default_rng(2)
    idx = pd.DatetimeIndex(dates)
    ens = pd.DataFrame({f"r{i}": values + rng.normal(0, 1.0, len(values))
                        for i in range(8)}, index=idx)
    ens["base"] = values
    obs = pd.Series(values[::30] + 0.5, index=idx[::30])
    return ens, obs


def _residual_stats(m):
    nodes = m.nodes_df().iloc[::40]
    rng = np.random.default_rng(3)
    return pd.DataFrame({
        "x": nodes["x"].to_numpy(float),
        "y": nodes["y"].to_numpy(float),
        "mean_res": rng.normal(0, 2, len(nodes)),
    }, index=[f"w{i}" for i in range(len(nodes))])


def _subsidence_field(m):
    nodes = m.nodes_df()
    x, y = nodes["x"].to_numpy(float), nodes["y"].to_numpy(float)
    r2 = (x - x.mean()) ** 2 + (y - y.mean()) ** 2
    return np.exp(-r2 / (r2.max() / 4))


# ---------------------------------------------------------------------------
# Argument table: function name -> builder(adapter) -> (args, kwargs)
# ---------------------------------------------------------------------------

def M(**kwargs):
    """Model-first call: ``fn(adapter, **kwargs)``."""
    return lambda m: ((m,), dict(kwargs))


def MB(builder):
    """Model-first call with kwargs derived from the adapter."""
    return lambda m: ((m,), builder(m))


def D(builder):
    """Data-only call: ``builder(adapter)`` returns ``(args, kwargs)``."""
    return builder


KWARGS = {
    # iwfm_io.plots (shared primitives)
    "plot_element_map": MB(lambda m: dict(values=np.arange(m.n_elements, dtype=float))),
    "plot_contour_map": MB(lambda m: dict(node_values=m.nodes_df()["x"].to_numpy(float))),
    # animations
    "animate_gw_heads": M(layer=1, begin_date=ANIM_BD, end_date=ANIM_ED),
    "animate_stream_flows": M(layer=1, begin_date=ANIM_BD, end_date=ANIM_ED),
    "animate_depth_to_water": M(layer=1, begin_date=ANIM_BD, end_date=ANIM_ED),
    # calibration (pest data structures, model optional)
    "plot_phi_convergence": D(lambda m: ((_phi_frame(),), {})),
    "plot_phi_by_group": D(lambda m: ((_phi_group_frame(),), {})),
    "plot_residual_butterfly": D(lambda m: ((_residual_stats(m),), {})),
    "plot_obs_vs_sim": D(lambda m: ((pd.DataFrame({
        "observed": np.linspace(10, 50, 40),
        "simulated": np.linspace(10, 50, 40) + np.sin(np.arange(40))}),), {})),
    "plot_parameter_histograms": D(lambda m: ((_FakeIesResults(),), {})),
    "plot_parameter_railing": D(lambda m: ((_railing_state(),), {})),
    "plot_ensemble_hydrograph": D(lambda m: (
        (_ensemble_frame(m)[0],), dict(observed=_ensemble_frame(m)[1]))),
    "plot_residual_map": D(lambda m: ((_residual_stats(m),), dict(model=m))),
    # connectivity
    "plot_diversion_network": M(),
    "plot_bypass_flow_diagram": M(),
    # cross_sections
    "animate_cross_section": MB(lambda m: dict(
        points=_transect(m), layer=1, begin_date=ANIM_BD, end_date=ANIM_ED, n_samples=20)),
    "plot_multi_layer_head_panel": MB(lambda m: dict(
        points=_transect(m), begin_date=BD, end_date=ED, n_samples=20, time_index=0)),
    # maps
    "plot_grid_mesh": M(),
    "plot_ground_surface_elevation": M(),
    "plot_layer_thickness": M(layer=1),
    "plot_aquifer_parameter": M(parameter="Kh", layer=1),
    "plot_gw_head_contour": M(layer=1, time_index=-1, begin_date=BD, end_date=ED),
    "plot_depth_to_water": M(layer=1),
    "plot_head_change": MB(lambda m: dict(
        layer=1,
        heads_t1=m.heads_df(1, BD, ED).iloc[0].to_numpy(float),
        heads_t2=m.heads_df(1, BD, ED).iloc[-1].to_numpy(float))),
    "plot_stream_network": M(),
    "plot_well_locations": M(),
    "plot_lake_and_diversion_elements": M(),
    "plot_tile_drain_locations": M(),
    # profiles
    "plot_stratigraphic_cross_section": MB(lambda m: dict(points=_transect(m), n_samples=20)),
    "plot_stream_longitudinal_profile": M(reach_ids=[1]),
    # seasonal
    "plot_ridgeline": D(lambda m: (_node_series(m), dict(value_label="Head"))),
    "plot_calendar_heatmap": D(lambda m: (_node_series(m), dict(value_label="Head"))),
    "plot_polar_seasonal": D(lambda m: ((_monthly_means(m),), {})),
    "plot_budget_polar_seasonal": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    # spatial_patterns
    "plot_sparkline_grid": M(layer=1, begin_date=BD, end_date=ED, n_points=8),
    "plot_small_multiples": M(layer=1, begin_date=BD, end_date=ED, n_panels=4),
    "plot_head_vs_gse_scatter": M(layer=1),
    # stream_analysis
    "plot_stream_gain_loss_profile": M(reach_ids=[1]),
    "plot_stream_aquifer_exchange_map": M(layer=1),
    # subsidence
    "plot_subsidence_bowl": MB(lambda m: dict(subsidence_values=_subsidence_field(m))),
    "plot_subsidence_vs_head": D(lambda m: (
        (_node_series(m)[1], np.linspace(0, 0.5, len(_node_series(m)[1]))),
        dict(dates=_node_series(m)[0], node_label="Node 1"))),
    # summary
    "plot_budget_pie": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_budget_monthly_average": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_budget_annual_bars": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_rating_curve": M(stream_nodes=[1, 5, 10]),
    "plot_aquifer_parameter_histograms": M(layer=1),
    "plot_water_balance_summary": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_supply_vs_demand": M(location_type=1, locations=[1, 2], supply_type=1, supplies=[1, 2]),
    # supply_demand
    "plot_supply_gap_timeline": D(lambda m: (
        (_node_series(m)[0],
         np.full(len(_node_series(m)[0]), 100.0),
         np.linspace(70.0, 100.0, len(_node_series(m)[0]))),
        dict(label="Synthetic Supply"))),
    "plot_budget_supply_gap": M(budget_type="GW", location=1, supply_col=1, demand_col=2,
                                begin_date=BD, end_date=ED),
    "plot_pumping_depth_vs_shortage": D(lambda m: (
        (np.linspace(10, 200, 12), np.linspace(1, 60, 12)),
        dict(location_labels=[f"Loc {i + 1}" for i in range(12)]))),
    "plot_subregion_depth_vs_shortage": M(supply_type=1),
    # timeseries
    "plot_gw_head_hydrographs": M(node_indices=[1, 50, 100], layer=1, begin_date=BD, end_date=ED),
    "plot_stream_flow_hydrograph": M(stream_node_indices=[1, 5, 10], begin_date=BD, end_date=ED),
    "plot_stream_stage_hydrograph": M(stream_node_indices=[1, 5, 10], begin_date=BD, end_date=ED),
    "plot_budget_timeseries": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_zbudget_timeseries": M(zbudget_type="GW_ZBud", zone_id=1, columns=[0, 1, 2],
                                 zone_extent="Zone", elements=None, layers=None, zone_ids=None,
                                 begin_date=BD, end_date=ED),
    "plot_cumulative_gw_storage_change": M(subregions=1, begin_date=BD, end_date=ED),
    "plot_land_use_area_timeseries": M(begin_date=BD, end_date=ED),
    # trends
    "plot_head_trend_map": M(layer=1, begin_date=BD, end_date=ED),
    "plot_seasonal_amplitude_map": M(layer=1, begin_date=BD, end_date=ED),
    "plot_drought_drawdown_rate": M(layer=1, begin_date=BD, end_date=ED),
    "plot_recovery_lag_map": M(layer=1, begin_date=BD, end_date=ED),
    # water_balance
    "plot_water_balance_sankey": D(lambda m: (_balance_names_values(), {})),
    "plot_budget_sankey": M(budget_type="GW", location=1, begin_date=BD, end_date=ED,
                            engine="matplotlib"),
    "plot_butterfly_chart": D(lambda m: (_balance_names_values(), {})),
    "plot_budget_butterfly": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
    "plot_cumulative_departure": M(budget_type="GW", location=1, begin_date=BD, end_date=ED),
}


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------

def _public_plot_functions():
    """Yield ``(module_label, name, fn)`` for every public plot function."""
    found = []
    for mod in MODULES:
        qualname = "iwfm_io.plots" + (f".{mod}" if mod else "")
        module = importlib.import_module(qualname)
        for name, obj in sorted(vars(module).items()):
            if not (name.startswith("plot_") or name.startswith("animate_")):
                continue
            if not callable(obj) or getattr(obj, "__module__", None) != module.__name__:
                continue
            found.append((mod or "plots", name, obj))
    return found


PLOT_FUNCTIONS = _public_plot_functions()


@pytest.fixture(scope="module")
def adapter():
    """Module-scoped ``IOModelAdapter`` on the read-only sample model.

    (The root ``open_sample`` fixture cannot be used from ``tests/io``:
    ``tests/io/conftest.py`` re-declares ``sample_model`` function-scoped.)
    """
    from tests.conftest import SAMPLE_MODEL
    from iwfm_io import open_model
    return open_model(SAMPLE_MODEL)


def _param(mod, name, fn):
    marks = [KNOWN_MARKS[name]] if name in KNOWN_MARKS else []
    return pytest.param(name, fn, id=f"{mod}.{name}", marks=marks)


def test_kwargs_table_is_complete():
    names = [name for _, name, _ in PLOT_FUNCTIONS]
    assert len(names) == len(set(names)), "plot function names must be unique"
    assert set(names) == set(KWARGS), (
        f"missing KWARGS entries: {sorted(set(names) - set(KWARGS))}; "
        f"stale entries: {sorted(set(KWARGS) - set(names))}")
    assert set(KNOWN_MARKS) <= set(names)
    assert MULTI_RETURN <= set(names)


@pytest.mark.parametrize("name,fn", [_param(*t) for t in PLOT_FUNCTIONS])
def test_plot_function_smoke(name, fn, adapter, tmp_path):
    args, kwargs = KWARGS[name](adapter)
    params = inspect.signature(fn).parameters
    is_anim = name.startswith("animate_")
    save_path = None
    if "save_path" in params:
        save_path = tmp_path / f"{name}.{'gif' if is_anim else 'png'}"
        kwargs["save_path"] = str(save_path)
    if "figsize" in params and "figsize" not in kwargs:
        kwargs["figsize"] = (4, 3)
    if "dpi" in params:
        kwargs["dpi"] = 50
    try:
        out = fn(*args, **kwargs)
        if is_anim:
            assert isinstance(out, FuncAnimation)
        else:
            assert isinstance(out, tuple), f"{name} returned {type(out).__name__}"
            assert isinstance(out[0], Figure), f"{name}[0] is {type(out[0]).__name__}"
            if name not in MULTI_RETURN:
                assert len(out) == 2, f"{name} returned a {len(out)}-tuple"
        if save_path is not None:
            assert save_path.is_file() and save_path.stat().st_size > 0
    finally:
        plt.close("all")
