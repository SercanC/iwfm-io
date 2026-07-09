"""
Example 5: Plotting Gallery
============================

Demonstrates representative functions from all 13 visualization modules.

Most plots use IOModelAdapter and require no DLL.  Sections that need
DLL-specific data (live budget queries, stream gain/loss) are clearly
marked and skipped automatically when the DLL is unavailable.

Outputs are saved to test_output/ as ex_*.png / ex_*.gif.

Usage:
    python examples/05_plotting.py

Plot modules covered (58 functions total):
  maps            (11) — grid, GSE, head contour, streams, parameters, wells
  profiles         (2) — stratigraphic cross-section, stream longitudinal profile
  timeseries       (7) — head hydrographs, stream flow, budget time series
  trends           (4) — head trend map, seasonal amplitude
  seasonal         (4) — ridgeline, calendar heatmap, polar
  spatial_patterns (3) — sparkline grid, small multiples
  summary          (7) — rating curves, budget pie, monthly average
  water_balance    (5) — Sankey diagram, butterfly chart, cumulative departure
  stream_analysis  (2) — gain/loss profile, exchange map
  animations       (3) — head animation, DTW animation
  subsidence       (2) — subsidence bowl
  supply_demand    (4) — supply gap timeline
  connectivity     (2) — diversion network, bypass diagram
"""

import sys
from pathlib import Path

# Windows consoles/pipes may default to cp1252, which cannot encode the
# box-drawing characters printed below.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib
matplotlib.use("Agg")   # non-interactive; remove this line for interactive use
import matplotlib.pyplot as plt

REPO_ROOT    = Path(__file__).resolve().parent.parent
SAMPLE_MODEL = REPO_ROOT / ".assets" / "sample_model"
RESULTS_DIR  = SAMPLE_MODEL / "Results"
OUTPUT_DIR   = REPO_ROOT / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(REPO_ROOT))

BEGIN = "10/01/1990_24:00"
END   = "09/30/2000_24:00"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save(fig, name):
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
    print(f"    saved → {path.name}")


def _section(title):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def build_adapter():
    """Build IOModelAdapter from sample model files."""
    from iwfm_io import read_preprocessor, IOModelAdapter

    pp = read_preprocessor(SAMPLE_MODEL / "Preprocessor" / "PreProcessor_MAIN.IN")

    budget_hdfs = {}
    for name, fname in [("GW", "GW.hdf"), ("Stream", "StrmBud.hdf"),
                        ("RootZone", "RootZone.hdf"), ("LWU", "LWU.hdf")]:
        p = RESULTS_DIR / fname
        if p.exists():
            budget_hdfs[name] = str(p)

    hydrograph_hdfs = {}
    for name, fname in [("GWHyd", "GWHyd.hdf"), ("StrmHyd", "StrmHyd.hdf")]:
        p = RESULTS_DIR / fname
        if p.exists():
            hydrograph_hdfs[name] = str(p)

    heads_hdf = RESULTS_DIR / "GWHeadAll.hdf"
    return IOModelAdapter(
        preprocessor=pp,
        heads_hdf=str(heads_hdf) if heads_hdf.exists() else None,
        budget_hdfs=budget_hdfs,
        hydrograph_hdfs=hydrograph_hdfs,
    )


# ── 1. Maps ───────────────────────────────────────────────────────────────────

def demo_maps(adapter):
    from iwfm_io.plots import maps

    _section("Maps (11 functions)")

    fig, ax = maps.plot_grid_mesh(adapter, title="FE Grid — colored by subregion")
    _save(fig, "ex_01_grid_mesh.png")

    fig, ax = maps.plot_ground_surface_elevation(adapter)
    _save(fig, "ex_02_ground_surface_elevation.png")

    fig, ax = maps.plot_stream_network(adapter)
    _save(fig, "ex_03_stream_network.png")

    for lyr in range(1, adapter.n_layers + 1):
        fig, ax = maps.plot_layer_thickness(adapter, layer=lyr)
        _save(fig, f"ex_04_layer_{lyr}_thickness.png")

    fig, ax = maps.plot_tile_drain_locations(adapter)
    _save(fig, "ex_05_tile_drain_locations.png")

    fig, ax = maps.plot_well_locations(adapter)
    _save(fig, "ex_06_well_locations.png")

    fig, ax = maps.plot_lake_and_diversion_elements(adapter)
    _save(fig, "ex_07_lakes_and_diversions.png")

    # Head-based maps require GWHeadAll.hdf
    if adapter._heads_hdf:
        fig, ax = maps.plot_gw_head_contour(
            adapter, layer=1, begin_date=BEGIN, end_date=END, time_index=-1,
        )
        _save(fig, "ex_08_gw_head_contour.png")

        heads = adapter.heads_df(layer=1)
        fig, ax = maps.plot_head_change(
            adapter, layer=1,
            heads_t1=heads.iloc[0].values, heads_t2=heads.iloc[-1].values,
        )
        _save(fig, "ex_09_head_change.png")


# ── 2. Profiles ───────────────────────────────────────────────────────────────

def demo_profiles(adapter):
    from iwfm_io.plots import profiles

    _section("Profiles (2 functions)")

    fig, ax = profiles.plot_stream_longitudinal_profile(adapter)
    _save(fig, "ex_10_stream_longitudinal_profile.png")

    # Cross-section: pick a transect across the model domain
    nodes_gdf = adapter.nodes_df()
    x_mid = nodes_gdf["x"].median()
    y_min  = nodes_gdf["y"].min()
    y_max  = nodes_gdf["y"].max()
    transect = [(x_mid, y_min), (x_mid, y_max)]

    fig, ax = profiles.plot_stratigraphic_cross_section(
        adapter, points=transect, show_heads=False,
    )
    _save(fig, "ex_11_stratigraphic_cross_section.png")


# ── 3. Time series ────────────────────────────────────────────────────────────

def demo_timeseries(adapter):
    from iwfm_io.plots import timeseries

    _section("Time series (7 functions)")

    if adapter._heads_hdf:
        fig, ax = timeseries.plot_gw_head_hydrographs(
            adapter, node_indices=[0, 50, 200, 440], layer=1,
            begin_date=BEGIN, end_date=END,
            title="GW Head Hydrographs — selected nodes",
        )
        _save(fig, "ex_12_gw_head_hydrographs.png")

    # Cumulative GW storage change — requires DLL budget; skip if unavailable
    if hasattr(adapter, "get_budget_timeseries"):
        fig, ax = timeseries.plot_cumulative_gw_storage_change(
            adapter, begin_date=BEGIN, end_date=END,
        )
        _save(fig, "ex_13_cumulative_storage_change.png")


# ── 4. Trends ─────────────────────────────────────────────────────────────────

def demo_trends(adapter):
    from iwfm_io.plots import trends

    _section("Trends (4 functions)")

    if not adapter._heads_hdf:
        print("    No GWHeadAll.hdf — skipping trend maps.")
        return

    fig, ax = trends.plot_head_trend_map(
        adapter, layer=1, begin_date=BEGIN, end_date=END,
    )
    _save(fig, "ex_14_head_trend_map.png")

    fig, ax = trends.plot_seasonal_amplitude_map(
        adapter, layer=1, begin_date=BEGIN, end_date=END,
    )
    _save(fig, "ex_15_seasonal_amplitude_map.png")


# ── 5. Seasonal patterns ──────────────────────────────────────────────────────

def demo_seasonal(adapter):
    from iwfm_io.plots import seasonal
    from iwfm_io import read_hydrograph_hdf
    import numpy as np

    _section("Seasonal patterns (4 functions)")

    # Use GW hydrograph data if available; otherwise synthesize
    hyd_path = RESULTS_DIR / "GWHyd.hdf"
    if hyd_path.exists():
        hyd_df = read_hydrograph_hdf(hyd_path)
        dates  = list(hyd_df.index.to_pydatetime())
        values = hyd_df.iloc[:, 0].values
    else:
        from datetime import datetime, timedelta
        dates  = [datetime(1991, 1, 1) + timedelta(days=30 * i) for i in range(120)]
        values = 200 + 10 * np.cos(np.linspace(0, 20 * np.pi, 120))

    # Ridgeline: overlapping annual hydrographs
    fig, ax = seasonal.plot_ridgeline(dates, values, value_label="Head (ft)")
    _save(fig, "ex_16_ridgeline.png")

    # Calendar heatmap: year × month grid
    fig, ax = seasonal.plot_calendar_heatmap(dates, values, value_label="Head (ft)")
    _save(fig, "ex_17_calendar_heatmap.png")

    # Polar seasonal: monthly averages on polar axis
    import collections
    monthly = collections.defaultdict(list)
    for d, v in zip(dates, values):
        monthly[d.month].append(v)
    monthly_avgs = [sum(monthly[m]) / len(monthly[m]) if monthly[m] else 0
                    for m in range(1, 13)]

    fig, ax = seasonal.plot_polar_seasonal(monthly_avgs, title="Average Monthly Head")
    _save(fig, "ex_18_polar_seasonal.png")


# ── 6. Spatial patterns ───────────────────────────────────────────────────────

def demo_spatial_patterns(adapter):
    from iwfm_io.plots import spatial_patterns

    _section("Spatial patterns (3 functions)")

    if not adapter._heads_hdf:
        print("    No GWHeadAll.hdf — skipping spatial patterns.")
        return

    fig, ax = spatial_patterns.plot_sparkline_grid(
        adapter, layer=1, begin_date=BEGIN, end_date=END,
    )
    _save(fig, "ex_19_sparkline_grid.png")

    fig, ax = spatial_patterns.plot_small_multiples(
        adapter, layer=1, begin_date=BEGIN, end_date=END,
    )
    _save(fig, "ex_20_small_multiples.png")


# ── 7. Summary statistics ─────────────────────────────────────────────────────

def demo_summary(adapter):
    from iwfm_io.plots import summary

    _section("Summary statistics (7 functions)")

    # Rating curves — uses stream geometry from preprocessor
    fig, ax = summary.plot_rating_curve(
        adapter, stream_nodes=list(range(1, 4)),
    )
    _save(fig, "ex_21_rating_curves.png")


# ── 8. Water balance ──────────────────────────────────────────────────────────

def demo_water_balance(adapter):
    from iwfm_io.plots import water_balance
    from iwfm_io import read_budget_hdf

    _section("Water balance (5 functions)")

    gw_path = RESULTS_DIR / "GW.hdf"
    if not gw_path.exists():
        print("    No GW.hdf — skipping water balance plots.")
        return

    bud = read_budget_hdf(gw_path)
    # Use 'entire model' location (last in list)
    df = bud["data"][bud["locations"][-1]]

    names  = df.columns.tolist()
    values = df.mean().values.tolist()

    # Sankey: generic (data from HDF, no DLL needed)
    fig, ax = water_balance.plot_water_balance_sankey(
        names, values, title="GW Water Balance — Entire Model",
    )
    _save(fig, "ex_22_water_balance_sankey.png")

    # Butterfly chart: generic (data from HDF, no DLL needed)
    fig, ax = water_balance.plot_butterfly_chart(
        names, values, title="GW Budget — Inflows vs Outflows",
    )
    _save(fig, "ex_23_butterfly_chart.png")


# ── 9. Stream analysis ────────────────────────────────────────────────────────

def demo_stream_analysis(adapter):
    from iwfm_io.plots import stream_analysis

    _section("Stream analysis (2 functions)")

    # gain/loss requires live solver output — adapter returns empty DataFrame
    flows = adapter.stream_flows_df()
    if flows.empty:
        print("    stream_flows_df() empty (requires DLL solver output).")
        print("    Use IWFMModel in 04_dll_wrapper.py for live stream data.")
    else:
        fig, ax = stream_analysis.plot_stream_gain_loss_profile(adapter)
        _save(fig, "ex_24_stream_gain_loss_profile.png")

        fig, ax = stream_analysis.plot_stream_aquifer_exchange_map(adapter)
        _save(fig, "ex_25_stream_aquifer_exchange_map.png")


# ── 10. Animations ────────────────────────────────────────────────────────────

def demo_animations(adapter):
    from iwfm_io.plots import animations

    _section("Animations (3 functions)")

    if not adapter._heads_hdf:
        print("    No GWHeadAll.hdf — skipping animations.")
        return

    # Limit to ~2 years of frames so the GIFs render quickly
    ani = animations.animate_gw_heads(
        adapter, layer=1,
        begin_date=BEGIN, end_date="09/30/1992_24:00",
        save_path=str(OUTPUT_DIR / "ex_26_gw_heads.gif"),
    )
    plt.close("all")
    print("    saved → ex_26_gw_heads.gif")

    ani = animations.animate_depth_to_water(
        adapter, layer=1,
        begin_date=BEGIN, end_date="09/30/1992_24:00",
        save_path=str(OUTPUT_DIR / "ex_27_depth_to_water.gif"),
    )
    plt.close("all")
    print("    saved → ex_27_depth_to_water.gif")


# ── 11. Connectivity ──────────────────────────────────────────────────────────

def demo_connectivity(adapter):
    from iwfm_io.plots import connectivity

    _section("Connectivity (2 functions)")

    # Bypass diagram — works if bypasses_df() is non-empty
    bypasses = adapter.bypasses_df()
    if bypasses.empty:
        print("    No bypass data in preprocessor.")
    else:
        fig, ax = connectivity.plot_bypass_flow_diagram(adapter)
        _save(fig, "ex_28_bypass_flow_diagram.png")

    # Diversion network — diversions_df() is a placeholder, shows "no diversions"
    fig, ax = connectivity.plot_diversion_network(adapter)
    _save(fig, "ex_29_diversion_network.png")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not SAMPLE_MODEL.exists():
        raise SystemExit(f"Sample model not found: {SAMPLE_MODEL}")

    print("Building IOModelAdapter ...")
    adapter = build_adapter()
    print(f"  {adapter.n_nodes} nodes, {adapter.n_elements} elements, "
          f"{adapter.n_layers} layers, {adapter.n_subregions} subregions")
    print(f"  heads HDF: {'yes' if adapter._heads_hdf else 'no'}")
    print(f"  budget HDFs: {list(adapter._budget_hdfs.keys())}")

    demo_maps(adapter)
    demo_profiles(adapter)
    demo_timeseries(adapter)
    demo_trends(adapter)
    demo_seasonal(adapter)
    demo_spatial_patterns(adapter)
    demo_summary(adapter)
    demo_water_balance(adapter)
    demo_stream_analysis(adapter)
    demo_animations(adapter)
    demo_connectivity(adapter)

    print(f"\nAll plots saved to: {OUTPUT_DIR}")
