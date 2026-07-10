"""Exercise all 58 plot functions through the DLL wrapper.

Usage:  python examples/test_plots.py [model_root]
        (default model_root: .assets/sample_model)

The preprocessor and simulation main files are discovered from the
model root; the plotting window is the model's own simulation period.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
    os.path.join(_REPO, ".assets", "sample_model")
os.chdir(os.path.join(MODEL_ROOT, "Simulation"))

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for saving PNGs
import matplotlib.pyplot as plt

import iwfm_io
import numpy as np

from pathlib import Path
from iwfm_io.model_adapter import _find_main_file, _find_simulation_main

_root = Path(MODEL_ROOT)
PP = str(_find_main_file(_root, "Preprocessor", ("preproc",)))
SIM = str(_find_simulation_main(_root))

OUT = os.path.join(_REPO, "test_output",
                   os.path.basename(os.path.normpath(MODEL_ROOT)))
os.makedirs(OUT, exist_ok=True)
print(f"model: {MODEL_ROOT}\npp:    {PP}\nsim:   {SIM}\nout:   {OUT}")

with iwfm_io.dll.IWFMModel(
    preprocessor_file=PP,
    simulation_file=SIM,
    is_for_inquiry=True,
) as m:
    _specs = m.get_time_specs()
    bd, ed = _specs["dates"][0], _specs["dates"][-1]
    # Animations render one frame per timestep — cap them at the last
    # 48 steps so long simulations stay reasonable
    anim_bd = _specs["dates"][max(0, len(_specs["dates"]) - 48)]
    anim_ed = ed
    print(f"period: {bd} -> {ed}  (animations from {anim_bd})")

    # ==================================================================
    # Shared data extraction
    # ==================================================================
    from iwfm_io.plots import excel_date_to_datetime

    # Transect points (for profiles, cross-sections)
    x, y = m.get_node_coordinates()
    p1 = (float(x.min()), float(y.mean()))
    p2 = (float(x.max()), float(y.mean()))

    # GW heads for layer 1 over date range
    dates_raw, heads_layer = m.get_gw_heads_for_layer(
        layer=1, begin_date=bd, end_date=ed)
    heads_t1 = heads_layer[:, 0]    # first timestep
    heads_t2 = heads_layer[:, -1]   # last timestep

    # Single node time series (for seasonal plots)
    gw_dates = excel_date_to_datetime(dates_raw)
    gw_values = heads_layer[0, :]   # node 0's time series

    # Monthly means (for polar seasonal)
    import collections
    monthly_sums = collections.defaultdict(list)
    for dt, val in zip(gw_dates, gw_values):
        monthly_sums[dt.month].append(val)
    monthly_means = [np.mean(monthly_sums.get(mo, [0])) for mo in range(1, 13)]

    # Budget info
    budgets = m.get_budget_list()
    bt = budgets[0]["budget_type"] if budgets else None

    # ==================================================================
    # maps.py  (01–11)
    # ==================================================================

    # --- 01. Grid mesh ---
    from iwfm_io.plots.maps import plot_grid_mesh
    try:
        fig, ax = plot_grid_mesh(m, save_path=os.path.join(OUT, "01_grid.png"))
        print("01 grid mesh OK")
        plt.close(fig)
    except Exception as e:
        print(f"01 grid mesh FAIL: {e}")

    # --- 02. Ground surface elevation ---
    from iwfm_io.plots.maps import plot_ground_surface_elevation
    try:
        fig, ax = plot_ground_surface_elevation(
            m, save_path=os.path.join(OUT, "02_gse.png"))
        print("02 GSE OK")
        plt.close(fig)
    except Exception as e:
        print(f"02 GSE FAIL: {e}")

    # --- 03. Head contour ---
    from iwfm_io.plots.maps import plot_gw_head_contour
    try:
        fig, ax = plot_gw_head_contour(
            m, layer=1, time_index=-1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "03_head_contour.png"))
        print("03 head contour OK")
        plt.close(fig)
    except Exception as e:
        print(f"03 head contour FAIL: {e}")

    # --- 04. Stream network ---
    from iwfm_io.plots.maps import plot_stream_network
    try:
        fig, ax = plot_stream_network(
            m, save_path=os.path.join(OUT, "04_streams.png"))
        print("04 stream network OK")
        plt.close(fig)
    except Exception as e:
        print(f"04 stream network FAIL: {e}")

    # --- 05. Depth to water ---
    from iwfm_io.plots.maps import plot_depth_to_water
    try:
        fig, ax = plot_depth_to_water(
            m, layer=1,
            save_path=os.path.join(OUT, "05_dtw.png"))
        print("05 depth to water OK")
        plt.close(fig)
    except Exception as e:
        print(f"05 DTW FAIL: {e}")

    # --- 06. Layer thickness ---
    from iwfm_io.plots.maps import plot_layer_thickness
    try:
        fig, ax = plot_layer_thickness(
            m, layer=1,
            save_path=os.path.join(OUT, "06_thickness.png"))
        print("06 layer thickness OK")
        plt.close(fig)
    except Exception as e:
        print(f"06 layer thickness FAIL: {e}")

    # --- 07. Head change ---
    from iwfm_io.plots.maps import plot_head_change
    try:
        fig, ax = plot_head_change(
            m, layer=1, heads_t1=heads_t1, heads_t2=heads_t2,
            save_path=os.path.join(OUT, "07_head_change.png"))
        print("07 head change OK")
        plt.close(fig)
    except Exception as e:
        print(f"07 head change FAIL: {e}")

    # --- 08. Aquifer parameter ---
    from iwfm_io.plots.maps import plot_aquifer_parameter
    try:
        fig, ax = plot_aquifer_parameter(
            m, parameter="Kh", layer=1,
            save_path=os.path.join(OUT, "08_aquifer_param.png"))
        print("08 aquifer parameter OK")
        plt.close(fig)
    except Exception as e:
        print(f"08 aquifer parameter FAIL: {e}")

    # --- 09. Well locations ---
    from iwfm_io.plots.maps import plot_well_locations
    try:
        fig, ax = plot_well_locations(
            m, save_path=os.path.join(OUT, "09_wells.png"))
        print("09 well locations OK")
        plt.close(fig)
    except Exception as e:
        print(f"09 well locations FAIL: {e}")

    # --- 10. Lake and diversion elements ---
    from iwfm_io.plots.maps import plot_lake_and_diversion_elements
    try:
        fig, ax = plot_lake_and_diversion_elements(
            m, save_path=os.path.join(OUT, "10_lake_div.png"))
        print("10 lake & diversion elements OK")
        plt.close(fig)
    except Exception as e:
        print(f"10 lake & diversion FAIL: {e}")

    # --- 11. Tile drain locations ---
    from iwfm_io.plots.maps import plot_tile_drain_locations
    try:
        fig, ax = plot_tile_drain_locations(
            m, save_path=os.path.join(OUT, "11_tile_drains.png"))
        print("11 tile drain locations OK")
        plt.close(fig)
    except Exception as e:
        print(f"11 tile drain locations FAIL: {e}")

    # ==================================================================
    # profiles.py  (12–13)
    # ==================================================================

    # --- 12. Stratigraphic cross-section ---
    from iwfm_io.plots.profiles import plot_stratigraphic_cross_section
    try:
        fig, ax = plot_stratigraphic_cross_section(
            m, [p1, p2],
            save_path=os.path.join(OUT, "12_xsec.png"))
        print("12 cross-section OK")
        plt.close(fig)
    except Exception as e:
        print(f"12 cross-section FAIL: {e}")

    # --- 13. Stream longitudinal profile ---
    from iwfm_io.plots.profiles import plot_stream_longitudinal_profile
    try:
        fig, ax = plot_stream_longitudinal_profile(
            m, reach_ids=[1],
            save_path=os.path.join(OUT, "13_long_profile.png"))
        print("13 longitudinal profile OK")
        plt.close(fig)
    except Exception as e:
        print(f"13 longitudinal profile FAIL: {e}")

    # ==================================================================
    # timeseries.py  (14–20)
    # ==================================================================

    # --- 14. GW head hydrographs ---
    from iwfm_io.plots.timeseries import plot_gw_head_hydrographs
    try:
        fig, ax = plot_gw_head_hydrographs(
            m, node_indices=[1, 50, 100], layer=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "14_gw_hydrographs.png"))
        print("14 GW head hydrographs OK")
        plt.close(fig)
    except Exception as e:
        print(f"14 GW head hydrographs FAIL: {e}")

    # --- 15. Stream flow hydrograph ---
    from iwfm_io.plots.timeseries import plot_stream_flow_hydrograph
    try:
        fig, ax = plot_stream_flow_hydrograph(
            m, stream_node_indices=[1, 5, 10],
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "15_stream_flow.png"))
        print("15 stream flow hydrograph OK")
        plt.close(fig)
    except Exception as e:
        print(f"15 stream flow hydrograph FAIL: {e}")

    # --- 16. Stream stage hydrograph ---
    from iwfm_io.plots.timeseries import plot_stream_stage_hydrograph
    try:
        fig, ax = plot_stream_stage_hydrograph(
            m, stream_node_indices=[1, 5, 10],
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "16_stream_stage.png"))
        print("16 stream stage hydrograph OK")
        plt.close(fig)
    except Exception as e:
        print(f"16 stream stage hydrograph FAIL: {e}")

    # --- 17. Budget timeseries ---
    from iwfm_io.plots.timeseries import plot_budget_timeseries
    try:
        fig, ax = plot_budget_timeseries(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "17_budget_ts.png"))
        print("17 budget timeseries OK")
        plt.close(fig)
    except Exception as e:
        print(f"17 budget timeseries FAIL: {e}")

    # --- 18. Zone budget timeseries ---
    from iwfm_io.plots.timeseries import plot_zbudget_timeseries
    try:
        zbudgets = m.get_zbudget_list()
        zt = zbudgets[0]["zbudget_type"] if zbudgets else None
        fig, ax = plot_zbudget_timeseries(
            m, zbudget_type=zt, zone_id=1,
            columns=[0, 1, 2], zone_extent="Zone",
            elements=None, layers=None, zone_ids=None,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "18_zbudget_ts.png"))
        print("18 zbudget timeseries OK")
        plt.close(fig)
    except Exception as e:
        print(f"18 zbudget timeseries FAIL: {e}")

    # --- 19. Cumulative GW storage change ---
    from iwfm_io.plots.timeseries import plot_cumulative_gw_storage_change
    try:
        fig, ax = plot_cumulative_gw_storage_change(
            m, subregions=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "19_cum_gw_storage.png"))
        print("19 cumulative GW storage change OK")
        plt.close(fig)
    except Exception as e:
        print(f"19 cumulative GW storage FAIL: {e}")

    # --- 20. Land use area timeseries ---
    from iwfm_io.plots.timeseries import plot_land_use_area_timeseries
    try:
        fig, ax = plot_land_use_area_timeseries(
            m, begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "20_land_use_area.png"))
        print("20 land use area timeseries OK")
        plt.close(fig)
    except Exception as e:
        print(f"20 land use area FAIL: {e}")

    # ==================================================================
    # trends.py  (21–24)
    # ==================================================================

    # --- 21. Head trend map ---
    from iwfm_io.plots.trends import plot_head_trend_map
    try:
        fig, ax = plot_head_trend_map(
            m, layer=1, begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "21_head_trend.png"))
        print("21 head trend map OK")
        plt.close(fig)
    except Exception as e:
        print(f"21 head trend FAIL: {e}")

    # --- 22. Seasonal amplitude map ---
    from iwfm_io.plots.trends import plot_seasonal_amplitude_map
    try:
        fig, ax = plot_seasonal_amplitude_map(
            m, layer=1, begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "22_seasonal_amp.png"))
        print("22 seasonal amplitude OK")
        plt.close(fig)
    except Exception as e:
        print(f"22 seasonal amplitude FAIL: {e}")

    # --- 23. Drought drawdown rate ---
    from iwfm_io.plots.trends import plot_drought_drawdown_rate
    try:
        fig, ax = plot_drought_drawdown_rate(
            m, layer=1, begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "23_drought_drawdown.png"))
        print("23 drought drawdown rate OK")
        plt.close(fig)
    except Exception as e:
        print(f"23 drought drawdown FAIL: {e}")

    # --- 24. Recovery lag map ---
    from iwfm_io.plots.trends import plot_recovery_lag_map
    try:
        fig, ax = plot_recovery_lag_map(
            m, layer=1, begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "24_recovery_lag.png"))
        print("24 recovery lag map OK")
        plt.close(fig)
    except Exception as e:
        print(f"24 recovery lag FAIL: {e}")

    # ==================================================================
    # seasonal.py  (25–28)
    # ==================================================================

    # --- 25. Ridgeline ---
    from iwfm_io.plots.seasonal import plot_ridgeline
    try:
        fig, ax = plot_ridgeline(
            gw_dates, gw_values, value_label="Head",
            save_path=os.path.join(OUT, "25_ridgeline.png"))
        print("25 ridgeline OK")
        plt.close(fig)
    except Exception as e:
        print(f"25 ridgeline FAIL: {e}")

    # --- 26. Calendar heatmap ---
    from iwfm_io.plots.seasonal import plot_calendar_heatmap
    try:
        fig, ax = plot_calendar_heatmap(
            gw_dates, gw_values, value_label="Head",
            save_path=os.path.join(OUT, "26_calendar_heatmap.png"))
        print("26 calendar heatmap OK")
        plt.close(fig)
    except Exception as e:
        print(f"26 calendar heatmap FAIL: {e}")

    # --- 27. Polar seasonal ---
    from iwfm_io.plots.seasonal import plot_polar_seasonal
    try:
        fig, ax = plot_polar_seasonal(
            monthly_means, title="Seasonal Head Pattern",
            save_path=os.path.join(OUT, "27_polar_seasonal.png"))
        print("27 polar seasonal OK")
        plt.close(fig)
    except Exception as e:
        print(f"27 polar seasonal FAIL: {e}")

    # --- 28. Budget polar seasonal ---
    from iwfm_io.plots.seasonal import plot_budget_polar_seasonal
    try:
        fig, ax = plot_budget_polar_seasonal(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "28_budget_polar.png"))
        print("28 budget polar seasonal OK")
        plt.close(fig)
    except Exception as e:
        print(f"28 budget polar seasonal FAIL: {e}")

    # ==================================================================
    # spatial_patterns.py  (29–31)
    # ==================================================================

    # --- 29. Sparkline grid ---
    from iwfm_io.plots.spatial_patterns import plot_sparkline_grid
    try:
        fig, ax = plot_sparkline_grid(
            m, layer=1, begin_date=bd, end_date=ed,
            n_points=30,
            save_path=os.path.join(OUT, "29_sparklines.png"))
        print("29 sparkline grid OK")
        plt.close(fig)
    except Exception as e:
        print(f"29 sparkline grid FAIL: {e}")

    # --- 30. Small multiples ---
    from iwfm_io.plots.spatial_patterns import plot_small_multiples
    try:
        fig, axes = plot_small_multiples(
            m, layer=1, begin_date=bd, end_date=ed,
            n_panels=6,
            save_path=os.path.join(OUT, "30_small_multiples.png"))
        print("30 small multiples OK")
        plt.close(fig)
    except Exception as e:
        print(f"30 small multiples FAIL: {e}")

    # --- 31. Head vs GSE scatter ---
    from iwfm_io.plots.spatial_patterns import plot_head_vs_gse_scatter
    try:
        fig, ax = plot_head_vs_gse_scatter(
            m, layer=1,
            save_path=os.path.join(OUT, "31_head_vs_gse.png"))
        print("31 head vs GSE scatter OK")
        plt.close(fig)
    except Exception as e:
        print(f"31 head vs GSE FAIL: {e}")

    # ==================================================================
    # summary.py  (32–38)
    # ==================================================================

    # --- 32. Rating curve ---
    from iwfm_io.plots.summary import plot_rating_curve
    try:
        fig, ax = plot_rating_curve(
            m, stream_nodes=[1, 5, 10],
            save_path=os.path.join(OUT, "32_rating.png"))
        print("32 rating curve OK")
        plt.close(fig)
    except Exception as e:
        print(f"32 rating curve FAIL: {e}")

    # --- 33. Aquifer parameter histograms ---
    from iwfm_io.plots.summary import plot_aquifer_parameter_histograms
    try:
        fig, axes = plot_aquifer_parameter_histograms(
            m, layer=1,
            save_path=os.path.join(OUT, "33_param_hist.png"))
        print("33 parameter histograms OK")
        plt.close(fig)
    except Exception as e:
        print(f"33 parameter histograms FAIL: {e}")

    # --- 34. Budget pie ---
    from iwfm_io.plots.summary import plot_budget_pie
    try:
        fig, ax = plot_budget_pie(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "34_budget_pie.png"))
        print("34 budget pie OK")
        plt.close(fig)
    except Exception as e:
        print(f"34 budget pie FAIL: {e}")

    # --- 35. Budget monthly average ---
    from iwfm_io.plots.summary import plot_budget_monthly_average
    try:
        fig, ax = plot_budget_monthly_average(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "35_budget_monthly_avg.png"))
        print("35 budget monthly average OK")
        plt.close(fig)
    except Exception as e:
        print(f"35 budget monthly avg FAIL: {e}")

    # --- 36. Budget annual bars ---
    from iwfm_io.plots.summary import plot_budget_annual_bars
    try:
        fig, ax = plot_budget_annual_bars(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "36_budget_annual.png"))
        print("36 budget annual bars OK")
        plt.close(fig)
    except Exception as e:
        print(f"36 budget annual bars FAIL: {e}")

    # --- 37. Water balance summary ---
    from iwfm_io.plots.summary import plot_water_balance_summary
    try:
        fig, ax = plot_water_balance_summary(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "37_water_balance_summary.png"))
        print("37 water balance summary OK")
        plt.close(fig)
    except Exception as e:
        print(f"37 water balance summary FAIL: {e}")

    # --- 38. Supply vs demand ---
    from iwfm_io.plots.summary import plot_supply_vs_demand
    try:
        sub_ids = m.get_subregion_ids()
        fig, ax = plot_supply_vs_demand(
            m, location_type=1, locations=sub_ids[:3],
            supply_type=1, supplies=[1, 2, 3],
            save_path=os.path.join(OUT, "38_supply_demand.png"))
        print("38 supply vs demand OK")
        plt.close(fig)
    except Exception as e:
        print(f"38 supply vs demand FAIL: {e}")

    # ==================================================================
    # stream_analysis.py  (39–40)
    # ==================================================================

    # --- 39. Stream gain/loss profile ---
    from iwfm_io.plots.stream_analysis import plot_stream_gain_loss_profile
    try:
        fig, ax = plot_stream_gain_loss_profile(
            m, reach_ids=[1],
            save_path=os.path.join(OUT, "39_gain_loss.png"))
        print("39 stream gain/loss profile OK")
        plt.close(fig)
    except Exception as e:
        print(f"39 stream gain/loss FAIL: {e}")

    # --- 40. Stream-aquifer exchange map ---
    from iwfm_io.plots.stream_analysis import plot_stream_aquifer_exchange_map
    try:
        fig, ax = plot_stream_aquifer_exchange_map(
            m, layer=1,
            save_path=os.path.join(OUT, "40_strm_aq_exchange.png"))
        print("40 stream-aquifer exchange map OK")
        plt.close(fig)
    except Exception as e:
        print(f"40 stream-aquifer exchange FAIL: {e}")

    # ==================================================================
    # water_balance.py  (41–45)
    # ==================================================================

    # --- 41. Water balance Sankey (raw data) ---
    from iwfm_io.plots.water_balance import plot_water_balance_sankey
    try:
        # Use budget column names and synthetic mean values
        if bt is not None:
            titles = m.get_budget_column_titles(bt, 1)
            n_cols = len(titles)
            cols = list(range(n_cols))
            ts = m.get_budget_timeseries(
                bt, 1, cols, bd, ed, "1MON")
            col_means = np.abs(ts["values"]).mean(axis=0)
            sankey_names = titles
            sankey_values = col_means
        else:
            sankey_names = ["Inflow A", "Inflow B", "Outflow A", "Outflow B"]
            sankey_values = [100, 80, -90, -70]
        fig, ax = plot_water_balance_sankey(
            sankey_names, sankey_values,
            save_path=os.path.join(OUT, "41_sankey_raw.png"))
        print("41 water balance Sankey OK")
        plt.close(fig)
    except Exception as e:
        print(f"41 water balance Sankey FAIL: {e}")

    # --- 42. Budget Sankey ---
    from iwfm_io.plots.water_balance import plot_budget_sankey
    try:
        fig, ax = plot_budget_sankey(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "42_budget_sankey.png"))
        print("42 budget Sankey OK")
        plt.close("all")  # engine="auto" may return a plotly Figure
    except Exception as e:
        print(f"42 budget Sankey FAIL: {e}")

    # --- 43. Butterfly chart (raw data) ---
    from iwfm_io.plots.water_balance import plot_butterfly_chart
    try:
        fig, ax = plot_butterfly_chart(
            sankey_names, sankey_values,
            save_path=os.path.join(OUT, "43_butterfly_raw.png"))
        print("43 butterfly chart OK")
        plt.close(fig)
    except Exception as e:
        print(f"43 butterfly chart FAIL: {e}")

    # --- 44. Budget butterfly ---
    from iwfm_io.plots.water_balance import plot_budget_butterfly
    try:
        fig, ax = plot_budget_butterfly(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "44_budget_butterfly.png"))
        print("44 budget butterfly OK")
        plt.close(fig)
    except Exception as e:
        print(f"44 budget butterfly FAIL: {e}")

    # --- 45. Cumulative departure ---
    from iwfm_io.plots.water_balance import plot_cumulative_departure
    try:
        fig, ax = plot_cumulative_departure(
            m, budget_type=bt, location=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "45_cum_departure.png"))
        print("45 cumulative departure OK")
        plt.close(fig)
    except Exception as e:
        print(f"45 cumulative departure FAIL: {e}")

    # ==================================================================
    # animations.py  (46–48)  — short date range, .gif output
    # ==================================================================

    # --- 46. Animate GW heads ---
    from iwfm_io.plots.animations import animate_gw_heads
    try:
        anim = animate_gw_heads(
            m, layer=1, begin_date=anim_bd, end_date=anim_ed,
            interval_frames=1,
            save_path=os.path.join(OUT, "46_anim_heads.gif"))
        print("46 animate GW heads OK")
        plt.close("all")
    except Exception as e:
        print(f"46 animate GW heads FAIL: {e}")

    # --- 47. Animate stream flows ---
    from iwfm_io.plots.animations import animate_stream_flows
    try:
        anim = animate_stream_flows(
            m, layer=1, begin_date=anim_bd, end_date=anim_ed,
            interval_frames=1,
            save_path=os.path.join(OUT, "47_anim_flows.gif"))
        print("47 animate stream flows OK")
        plt.close("all")
    except Exception as e:
        print(f"47 animate stream flows FAIL: {e}")

    # --- 48. Animate depth to water ---
    from iwfm_io.plots.animations import animate_depth_to_water
    try:
        anim = animate_depth_to_water(
            m, layer=1, begin_date=anim_bd, end_date=anim_ed,
            interval_frames=1,
            save_path=os.path.join(OUT, "48_anim_dtw.gif"))
        print("48 animate depth to water OK")
        plt.close("all")
    except Exception as e:
        print(f"48 animate DTW FAIL: {e}")

    # ==================================================================
    # subsidence.py  (49–50)
    # ==================================================================

    # --- 49. Subsidence bowl ---
    from iwfm_io.plots.subsidence import plot_subsidence_bowl
    try:
        subsidence = m.get_subsidence_all()
        fig, ax = plot_subsidence_bowl(
            m, subsidence_values=subsidence[:, 0],
            save_path=os.path.join(OUT, "49_subsidence_bowl.png"))
        print("49 subsidence bowl OK")
        plt.close(fig)
    except Exception as e:
        print(f"49 subsidence bowl FAIL: {e}")

    # --- 50. Subsidence vs head ---
    from iwfm_io.plots.subsidence import plot_subsidence_vs_head
    try:
        # Use synthetic data from extracted head timeseries
        heads_ts = gw_values
        subsidence_ts = np.linspace(0, 0.5, len(gw_values))
        fig, ax = plot_subsidence_vs_head(
            heads_ts, subsidence_ts, dates=gw_dates,
            node_label="Node 1",
            save_path=os.path.join(OUT, "50_subsidence_vs_head.png"))
        print("50 subsidence vs head OK")
        plt.close(fig)
    except Exception as e:
        print(f"50 subsidence vs head FAIL: {e}")

    # ==================================================================
    # supply_demand.py  (51–54)
    # ==================================================================

    # --- 51. Supply gap timeline (raw data) ---
    from iwfm_io.plots.supply_demand import plot_supply_gap_timeline
    try:
        # Synthesize requirement/actual from budget data
        n_ts = len(gw_dates)
        requirement = np.abs(np.random.default_rng(42).normal(100, 10, n_ts))
        actual = requirement * np.random.default_rng(43).uniform(0.7, 1.0, n_ts)
        fig, ax = plot_supply_gap_timeline(
            gw_dates, requirement, actual, label="Synthetic Supply",
            save_path=os.path.join(OUT, "51_supply_gap.png"))
        print("51 supply gap timeline OK")
        plt.close(fig)
    except Exception as e:
        print(f"51 supply gap timeline FAIL: {e}")

    # --- 52. Budget supply gap ---
    from iwfm_io.plots.supply_demand import plot_budget_supply_gap
    try:
        # Use first two budget columns as supply/demand proxies
        fig, ax = plot_budget_supply_gap(
            m, budget_type=bt, location=1,
            supply_col=0, demand_col=1,
            begin_date=bd, end_date=ed,
            save_path=os.path.join(OUT, "52_budget_supply_gap.png"))
        print("52 budget supply gap OK")
        plt.close(fig)
    except Exception as e:
        print(f"52 budget supply gap FAIL: {e}")

    # --- 53. Pumping depth vs shortage (raw data) ---
    from iwfm_io.plots.supply_demand import plot_pumping_depth_vs_shortage
    try:
        rng = np.random.default_rng(44)
        depth_to_gw = rng.uniform(10, 200, 20)
        shortage = depth_to_gw * rng.uniform(0.1, 0.5, 20)
        fig, ax = plot_pumping_depth_vs_shortage(
            depth_to_gw, shortage,
            location_labels=[f"Loc {i+1}" for i in range(20)],
            save_path=os.path.join(OUT, "53_depth_vs_shortage.png"))
        print("53 pumping depth vs shortage OK")
        plt.close(fig)
    except Exception as e:
        print(f"53 pumping depth vs shortage FAIL: {e}")

    # --- 54. Subregion depth vs shortage ---
    from iwfm_io.plots.supply_demand import plot_subregion_depth_vs_shortage
    try:
        fig, ax = plot_subregion_depth_vs_shortage(
            m, supply_type=1,
            save_path=os.path.join(OUT, "54_subregion_depth_short.png"))
        print("54 subregion depth vs shortage OK")
        plt.close(fig)
    except Exception as e:
        print(f"54 subregion depth vs shortage FAIL: {e}")

    # ==================================================================
    # cross_sections.py  (55–56)
    # ==================================================================

    # --- 55. Multi-layer head panel ---
    from iwfm_io.plots.cross_sections import plot_multi_layer_head_panel
    try:
        fig, axes = plot_multi_layer_head_panel(
            m, points=[p1, p2],
            begin_date=bd, end_date=ed, time_index=0,
            save_path=os.path.join(OUT, "55_multi_layer_panel.png"))
        print("55 multi-layer head panel OK")
        plt.close(fig)
    except Exception as e:
        print(f"55 multi-layer head panel FAIL: {e}")

    # --- 56. Animate cross-section ---
    from iwfm_io.plots.cross_sections import animate_cross_section
    try:
        anim = animate_cross_section(
            m, points=[p1, p2], layer=1,
            begin_date=anim_bd, end_date=anim_ed,
            interval_frames=1,
            save_path=os.path.join(OUT, "56_anim_xsec.gif"))
        print("56 animate cross-section OK")
        plt.close("all")
    except Exception as e:
        print(f"56 animate cross-section FAIL: {e}")

    # ==================================================================
    # connectivity.py  (57–58)
    # ==================================================================

    # --- 57. Diversion network ---
    from iwfm_io.plots.connectivity import plot_diversion_network
    try:
        fig, ax = plot_diversion_network(
            m, save_path=os.path.join(OUT, "57_diversion_network.png"))
        print("57 diversion network OK")
        plt.close(fig)
    except Exception as e:
        print(f"57 diversion network FAIL: {e}")

    # --- 58. Bypass flow diagram ---
    from iwfm_io.plots.connectivity import plot_bypass_flow_diagram
    try:
        fig, ax = plot_bypass_flow_diagram(
            m, save_path=os.path.join(OUT, "58_bypass_diagram.png"))
        print("58 bypass flow diagram OK")
        plt.close(fig)
    except Exception as e:
        print(f"58 bypass flow diagram FAIL: {e}")

print(f"\nAll outputs in: {os.path.abspath(OUT)}")
