# iwfm-io

Python file I/O, DLL wrapper, and visualization library for the Integrated Water Flow Model (IWFM).

**[📓 Tutorial notebooks](https://github.com/SercanC/iwfm-io/blob/main/notebooks/README.md)** — twelve executed Jupyter notebooks covering every feature area, from reading files to PEST++ calibration, CalSim/HEC-DSS integration, and GIS/VTK exports.

**[📊 Example plot gallery](https://github.com/SercanC/iwfm-io/blob/main/docs/GALLERY.md)** — all plot functions rendered from DWR's C2VSimFG v1.5 Central Valley model.

**[⚖️ How does this compare to PyWFM and cfbrush/iwfm?](https://github.com/SercanC/iwfm-io/blob/main/docs/COMPARISON.md)** — a factual feature comparison of the IWFM Python packages.

## Features

- **`iwfm_io`** — Pure-Python file I/O (no DLL, cross-platform):
  - Read and write all IWFM text input files (preprocessor, simulation, groundwater, stream, lake, root zone, time series)
  - Read IWFM HDF5 output files (budgets, heads, hydrographs, zone budgets)
  - Read IWFM text output files (hydrographs, final states, flow files, budget text)
  - `IOModelAdapter` presents the same DataFrame API as the DLL wrapper, so plot functions work without the DLL
  - **Model comparison**: `compare_models()` reports what changed between two model versions (checksum file diff + grid + head/budget statistics); `head_difference()`/`budget_difference()` return aligned `B − A` DataFrames
  - **Scenario builder**: `create_scenario()` copies a model and applies input changes (`set_keyed_value`, `replace_text`, or your own functions)
- **Run models from Python** (Windows): `iwfm_io.run_model()` drives the PreProcessor → Simulation → Budget → ZBudget executables with error detection — the full loop is `create_scenario()` → `run_model()` → `compare_models()`
- **`iwfm_io.pest`** — PEST(++) calibration support (pure Python; `pyemu` optional via `iwfm-io[pest]`):
  - **One-call quickstart**: `pest_setup_from_model(model_dir, obs, dest)` goes from a model folder + observed heads straight to a runnable pestpp-ies template — also available from the command line as `iwfm-io pest setup / agents / run / analyze` (plus `iwfm-io describe`)
  - Observation-name codec, PESTPP-IES ensemble loader + diagnostics, residual/calibration statistics (bias, RMSE, R², NSE, KGE, phi) at ensemble scale
  - SMP file I/O, sim-to-obs time matching (IWFM2OBS equivalent), budget-component and derived observations (head changes, vertical gradients, gauge accretion–depletion)
  - Multi-layer transmissivity-weighted well observations, paired output/instruction-file writers, worker orchestration, parameter write-back
  - Zone/group and pilot-point parameterization on the FE mesh, constrained reparameterization with Texture2Par hooks, and a `PestSetup` builder that assembles the whole PEST interface
  - DataFrame-first **well** (`gwl_metadata`) and **stream-gauge** (`gauge_metadata`) metadata suites: link metadata to IWFM hydrograph outputs by name, composite per-layer heads, extract per-gauge flow/stage series — no hand-maintained configuration files
- **HEC-DSS + CalSim** (`iwfm-io[dss]`, cross-platform via `pydsstools`): catalog and read DSS-6/DSS-7 time series, link gauges to CalSim channel arcs, and extract monthly channel flows (CFS or TAF) whose timestamps align with IWFM's `24:00` convention out of the box
- **GIS exports** (`iwfm-io[geo]`): `export_gis(model, "model.gpkg")` / `model.to_gis(...)` write the grid (nodes with stratigraphy, element polygons), dissolved subregions, stream network, lakes, tile drains, and wells to a GeoPackage or shapefiles — with optional per-node/per-element attribute joins (heads, depth to water, land use, …) and a user-supplied CRS; per-layer `*_gdf()` builders return GeoDataFrames for use in Python
- **VTK exports** (no VTK library needed — pure numpy): `export_vtk(model, "model.vtu")` / `model.to_vtk(...)` extrude the FE grid through the stratigraphy into a 3D layered mesh (wedges/hexahedra, aquitard gaps preserved) for ParaView, with vertical exaggeration and per-node/per-element data arrays; `export_vtk_timeseries()` writes a `.pvd` animation of simulated heads and depth to water
- **Python ctypes wrapper** for IWFM DLL — Windows x64 only (8 modules)
- **66 plotting functions** across 15 modules — matplotlib PNGs by default, and key plots (Sankey, budget time series/pie/bars, hydrographs, butterfly) accept `engine="plotly"` for interactive HTML with hover, zoom, and range sliders (`pip install iwfm-io[viz]`):
  - **Maps** (11 functions) — Grid, heads, streams, wells, lakes, tile drains
  - **Profiles** (2 functions) — Cross-sections, longitudinal profiles
  - **Time Series** (7 functions) — Hydrographs, budgets, land use
  - **Trends** (4 functions) — Long-term trends, seasonal patterns, drought analysis
  - **Seasonal** (4 functions) — Ridgelines, heatmaps, polar plots
  - **Spatial Patterns** (3 functions) — Sparklines, small multiples, scatter plots
  - **Summary** (7 functions) — Rating curves, histograms, pie charts, water balance
  - **Water Balance** (5 functions) — Sankey diagrams, butterfly charts, cumulative departure
  - **Animations** (3 functions) — GIF animations of heads, flows, depth to water
  - **Subsidence** (2 functions) — Subsidence bowls and correlations
  - **Supply/Demand** (4 functions) — Gap analysis, shortage plots
  - **Cross Sections** (2 functions) — Multi-layer panels, animations
  - **Connectivity** (2 functions) — Diversion networks, bypass diagrams
- Built on **matplotlib**, **numpy**, **pandas**, **geopandas**, **h5py**

## Installation

### Prerequisites
- Python 3.9 or higher
- For `iwfm_io` and plotting: any OS (plots work DLL-free via `IOModelAdapter`)
- For the DLL wrapper: Windows 10+ x64 and a copy of `IWFM_C_x64.dll`. One line fetches an official build (GPLv2, published with its corresponding source on this project's GitHub releases):

  ```python
  import iwfm_io
  iwfm_io.dll.download_dll("2025.0.1747")   # → ~/.iwfm/dlls/2025.0.1747/IWFM_C_x64.dll
  ```

  Published builds (sha256-verified): `2025.0.1747`, `2025.0.1688`, `2024.2.1594` (C2VSimFG v1.5), `2015.3.1443`, `2015.1.1273`, `2015.0.1403` — all official DWR builds from the [CNRA Open Data release archive](https://data.cnra.ca.gov/dataset/iwfm-integrated-water-flow-model). The DLL is version-sensitive: match it to your model's IWFM version. Other builds ship with IWFM from the [DWR IWFM site](https://water.ca.gov/Library/Modeling-and-Analysis/Modeling-Platforms/Integrated-Water-Flow-Model) — place them in `dlls/<version>/` or `~/.iwfm/dlls/<version>/` and select with `load_dll(version=...)` / `IWFMModel(..., dll_version=...)`.

### Install

```bash
pip install iwfm-io          # core: file I/O, DLL wrapper, plotting, pest
pip install iwfm-io[geo]     # + geopandas/shapely for GeoDataFrame output
pip install iwfm-io[viz]     # + plotly/kaleido for interactive Sankey diagrams
pip install iwfm-io[dss]     # + pydsstools for HEC-DSS / CalSim reading
pip install iwfm-io[pest]    # + pyemu (only needed for .jcb IES binaries)
```

Without the `geo` extra, spatial tables are returned as plain pandas
DataFrames instead of GeoDataFrames — everything else works the same.

### Install from Source (Development Mode)
```bash
cd iwfm-io
pip install -e .
```

## Quick Start

### Open a Model (no DLL required)

Point `open_model` at the model folder — the main input files and all
HDF5 results are found automatically:

```python
from iwfm_io import open_model

model = open_model(".assets/sample_model")

print(model.describe())            # what does this model contain?
model.validate_references()        # cross-file pointer checks (empty = clean)
model.nodes_df()                   # grid nodes (GeoDataFrame)
model.heads_df(layer=1)            # simulated heads, one column per node
model.budget_df("GW", location=1)  # groundwater budget time series

from iwfm_io.plots import maps
fig, ax = maps.plot_gw_head_contour(model, layer=1)
```

Readers are strict: a truncated or malformed input file raises
`IWFMParseError` naming the file, section and line. Pass
`open_model(path, strict=False)` (or wrap calls in
`iwfm_io.strict_mode(False)`) to keep whatever parsed, with warnings.

### Read Individual Files

```python
from iwfm_io import read_preprocessor, read_simulation

pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")
pp.nodes           # GeoDataFrame: node_id, x, y, geometry
pp.elements        # GeoDataFrame: element_id, node1-4, subregion, geometry
pp.stratigraphy    # DataFrame: elevation, layer thicknesses

sim = read_simulation(".assets/sample_model/Simulation/Simulation_MAIN.IN")
print(f"{len(pp.nodes)} nodes, sim runs {sim.sim_begin} → {sim.sim_end}")

# Or any file directly, without going through the main file
from iwfm_io import read_budget_hdf, read_head_hdf

gw_bud  = read_budget_hdf(".assets/sample_model/Results/GW.hdf")
head_df = read_head_hdf(".assets/sample_model/Results/GWHeadAll.hdf", n_nodes=441, n_layers=2)
```

See `examples/01_read_inputs.py` for a complete walkthrough of all input file readers, and `docs/agents.md` for compact recipes aimed at scripts and AI agents.

### Using the DLL Wrapper (Windows only)
```python
import iwfm_io

with iwfm_io.dll.IWFMModel(
    preprocessor_file=".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN",
    simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
    is_for_inquiry=True,
) as model:
    x, y = model.get_node_coordinates()
    print(f"{model.n_nodes} nodes, {model.n_elements} elements")
```

### Run a Scenario (Windows)
```python
from iwfm_io import run_model
from iwfm_io import create_scenario, set_keyed_value, compare_models

scenario = create_scenario(
    "runs/baseline", "runs/short_run",
    changes=[set_keyed_value("Simulation/Simulation_MAIN.IN",
                             "EDT", "09/30/1995_24:00")],
)
run_model(scenario, steps=("preprocessor", "simulation", "budget"))
report = compare_models("runs/baseline", scenario)
```

### Creating Plots
```python
from iwfm_io.plots import maps, timeseries

# Works with IWFMModel or IOModelAdapter
maps.plot_stream_network(model_or_adapter)
timeseries.plot_gw_head_hydrographs(
    model_or_adapter, node_indices=[1, 50, 100], layer=1,
    begin_date="10/01/1990_24:00", end_date="09/30/2000_24:00",
)
```

## Examples

**Prefer notebooks?** The [`notebooks/`](notebooks/README.md) folder holds twelve fully-executed Jupyter notebooks covering the same ground with narrative and rendered output — quickstart, every reader/writer, the DLL wrapper, scenario runs, plotting, the complete PEST++/CalSim calibration workflow, and GIS/VTK exports.

| File | Requires | Description |
|------|----------|-------------|
| `examples/01_read_inputs.py` | .assets/sample_model | Reading all IWFM input files via `iwfm_io` |
| `examples/02_read_outputs.py` | .assets/sample_model/Results | Reading HDF5 and text output files |
| `examples/03_roundtrip.py` | .assets/sample_model | Read → modify → write input files |
| `examples/04_dll_wrapper.py` | Windows + DLL | `IWFMModel`, `IWFMBudget`, `IWFMZBudget` |
| `examples/05_plotting.py` | .assets/sample_model | Plotting gallery — all 13 modules |
| `examples/06_multi_run_budgets.py` | .assets/sample_model/Results | Multi-run unified budget DataFrame |
| `examples/07_compare_models.py` | .assets/sample_model | File diff + comparison report between model versions |
| `examples/08_run_scenario.py` | Windows + sample_model/Bin | Full loop: create scenario → run IWFM → compare |
| `examples/09_full_input_datasets.py` | .assets/sample_model | Every input dataset as a DataFrame; edit + write back |
| `examples/10_pest_calibration.py` | .assets/sample_model/Results | One-call PEST++ setup (`pest_setup_from_model`) + extract-step demo |
| `examples/11_relationships.py` | .assets/sample_model | Cross-file relationships: `series()` resolution, `column_usage()` reverse lookup, `validate_references()`, and the convenience accessors |
| `examples/test_plots_dllfree.py` | .assets/sample_model (any OS) | The nine formerly DLL-only plots via `IOModelAdapter` |

## Claude Code Skill (analyze models by chatting)

`skills/iwfm-analyst/` is a [Claude Code](https://claude.com/claude-code)
skill that lets non-programmers analyze IWFM models conversationally —
"show me the groundwater budget for subregion 5", "map depth to water",
"compare these two runs" — with Claude doing the `iwfm-io` work and
returning tables and plot images. Install by copying it into your
personal skills folder:

```powershell
# Windows
Copy-Item skills\iwfm-analyst "$env:USERPROFILE\.claude\skills\" -Recurse
```
```bash
# macOS / Linux
cp -r skills/iwfm-analyst ~/.claude/skills/
```

Then start Claude Code anywhere and ask about your model (have
`pip install iwfm-io` available, or let Claude install it).

## Testing

```bash
# Pure-Python I/O test suite (pytest, no DLL required)
pytest tests/

# Full 58-function plot test suite (requires DLL + .assets/sample_model/)
python examples/test_plots.py
# Output goes to test_output/
```

See `docs/TEST_PLOTS_RESULTS.md` for detailed plot-test results: 48 of the 58 DLL plot tests pass in inquiry mode (all failures are DLL/inquiry-mode limitations, not wrapper bugs), and every failing function also renders DLL-free through `IOModelAdapter` — run `python examples/test_plots_dllfree.py` to verify.

## Project Structure

```
iwfm-io/
├── iwfm_io/                     # Python package (pure-Python I/O at top level)
│   ├── _tokens.py               # Date/line parsing primitives
│   ├── _parser.py               # IWFMFileReader
│   ├── _writer.py               # IWFMFileWriter
│   ├── _validation.py           # Cross-file consistency checks
│   ├── model_adapter.py         # IOModelAdapter (DLL-free DataFrame API)
│   ├── scenario.py / run.py / compare.py / collect.py
│   ├── models/                  # Dataclasses for each subsystem
│   ├── readers/                 # read_* functions
│   ├── writers/                 # write_* functions
│   ├── plots/                   # 66 plot functions across 15 modules
│   └── dll/                     # ctypes DLL wrapper (Windows only)
│       ├── model.py             # IWFMModel
│       ├── budget.py / zbudget.py
│       └── _dll.py / _marshal.py / _errors.py
├── examples/
│   ├── 01_read_inputs.py …      # Numbered examples 01–09 (see table above)
│   └── test_plots.py            # 58-function plot test suite
├── tests/
│   └── io/                      # pytest suite for iwfm_io
├── .assets/
│   └── sample_model/            # Reference model (441 nodes, 400 elements)
├── dlls/                        # Versioned DLL storage (dlls/<version>/IWFM_C_x64.dll)
└── docs/
```

The sample model (441 nodes, 400 elements — used by the tests and examples)
is published as a **release asset** on the GitHub Releases page. Download
`sample_model.zip` and extract it to `.assets/sample_model/`. Tests skip
automatically when it is absent.

## DLL Wrapper Architecture

The `iwfm` package wraps the IWFM C DLL using ctypes:

- **STDCALL convention** - All functions use WinDLL
- **Fortran interfacing** - All parameters passed by reference
- **Column-major arrays** - 2D arrays use Fortran order (`order='F'`)
- **Error handling** - Status codes checked via `IW_GetLastMessage`
- **String marshaling** - Fortran character arrays with length parameters

### DLL Exports Wrapped:
- **~161 Model functions** (`IW_Model_*`) - Grid, flow, BC, pumping
- **14 Budget functions** (`IW_Budget_*`) - Water budget analysis
- **16 ZBudget functions** (`IW_ZBudget_*`) - Zone budget analysis
- **~34 Misc functions** (`IW_*`) - Utilities, time conversion

## Requirements

- numpy >= 1.20
- matplotlib >= 3.3
- pandas >= 1.2
- h5py >= 3.0
- Optional (`iwfm-io[geo]`): geopandas >= 0.10, shapely >= 1.8

## Known Limitations

**DLL wrapper (Windows only):**
- Some features require `is_for_inquiry=False` with a full simulation run
- 10 of the 58 DLL plot tests fail on the sample model due to DLL inquiry-mode limitations (spurious duplicate-node error, partial instantiation) — not wrapper bugs

**`iwfm_io` (cross-platform):**
- `IOModelAdapter.subsidence_df()` returns an empty DataFrame (per-node subsidence exists only as DLL state; observation-point series are readable via `read_hydrograph_out`)
- `stream_flows_df()` needs a stream *node budget* HDF in Results (returns empty otherwise); `supply_demand_df()`/land-use areas need the L&WU or RootZone budget HDF; aquifer parameters need a per-node (NGROUP=0) parameter block — parametric-grid models require the DLL
- HEC-DSS reading needs the optional `[dss]` extra (`iwfm_io.dss`); the input-file readers store DSSFL pathname assignments but do not auto-fetch the referenced values — read them explicitly with `read_dss_timeseries`
- Binary `PreProcessor.bin` files cannot be read — only the text input files

See `docs/TEST_PLOTS_RESULTS.md` for detailed plot-test results and known issues.

## License

- **iwfm-io code**: Apache-2.0 (see `LICENSE` and `NOTICE`)
- **IWFM itself and the DLL builds published as release assets**: GPL-2.0, Copyright California Department of Water Resources (see `LICENSE-DLLS.md`)

The split reflects who wrote what: the Python code is an independent work that reads IWFM's file formats and calls the DLL's C API, while the DLL release assets are unmodified redistributions of DWR's GPL-2.0 binaries, published with their corresponding source.

## Credits

- **IWFM**: California Department of Water Resources
- **iwfm-io**: Python file I/O, DLL wrapper, and visualization toolkit (2026)

## Version History

- **v2.14.0** (2026-09-10) - **Hardening release, part 2 (Medium/Low)** — the deferred Medium/Low findings of the 2026-09-09 audit + hostile-QA pass, each flipped from a strict-xfail regression case to a passing test. **Adapter:** every table read lazily from disk (components, time series, budgets, text heads, stream flows, zone budgets) refreshes itself when its source file changes (mtime/size signature) and `IOModelAdapter.reload()` forces it; an empty/truncated `GWHeadAll.out` raises a clear `ValueError`; `open_model` prefers `*main*` files and skips `copy`/`backup`/`old` variants; HDF outputs whose `NTimeSteps` disagrees with the dataset keep the common prefix instead of a misaligned index. **Aggregation:** `aggregate_budget` returns an empty frame for an empty long input and propagates NaN on both the typed and heuristic paths. **Readers:** text budgets (`read_budget_text`) assemble multi-line column titles per data column (was: last header line only — duplicate `Loss` columns, truncated `Subreg.`); hydrograph metadata labels match whole words (`NODES` no longer read as `NODE` + `S`); decks with legacy cp1252 bytes in comments decode as cp1252 instead of U+FFFD; `read_diver_specs` chooses the row layout by numeric-token count only and warns on an out-of-range TYPDSTDL (was: silently re-parsed under the other layout); a land-use block missing its date raises (was: merged into the previous block); `read_zone_def` rejects an element assigned twice. **Writers:** a numeric-looking cell with a comma (`"1,000"`) and a name containing `/` are refused (both are read back wrong by IWFM); `write_gw_initial_conditions` requires layers `1..NL` without gaps and writes multi-line banners as comment lines; datetime dates in land-use tables are formatted as IWFM stamps; `validate_nodes`/`validate_stratigraphy` catch NaN/inf, `validate_elements` allows `0` only for `node4`, `validate_preprocessor` checks declared counts (`ND`/`NE`/`NREGN`/`NRH`/`NLAKE`) against the tables. **Plots:** `plot_gw_head_contour` honours `time_index` and `factor` without a date range; `plot_head_vs_gse_scatter` draws the aquifer-top *elevation* (was the aquitard thickness); trend/drawdown maps raise on an empty date window and skip NaN heads; `plot_element_map` rejects a wrong-length array (was: colours recycled); animations keep one contour level set across frames (colorbar matched frame 0 only) and reject `fps <= 0`; the stream–aquifer exchange map handles a model without streams. **GIS/VTK/wells/gauges:** `export_gis` rejects unknown suffixes (`.geojson` used to become a shapefile folder) and duplicate `node_data`/`element_data` ids, accepts a single layer name; VTK array names are XML-escaped; `build_well_mapping` rejects NaN coordinates and warns for wells outside the mesh; `stream_hydrograph_series(quantity="stage")` explains when the HDF holds flows only. **PEST:** `read_smp` accepts `24:00:00` stamps; `parrep_v2` rejects NaN values, never overwrites fixed/tied parameters, and finds `NOPTMAX` case-insensitively; `setup_agents(overwrite=True)` removes stale `agent_NN` folders; `balance_weights` rejects negative/NaN targets and infinite residuals; observation-name codecs decode year-9999 stamps and refuse 2-digit-year stamps that would not round-trip; `ParamSpec` rejects NaN zones, zone labels that slugify to the same name, and tie chains/cycles; the quickstart validates weights; `budget_observations` compares labels as text and rejects name collisions. **DSS:** `dss_catalog`/`read_dss_timeseries` raise `FileNotFoundError` instead of creating an empty file; recurring-year (4000) records read at second resolution. **CLI:** `--traceback` is accepted after the subcommand too. **API surface:** `IOModelAdapter` gains public `model_root`, `simulation`, `preprocessor`, `gw_main`, `stream_main`, `heads_file`, `available_budgets`, `available_zbudgets` (used by `compare_models`, which now also counts text `.bud` budgets, and by the PEST quickstart instead of private attributes); `scenario.NEVER_LINK_SUFFIXES` is public; `write_swshed`/`write_unsatzone` take `base_dir`; `collect_gwheads` raises when node/layer filters are given without `n_nodes`/`n_layers` (they were silently ignored); `plot_contour_map` masks NaN nodes (points fallback when too few remain) instead of drawing substitutes, the recovery-lag map leaves never-recovered nodes blank, `plot_budget_sankey` defaults to matplotlib; GIS builder failures log at warning; PEST template fields are at least 12 wide. **DLL wrapper:** intervals are checked against IWFM's recognised list (`3MON` counted as zero intervals); unknown hydrograph location types, NaN coordinates, unknown zone extents, out-of-range Z-Budget columns/zones and windows outside the file raise `ValueError` (several were access violations); `get_column_headers_general(max_columns)` is a buffer floor; `describe()` on a closed model, `print_results`/`advance_state` and the stream-inflow / `get_supply_purpose` getters in inquiry mode raise (partial instantiation); `delete_inquiry_data_file` refuses a file that is not the active model's simulation main (the DLL export ignores its argument); `download_dll` verifies the extracted file is a PE image and `load_dll` refuses a library without the IWFM exports.
- **v2.13.0** (2026-09-10, folded into 2.14.0 — never published on its own) - **Hardening release, part 1 (Critical/High)** — every Critical and High finding of the 2026-09-09 pre-release audit and hostile-QA pass, plus the CI gating that keeps them fixed. **Breaking:** Python 3.8 dropped (`>=3.9`); readers **raise `IWFMParseError`** (file, section, line) on truncated, short-row, non-numeric or malformed input instead of warning and returning partial objects — the previous keep-what-parsed behaviour is `iwfm_io.strict_mode(False)` / `open_model(strict=False)`, which warns with `IWFMReadWarning`; `IWFMParseError` no longer subclasses `StopIteration`; writers refuse NaN/None/inf/empty/line-break cells and non-integral IDs (`ValueError` naming file, column and row), `fmt_num` no longer returns `""` for NaN, positional tables (`col_N`, `head_layer_N`, root-zone element tables, land-use areas) are written by column *name*, never DataFrame order, and per-layer tables must hold layers `1..NL` exactly once; `parse_iwfm_date` requires a full `MM/DD/YYYY_HH:MM` (`24:MM` with minutes rejected); a non-date row in a time-series file is an error (was: silent truncation of everything after it); `write_keyed_value(None)` writes a blank; `read_velocity_out` returns one row per element per timestep (was an alias of the hydrograph reader keeping 1 element in 400); text-heads columns are labelled by real node id. **PEST:** `apply_parameters` reads a pristine `<file>.base` snapshot (created by `PestSetup.write` or on first use) so multipliers no longer compound across forward runs; duplicate/NaN/header-only value files and a missing `base_dir` raise; generated run steps use the building interpreter (`sys.executable`); `setup_agents` refuses a destination inside the template (was: unbounded recursion); the quickstart copies the model before writing the template, refuses a populated destination, and honours SMP `excluded` flags and per-row `weight` columns; kriging rejects NaN pilot values and checks weight sums. **Scenario/run:** `create_scenario` refuses identical or nested source/destination (it could delete the base model), removes a half-built scenario when a change fails, no longer copies baseline outputs under `Budget/`/`ZBudget/` (`copy_outputs=True` to keep), `set_keyed_value` edits only the value span and can set blank entries; `run_model` reports timeouts as failed `RunResult`s (`timed_out`), keeps the FATAL detail lines and `stdout_tail`, raises `RunError` carrying partial results, and resolves a relative `input_file` against the model. **Aggregation:** monthly/annual window ends are generated with IWFM's own month arithmetic (`iwfm_increment_months`: last-day-of-month sticky, February clamp) — daily models starting late in a month now match the DLL exactly; `collect_*` date bounds use the 24:00 owning-day convention. **DLL wrapper:** every call goes through a guard (process-wide lock, model activation via `IW_Model_Switch`, closed-object check, working-directory anchor) so two `IWFMModel`s no longer alias or crash each other; dates, intervals, layers, locations, ids and array lengths are validated in Python before the Fortran (a mistyped date used to STOP the process with exit code 0, location 0 corrupted the heap); `IWFMBudget`/`IWFMZBudget` instances re-open their own file transparently; `generate_zone_list` always sends zone names; non-native hydrograph intervals are rejected (the DLL used fixed-day strides); `download_dll` writes atomically with a timeout. **Plots:** all 66 functions render DLL-free (`IOModelAdapter` gained `get_budget_*`/`get_hydrograph*` shims), land-use time series use the requested window, matplotlib/numpy deprecations removed, stale `__main__` demo blocks deleted. **Tooling:** CI fetches `sample_model.zip`, runs `ruff --select F`, asserts a minimum passed count, and adds a Windows DLL job; pytest markers `sample_model`/`exe`/`dll`/`c2vsimfg`/`regression` replace ad-hoc skips; `tests/regression/` holds the 135 hostile-QA reproductions (strict xfail until fixed; `tests/_ci/unxfail.py` flips them) and `tests/io/test_plots_smoke.py` covers every plot function.
- **v2.12.0** (2026-09-04) - **DLL-faithful temporal aggregation** ([#33](https://github.com/SercanC/iwfm-io/issues/33), [#34](https://github.com/SercanC/iwfm-io/issues/34)). Aggregated budget reads now reproduce the IWFM DLL exactly — semantics verified line-by-line against DWR's Fortran source and proven at machine precision against `IWFMBudget.get_values` / `IWFMZBudget.get_values_for_zone` on the sample model (GW/LWU/RootZone budgets and LWU/UnsatZone zone budgets, every location/zone, native/monthly/annual) and on C2VSimFG v1.5 (all 48 water years ≤ 6e-16). **Anchored windows (breaking):** `read_budget_hdf` / `read_zbudget_hdf` `interval="1YEAR"` now means what the DLL means — consecutive 12-month windows anchored to the data begin (for October-start models, the water year), stamped at the window end (`09/30_24:00` → Oct 1 midnight under the library's 24:00 convention), with a trailing partial window dropped as the DLL does; `"1MON"` windows are likewise anchored, so monthly labels from daily data now match native monthly files (next-period-begin stamps) and each `24:00` stamp lands in the month it belongs to; calendar years remain available under the new explicit `interval="1CALYEAR"` (January-anchored, partial years kept). **LWU carry-over corrected:** the carried shortage is the previous step's *raw* shortage column (the Fortran never feeds back the recomputed one), reset at each window start; aggregated shortage is signed (never clipped) and subtracts the other-inflow column (type 11) where present; Potential CUAW contributes nothing at steps with zero supply requirement; all vectorized. **Zone budgets (#33):** zone-mode frames now carry the DLL's full column set — datasets with no active elements appear as all-zero columns instead of vanishing (positional column indexing now matches the DLL) — with clean display names (the raw `@...@` unit annotations are stripped; `metadata` keeps the raw names and adds `data_names_clean`), and the LWU carry-over columns are aggregated **per element before zone summation** exactly as the DLL does (the clipping does not commute with spatial sums), in raw element mode too. **`aggregate_budget(df, period=, data_types=)` (#34):** pass the `data_types` mapping `read_budget_hdf` returns and the helper applies the DLL's per-type rules — volumetric rates (1/9/10/11) sum, beginning storage (2) keeps the period's first value, ending storage/area/length (3/4/5) the last (a monthly Area column no longer sums to ~12× its real value), and the LWU trio (6/7/8) uses the carry-over accumulation — for wide and long frames alike, with the existing name heuristic as the fallback for untyped columns. New DLL-parity test module (`tests/io/test_dll_agg_parity.py`, runs wherever the DLL loads) plus an engine test suite that checks the vectorized carry-over against a straight transcription of the Fortran loop. **Also new: GW initial-conditions (restart) file support** — `write_gw_initial_conditions(path, heads, facthp=)` writes the optional restart file the GW main names as its INITIAL CONDITIONS FILE (the `FinalGWHeads.out` layout), `initial_heads_from_head_all(head_all, date=)` builds the heads table from one `GWHeadAll.out` timestep (defaults to the last — the spin-up → production handoff), and `read_final_state_out` now also reads hand-written restart files (no dashed separators, bare factor line without the `/ FACTHP` keyword — layouts IWFM itself accepts).
- **v2.11.1** (2026-08-29) - **Relationships walkthrough.** New `examples/11_relationships.py` — a comprehensive, runnable tour of the cross-file relationship layer: why pointer columns exist, `series()` resolution shown raw / factor-applied / calendar-expanded, the `column_usage()` reverse lookup recovering the meaning of anonymous `col_N` columns, `validate_references()` on a clean model and on a deliberately broken one, and all seven convenience accessors including the informative 0-pointer error. No library changes.
- **v2.11.0** (2026-08-29) - **Cross-file relationships as a first-class layer.** IWFM inputs constantly reference each other — pointer columns hold column numbers into role-referenced time-series files, ID columns reference the grid, and `(TYPDST, DST)` pairs pick destinations under per-file code tables. The model now knows every such relationship. On the object returned by `open_model()`: **`model.component(name)`** and **`model.timeseries(role)`** lazily read and cache any component/sub-file or pointer-target time-series file (~24 roles); **`model.series(role, column)`** returns the actual series a pointer points at — conversion factor applied (`raw=True` for file-native values) and recurring-year data (sentinel years 4000/2500) expanded onto the simulation period (`expand=False` for the raw pattern), with step-function semantics matching IWFM; **`model.column_usage(role)`** is the reverse lookup that gives the anonymous `col_N` columns their meaning (on the sample model it reconstructs the ET file's lost column-label comment exactly: col 1 = tomatoes … col 7 = the lake); **`model.validate_references()`** checks every pointer against its target's column count, every entity ID against the grid, and every destination pair against its code table, returning a findings DataFrame (C2VSimFG v1.5 validates clean in ~30 s — and the layer directly reproduces real QA findings such as deliveries pointed at a never-irrigable crop column). **Convenience accessors** answer common questions in one call, handling the `element_id=0` "all elements" sentinel and applying share fractions (FRACWL/FRACSK/diversion fractions): `crop_series(kind, crop, element=)` (non-ponded codes, ponded types, `"native"`/`"riparian"`; kinds `et`, `irrigation_period`, `supply_requirement`, `min_moisture`, `target_moisture`, `return_flow`, `reuse`, `min_perc`, `ponding_depth`), `urban_series(kind, element=)`, `well_pumping(id)` / `element_pumping(id)` (`kind="max"`, `scaled=False`), `bc_series(node, layer=)` (searches all four BC files; constant BCs return their value at simulation start), `diversion_series(id, kind=)`, and `lake_max_elevation()`. A pointer of 0 raises an informative "none / computed internally" error instead of an index error. New public helper **`expand_recurring(data, begin, end)`** maps recurring-year data onto a real calendar period (single constant entries, leap-day fallback). The relationship registry itself is internal for now and will be considered for public API once mature.
- **v2.10.0** (2026-08-29) - **Complete file coverage, audited twice.** Every dataset in every IWFM input file reachable from the preprocessor and simulation mains now has a full reader/writer pair, proven end-to-end: the sample model rebuilt from **all** regenerated inputs reproduces baseline heads exactly through the real executables, and a regenerated C2VSimFG v1.5 preprocessor deck produces a **byte-identical** binary. New API: **`read_timeseries_file` / `write_timeseries_file`** (any standard 3/4/5-param time-series file — covers RootDepthFrac, MinMoist, PondDepth, RiceOps, Population, PerCapWaterUse, UrbanWaterUseSpecs, ReturnFlowFrac, ReuseFrac, incl. DSS mode; spec keywords preserved, `has_factor=`/`has_dssfl=`/`columns=` overrides), **`read_surface_flow_dest` / `write_surface_flow_dest`** (v4.12 `(T,D)` destination tuples), **`read_max_lake_elev` / `write_max_lake_elev`**, **`read_irr_period` / `write_irr_period`**, and a rebuilt lake component (bed factors, multi-lake table, initial elevations). **Correctness fixes** (several found by auditing against DWR's Fortran source and negative-testing the executables): v4.2 stream bed-table column order dispatched by version (`IR WETPR IGW CSTRM DSTRM` — previously misread on C2VSimFG-class decks), element-pumping per-layer fractions sized by the model's layer count instead of a hard-coded 2 (`read_elem_pump(n_layers=)`), 7-token hydrograph rows (x-y + placeholder node) keep their names, `/`-prefixed lines parse as blank-value data lines (IWFM's comment chars are `C c *` only), DSS mode for IrigFrac/SupplyAdjust, DELTAT (non-time-tracked mains), stream-geometry partial-interaction table, `IWFMModel` opens from any working directory (deck-relative paths anchored to the simulation folder, `run_dir=` override). **Contracts:** declared dimension variables (ND, NE, NRDV, NOUTH, …) are stored on the dataclasses and writers refuse count↔table mismatches with a clear `ValueError`; NaN cells can no longer write silently short rows; time-series values write at full practical precision (`%.10g`). **Annotations preserved:** end-of-line `/` comments round-trip — element-group/delivery-area names (e.g. C2VSimFG's "Arvin-Edison WSD"), hydrograph station/InSAR notes, well and crop names (`crop_names` incl. budget crops), all re-emitted on write. Issue fixes [#28](https://github.com/SercanC/iwfm-io/issues/28), [#30](https://github.com/SercanC/iwfm-io/issues/30), [#31](https://github.com/SercanC/iwfm-io/issues/31), [#32](https://github.com/SercanC/iwfm-io/issues/32). **Breaking renames** (the old names were wrong): `StreamMain.reach_params` columns are now `stream_node_id`/`conductance`/`bed_thickness`/`wetted_perimeter` (rows are per stream node; the previous `width`/`bed_thickness` labels mis-assigned DSTRM/WETPR), and `SpecifiedHeadFile.data.ibctyp` is now `itscol` (it is the time-series BC column pointer). Diversion NAMEs are written positionally again (a `/`-relocated name reads as blank to IWFM). Typed parse errors (`IWFMParseError`) name the file; `write_subsidence` joins `write_subsidence_file` as the canonical name.
- **v2.9.0** (2026-08-25) - **Land use area tables + IWFM2OBS/CalcTypHyd parity.** **`read_land_use_area(path, columns=)` / `write_land_use_area()`** cover all four root-zone land use area files (non-ponded crops, ponded crops, urban, native/riparian vegetation — one shared format) as a long DataFrame (`date`, `element_id`, one area column per land use; `columns=` names them with crop codes), including the DSS-pathname variant; both directions are vectorized (C2VSimFG's 140 MB urban file reads in ~19 s and round-trips exactly; the 1 GB non-ponded file — 3.25M rows × 20 crops — reads in under two minutes), and the writer's output is exe-verified: the sample model reproduces baseline heads exactly with all four area files regenerated. **`read_all_land_use_areas(rootzone_main, element_areas=)`** combines every land use group of a model into one DataFrame with each file's conversion factor applied so columns are areas in model plane units; fraction-based files (FACT=0.0) are converted with `element_areas=` (pass the parsed preprocessor — element areas are computed from the grid — a Series, or a dict) or kept as fractions when it's omitted, with a warning only if that would mix fractions and areas. PEST additions matching DWR's calibration utilities: `read_smp`/`write_smp` handle the exclusion-flag column and IWFM2OBS fixed-width layout (`fixed_width=True`), `match_sim_to_obs(extrapolate=)` adds IWFM2OBS-style bounded endpoint extrapolation, and new `iwfm_io.pest.typhyd` (`typical_hydrographs`) is a CalcTypHyd equivalent — cluster-averaged, de-meaned typical hydrographs from period-year slot averages.
- **v2.8.0** (2026-08-24) - **One-call PEST++ setup and the `iwfm-io` command line.** **`pest_setup_from_model(model_dir, obs, dest)`** goes from a model folder plus observed heads (long-form frame, SMP, or CSV) straight to a runnable pestpp-ies template: multiplier parameters for the requested aquifer properties (`kh, ss, sy, kv, aquitard_kv` — NGROUP=0 tables and single parametric grids both supported) zoned by subregion × layer (or per layer, or global) plus stream-reach conductance; observations paired to the model's own GW hydrograph outputs by name (unmatched or unpairable rows reported, never silently kept); a hardlinked copy of the model inside the template; and a generated fail-fast forward run — apply multipliers → run the IWFM executables → re-extract simulated values at the observation timestamps. Exe-verified: the generated forward run reproduces baseline heads **exactly** at every observation through the real executables, and the template runs unmodified under the real pestpp-ies. **New console script `iwfm-io`**: `describe` (model inventory as JSON), `pest setup` (the quickstart from the shell), `pest agents` (hardlinked agent directories + manager script), `pest run` (serial, or manager plus N local agents launched and awaited), and `pest analyze` (phi + `diagnose_ies` report, text or JSON). Supporting improvements: `ApplyAction` reaches nested tables via dotted paths (`"parametric_grids.0.params"`) and takes `base_dir` so component writers re-relativise referenced file paths on rewrite — fixing cumulative path corruption when the apply step ran outside the simulation working directory; the writers now emit the load-bearing comment lines that terminate the time-series spec block and stream-inflow node list (exe-verified — IWFM otherwise consumes the first data line); `budget_observations(aggregate="annual")` applies per-component water-year rules (flows sum, storage stocks take first/last — never summed); IWFM `_24:00` hydrograph stamps parse directly (faster, no more dateutil warning). New `examples/10_pest_calibration.py` (cross-platform, runs in seconds — no executable needed), notebook 09 re-executed with a leading one-call quickstart section, and the `iwfm-analyst` skill teaches the new workflow.
- **v2.7.1** (2026-08-15) - **Correct calendar grouping and budget aggregation for IWFM's `24:00` stamps.** IWFM stamps every output value at the first instant *after* its period ends (`24:00` = next-day midnight), so naive `.dt.year`/`.dt.month` labels and `resample()` bins drift at period boundaries — a `9/30` value lands in the wrong water year — and plain `.sum()` aggregation destroys the storage *stocks* (Beginning/Ending Storage are levels, not flows). New tools fix both, and the tutorial notebooks' aggregation examples now use them: **`iwfm_day(times)`** returns the day a stamp belongs to (midnight stamps map to the day they close; accepts IWFM date strings, datetimes, Series, or a DatetimeIndex); **`water_year(times)`** returns the Oct–Sep water year as a plain integer labeled by ending year (`09/30/2024_24:00` → 2024, `10/01/2024_24:00` → 2025); **`aggregate_budget(df, period="WY"|"CY"|"MON")`** aggregates a wide `budget_df()` frame or the long `collect_budgets` frame with the right rule per component (`budget_component_agg`: flows sum, `Beginning Storage` takes the period's first value, `Ending Storage` and `Cumulative …` the last) — verified by stock continuity on the sample model (each water year begins exactly where the previous one ended); and **`day_index=True`** on `heads_df()` / `budget_df()` / `hydrograph_df()` (both `IOModelAdapter` and the DLL `IWFMModel`) returns the frame indexed by owning day, so calendar idioms like `resample("YE-SEP")` label periods correctly when you want to stay in plain pandas. Parsing is unchanged: `parse_iwfm_date` still returns the true instant, which DSS/CalSim alignment and exact-timestamp joins depend on.
- **v2.7.0** (2026-08-14) - **Complete reader/writer coverage + text-budget fallback.** Writers now exist for every reader — the last unpaired files gained theirs: the three boundary-condition sub-files (`write_spec_flow_bc`, `write_general_head_bc`, `write_constrained_head_bc` — keywords match DWR's release files, and the constrained rows' `/name` annotations round-trip) and the four root-zone sub-component mains (`write_nonponded_ag_main`, `write_ponded_ag_main`, `write_urban_main`, `write_native_veg_main` — crop-code blocks, root depths, every per-element pointer table including the element-0 "all elements" shorthand, and blank-optional-file handling; all take `base_dir` like the other component writers). Verified three ways: write→re-read equality on the sample model, write→re-read equality on the **real C2VSimFG v1.5 files** (the v4.11 variants with 20 crops and 32,537-element tables), and the executable round-trip — the sample model reproduces baseline heads **exactly** with the root-zone sub-mains and BC files regenerated too. **`open_model()` now surfaces text `.bud` budgets**: for packaged/older models (or fresh executable runs) that ship no budget HDF files, `.bud` files in `Results/` and `Budget/` are discovered automatically, `describe()` lists them with `"format": "text"`, and `budget_df()` serves them identically (locations by index or name, date windows) at the file's native output interval; where a budget exists in both formats the HDF wins, matched on a normalized stem (`Strm.bud` defers to `StrmBud.hdf`).
- **v2.6.0** (2026-08-13) - **GIS and VTK exports** (roadmap item 5). **GIS** (`pip install iwfm-io[geo]`): new `iwfm_io.gis` — `export_gis(model, "model.gpkg")` / `IOModelAdapter.to_gis()` write every spatial layer to a multi-layer GeoPackage or a folder of ESRI Shapefiles: nodes (stratigraphy attributes joined), element polygons (with subregion names), dissolved subregion polygons, stream-reach LineStrings, stream-node points, merged lake polygons, tile drains, and wells. Per-layer `*_gdf()` builders return GeoDataFrames for spatial analysis in Python; `node_data=`/`element_data=` merge simulation results (heads, depth to water, land use, …) onto the layers; `crs=` georeferences the output (IWFM files carry no CRS). Geometry is rebuilt from node coordinates and element configurations, so both `open_model()` adapters and the DLL `IWFMModel` work as sources; geopandas imports at call time, keeping `[geo]` optional. **VTK** (no extra install — written with plain numpy): new `iwfm_io.vtk` — `export_vtk(model, "model.vtu")` / `to_vtk()` extrude the FE grid through the stratigraphy into a 3D layered mesh for ParaView (wedges for triangles, hexahedra for quads, one cell layer per aquifer, aquitard gaps preserved via IWFM's aquitard-above-aquifer convention), with built-in `layer`/`thickness`/`element_id`/`subregion` cell arrays, `z_scale` vertical exaggeration, layer subsetting, and `(n,)`/`(n, n_layers)` point/cell data arrays; `export_vtk_timeseries()` writes per-timestep frames with `head` + `dtw` point arrays and the `.pvd` collection file ParaView animates. Cell orientation verified against pyvista (positive volumes) on the sample model and C2VSimFG v1.5 (130k mixed cells, ~2 s). Tutorial notebook 12 now covers both, including an inline 3D render.
- **v2.5.0** (2026-08-13) - **PEST(++) calibration support** ([#6](https://github.com/SercanC/iwfm-io/issues/6)–[#27](https://github.com/SercanC/iwfm-io/issues/27)): the new `iwfm_io.pest` subpackage covers both sides of a PEST++ calibration of an IWFM model — pure pandas, with `pyemu` needed only for `.jcb` binary ensembles (`pip install iwfm-io[pest]`). **Building:** round-trip-safe observation-name codec (standard + DWR grouped schemes, custom schemes registrable); SMP bore-sample file I/O; IWFM2OBS-equivalent sim-to-obs time matching (gap-guarded, `24:00`-aware); budget-component observations (means, water-year totals, full series); derived observations (successive/seasonal/drawdown head changes, vertical head differences, gauge accretion–depletion, long-term stats); zone/group parameterization (`ParamSpec` → PEST++ v2 external tables + templates + initial-value files, with a fill-and-compare verify); pure-numpy pilot-point kriging on the FE mesh (exp/sph/gau variograms, anisotropy, zones); constrained reparameterization (`RatioChain` with corner-checked ordering guarantees, Texture2Par `PP_LOCS` I/O); paired output+instruction writers (`ObsFileSpec` — the `.ins` and the output file come from one spec, consistent by construction); multiplier write-back through the round-trip writers (`apply_parameters`) plus IWFM's native GW overwrite file; phi-budget weight balancing; hardlinked agent replication, fail-fast forward-run scripts, and pyemu-free finals reruns; and the `PestSetup` capstone that writes a complete runnable PEST++ v2 template directory. **Analyzing:** `load_ies_ensembles` (lazy PESTPP-IES loader — per-iteration ensembles, tidy phi, per-group phi, prior-data conflict, obs+noise, base REI), vectorized fit statistics (`residual_stats`/`rei_stats`/`ies_stats`: bias, RMSE, R², NSE, KGE, phi at ensemble scale), `diagnose_ies` (convergence, collapse, conflict, bound railing, bias, objective balance as JSON state + signals), and a new `iwfm_io.plots.calibration` figure module. **Core additions:** `iwfm_io.wells` (validated `gwl_metadata` schema, hydrograph linking incl. the `name%layer` convention, multi-layer compositing, `build_well_mapping` with perforation∩stratigraphy transmissivity weighting, best-layer selection) and `iwfm_io.gauges` (the stream mirror, incl. the IHSQR=2 flow+stage block layout); `iwfm_io.dss` (`pip install iwfm-io[dss]`): HEC-DSS cataloging and reading, CalSim channel-arc linking, month-length-aware CFS→TAF. Plus **eleven executed tutorial notebooks** (`notebooks/`) covering every feature area. The sample model was regenerated with IHSQR=2 stream hydrographs (flow + stage) — re-download `sample_model.zip` from this release. Validated against a production CalSim3 + C2VSimCG IES calibration.
- **v2.4.0** (2026-07-26) - `create_scenario(..., link_unchanged=True)` ([#5](https://github.com/SercanC/iwfm-io/issues/5)): hardlink unchanged input files into the scenario instead of copying them — stamping out N worker copies of a multi-GB model takes seconds and near-zero marginal disk. Copy-on-change semantics: files touched by `changes` become independent real files (the change factories and `IWFMFileWriter.flush` now write via temp file + atomic rename, never in-place), `Results/` stays a real directory, and file types the executables or DLL inquiry mode rewrite (`.out`, `.bin`, `.bud`, `.log`, `.dss`, `.hdf`, `.h5`) are always real copies. Falls back to copying with a warning when source and destination are on different filesystems.
- **v2.3.0** (2026-07-19) - Fixes all four issues from the first round of downstream feedback ([#1](https://github.com/SercanC/iwfm-io/issues/1)–[#4](https://github.com/SercanC/iwfm-io/issues/4)). **2015-line DLL open failures are no longer silently swallowed** (#1): the wrapper now detects the DLL generation from its export set and calls the matching 7-argument `IW_Model_New` — previously the DLL wrote its status code into the model-id slot and a failed open returned a model reporting 0 nodes. `read_budget_hdf` (#2) now returns the file's native output interval (`'interval'` key, from `TimeStep%Unit`) and lists locations in the file's native DLL order (recovered from the `Attributes/cLocationNames` dataset) instead of h5py's alphabetical order — this also fixes wrong ordering for numeric location names (`NODE 1, 19, 8` → `NODE 1, 8, 19`) and aligns per-location column metadata in files where the orders differ. `read_head_all_out` (#3) names columns `node_<id>_layer_<L>` from the file's header node IDs, mirroring `read_head_hdf`. `load_dll(version=...)` (#4) now downloads published builds on a cache miss via the existing sha256-verified `download_dll` machinery (`download=False` restores search-only behavior for air-gapped machines); `IWFMModel`/`IWFMBudget`/`IWFMZBudget` inherit this when opened with `dll_version=`.
- **v2.2.0** (2026-07-14) - **Relicensed iwfm-io code from GPL-2.0 to Apache-2.0.** IWFM and the DLL builds distributed as release assets remain GPL-2.0 (DWR) — see `LICENSE-DLLS.md`. No code changes.
- **v2.1.0** (2026-07-10) - **Every input dataset is now a DataFrame, and writers regenerate files entirely from them.** Readers no longer stash unparsed sections as raw text: GW main aquifer parameters (per-node and parametric-grid layouts), Kh anomalies, return-flow specs and initial heads; subsidence parameters; tile-drain hydrograph controls; per-well pumping configuration; diversion specs incl. recharge zones and (old-format) spill locations; small watersheds; unsaturated zone; the root-zone soil table; plus new readers for the root-zone sub-components (non-ponded/ponded crops, urban, native vegetation) and the specified-flow / general-head / constrained general-head BC files. Pointer columns (`ic*`, `irn*`, `itscol*`) are documented per dataclass with the file they reference. Writers rebuild every section from the parsed DataFrames — verified against the real IWFM executables: the sample model reproduces baseline heads **exactly** from fully regenerated inputs (`read → write → PreProcessor → Simulation`, max head difference 0.0). `download_dll()` now offers six official DWR builds (2015.0.1403 → 2025.0.1747, incl. 2024.2.1594 used by C2VSimFG v1.5), sha256-verified from this project's releases. All examples repaired and a new `examples/09_full_input_datasets.py` tours the parsed datasets. Fixed: `validate_stratigraphy` false positives; element-group parsing of zero-element recharge zones.
- **v2.0.0** (2026-07-09) - **Import package renamed `iwfm` → `iwfm_io`** to match the distribution name and coexist with other IWFM Python packages (cfbrush/iwfm, DWR's PyWFM). The pure-Python I/O layer moves to the top level and the DLL wrapper into an explicit subpackage — migration: `iwfm.io.X` → `iwfm_io.X`, `iwfm.plots` → `iwfm_io.plots`, `iwfm.IWFMModel` / `download_dll` / `load_dll` → `iwfm_io.dll.…`, `iwfm.run_model` → `iwfm_io.run_model`. No functional changes.
- **v1.4.0** (2026-07-08) - Wells and diversions fully readable without the DLL: new `read_well_spec` (well locations, screens, names, delivery element groups), complete diversion-spec parsing (all component column/fraction pairs incl. spills where the format has them, destination type/id resolved to delivery elements for group/subregion/element destinations, recharge zones with loss fractions), and element-group parsing shared across well specs, element pumping, and diversion specs. `wells_df()` and `diversions_df()` on `IOModelAdapter` are now fully populated; `plot_well_locations` and `plot_diversion_network` (with delivery arrows) render DLL-free. Robust to real-world file quirks (comments glued to numbers, name comments missing the leading slash).
- **v1.3.0** (2026-07-08) - `iwfm_io.dll.download_dll(version)`: one-line install of official IWFM DLL builds from the project's GitHub releases (sha256-verified, GPLv2 with corresponding source attached) into `~/.iwfm/dlls/`. `IOModelAdapter.get_zbudget_timeseries()`: DLL-free zone-budget time series (zones = subregions), so `plot_zbudget_timeseries` works without the DLL. `examples/test_plots.py` now runs against any model root. New [example plot gallery](https://github.com/SercanC/iwfm-io/blob/main/docs/GALLERY.md) — all 58 plot functions rendered from DWR's C2VSimFG v1.5.
- **v1.2.0** (2026-07-08) - DLL-free plotting for everything inquiry mode can't do: `IOModelAdapter` now serves tile drains, bypasses, aquifer parameters (per-node NGROUP=0 blocks), supply requirement/shortage, land-use areas, and per-node stream–GW exchange from the model's input and budget-output files. `open_model()` follows the GW/stream mains to their child files. DLL wrapper hardening: `get_hydrograph` masks the DLL's invalid trailing dates *and* the uninitialized values that accompany them; stream-state getters raise a clean `IWFMError` in inquiry mode instead of letting older DLL builds crash Python (root-cause analyses in `docs/DLL_INQUIRY_MODE_LIMITS.md`). Fixed component child-file path resolution (relative to the simulation folder, not the component file's folder).
- **v1.1.1** (2026-07-07) - Fix two budget HDF reader bugs found by validating against a full C2VSimFG v1.5 simulation run: budget column labels were shifted one column left of the data (the first data column was silently dropped as a supposed time marker), and monthly/annual output DatetimeIndexes drifted by using fixed 30-day steps instead of calendar months. All budget HDF users should upgrade.
- **v1.1.0** (2026-07-07) - `open_model()` one-call model opening, `describe()` model summaries, direct data properties on parsed files; scenario loop: `create_scenario()` input editing, `run_model()` executable driver (Windows), `compare_models()`/`head_difference()`/`budget_difference()` comparison tools, multi-run budget collection; readers validated against C2VSimFG v1.5 and handle IWFM 2024.x format variants (keyword-driven parsing); plotting library moved into the package (`iwfm_io.plots`), geopandas made optional, modern packaging (pyproject.toml)
- **v1.0** (2026-02-15) - Initial release with full plotting library and DLL wrapper
