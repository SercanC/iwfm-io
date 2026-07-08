# Plot Gallery

58 visualization functions across 13 modules. All accept either an `IWFMModel` or `IOModelAdapter` instance and return `(fig, ax)`. Most accept an optional `save_path` parameter.

```python
from iwfm.plots import maps, timeseries, water_balance  # etc.
```

## Maps (11 functions)

| Function | Description |
|----------|-------------|
| `maps.plot_element_map` | Model grid colored by subregion |
| `maps.plot_node_map` | Node locations |
| `maps.plot_stream_network` | Stream reaches and nodes |
| `maps.plot_head_contour` | GW head contour map for a given layer/date |
| `maps.plot_depth_to_water` | Depth-to-water contour map |
| `maps.plot_head_change_map` | Change in head between two dates |
| `maps.plot_well_locations` | Well/pumping locations on grid |
| `maps.plot_lake_map` | Lake outlines on grid |
| `maps.plot_tile_drain_map` | Tile drain node locations |
| `maps.plot_stream_aquifer_exchange_map` | Stream-aquifer exchange by reach |
| `maps.plot_aquifer_parameter` | Spatial distribution of an aquifer parameter |

## Profiles (2 functions)

| Function | Description |
|----------|-------------|
| `profiles.plot_stratigraphic_cross_section` | Vertical cross-section through layers |
| `profiles.plot_stream_gain_loss_profile` | Longitudinal gain/loss along a stream |

## Time Series (7 functions)

| Function | Description |
|----------|-------------|
| `timeseries.plot_gw_head_hydrographs` | GW head at selected nodes over time |
| `timeseries.plot_stream_hydrographs` | Stream flow at selected reaches |
| `timeseries.plot_budget_timeseries` | Budget component time series |
| `timeseries.plot_budget_stacked_area` | Stacked area chart of budget components |
| `timeseries.plot_land_use_timeseries` | Land-use area changes over time |
| `timeseries.plot_diversion_timeseries` | Diversion flows over time |
| `timeseries.plot_pumping_timeseries` | Pumping rates over time |

## Trends (4 functions)

| Function | Description |
|----------|-------------|
| `trends.plot_head_trend` | Long-term GW head trend with linear fit |
| `trends.plot_seasonal_decomposition` | Trend + seasonal + residual decomposition |
| `trends.plot_drought_analysis` | Drought periods highlighted on hydrograph |
| `trends.plot_exceedance_curve` | Flow/head duration (exceedance) curve |

## Seasonal (4 functions)

| Function | Description |
|----------|-------------|
| `seasonal.plot_monthly_ridgeline` | Monthly distribution ridgeline plot |
| `seasonal.plot_monthly_heatmap` | Year × month heatmap |
| `seasonal.plot_polar_seasonal` | Polar plot of monthly averages |
| `seasonal.plot_seasonal_boxplot` | Seasonal box-and-whisker plots |

## Spatial Patterns (3 functions)

| Function | Description |
|----------|-------------|
| `spatial_patterns.plot_node_sparklines` | Small sparklines at each node on the map |
| `spatial_patterns.plot_small_multiples` | Grid of per-subregion hydrographs |
| `spatial_patterns.plot_head_vs_gse_scatter` | Head vs ground surface elevation scatter |

## Summary (7 functions)

| Function | Description |
|----------|-------------|
| `summary.plot_rating_curve` | Stage-discharge rating curve |
| `summary.plot_aquifer_parameter_histograms` | Histograms of aquifer Kh, Kv, Ss, Sy |
| `summary.plot_budget_pie` | Pie chart of budget components |
| `summary.plot_budget_bar` | Bar chart comparing budget components |
| `summary.plot_water_table_depth_histogram` | Distribution of depth-to-water |
| `summary.plot_subregion_summary_table` | Tabular summary figure by subregion |
| `summary.plot_model_overview` | Multi-panel model summary dashboard |

## Water Balance (5 functions)

| Function | Description |
|----------|-------------|
| `water_balance.plot_budget_sankey` | Sankey diagram of water flows |
| `water_balance.plot_budget_butterfly` | Butterfly (mirror bar) chart: inflows vs outflows |
| `water_balance.plot_cumulative_departure` | Cumulative departure from mean |
| `water_balance.plot_mass_balance_error` | Mass balance closure error over time |
| `water_balance.plot_storage_change` | Storage change time series |

## Animations (3 functions)

| Function | Description |
|----------|-------------|
| `animations.animate_head_contour` | Animated GW head contour (saves GIF) |
| `animations.animate_stream_flow` | Animated stream flow (saves GIF) |
| `animations.animate_depth_to_water` | Animated depth-to-water (saves GIF) |

## Subsidence (2 functions)

| Function | Description |
|----------|-------------|
| `subsidence.plot_subsidence_bowl` | Subsidence contour map |
| `subsidence.plot_subsidence_correlation` | Subsidence vs head/pumping scatter |

## Supply & Demand (4 functions)

| Function | Description |
|----------|-------------|
| `supply_demand.plot_supply_demand_gap` | Supply vs demand with gap shading |
| `supply_demand.plot_shortage_duration` | Shortage frequency/duration analysis |
| `supply_demand.plot_supply_reliability` | Supply reliability curve |
| `supply_demand.plot_subregion_depth_to_gw` | Subregion-average depth to GW |

## Cross Sections (2 functions)

| Function | Description |
|----------|-------------|
| `cross_sections.plot_multi_layer_section` | Multi-layer cross-section panel |
| `cross_sections.animate_cross_section` | Animated cross-section (saves GIF) |

## Connectivity (2 functions)

| Function | Description |
|----------|-------------|
| `connectivity.plot_diversion_network` | Diversion connectivity diagram |
| `connectivity.plot_bypass_diagram` | Bypass routing diagram |

---

## Running the Test Suite

```bash
# Run all 58 plots against the sample model
python examples/test_plots.py

# Output PNGs saved to test_output/
```

See [TEST_PLOTS_RESULTS.md](TEST_PLOTS_RESULTS.md) for pass/fail details. 42 of 58 pass on the sample model; the 16 failures are all due to sample model defects or DLL limitations (not code bugs).
