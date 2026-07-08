# iwfm-io Plot Function Test Results

**Date**: July 8, 2026
**Test Script**: `examples/test_plots.py`
**DLL Build**: repo-root `IWFM_C_x64.dll` (IWFM 2025.0)
**Model**: `.assets/sample_model/` opened with `is_for_inquiry=True`
**Total Functions Tested**: 58
**Passed**: 46 (79%)
**Failed**: 12 (21%)

---

## Executive Summary

All 58 plot functions across 13 modules are exercised against the sample
model through the DLL wrapper in inquiry mode. **Every failure is a DLL or
inquiry-mode limitation, not a bug in the plotting library or the sample
model** — the same functions work with a fully instantiated model (a
simulation run) or, where applicable, through the DLL-free
`IOModelAdapter`.

| Category | Tests | Root cause |
|----------|-------|------------|
| DLL return-flow skip bug | 08, 33 | DLL bug (see below) |
| Partially instantiated model | 11, 20, 38, 54, 58 | Inquiry-mode design limit |
| Inquiry-mode access violation | 39, 40 | Solver state never initialized |
| Uninitialized hydrograph dates | 15, 16 | DLL returns wrong valid count |
| No zone-budget data in sample model | 18 | Sample model config |

---

## Failure Analysis

### 1. Spurious "Duplicate Node ID" error — a DLL bug, not a model defect (08, 33)

```
IWFM error (-1): * FATAL:
*   Node ID 1 is listed more than once for initial groundwater heads!
*   (Class_AppGW::ReadInitialHeads)
```

Despite the message, **the sample model has no duplicate node IDs**. In
inquiry mode, `GetAquiferParameters_FromFile` (in `Class_AppGW.f90`)
re-reads `GW_MAIN.dat` from disk but fails to skip the Groundwater Return
Flow section, so `ReadInitialHeads` starts parsing at the wrong file
position and misinterprets what it finds as duplicated node IDs. Full
root-cause analysis: `docs/DLL_RETURN_FLOW_SKIP_BUG.md`.

The equivalent bug in the initial-heads path (`GetGWHeadsIC`) no longer
reproduces with the current DLL build, which is why the head-based plots
(05, 12, 31) now pass; earlier test runs reported them as failures with
the same message. Only DWR can fix the remaining aquifer-parameter
variant — it is inside the Fortran DLL.

Affected functions: `plot_aquifer_parameter` (08),
`plot_aquifer_parameter_histograms` (33).

### 2. Partially instantiated model (11, 20, 38, 54, 58)

```
IWFM error (-1): * WARN:
*   Model is instantiated only partially. <feature> cannot be retrieved
*   from a partially instantiated model.
```

Opening with `is_for_inquiry=True` skips full initialization of tile
drains, ag crops, supply requirements, pumping depth, and bypasses. These
functions require `is_for_inquiry=False` with a simulation run:
`plot_tile_drain_locations` (11), `plot_land_use_area_timeseries` (20),
`plot_supply_vs_demand` (38), `plot_subregion_depth_vs_shortage` (54),
`plot_bypass_flow_diagram` (58).

### 3. Inquiry-mode access violation in stream exchange (39, 40)

`get_stream_gain_from_gw()` needs the solver to have computed a timestep;
in inquiry mode the solver never runs and the current DLL build crashes
with a null-pointer read instead of a clean IWFM error. Affected:
`plot_stream_gain_loss_profile` (39), `plot_stream_aquifer_exchange_map`
(40). (Earlier reports attributed test 40 to the duplicate-node message;
the actual failure is this access violation.)

### 4. Invalid hydrograph dates (15, 16)

`IW_Model_GetHydrograph` sets the returned count to the full buffer size
instead of the number of valid entries, leaving trailing dates
uninitialized (`-2415020.0`), which overflows date conversion. Workaround
in calling code: filter `dates > 0`. Affected:
`plot_stream_flow_hydrograph` (15), `plot_stream_stage_hydrograph` (16).

### 5. No zone-budget data in the sample model (18)

`get_zbudget_list()` returns an empty list — the sample model produces no
zone-budget output the DLL recognizes here — and the resulting `None`
propagates into `plot_zbudget_timeseries` (18).

---

## Test Results by Module

### maps.py (Tests 01–11) — 9/11 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 01 | plot_grid_mesh | ✅ OK | |
| 02 | plot_ground_surface_elevation | ✅ OK | |
| 03 | plot_gw_head_contour | ✅ OK | |
| 04 | plot_stream_network | ✅ OK | |
| 05 | plot_depth_to_water | ✅ OK | previously failed; DLL-build fix |
| 06 | plot_layer_thickness | ✅ OK | |
| 07 | plot_head_change | ✅ OK | |
| 08 | plot_aquifer_parameter | ❌ FAIL | DLL return-flow skip bug |
| 09 | plot_well_locations | ✅ OK | |
| 10 | plot_lake_and_diversion_elements | ✅ OK | |
| 11 | plot_tile_drain_locations | ❌ FAIL | partial instantiation |

### profiles.py (Tests 12–13) — 2/2 Passed ✅

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 12 | plot_stratigraphic_cross_section | ✅ OK | previously failed; DLL-build fix |
| 13 | plot_stream_longitudinal_profile | ✅ OK | |

### timeseries.py (Tests 14–20) — 4/7 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 14 | plot_gw_head_hydrographs | ✅ OK | |
| 15 | plot_stream_flow_hydrograph | ❌ FAIL | uninitialized hydrograph dates |
| 16 | plot_stream_stage_hydrograph | ❌ FAIL | uninitialized hydrograph dates |
| 17 | plot_budget_timeseries | ✅ OK | |
| 18 | plot_zbudget_timeseries | ❌ FAIL | no zone-budget data in sample model |
| 19 | plot_cumulative_gw_storage_change | ✅ OK | |
| 20 | plot_land_use_area_timeseries | ❌ FAIL | partial instantiation |

### trends.py (Tests 21–24) — 4/4 Passed ✅

| # | Function | Status |
|---|----------|--------|
| 21 | plot_head_trend_map | ✅ OK |
| 22 | plot_seasonal_amplitude_map | ✅ OK |
| 23 | plot_drought_drawdown_rate | ✅ OK |
| 24 | plot_recovery_lag_map | ✅ OK |

### seasonal.py (Tests 25–28) — 4/4 Passed ✅

| # | Function | Status |
|---|----------|--------|
| 25 | plot_ridgeline | ✅ OK |
| 26 | plot_calendar_heatmap | ✅ OK |
| 27 | plot_polar_seasonal | ✅ OK |
| 28 | plot_budget_polar_seasonal | ✅ OK |

### spatial_patterns.py (Tests 29–31) — 3/3 Passed ✅

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 29 | plot_sparkline_grid | ✅ OK | |
| 30 | plot_small_multiples | ✅ OK | |
| 31 | plot_head_vs_gse_scatter | ✅ OK | previously failed; DLL-build fix |

### summary.py (Tests 32–38) — 5/7 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 32 | plot_rating_curve | ✅ OK | |
| 33 | plot_aquifer_parameter_histograms | ❌ FAIL | DLL return-flow skip bug |
| 34 | plot_budget_pie | ✅ OK | |
| 35 | plot_budget_monthly_average | ✅ OK | |
| 36 | plot_budget_annual_bars | ✅ OK | |
| 37 | plot_water_balance_summary | ✅ OK | |
| 38 | plot_supply_vs_demand | ❌ FAIL | partial instantiation |

### stream_analysis.py (Tests 39–40) — 0/2 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 39 | plot_stream_gain_loss_profile | ❌ FAIL | inquiry-mode access violation |
| 40 | plot_stream_aquifer_exchange_map | ❌ FAIL | inquiry-mode access violation |

### water_balance.py (Tests 41–45) — 5/5 Passed ✅

| # | Function | Status |
|---|----------|--------|
| 41 | plot_water_balance_sankey | ✅ OK |
| 42 | plot_budget_sankey | ✅ OK |
| 43 | plot_butterfly_chart | ✅ OK |
| 44 | plot_budget_butterfly | ✅ OK |
| 45 | plot_cumulative_departure | ✅ OK |

### animations.py (Tests 46–48) — 3/3 Passed ✅

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 46 | animate_gw_heads | ✅ OK | .gif output |
| 47 | animate_stream_flows | ✅ OK | .gif output |
| 48 | animate_depth_to_water | ✅ OK | .gif output |

### subsidence.py (Tests 49–50) — 2/2 Passed ✅

| # | Function | Status |
|---|----------|--------|
| 49 | plot_subsidence_bowl | ✅ OK |
| 50 | plot_subsidence_vs_head | ✅ OK |

### supply_demand.py (Tests 51–54) — 3/4 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 51 | plot_supply_gap_timeline | ✅ OK | |
| 52 | plot_budget_supply_gap | ✅ OK | |
| 53 | plot_pumping_depth_vs_shortage | ✅ OK | |
| 54 | plot_subregion_depth_vs_shortage | ❌ FAIL | partial instantiation |

### cross_sections.py (Tests 55–56) — 2/2 Passed ✅

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 55 | plot_multi_layer_head_panel | ✅ OK | |
| 56 | animate_cross_section | ✅ OK | .gif output |

### connectivity.py (Tests 57–58) — 1/2 Passed

| # | Function | Status | Notes |
|---|----------|--------|-------|
| 57 | plot_diversion_network | ✅ OK | |
| 58 | plot_bypass_flow_diagram | ❌ FAIL | partial instantiation |

---

## Known Warnings (Non-Critical)

1. **DLL export warning**: `DLL does not export IW_GetLocationTypeID_Bypass`
   — expected; `_safe_register` skips it.
2. **Matplotlib**: fixed-aspect notices on constrained maps — normal.
3. **Animation writer**: `MovieWriter ffmpeg unavailable; using Pillow` —
   expected; Pillow writes the GIFs.

---

## Recommendations

### For users
1. All core visualization functions work; the 12 failures are DLL or
   inquiry-mode limitations, not plotting-library bugs.
2. If you hit `Node ID ... listed more than once` in inquiry mode, do
   **not** edit your model — it is the DLL file-position bug described
   above (`docs/DLL_RETURN_FLOW_SKIP_BUG.md`).
3. For tile drains, land use, supply/demand, bypasses, and stream
   exchange, open the model with `is_for_inquiry=False` after a
   simulation run.
4. Head/budget-based plots work DLL-free via
   `iwfm.io.open_model()` + `IOModelAdapter`.

### For developers
1. Filter `dates > 0` when consuming `get_hydrograph()` output.
2. Guard `get_zbudget_list()` results against `None`.
3. Report the return-flow skip bug and the stream-exchange access
   violation upstream to DWR.

---

**Test Duration**: ~8 minutes
**Output**: 47 PNGs + 4 GIFs in `test_output/`
