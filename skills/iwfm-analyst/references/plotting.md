# iwfm.plots catalog — 58 functions by user intent

Every function accepts the `open_model()` adapter (no DLL needed),
returns `(fig, ax)`, and takes `save_path=` to write a PNG.
Gallery from a real model:
https://github.com/SercanC/iwfm-io/blob/main/docs/GALLERY.md

```python
from iwfm.plots import maps, timeseries, trends, seasonal, profiles, \
    spatial_patterns, summary, stream_analysis, water_balance, \
    animations, subsidence, supply_demand, cross_sections, connectivity
```

## "Show me a map of …" — maps
- `plot_grid_mesh(m)` — model grid
- `plot_ground_surface_elevation(m)`
- `plot_gw_head_contour(m, layer=1)` — head contours
- `plot_depth_to_water(m, layer=1)`
- `plot_head_change(m, layer, heads_t1=, heads_t2=)` — drawdown between two times
- `plot_layer_thickness(m, layer=1)`
- `plot_aquifer_parameter(m, parameter="Kh"|"Kv"|"Sy"|"Ss", layer=1, log_scale=True)`
- `plot_stream_network(m)` / `plot_well_locations(m)` /
  `plot_lake_and_diversion_elements(m)` / `plot_tile_drain_locations(m)`

## "How does X change over time?" — timeseries
- `plot_gw_head_hydrographs(m, node_indices=[...], layer=1)`
- `plot_stream_flow_hydrograph(m, stream_node_indices=[...])` / `plot_stream_stage_hydrograph(...)`
- `plot_budget_timeseries(m, budget_type=, location=)`
- `plot_zbudget_timeseries(m, "GW", zone_id, columns=[0,1,2], ...)`
- `plot_cumulative_gw_storage_change(m, subregions=1)`
- `plot_land_use_area_timeseries(m)` — stacked Ag/Urban/Native areas

## "Is it declining / seasonal?" — trends & seasonal
- `plot_head_trend_map(m, layer=1)` — ft/yr trend per node
- `plot_seasonal_amplitude_map(m, layer=1)`
- `plot_drought_drawdown_rate(m, layer=1)` / `plot_recovery_lag_map(m, layer=1)`
- `plot_ridgeline(dates, values)` / `plot_calendar_heatmap(dates, values)`
- `plot_polar_seasonal(monthly_means)` / `plot_budget_polar_seasonal(m, budget_type=, location=)`

## Cross-sections & profiles
- `plot_stratigraphic_cross_section(m, [(x1,y1),(x2,y2)])`
- `plot_stream_longitudinal_profile(m, reach_ids=[...])`
- `plot_multi_layer_head_panel(m, points, begin_date, end_date)`
- `animate_cross_section(m, points, layer=1, ...)` → GIF
- Transect tip: pick endpoints inside the active model area (a straight
  line across a curved domain can exit it and fail).

## Spatial pattern overviews
- `plot_sparkline_grid(m, layer=1, n_points=30)` — tiny hydrographs on a map
- `plot_small_multiples(m, layer=1, n_panels=6)` — head snapshots over time
- `plot_head_vs_gse_scatter(m, layer=1)`

## Water balance & summaries
- `plot_budget_pie` / `plot_budget_monthly_average` / `plot_budget_annual_bars`
- `plot_water_balance_summary(m, budget_type=, location=)`
- `plot_budget_sankey` / `plot_budget_butterfly` / `plot_cumulative_departure`
- `plot_water_balance_sankey(names, values)` / `plot_butterfly_chart(names, values)` (raw arrays)
- `plot_rating_curve(m, stream_nodes=[...])`
- `plot_aquifer_parameter_histograms(m, layer=1)`

## Streams ↔ aquifer
- `plot_stream_gain_loss_profile(m)` — gaining/losing reaches
- `plot_stream_aquifer_exchange_map(m, layer=1)`
  (needs a stream *node budget* HDF in Results, or simulation-mode DLL)

## Supply & demand
- `plot_supply_vs_demand(m, location_type, locations, supply_type, supplies)`
- `plot_subregion_depth_vs_shortage(m, supply_type=1)`
- `plot_supply_gap_timeline(dates, requirement, actual)` / `plot_budget_supply_gap(m, ...)`
- `plot_pumping_depth_vs_shortage(depth, shortage)` (raw arrays)

## Subsidence
- `plot_subsidence_bowl(m, subsidence_values=...)` / `plot_subsidence_vs_head(heads, subsidence, dates=)`

## Animations (GIF)
- `animate_gw_heads(m, layer=1, begin_date=, end_date=)`
- `animate_stream_flows(...)` / `animate_depth_to_water(...)`
- Keep frame counts sane: pass a begin/end window of ≤ ~48 timesteps.

## Connectivity
- `plot_diversion_network(m)` / `plot_bypass_flow_diagram(m)`
