# API Reference

## `iwfm` — DLL Wrapper (Windows x64)

### Classes

| Class | Module | Description |
|-------|--------|-------------|
| `IWFMModel` | `iwfm_io.dll.model` | Main model interface. Context manager. Wraps grid, GW, streams, budgets, diversions, wells, lakes, simulation control. `describe()` returns a JSON-serializable model summary. |
| `IWFMBudget` | `iwfm_io.dll.budget` | Standalone budget HDF5 reader via `IW_Budget_*` functions. |
| `IWFMZBudget` | `iwfm_io.dll.zbudget` | Standalone zone-budget reader via `IW_ZBudget_*` functions. |
| `IWFMError` | `iwfm_io.dll._errors` | Exception raised when a DLL call returns a non-zero status code. |

### Running Models

| Function | Description |
|----------|-------------|
| `run_model(model_dir, steps=(...))` | Run the IWFM toolchain (default: preprocessor + simulation; add `"budget"`, `"zbudget"`). Executables resolved from `<model_dir>/Bin` or `IWFM_BIN_DIR`. Raises on failure (`check=False` to inspect instead). |
| `run_preprocessor / run_simulation / run_budget / run_zbudget(model_dir)` | Run one tool. Returns a `RunResult` (`success`, `elapsed`, `errors`, `returncode`). Failure = nonzero exit **or** FATAL/ERROR lines in console output or the tool's Messages file. |

### Module-Level Functions

| Function | Description |
|----------|-------------|
| `load_dll(dll_path=None, version=None, download=True)` | Load the IWFM DLL. Returns a `ctypes.WinDLL` handle. When `version` names a published build that is not installed, it is downloaded automatically (`download=False` disables the fetch for offline machines). |
| `list_dll_versions()` | Scan `dlls/` and `~/.iwfm/dlls/` for installed DLL versions. |
| `download_dll(version="2025.0.1747")` | Download an official DLL build (sha256-verified) from the project's GitHub releases into `~/.iwfm/dlls/<version>/`. |
| `get_version(dll)` | Return the IWFM version string. |
| `get_kernel_version(dll)` | Return the IWFM kernel version string. |
| `set_log_file(dll, path)` | Redirect DLL log output to a file. |
| `close_log_file(dll)` | Close the DLL log file. |
| `get_last_message(dll)` | Return the last DLL message string. |
| `get_n_intervals(dll, begin, end, step)` | Number of timesteps between two dates. |
| `increment_time(dll, date, step)` | Advance a date string by one timestep. |

### Enum Classes

| Enum | Values populated from |
|------|-----------------------|
| `BudgetTypeID` | `IW_GetBudgetType_*` |
| `ZBudgetTypeID` | `IW_GetZBudgetType_*` |
| `LandUseTypeID` | `IW_GetLandUseType_*` |
| `LocationTypeID` | `IW_GetLocationType_*` |
| `FlowDestTypeID` | `IW_GetFlowDestType_*` |
| `SupplyTypeID` | `IW_GetSupplyType_*` |
| `ZoneExtentID` | `IW_GetZoneExtent_*` |
| `DataUnitTypeID` | `IW_GetDataUnitType_*` |

---

## `iwfm_io` — Pure-Python File I/O

### Opening a Model

| Function | Description |
|----------|-------------|
| `open_model(path)` | Open a model from its root folder (or a main-file path). Discovers the preprocessor/simulation main files and all HDF5 results; returns a ready `IOModelAdapter`. Accepts `preprocessor=`, `simulation=`, `results_dir=` overrides. |

```python
from iwfm_io import open_model

model = open_model("path/to/my_model")
model.describe()   # JSON-serializable summary: grid, streams, lakes,
                   # simulation period, and every budget/hydrograph found
```

### Date Utilities

| Function | Description |
|----------|-------------|
| `parse_iwfm_date(s)` | Parse `"MM/DD/YYYY_HH:MM"` → `datetime`. Handles `24:00` (the parsed instant is next-day midnight — the moment the period ends). |
| `format_iwfm_date(dt)` | Format `datetime` → `"MM/DD/YYYY_HH:MM"`. Midnight formats as `24:00` of the previous day (exact inverse of the parser). |
| `iwfm_day(times)` | The day a stamp *belongs to*: midnight stamps map to the previous day (the day they close), intraday stamps to their own day. Scalar, Series, or DatetimeIndex. Use this — not `.dt.day`/`.dt.month` on raw stamps — when grouping IWFM output by calendar period. |
| `water_year(times)` | Water year (Oct 1–Sep 30, labeled by ending year) each stamp belongs to, built on `iwfm_day` — a `9/30_24:00` stamp closes its water year. |

### Preprocessor Readers

| Function | Input file | Returns |
|----------|-----------|---------|
| `read_preprocessor(path)` | `PreProcessor_MAIN.IN` | `PreprocessorMain` — data available directly: `.nodes`, `.elements`, `.subregions`, `.stratigraphy`, `.n_layers`, `.stream_reaches`, `.stream_nodes`, `.lakes` |
| `read_nodes(path)` | `NodeXY.dat` | Result with `.data` GeoDataFrame |
| `read_elements(path)` | `Element.dat` | Result with `.data` GeoDataFrame |
| `read_strata(path)` | `Strata.dat` | Result with `.data` DataFrame, `.n_layers` |
| `read_stream_geom(path)` | `Stream.dat` | Stream geometry result |
| `read_lake_geom(path)` | `Lake.dat` | Lake geometry result |

### Simulation Readers

| Function | Input file | Returns |
|----------|-----------|---------|
| `read_simulation(path)` | `Simulation_MAIN.IN` | `SimulationMain` with `.sim_begin`, `.sim_end`, `.time_step` |
| `read_precip(path)` | `Precip.dat` | Result with `.data` DataFrame, `.spec` |
| `read_et(path)` | `ET.dat` | Result with `.data` DataFrame, `.spec` |
| `read_irigfrac(path)` | `IrigFrac.dat` | Irrigation fractions |
| `read_supply_adjust(path)` | `SupplyAdjust.dat` | Supply adjustment specs |

### Groundwater Readers

| Function | Input file |
|----------|-----------|
| `read_gw_main(path)` | `GW_MAIN.dat` — incl. aquifer parameters (per-node or parametric grid), Kh anomalies, return-flow specs, initial heads |
| `read_bc_main(path)` | `BC_MAIN.dat` |
| `read_spec_head_bc(path)` | `SpecHeadBC.dat` |
| `read_spec_flow_bc(path)` | Specified flow BC file |
| `read_general_head_bc(path)` | General head BC file |
| `read_constrained_head_bc(path)` | Constrained general head BC file |
| `read_boundary_ts(path)` | `BoundTSD.dat` |
| `read_pump_main(path)` | `Pump_MAIN.dat` |
| `read_well_spec(path)` | `WellSpec.dat` — well locations, per-well pumping config, delivery element groups |
| `read_elem_pump(path)` | `ElemPump.dat` |
| `read_ts_pumping(path)` | `TSPumping.dat` |
| `read_tile_drain(path)` | `TileDrain.dat` — incl. hydrograph print control |
| `read_subsidence(path)` | `Subsidence.dat` — incl. subsidence parameters (per-node or parametric grid) |

### Stream Readers

| Function | Input file |
|----------|-----------|
| `read_stream_main(path)` | `Stream_MAIN.dat` — incl. reach bed parameters and stream evaporation table |
| `read_stream_inflow(path)` | `StreamInflow.dat` |
| `read_diver_specs(path)` | `DiverSpecs.dat` |
| `read_bypass_specs(path)` | `BypassSpecs.dat` |
| `read_diversions(path)` | `Diversions.dat` |

### Other Input Readers

| Function | Input file |
|----------|-----------|
| `read_lake_main(path)` | `Lake_MAIN.dat` |
| `read_rootzone_main(path)` | `RootZone_MAIN.dat` — incl. per-element soil parameter table |
| `read_nonponded_ag_main(path)` | Non-ponded crops main (AGNPFL) — crop codes, root depths, CN and pointer tables, initial moisture |
| `read_ponded_ag_main(path)` | Ponded crops main (PFL) — rice/refuge parameters and pointer tables |
| `read_urban_main(path)` | Urban main (URBFL) — per-element urban water use parameters |
| `read_native_veg_main(path)` | Native/riparian vegetation main (NVRVFL) |
| `read_swshed(path)` | `SWShed.dat` — watershed definitions, root zone/aquifer parameters, initial conditions |
| `read_unsatzone(path)` | `UnsatZone.dat` — per-element parameters and initial moisture |

Pointer-table columns whose names start with `ic`/`irn`/`itscol` are 1-based column numbers referencing data columns of other files (ET, Precipitation, return-flow/reuse fractions, time-series pumping, surface-flow destinations, …); each dataclass docstring states which file every such column points at.

### HDF5 Output Readers

| Function | Description |
|----------|-------------|
| `read_budget_hdf(path)` | Budget HDF5 → dict with `locations` (native DLL order), `data` dict of DataFrames, `data_types`, and `interval` (the file's native output interval, e.g. `'1DAY'`) |
| `read_head_hdf(path, n_nodes, n_layers)` | GWHeadAll.hdf → DataFrame |
| `read_hydrograph_hdf(path)` | Hydrograph HDF5 → DataFrame |
| `read_zone_def(path)` | Zone definition file → zone mapping |
| `read_zbudget_hdf(path)` | Zone budget HDF5 → dict |

### Text Output Readers

| Function | Description |
|----------|-------------|
| `read_hydrograph_out(path)` | `GWHyd.out` or `StrmHyd.out` → DataFrame |
| `read_hydrograph_out_with_metadata(path)` | Same, plus parsed metadata |
| `read_head_all_out(path)` | `GWHeadAll.out` → DataFrame with `node_<id>_layer_<L>` columns |
| `read_final_state_out(path)` | `FinalGWHeads.out`, etc. → DataFrame |
| `read_flow_out(path)` | `FaceFlow.out`, `BoundaryFlow.out` → DataFrame |
| `read_velocity_out(path)` | `GWVelocities.out` → DataFrame |
| `read_budget_text(path)` | `GW.bud`, `Strm.bud` text budgets → DataFrame |

### Writers

Writers follow the reader name pattern (`read_*` → `write_*`) and accept the same result object. Every section — including aquifer/subsidence parameters, initial conditions, and all pointer tables — is regenerated from the parsed DataFrames, so `read → edit DataFrame → write` produces a valid IWFM input file (verified: the sample model reproduces baseline heads exactly from fully regenerated inputs).

```python
from iwfm_io import read_gw_main, write_gw_main

gw = read_gw_main("GW_MAIN.dat")
gw.initial_heads["head_layer_1"] += 5.0            # modify
write_gw_main(gw, "GW_MAIN_new.dat", base_dir=sim_dir)
```

Component-main writers (`write_gw_main`, `write_subsidence_file`, `write_stream_main`, `write_rootzone_main`, `write_bc_main`, and the four root-zone sub-main writers) accept `base_dir` — pass the simulation working directory (the folder of the simulation main file) so referenced paths are written relative to it; IWFM does not accept absolute paths.

Full list: `write_preprocessor`, `write_nodes`, `write_elements`, `write_strata`, `write_stream_geom`, `write_lake_geom`, `write_simulation`, `write_precip`, `write_et`, `write_irigfrac`, `write_supply_adjust`, `write_gw_main`, `write_bc_main`, `write_spec_head_bc`, `write_spec_flow_bc`, `write_general_head_bc`, `write_constrained_head_bc`, `write_boundary_ts`, `write_pump_main`, `write_well_spec`, `write_elem_pump`, `write_ts_pumping`, `write_tile_drain`, `write_subsidence_file`, `write_stream_main`, `write_stream_inflow`, `write_diver_specs`, `write_bypass_specs`, `write_diversions`, `write_lake_main`, `write_rootzone_main`, `write_nonponded_ag_main`, `write_ponded_ag_main`, `write_urban_main`, `write_native_veg_main`, `write_swshed`, `write_unsatzone`.

**Every reader now has a mirror writer** — the reader/writer pairs cover the complete input tree, and the exe round-trip test regenerates all of them (root-zone sub-mains and BC files included) and reproduces baseline heads exactly.

### Validation

| Function | Description |
|----------|-------------|
| `validate_nodes(nodes_result)` | Check node data integrity |
| `validate_elements(elements_result, nodes_result)` | Check element connectivity |
| `validate_stratigraphy(strata_result, nodes_result)` | Check strata consistency |
| `validate_preprocessor(pp)` | Run all validation checks on a preprocessor result |

### IOModelAdapter

`IOModelAdapter` wraps `iwfm_io` reader output to present the same DataFrame API as `IWFMModel`, enabling plot functions to work without the DLL. The easiest way to get one is `open_model()` (above); you can also construct it by hand:

```python
adapter = IOModelAdapter(
    preprocessor=pp,                    # from read_preprocessor()
    heads_hdf="Results/GWHeadAll.hdf",  # optional
    budget_hdfs={"GW": "GW.hdf"},       # optional
    budget_texts={"GW": "GW.bud"},      # optional text-.bud fallback
)
```

`open_model()` discovers text `.bud` budgets automatically (in `Results/` and `Budget/`) for models that ship no budget HDFs — `describe()` marks them `"format": "text"` and `budget_df()` serves them at their native output interval (pass no `interval=`; resample the returned frame instead). When a budget exists in both formats the HDF wins.

```python

adapter.describe()       # JSON-serializable model summary
adapter.n_nodes          # int
adapter.n_elements       # int
adapter.n_layers         # int
adapter.nodes_df()       # GeoDataFrame
adapter.elements_df()    # GeoDataFrame
adapter.stratigraphy_df() # DataFrame
adapter.reaches_df()     # DataFrame
adapter.heads_df(layer=1, begin_date=..., end_date=...)  # DataFrame
adapter.budget_df("GW", location=1)  # DataFrame
```

`heads_df` / `budget_df` / `hydrograph_df` (on both `IOModelAdapter` and the DLL `IWFMModel`) accept **`day_index=True`**: the frame comes back indexed by `iwfm_day` — the day each `24:00` stamp belongs to — so calendar idioms like `resample("YE-SEP")`, `.dt.year`, and `.dt.month` label periods correctly. Default `False` keeps the true end-of-period instants (what DSS/CalSim alignment and exact-timestamp joins need). For water-year budget totals prefer `aggregate_budget`, which also handles the storage stocks.

DLL-free simulation-state equivalents (v1.2+), served from the model's
input and budget-output files:

```python
adapter.tile_drains_df()               # from the GW main's tile drain file
adapter.bypasses_df()                  # from the stream main's bypass specs
adapter.stream_flows_df(stat="mean")   # per-node gain from GW etc. (needs a stream node budget HDF)
adapter.supply_demand_df()             # ag/urban requirement + shortage per subregion (L&WU budget)
adapter.get_land_use_areas(lu_type="AG")             # (n_subregions, n_times)
adapter.get_aquifer_horizontal_k()     # (n_nodes, n_layers); also _vertical_k,
                                       #   _specific_yield, _specific_storage,
                                       #   get_aquitard_vertical_k (NGROUP=0 models)
adapter.get_subregion_ag_pumping_avg_depth_to_gw()   # GSE − head per subregion
adapter.get_zbudget_timeseries("GW", zone_id=1, columns=[0, 1, 2])  # zones = subregions
adapter.wells_df()                     # well specs: id, x, y, radius, perf top/bot, name
adapter.diversions_df()                # id, export node, dest type/id, name,
                                       #   delivery elements (group/subregion/element
                                       #   destinations resolved), recharge elements,
                                       #   and the component column/fraction pairs
                                       #   (max, recoverable/non-recoverable loss,
                                       #   spills where the format has them, delivery)
```

Delivery element groups and recharge zones are parsed on the file
objects too: `DiverSpecsFile.delivery_groups` / `.recharge_zones`,
`WellSpecFile.element_groups`, `ElemPumpFile.element_groups` — each a
list of `{group_id, elements, [fractions]}`.

### Comparing Models

| Function | Description |
|----------|-------------|
| `compare_models(a, b)` | One-call JSON-serializable comparison report: checksum file diff, grid comparison, per-layer head statistics (rmse / max drawdown / where & when), budget availability. Accepts paths or adapters. |
| `diff_model_files(a, b, subdirs=None)` | Checksum (SHA-256) diff of two model folders: `only_in_a` / `only_in_b` / `changed` / `identical`. Parallel hashing; `subdirs=["Preprocessor", "Simulation"]` compares inputs only. |
| `head_difference(a, b, layer)` | Aligned `B − A` head DataFrame (common dates × common nodes) — feed a row to `plot_contour_map` for a difference map |
| `budget_difference(a, b, budget, location)` | Aligned `B − A` budget DataFrame, supports `interval="1MON"/"1YEAR"` |

### Scenario Builder

| Function | Description |
|----------|-------------|
| `create_scenario(base, out_dir, changes=[...])` | Copy a model's inputs (+ `Bin/`) and apply changes; returns the scenario folder ready for `iwfm_io.run_model()`. `link_unchanged=True` hardlinks unchanged inputs instead of copying (copy-on-change; near-zero marginal disk/time for many worker copies of a large model — changed files and run-rewritten types like `.out`/`.bin`/`.bud`/`.dss`/`.hdf` are always real copies; falls back to copying across filesystems) |
| `set_keyed_value(relpath, keyword, value)` | Change factory: edit a `VALUE / KEYWORD` line (e.g. `EDT` end date) preserving layout |
| `replace_text(relpath, old, new, count=-1)` | Change factory: literal text replacement in one file |

### Multi-Run Collection

All four accept `max_workers=N` to read the runs' HDF5 files concurrently (worthwhile on network storage).

| Function | Description |
|----------|-------------|
| `collect_budgets(runs_dict, location)` | Combine budget HDF files from multiple runs into one DataFrame |
| `collect_zbudgets(runs_dict, zone_def, zone)` | Combine zone budgets from multiple runs |
| `collect_hydrographs(runs_dict)` | Combine hydrograph outputs |
| `collect_gwheads(runs_dict, n_nodes, n_layers)` | Combine head outputs |
| `aggregate_budget(df, period="WY")` | Component-aware budget aggregation to water years / calendar years / months: flow components sum, `Beginning Storage` takes the period's first value, `Ending Storage` and `Cumulative …` the last; period membership honors the `24:00` convention. Accepts a wide `budget_df()` frame or the long `collect_budgets` frame |
| `budget_component_agg(name)` | The rule (`"sum"`/`"first"`/`"last"`) `aggregate_budget` applies to a component name |

### GIS Exports (`iwfm_io/gis.py` — core, requires the `[geo]` extra)

Model geometry as geopandas GeoDataFrames and one-call export to GeoPackage or ESRI Shapefiles. Every function takes a *model* — an `IOModelAdapter` or a DLL `IWFMModel` (geometry is built from node coordinates and element configurations, so plain DataFrames suffice). IWFM files carry no CRS; pass `crs="EPSG:xxxx"` when known.

| Function | Description |
|----------|-------------|
| `export_gis(model, path, layers=None, crs=None, node_data=None, element_data=None)` | Write every available layer to a `.gpkg` (multi-layer, replaced if present) or a folder of shapefiles; returns `{layer: rows}`. Default mode skips unavailable/empty layers; an explicit `layers=` list makes failures raise. `node_data`/`element_data` merge extra attributes (keyed `node_id`/`element_id`) onto those layers |
| `IOModelAdapter.to_gis(path, ...)` | Convenience method delegating to `export_gis` |
| `nodes_gdf(model, crs=None, data=None, stratigraphy=True)` | Node points, stratigraphy attributes joined by default |
| `elements_gdf(model, crs=None, data=None)` | Element polygons with subregion id + name |
| `subregions_gdf(model, crs=None)` | Dissolved subregion polygons (`n_elements`, `area`) |
| `streams_gdf(model, crs=None)` | One LineString per reach (via the reaches' GW nodes) |
| `stream_nodes_gdf(model, crs=None)` | Stream-node points at their GW nodes |
| `lakes_gdf(model, crs=None)` | Lake polygons (element polygons merged per lake) |
| `tile_drains_gdf(model, crs=None)` | Tile-drain points |
| `wells_gdf(model, crs=None)` | Well points from the well-spec file (empty for element-only pumping) |
| `GIS_LAYERS` | Tuple of exportable layer names, in export order |

### VTK Exports (`iwfm_io/vtk.py` — core, no VTK library needed)

The model as a 3D layered mesh for ParaView, written as VTK XML with plain numpy. The 2D FE grid is extruded through the stratigraphy (each layer's aquitard sits above its aquifer, so aquitard gaps are preserved); triangles become wedges, quads become hexahedra. Works from `IOModelAdapter` or the DLL `IWFMModel`.

| Function | Description |
|----------|-------------|
| `export_vtk(model, path, point_data=None, cell_data=None, z_scale=1.0, layers=None)` | Write one `.vtu` UnstructuredGrid. Built-in arrays: `node_id` (points), `element_id`/`layer`/`thickness`/`subregion` (cells). `point_data`/`cell_data` add arrays shaped `(n,)` (constant over layers) or `(n, n_layers)` (per layer), in `nodes_df()`/`elements_df()` row order. `z_scale` bakes in vertical exaggeration (regional models want 20–100) |
| `export_vtk_timeseries(model, out_dir, name="heads", begin_date=None, end_date=None, stride=1, z_scale=1.0, layers=None)` | One `.vtu` per (strided) timestep with `head` and `dtw` point arrays + the `.pvd` collection ParaView animates (timestep = days since first frame) |
| `IOModelAdapter.to_vtk(path, ...)` | Convenience method delegating to `export_vtk` |

---

## `iwfm_io.pest` — PEST(++) Calibration Support

Utilities for building and post-processing PEST / PEST++ calibrations of IWFM
models. Pure Python (pandas only); `pyemu` is an optional companion, never a
hard dependency. Lazy subpackage — import as `from iwfm_io.pest import ...`.

### Observation-name codec (`iwfm_io/pest/names.py`)

Structured, round-trip-safe conversion between `(obs_type, location, time)`
and PEST observation names. The default `StandardScheme` writes
`{type}_{location}_{YYYYMMDD}` (lowercase; the date part is omitted for
time-aggregated observations, and locations may themselves contain
underscores — `stf_105_zcs014_13_20001031` round-trips unambiguously).

| Function / class | Purpose |
|---|---|
| `encode_obs_name(obs_type, location, time=None, scheme="standard")` | One name, e.g. `("gwh", "w1234", "2000-10-31")` → `"gwh_w1234_20001031"` |
| `decode_obs_name(name, scheme="standard")` | One name → `ObsName(obs_type, location, time)` |
| `encode_obs_names(obs_types, locations, times=None, ...)` | Vectorized encode (scalars broadcast); returns `Series` |
| `decode_obs_names(names, scheme="standard")` | Vectorized decode; returns `DataFrame(obs_type, location, time)` indexed by name |
| `validate_obs_names(names, max_len=200)` | Case-insensitive uniqueness, length (`20` for classic PEST tools), character-set checks; returns `list[str]` of problems |
| `ObsName` | Frozen dataclass of decoded parts (`time is None` for dateless names) |
| `NameScheme` / `StandardScheme` | Scheme base class / default implementation (`sep`, `date_format` configurable) |
| `register_scheme(name, scheme)` / `get_scheme(name)` | Register project-specific legacy schemes and use them by name everywhere |
| `GroupSequenceScheme` (registered as `"grouped"`) | `{type}{group:02d}{seq:04d}_{date}` names — hydrograph figures sort by location; pairs with `assign_sequences` |

### PESTPP-IES results loader (`iwfm_io/pest/ies.py`)

`load_ies_ensembles(path)` discovers a PESTPP-IES run's output files (from a
`<case>.pst` path, the master directory, or a `<dir>/<case>` prefix) and
returns an `IesResults` handle. All accessors are lazy and cached — ensemble
CSVs for large models can run to hundreds of MB. `.jcb` binaries
(`ies_save_binary`) are read through pyemu when installed (clear error
otherwise); CSV wins when both exist.

| Method / function | Purpose |
|---|---|
| `IesResults.iterations` | Sorted iterations with any ensemble file |
| `.par(iteration=None)` / `.obs(iteration=None)` | Parameter / simulated-observation ensemble, `real_name`-indexed (default: last iteration) |
| `.par_all()` / `.obs_all()` | All iterations concatenated, `(iteration, real_name)` MultiIndex |
| `.phi(kind="composite")` | Tidy phi: `iteration, real_name, phi` (kinds: composite/actual/meas/regul) |
| `.phi_summary(kind)` | Per-iteration total_runs/mean/std/min/max |
| `.phi_groups()` | Tidy per-group phi: `iteration, real_name, group, phi` |
| `.pdc()` / `.obs_plus_noise()` | Prior-data-conflict table / obs+noise realizations (`None` if absent) |
| `.base_rei(iteration=None)` | Base-realization residuals as a DataFrame |
| `.best_realization(iteration=None)` | Minimum-phi realization name |
| `.describe()` | JSON-serializable file inventory + phi summary (agent-friendly) |
| `read_rei(path)` | Standalone PEST `.rei`/`.res` residual-file reader |

### Residual & calibration statistics (`iwfm_io/pest/stats.py`)

Goodness-of-fit metrics on observed/simulated pairs: `n`, `mean_res` (bias),
`med_res`, `mean_abs_res`, `max_abs_res`, `rmse`, `r2`, `nse`, `kge`, plus
`phi` (PEST objective contribution, `Σ(w·res)²`) when weights are supplied.
Convention: `residual = observed − simulated` (PEST's Measured − Modelled).
All computations are vectorized groupby reductions — no per-group Python
loops — so full IES ensembles (10⁵–10⁶ obs × 10² realizations) are practical.

| Function | Purpose |
|---|---|
| `residual_stats(df, by=..., observed=..., simulated=..., weight=None)` | Core engine on a long-form frame; group by any column combination |
| `rei_stats(path_or_df, by="group", weighted_only=False)` | Stats (incl. `phi`) straight from a PEST residual file |
| `ies_stats(results, observed=None, iterations=None, by=None)` | Per-`(iteration, realization, group)` stats for an IES run; `observed` defaults to the obs+noise `base` row; `by` maps obs name → group (pairs naturally with `decode_obs_names`) |
| `METRICS` | List of metric column names |

### SMP bore-sample files (`iwfm_io/pest/smp.py`)

The interchange format of the DWR/IWFM2OBS calibration toolchain
(`site  date  time  value`, whitespace-delimited). Frames use the package's
standard long-form columns `site, datetime, value` (same as
`collect_hydrographs`).

| Function | Purpose |
|---|---|
| `read_smp(path, date_format=None)` | Read to a long-form frame. Auto-detects `dd/mm/yyyy` vs `mm/dd/yyyy` from the data; refuses to guess when ambiguous (pass `date_format` explicitly) |
| `write_smp(df, path, date_format="dd/mm/yyyy", max_site_len=10, sort=True)` | Write atomically; validates site names (10-char classic-PEST limit, no whitespace), drops NaN values with a warning, sorts site-then-time |

### Sim-to-obs matching (`iwfm_io/pest/sim2obs.py`)

Python IWFM2OBS equivalent: pair simulated hydrographs with observed records
by time interpolation. Long-form `site, datetime, value` in (from `read_smp`,
`collect_hydrographs`, or the hydrograph readers), long-form
`site, datetime, observed, simulated` out — ready for `residual_stats` and
`write_smp`.

| Function | Purpose |
|---|---|
| `match_sim_to_obs(sim, obs, method="linear", max_gap=None)` | Interpolate sim to obs timestamps. `linear` never extrapolates; `max_gap` refuses to bridge data gaps (NaN instead); `nearest` also supported. Sites without simulation are dropped with a warning |
| `resample_month_end(df, how="mean", iwfm_convention=True)` | Month-end aggregation honoring IWFM's 24:00 end-of-timestep stamps (a `10/31 24:00` value buckets into October, not November) |

### Budget observations (`iwfm_io/pest/budget_obs.py`)

Named observation tables from IWFM budget output — the water-balance
regularizers of DWR-style calibrations.

| Function | Purpose |
|---|---|
| `budget_observations(source, budget=None, locations=None, components=None, aggregate="none")` | Source: `IOModelAdapter`/model dir (+ `budget="GW"`), a budget `.hdf` path, or a long-form frame (covers z-budgets). `aggregate`: `"none"` (full series), `"mean"` (dateless long-term means — the classic setup), `"annual"` (water-year aggregation named by Sep-30 WY end, 24:00-aware, per-component rules via `budget_component_agg` — flows sum, Beginning Storage takes the WY's first value, Ending Storage/Cumulative the last). Names via the obs-name codec: `bud_{component}_{location}[_{date}]` |
| `slugify_label(label)` | PEST-safe label slugs: `"Region1 (SR1)"` → `region1_sr1` |

### Derived observations (`iwfm_io/pest/derived.py`)

The DWR-proven regularizing observation types, as pure transforms on
long-form `site, datetime, value` frames — apply the same call to observed
and simulated series and the results pair cleanly. Pass `obs_type=` to add
codec-encoded `obsnme` columns. Verified to reproduce a production IES
setup's successive-change observations exactly (106k values, bit-for-bit).

| Function | Purpose |
|---|---|
| `head_changes(df, kind, ...)` | `"successive"` (month-over-month, `max_gap` guard), `"seasonal"` (year-over-year for a chosen month), `"drawdown"` (within-year spring−fall) |
| `vertical_head_difference(df, pairs)` | `shallow − deep` at multi-completion well pairs (positive = downward gradient); pairs as tuples or `{label: (a, b)}` |
| `accretion_depletion(df, pairs)` | `downstream − upstream` gauge flow difference (positive = stream gains) |
| `long_term_stats(df, stat="mean", min_n=1)` | One whole-record statistic per site, dateless names |

### Wells & GWL metadata (`iwfm_io/wells.py` — core)

DataFrame-first replacement for hand-maintained well-configuration files.
The **`gwl_metadata` frame** is a documented schema, not a file format
(`well_id, group, seq, site_code, hydrograph_name, perf_top, perf_bottom,
layer`; extras pass through; persist with plain pandas if desired).

| Function / class | Purpose |
|---|---|
| `validate_gwl_metadata(df)` | Problem-string list (unique well_id, per-group seq uniqueness, perf sanity, no legacy 0/-1 layer codes) |
| `link_hydrographs(gwl_metadata, gw_main, on="site_code", name_sep="%")` | Interpret the `well_identifier%layer` hydrograph-name convention: parse stems, group per-layer rows into wells, join on any metadata column. Cross-checks parsed layer vs the LAYER field; reports unmatched wells / orphan stems / mismatches (`HydrographLink`) |
| `composite_well_hydrographs(link, hyd_output, fractions)` | IWFM's FE-interpolated per-layer hydrograph output × layer fractions (`WellMapping` or frame) → time × well composite heads; resolves `col_N` labels and IWFM 24:00 date stamps |
| `assign_sequences(gwl_metadata, link, order="north_to_south")` | Pure-function seq ledger: fills only missing within-group numbers by spatial order; caller persists the returned frame |
| `enrich_gwl_metadata(model, gwl_metadata, link=None, obs=None)` | Derived columns on demand: subregion, gse, obs-record stats |
| `gwl_metadata_from_legacy(df)` | One-time converter from historical keys frames (maps the -1/0 layer codes onto the schema) |

### Stream gauges (`iwfm_io/gauges.py` — core)

The stream-side counterpart of the GWL suite (no vertical dimension). The
`gauge_metadata` frame: `gauge_id, group, seq, site_code` (+ extras).

| Function / class | Purpose |
|---|---|
| `validate_gauge_metadata(df)` | Schema problem-string list |
| `link_stream_hydrographs(gauge_metadata, stream_main, on="site_code", name_sep=None)` | Join metadata against the NOUTR hydrograph spec names (full-name or stem matching); `GaugeLink` carries hyd_id (spec position = output column), node_id, and the file's IHSQR flag; reports unmatched gauges / orphan names |
| `stream_hydrograph_series(link, hyd_output, quantity=None)` | time × gauge_id series from the hydrograph output (`col_N` + IWFM date handling); IHSQR=2 outputs carry both quantities as two blocks in spec order (flows 1..NOUTR, stages NOUTR+1..2·NOUTR — validated vs a sample-model IHSQR=2 run) — pass `quantity="flow"` or `"stage"` |
| `assign_gauge_sequences(gauge_metadata, link, order="stream_node")` | Fill-only seq ledger; default ordering along the stream-node numbering, spatial orders via metadata x/y |

Gauge pairs feed `accretion_depletion`; series feed `match_sim_to_obs` and
`residual_stats`; the `"grouped"` naming scheme applies unchanged.

### HEC-DSS + CalSim channel flows (`iwfm_io/dss.py` — core, optional `[dss]` extra)

Reads value data out of HEC-DSS files (`pip install iwfm-io[dss]`;
pydsstools ≥ 3, imported lazily at call time, reads DSS-6 and DSS-7).
CalSim prints streamflows as monthly `PER-AVER` CFS records in the DV
`.dss` file, one per channel arc (B part, e.g. `C_SAC041`); DSS
end-of-period stamps read back as next-day midnight — the same convention
as IWFM's `24:00`, so CalSim and IWFM series align without shifting.

| Function / class | Purpose |
|---|---|
| `dss_catalog(dss_file, pattern="")` | DataFrame of record pathnames split into parts `a`–`f` + the `condensed` (D-blanked) record identity |
| `read_dss_timeseries(dss_file, paths)` | Wide time × pathname frame (condensed paths read whole records across blocks); NaN for missing; record units/type in `df.attrs` |
| `cfs_to_taf(frame)` | Period-average CFS → TAF/month using each stamp's period day count (pure function) |
| `link_calsim_channels(gauge_metadata, dss, on="calsim_bpart", cpart=, epart=, fpart=, arc_prefix="C_")` | Case-insensitive B-part match of metadata against the catalog (a catalog frame also accepted); per-row `dss_path` override; `CalSimLink` reports unmatched gauges / orphan arcs; C/E/F-part filters resolve multi-scenario ambiguity |
| `calsim_streamflow_series(link, dss_file, units="cfs")` | time × gauge_id channel flows; `units="taf"` converts (guards that records are CFS) |

Downstream unchanged: `match_sim_to_obs`, `residual_stats`,
`accretion_depletion` for arc pairs, `"grouped"` naming.

### Multi-layer well observations (`iwfm_io/wells.py`, re-exported by `iwfm_io.pest`)

Map real observation wells onto the FE mesh and composite simulated heads
across layers by transmissivity. Two-phase: an expensive build step
producing a persistable weight table, and a one-matrix-multiply composite
for the forward-run loop. Verified to reproduce a production C2VSimCG
workflow's layer fractions exactly (2,148 wells, bit-for-bit, identical
node assignments).

| Function / class | Purpose |
|---|---|
| `build_well_mapping(model, wells, kh=None, spatial="nearest", k=4, default_layer=1)` | Wells need `well_id, x, y` (+ optional `layer` override, `perf_top/perf_bottom` depths). Perforation ∩ stratigraphy × Kh → layer fractions; falls back deepest-layer/layer-1 for non-intersecting intervals (logged). `spatial="idw"` spreads over the k nearest nodes. No kh → thickness weighting. Pure numpy (no scipy) |
| `WellMapping` | `.wells` (well → node, method), `.weights` (`well_id, node, layer, weight`), `.composite(heads)` (heads as `{layer: frame}`, `node_<n>_layer_<l>` frame, `(node, layer)` MultiIndex frame, or a model with `heads_df`) → time × well frame; `.to_csv()/.from_csv()` persistence (the `fracs.csv` role) |
| `select_best_layers(mapping, heads, obs, min_n=6, default_layer=1)` | Resolve unknown completions: per-layer RMSE against the observed record → `well_id → layer`; feed back into the wells frame and rebuild |

### Paired output/instruction writers (`iwfm_io/pest/obsfiles.py`)

One `ObsFileSpec` (an ordered list of observation names + layout) writes both
the forward-run output file (`write_output`, fixed-column `.pout` style or
`name,value` CSV) and its matching PEST instruction file (`write_ins`) — so
name/column/order consistency holds by construction. `read_output` parses
with the same semantics; `verify_round_trip()` asserts write→parse fidelity
(catching too-narrow formats); `from_frame`/`obs_data` bridge to the
observation tables the other pest modules produce.

### Run orchestration (`iwfm_io/pest/orchestrate.py`)

| Function | Purpose |
|---|---|
| `setup_agents(template, n, dest_root=None, host=..., port=4004, link=True)` | Stamp out N agent dirs by hardlinking the whole template (root files included, `Results/` recreated empty, output suffixes real-copied); writes per-agent start scripts |
| `write_manager_script(dir, port=4004)` | Matching manager starter |
| `write_forward_run(path, steps)` | Generate the fail-fast `forward_run.py`: ordered shell steps, first nonzero exit aborts with that code so PEST++ drops the run |
| `parrep_v2(pst_path, values, noptmax=0)` | pyemu-free parrep for PEST++ v2 control files: rewrite the external parameter-data CSV(s) from a Series and set `noptmax` |
| `run_finals(results, template, dest, iteration=None, realization="base")` | Stage a verification rerun of one ensemble realization in a fresh hardlinked copy |

### Parameter write-back (`iwfm_io/pest/apply.py`)

The multiplier apply step of the forward run: PEST writes small value CSVs
(through trivial templates), `apply_parameters` merges them onto the base
parameter tables and regenerates the model input through the round-trip
writers — no template markers in fixed-format IWFM files.

| Function / class | Purpose |
|---|---|
| `ApplyAction(reader, path, table, column, values_file, key_cols, op, lower, upper, base_dir)` | One declarative write-back: `reader` ∈ gw_main/stream_main/subsidence; `table` reaches nested tables via dotted paths (`"parametric_grids.0.params"` for NGROUP>0 GW mains); `op` ∈ multiply/replace/add; bounds clip with a logged count; value rows matching no table row are an error; `base_dir` (the simulation working dir, relative to the run dir) makes the writer re-relativise referenced file paths so repeated rewrites stay valid |
| `apply_parameters(run_dir, actions, log_path=...)` | Apply all actions (targets read once), rewrite atomically, and write the bookkeeping CSV (the `mult2model_info` role) |
| `write_gw_overwrite(path, df, factors=None, time_unit="1MON")` / `read_gw_overwrite(path)` | IWFM's native GW parameter overwrite file (`node layer PKH PS PN PV PL SCE SCI`, `-1` = keep) |

### Zone/group parameterization (`iwfm_io/pest/params.py`)

`ParamSpec` declares one parameterized quantity (base name, the value CSV the
apply step consumes, key rows, optional zone column, transform/bounds, tie
chains); `build_parameters(specs)` emits a `ParamBundle`: `ptf ~` template
files + initial value files (forward run works before PEST writes anything) +
PEST++ v2 `par_data`/`pargp_data` tables with `tied` chains. `bundle.write(dir)`
persists; `bundle.verify()` fills each template with `parval1` and asserts it
reproduces the value file — run automatically at build.

### Pilot points (`iwfm_io/pest/pilot_points.py`)

Pure-numpy ordinary kriging on the FE mesh (no scipy/pyemu):
`ExpVariogram`/`SphVariogram`/`GauVariogram` (range, nugget, geometric
anisotropy + bearing); `place_pilot_points_grid(model, spacing, zones=...)`
lays out points clipped to the node cloud; `compute_kriging_factors(pps,
nodes, variogram, max_points=12, search_radius=..., same_zone_only=...)`
solves the OK systems once (weights per target sum to 1; exact at pilot
locations) and persists as a plain CSV; `apply_kriging_factors(factors,
pp_values, log=True)` is the cheap FAC2REAL step for the forward run
(log-space kriging for conductivities). C2VSimCG-scale: 73 points → 1,393
nodes in 0.4 s.

### Constrained reparameterization + Texture2Par (`iwfm_io/pest/reparam.py`)

`RatioChain`: declare free parameters (bounds/transform) and derived
quantities as expressions (`kmin_coarse = kxc * 10**(-pa*dt)`);
`assert_ordering([...])` checks physical orderings at every bound corner —
for the monotone chains this pattern uses, a pass guarantees no ensemble
draw can be invalid. `evaluate()` is the forward-run step; `par_data()`
emits the v2 parameter rows. `read_t2p_pilot_points`/`write_t2p_pilot_points`
handle Texture2Par `BEGIN PP_LOCS` files (`.ppaq`/`.ppaqt`).

### PestSetup — the integration builder (`iwfm_io/pest/setup.py`)

Accumulate `add_parameters(bundle, actions)` (from `build_parameters` +
`ApplyAction`), `add_observations(obs_data, spec, output_file)` (paired
`ObsFileSpec`), and `add_run_step(label, cmd)` — then `write(dest)` emits a
complete runnable template: `{case}.pst` (v2), external
par/pargp/obs CSVs, all templates + initial value files + instruction
files, and the fail-fast `forward_run.py` whose first step applies PEST's
value files onto the model inputs. Duplicate names, spec/obs mismatches and
empty setups are hard errors. Verified end-to-end against the real
pestpp-ies executable (base run of a toy problem; residuals load back
through `load_ies_ensembles`/`rei_stats`).

### One-call quickstart (`iwfm_io/pest/quickstart.py`)

`pest_setup_from_model(model_dir, obs, dest_dir, ...)` builds a runnable
pestpp-ies template directly from a model folder plus observed heads
(long-form frame, SMP, or CSV — site names matched to GW hydrograph
names/ids case-insensitively). It composes the verified pieces: multiplier
parameters for the requested properties (`kh, ss, sy, kv, aquitard_kv`
from the GW main's table — NGROUP=0 or a single parametric grid — plus
`strk` stream conductance), zoned `subregion` × layer / `layer` /
`global`; observations paired against the model's own hydrograph output
via `match_sim_to_obs` (unmatched/unpairable rows reported in
`.dropped`); a model copy under `template/model/` (hardlinked); and a
generated forward run — apply → `run_model` → re-extract at the
observation timestamps (`run_forward`/`run_extract`, driven by
`_quickstart.json` + `_obs_index.csv`). Returns `QuickstartSetup`
(`template, paired, par_data, obs_data, dropped, stats, summary()`).
Key options: `parameters`, `zones`, `bounds`, `max_gap`, `weight`,
`noptmax` (default 0 — first run is a cheap check), `ies_num_reals`,
`pestpp_options`, `run_steps`. Exe-verified on the sample model: the
generated forward run reproduces baseline heads at every observation
through the real IWFM executables.

### Phi-budget weight balancing (`iwfm_io/pest/weights.py`)

Rescales observation weights so each observation *category* contributes a
chosen target to the objective function (weights × `√(target/current phi)`
per group). Works pyemu-free on the PEST++ v2 external observation-data
layout (`obsnme, weight, obgnme` DataFrame/CSV) with residuals from any
source (`.rei` path, `read_rei` frame, `IesResults.base_rei()`, or Series).
Per-observation 1/σ weighting composes: set `weight = 1/σ` first, then
balance — the group-uniform rescale preserves relative weighting.

| Function / class | Purpose |
|---|---|
| `balance_weights(obs_data, residuals, budgets, split="even", min_weight=None, max_weight=None)` | Core rescale. `budgets` = `{pattern: target_phi}`, patterns match groups by exact name / regex / prefix; a pattern's budget splits evenly or proportional-to-phi among its groups. Overlaps and no-match patterns raise |
| `WeightBalance` | Result: `.obs_data` (rescaled weights) + `.report` (per group: phi before/after, target, factor, shares) |
| `balance_pst_weights(pst_path, budgets, residuals=None)` | Classic inline `.pst` adapter via pyemu (optional dependency) |

### IES diagnostics (`iwfm_io/pest/diagnostics.py`)

`diagnose_ies(results, par_data=None, ...)` distills a PESTPP-IES run into a
few-KB JSON-serializable state + boolean signals + a text summary — small
enough to hand to a person or an LLM without exposing the raw ensembles.
Every section is fault-tolerant (missing inputs become notes, not errors).

| Section | Metrics / signals |
|---|---|
| `phi` | Per-iteration mean/min/max/std, total & last-step reduction, std collapse ratio → `phi_stalled`, `ensemble_collapsed` |
| `prior_data_conflict` | Conflict count/rate by category → `conflict_systemic` |
| `bound_railing` | % of (parameter × realization) values at bounds per group, log-aware, over the whole last ensemble (needs `par_data` with bounds) → `railing_present` |
| `residuals` | Per-group bias, abs-mean, time trend (dates via the obs-name codec) + flagged groups |
| `outliers` | Weighted obs with \|residual\| over threshold, top-N table |
| `objective_balance` | Last-iteration phi share by category → `objective_imbalance`, `dominant_category` |

`DiagThresholds` holds all signal cut-offs; `IesDiagnostics` exposes
`.state`, `.signals`, `.summary()`, `.to_json(path)`.

### Calibration figures (`iwfm_io/plots/calibration.py`)

Eight matplotlib functions for reviewing ensemble calibrations — phi
convergence/by-group, residual butterfly, obs-vs-sim 1:1, prior-vs-posterior
histograms, bound railing, ensemble hydrographs, and residual maps. See the
Calibration section of [plotting.md](plotting.md) for the full table; all
follow the package plotting interface (`ax`/`figsize`/`save_path`/`dpi`,
return `(fig, ax)`).

---

## `iwfm-io` — Command Line

Installed as a console script (`iwfm_io/cli.py`); every command is a thin
wrapper over the public API, so anything the CLI does can be scripted with
the same names. `--traceback` shows full stack traces.

| Command | Purpose |
|---|---|
| `iwfm-io describe <model_dir>` | `open_model(...).describe()` as JSON |
| `iwfm-io pest setup --model-dir M --obs obs.smp --dest T [--parameters kh ss sy strk] [--zones subregion\|layer\|global] [--reals N] [--noptmax N] [--max-gap 45D] [--date-format ...]` | `pest_setup_from_model` → runnable pestpp-ies template |
| `iwfm-io pest agents --template T -n 8 [--port 4004] [--exe pestpp-ies]` | `setup_agents` + `write_manager_script` (start manually) |
| `iwfm-io pest run --template T [-n 8] [--exe pestpp-ies] [--port 4004]` | Run PEST++: serial, or launch the manager plus N local hardlinked agents and wait |
| `iwfm-io pest analyze <master_dir or .pst> [--json out.json] [--par-data csv]` | `load_ies_ensembles` + `diagnose_ies` summary (auto-discovers `*_par_data.csv` for railing checks) |

---

## `iwfm_io.plots` — Visualization Library

See [Plot Gallery](plotting.md) for the full list of 58 functions across 13 modules.
