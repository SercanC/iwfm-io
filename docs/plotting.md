# Plot Gallery

66 visualization functions across 15 modules. All accept either an `IWFMModel` or `IOModelAdapter` instance and return `(fig, ax)`. Most accept an optional `save_path` parameter, and `close=True` to close the figure after saving (useful when generating many plots in a loop).

This catalogue is generated from the modules themselves; the descriptions are the functions' own docstring summaries.

```python
from iwfm_io.plots import maps, timeseries, water_balance  # etc.
```

## Maps (`maps`, 11 functions)

| Function | Description |
|----------|-------------|
| `maps.plot_grid_mesh` | Plot the finite-element mesh, optionally colored by subregion |
| `maps.plot_ground_surface_elevation` | Plot a filled contour map of ground surface elevation |
| `maps.plot_layer_thickness` | Plot a filled contour map of aquifer layer thickness |
| `maps.plot_aquifer_parameter` | Plot a per-element map of an aquifer parameter for a given layer |
| `maps.plot_gw_head_contour` | Plot a groundwater head contour map |
| `maps.plot_depth_to_water` | Plot depth to water (ground surface minus head at last output timestep) |
| `maps.plot_head_change` | Plot the difference between two head arrays (t2 minus t1) |
| `maps.plot_stream_network` | Plot the stream network on top of the model grid |
| `maps.plot_well_locations` | Plot well locations colored/sized by perforation depth |
| `maps.plot_lake_and_diversion_elements` | Highlight lake and diversion element groups on the model grid |
| `maps.plot_tile_drain_locations` | Plot tile drain node locations on the model grid |

## Profiles (`profiles`, 2 functions)

| Function | Description |
|----------|-------------|
| `profiles.plot_stratigraphic_cross_section` | Plot a stratigraphic cross-section along a transect |
| `profiles.plot_stream_longitudinal_profile` | Plot stream bottom elevation along reaches |

## Cross Sections (`cross_sections`, 2 functions)

| Function | Description |
|----------|-------------|
| `cross_sections.animate_cross_section` | Animate the water table along a cross-section over time |
| `cross_sections.plot_multi_layer_head_panel` | Same transect, one subplot per layer, showing how head |

## Time Series (`timeseries`, 7 functions)

| Function | Description |
|----------|-------------|
| `timeseries.plot_gw_head_hydrographs` | Multi-line plot of groundwater head vs. time at selected nodes |
| `timeseries.plot_stream_flow_hydrograph` | Plot stream flow vs. time at selected stream nodes |
| `timeseries.plot_stream_stage_hydrograph` | Plot stream stage (water surface elevation) vs. time |
| `timeseries.plot_budget_timeseries` | Plot budget components as a stacked area chart or multi-line chart |
| `timeseries.plot_zbudget_timeseries` | Plot zone-budget components over time |
| `timeseries.plot_cumulative_gw_storage_change` | Line chart of cumulative groundwater storage change |
| `timeseries.plot_land_use_area_timeseries` | Stacked area chart of land-use categories over time |

## Trends (`trends`, 4 functions)

| Function | Description |
|----------|-------------|
| `trends.plot_head_trend_map` | Map of linear head trend (slope) at every node |
| `trends.plot_seasonal_amplitude_map` | Map of (max head − min head) at each node over the period |
| `trends.plot_drought_drawdown_rate` | Map of head decline rate during a drought window |
| `trends.plot_recovery_lag_map` | Map of recovery time after heads reach their minimum |

## Seasonal (`seasonal`, 4 functions)

| Function | Description |
|----------|-------------|
| `seasonal.plot_ridgeline` | Overlapping monthly hydrographs for successive years |
| `seasonal.plot_calendar_heatmap` | Year × month heatmap of monthly values |
| `seasonal.plot_polar_seasonal` | 12-month values on a polar axis |
| `seasonal.plot_budget_polar_seasonal` | Polar seasonal plot from budget monthly averages |

## Spatial Patterns (`spatial_patterns`, 3 functions)

| Function | Description |
|----------|-------------|
| `spatial_patterns.plot_sparkline_grid` | Plot tiny hydrographs at sampled node locations on the map |
| `spatial_patterns.plot_small_multiples` | Tile the same head contour map for each year |
| `spatial_patterns.plot_head_vs_gse_scatter` | Scatter plot of initial head vs ground surface elevation |

## Summary (`summary`, 7 functions)

| Function | Description |
|----------|-------------|
| `summary.plot_budget_pie` | Pie chart of average absolute flow by budget component |
| `summary.plot_budget_monthly_average` | Grouped bar chart of monthly-average budget flows |
| `summary.plot_budget_annual_bars` | Grouped or stacked bar chart of annual budget totals |
| `summary.plot_rating_curve` | Stage-discharge rating curves for one or more stream nodes |
| `summary.plot_aquifer_parameter_histograms` | Histogram grid of aquifer parameters for a single layer |
| `summary.plot_water_balance_summary` | Horizontal bar chart of mean inflows (positive) and outflows (negative) |
| `summary.plot_supply_vs_demand` | Grouped bar chart of supply requirements vs shortages |

## Water Balance (`water_balance`, 5 functions)

| Function | Description |
|----------|-------------|
| `water_balance.plot_water_balance_sankey` | Sankey diagram of water balance components |
| `water_balance.plot_budget_sankey` | Sankey of the average water-year budget |
| `water_balance.plot_butterfly_chart` | Mirrored horizontal bar chart: inflows left, outflows right |
| `water_balance.plot_budget_butterfly` | Butterfly chart from model budget time-series averages |
| `water_balance.plot_cumulative_departure` | Running sum of (total inflow − total outflow) over time |

## Stream Analysis (`stream_analysis`, 2 functions)

| Function | Description |
|----------|-------------|
| `stream_analysis.plot_stream_gain_loss_profile` | Longitudinal plot coloring each segment by GW gain/loss |
| `stream_analysis.plot_stream_aquifer_exchange_map` | Spatial map of GW gain/loss magnitude at each stream node |

## Supply / Demand (`supply_demand`, 4 functions)

| Function | Description |
|----------|-------------|
| `supply_demand.plot_supply_gap_timeline` | Stacked area: requirement on top, actual delivery below, gap in red |
| `supply_demand.plot_budget_supply_gap` | Supply gap timeline from budget time-series columns |
| `supply_demand.plot_pumping_depth_vs_shortage` | Scatter plot correlating depth-to-GW with supply shortfall |
| `supply_demand.plot_subregion_depth_vs_shortage` | Depth vs shortage for all subregions using model API |

## Subsidence (`subsidence`, 2 functions)

| Function | Description |
|----------|-------------|
| `subsidence.plot_subsidence_bowl` | Contour map of cumulative subsidence |
| `subsidence.plot_subsidence_vs_head` | Cross-plot of subsidence vs head at a single node over time |

## Animations (`animations`, 3 functions)

| Function | Description |
|----------|-------------|
| `animations.animate_gw_heads` | Create an animation of groundwater head contours over time |
| `animations.animate_stream_flows` | Animate stream flow by varying line width and color over time |
| `animations.animate_depth_to_water` | Animate depth-to-water (GSE minus head) over time |

## Connectivity (`connectivity`, 2 functions)

| Function | Description |
|----------|-------------|
| `connectivity.plot_diversion_network` | Graph visualization showing diversion flow paths |
| `connectivity.plot_bypass_flow_diagram` | Bypass routing diagram with loss fractions |

## Calibration (PEST / PESTPP-IES) (`calibration`, 8 functions)

| Function | Description |
|----------|-------------|
| `calibration.plot_phi_convergence` | Box-plot the ensemble phi distribution per IES iteration |
| `calibration.plot_phi_by_group` | Horizontal bars of mean per-group phi, first vs last iteration |
| `calibration.plot_residual_butterfly` | Diverging horizontal bars of a residual metric by group |
| `calibration.plot_obs_vs_sim` | Observed vs simulated 1:1 plot with fit statistics |
| `calibration.plot_parameter_histograms` | Prior-vs-posterior histograms, one panel per parameter |
| `calibration.plot_parameter_railing` | Stacked horizontal bars: % of ensemble values at bounds, per group |
| `calibration.plot_ensemble_hydrograph` | Ensemble time-series band with base realization and observations |
| `calibration.plot_residual_map` | Map a residual metric at observation locations |

## Running the Test Suite

```bash
# Run the 58-case DLL plot test suite against the sample model
python examples/test_plots.py

# Output PNGs saved to test_output/
```

See [TEST_PLOTS_RESULTS.md](TEST_PLOTS_RESULTS.md) for pass/fail details. 45 of the 58 DLL test cases pass on the sample model; the 10 failures are DLL inquiry-mode limitations (not code bugs), and every one of those functions renders DLL-free through `IOModelAdapter` (`tests/io/test_plots_smoke.py` covers all 66 functions in CI).
