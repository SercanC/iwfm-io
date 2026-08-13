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
| `parse_iwfm_date(s)` | Parse `"MM/DD/YYYY_HH:MM"` → `datetime`. Handles `24:00`. |
| `format_iwfm_date(dt)` | Format `datetime` → `"MM/DD/YYYY_HH:MM"`. |

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

Component-main writers (`write_gw_main`, `write_subsidence_file`, `write_stream_main`, `write_rootzone_main`) accept `base_dir` — pass the simulation working directory (the folder of the simulation main file) so referenced paths are written relative to it; IWFM does not accept absolute paths.

Full list: `write_preprocessor`, `write_nodes`, `write_elements`, `write_strata`, `write_stream_geom`, `write_lake_geom`, `write_simulation`, `write_precip`, `write_et`, `write_irigfrac`, `write_supply_adjust`, `write_gw_main`, `write_bc_main`, `write_spec_head_bc`, `write_boundary_ts`, `write_pump_main`, `write_well_spec`, `write_elem_pump`, `write_ts_pumping`, `write_tile_drain`, `write_subsidence_file`, `write_stream_main`, `write_stream_inflow`, `write_diver_specs`, `write_bypass_specs`, `write_diversions`, `write_lake_main`, `write_rootzone_main`, `write_swshed`, `write_unsatzone`.

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
)

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
| `budget_observations(source, budget=None, locations=None, components=None, aggregate="none")` | Source: `IOModelAdapter`/model dir (+ `budget="GW"`), a budget `.hdf` path, or a long-form frame (covers z-budgets). `aggregate`: `"none"` (full series), `"mean"` (dateless long-term means — the classic setup), `"annual"` (water-year sums named by Sep-30 WY end, 24:00-aware). Names via the obs-name codec: `bud_{component}_{location}[_{date}]` |
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

### Multi-layer well observations (`iwfm_io/pest/wells.py`)

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

## `iwfm_io.plots` — Visualization Library

See [Plot Gallery](plotting.md) for the full list of 58 functions across 13 modules.
