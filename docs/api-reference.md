# API Reference

## `iwfm` — DLL Wrapper (Windows x64)

### Classes

| Class | Module | Description |
|-------|--------|-------------|
| `IWFMModel` | `iwfm.model` | Main model interface. Context manager. Wraps grid, GW, streams, budgets, diversions, wells, lakes, simulation control. `describe()` returns a JSON-serializable model summary. |
| `IWFMBudget` | `iwfm.budget` | Standalone budget HDF5 reader via `IW_Budget_*` functions. |
| `IWFMZBudget` | `iwfm.zbudget` | Standalone zone-budget reader via `IW_ZBudget_*` functions. |
| `IWFMError` | `iwfm._errors` | Exception raised when a DLL call returns a non-zero status code. |

### Running Models

| Function | Description |
|----------|-------------|
| `run_model(model_dir, steps=(...))` | Run the IWFM toolchain (default: preprocessor + simulation; add `"budget"`, `"zbudget"`). Executables resolved from `<model_dir>/Bin` or `IWFM_BIN_DIR`. Raises on failure (`check=False` to inspect instead). |
| `run_preprocessor / run_simulation / run_budget / run_zbudget(model_dir)` | Run one tool. Returns a `RunResult` (`success`, `elapsed`, `errors`, `returncode`). Failure = nonzero exit **or** FATAL/ERROR lines in console output or the tool's Messages file. |

### Module-Level Functions

| Function | Description |
|----------|-------------|
| `load_dll(dll_path=None, version=None)` | Load the IWFM DLL. Returns a `ctypes.WinDLL` handle. |
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

## `iwfm.io` — Pure-Python File I/O

### Opening a Model

| Function | Description |
|----------|-------------|
| `open_model(path)` | Open a model from its root folder (or a main-file path). Discovers the preprocessor/simulation main files and all HDF5 results; returns a ready `IOModelAdapter`. Accepts `preprocessor=`, `simulation=`, `results_dir=` overrides. |

```python
from iwfm.io import open_model

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
| `read_gw_main(path)` | `GW_MAIN.dat` |
| `read_bc_main(path)` | `BC_MAIN.dat` |
| `read_spec_head_bc(path)` | `SpecHeadBC.dat` |
| `read_boundary_ts(path)` | `BoundTSD.dat` |
| `read_pump_main(path)` | `Pump_MAIN.dat` |
| `read_elem_pump(path)` | `ElemPump.dat` |
| `read_ts_pumping(path)` | `TSPumping.dat` |
| `read_tile_drain(path)` | `TileDrain.dat` |
| `read_subsidence(path)` | `Subsidence.dat` |

### Stream Readers

| Function | Input file |
|----------|-----------|
| `read_stream_main(path)` | `Stream_MAIN.dat` |
| `read_stream_inflow(path)` | `StreamInflow.dat` |
| `read_diver_specs(path)` | `DiverSpecs.dat` |
| `read_bypass_specs(path)` | `BypassSpecs.dat` |
| `read_diversions(path)` | `Diversions.dat` |

### Other Input Readers

| Function | Input file |
|----------|-----------|
| `read_lake_main(path)` | `Lake_MAIN.dat` |
| `read_rootzone_main(path)` | `RootZone_MAIN.dat` |
| `read_swshed(path)` | `SWShed.dat` |
| `read_unsatzone(path)` | `UnsatZone.dat` |

### HDF5 Output Readers

| Function | Description |
|----------|-------------|
| `read_budget_hdf(path)` | Budget HDF5 → dict with `locations` list and `data` dict of DataFrames |
| `read_head_hdf(path, n_nodes, n_layers)` | GWHeadAll.hdf → DataFrame |
| `read_hydrograph_hdf(path)` | Hydrograph HDF5 → DataFrame |
| `read_zone_def(path)` | Zone definition file → zone mapping |
| `read_zbudget_hdf(path)` | Zone budget HDF5 → dict |

### Text Output Readers

| Function | Description |
|----------|-------------|
| `read_hydrograph_out(path)` | `GWHyd.out` or `StrmHyd.out` → DataFrame |
| `read_hydrograph_out_with_metadata(path)` | Same, plus parsed metadata |
| `read_head_all_out(path)` | `GWHeadAll.out` → DataFrame |
| `read_final_state_out(path)` | `FinalGWHeads.out`, etc. → DataFrame |
| `read_flow_out(path)` | `FaceFlow.out`, `BoundaryFlow.out` → DataFrame |
| `read_velocity_out(path)` | `GWVelocities.out` → DataFrame |
| `read_budget_text(path)` | `GW.bud`, `Strm.bud` text budgets → DataFrame |

### Writers

Every reader has a corresponding writer with the same name pattern (`read_*` → `write_*`). Writers accept the same result object returned by the reader:

```python
from iwfm.io import read_nodes, write_nodes

result = read_nodes("NodeXY.dat")
result.data["x"] += 100  # modify
write_nodes(result, "NodeXY_shifted.dat")
```

Full list: `write_preprocessor`, `write_nodes`, `write_elements`, `write_strata`, `write_stream_geom`, `write_lake_geom`, `write_simulation`, `write_precip`, `write_et`, `write_irigfrac`, `write_supply_adjust`, `write_gw_main`, `write_bc_main`, `write_spec_head_bc`, `write_boundary_ts`, `write_pump_main`, `write_elem_pump`, `write_ts_pumping`, `write_tile_drain`, `write_subsidence_file`, `write_stream_main`, `write_stream_inflow`, `write_diver_specs`, `write_bypass_specs`, `write_diversions`, `write_lake_main`, `write_rootzone_main`, `write_swshed`, `write_unsatzone`.

### Validation

| Function | Description |
|----------|-------------|
| `validate_nodes(nodes_result)` | Check node data integrity |
| `validate_elements(elements_result, nodes_result)` | Check element connectivity |
| `validate_stratigraphy(strata_result, nodes_result)` | Check strata consistency |
| `validate_preprocessor(pp)` | Run all validation checks on a preprocessor result |

### IOModelAdapter

`IOModelAdapter` wraps `iwfm.io` reader output to present the same DataFrame API as `IWFMModel`, enabling plot functions to work without the DLL. The easiest way to get one is `open_model()` (above); you can also construct it by hand:

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
                                       #   destinations resolved), recharge elements
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
| `create_scenario(base, out_dir, changes=[...])` | Copy a model's inputs (+ `Bin/`) and apply changes; returns the scenario folder ready for `iwfm.run_model()` |
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

## `iwfm.plots` — Visualization Library

See [Plot Gallery](plotting.md) for the full list of 58 functions across 13 modules.
