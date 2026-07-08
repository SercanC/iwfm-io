# iwfm-io

Python file I/O, DLL wrapper, and visualization library for the Integrated Water Flow Model (IWFM).

**[📊 Example plot gallery](docs/GALLERY.md)** — all 58 plot functions rendered from DWR's C2VSimFG v1.5 Central Valley model.

## Features

- **`iwfm.io`** — Pure-Python file I/O (no DLL, cross-platform):
  - Read and write all IWFM text input files (preprocessor, simulation, groundwater, stream, lake, root zone, time series)
  - Read IWFM HDF5 output files (budgets, heads, hydrographs, zone budgets)
  - Read IWFM text output files (hydrographs, final states, flow files, budget text)
  - `IOModelAdapter` presents the same DataFrame API as the DLL wrapper, so plot functions work without the DLL
  - **Model comparison**: `compare_models()` reports what changed between two model versions (checksum file diff + grid + head/budget statistics); `head_difference()`/`budget_difference()` return aligned `B − A` DataFrames
  - **Scenario builder**: `create_scenario()` copies a model and applies input changes (`set_keyed_value`, `replace_text`, or your own functions)
- **Run models from Python** (Windows): `iwfm.run_model()` drives the PreProcessor → Simulation → Budget → ZBudget executables with error detection — the full loop is `create_scenario()` → `run_model()` → `compare_models()`
- **Python ctypes wrapper** for IWFM DLL — Windows x64 only (8 modules)
- **58 plotting functions** across 13 modules:
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
- Python 3.8 or higher
- For `iwfm.io` and plotting: any OS (plots work DLL-free via `IOModelAdapter`)
- For the DLL wrapper: Windows 10+ x64 and a copy of `IWFM_C_x64.dll`. One line fetches an official build (GPLv2, published with its corresponding source on this project's GitHub releases):

  ```python
  import iwfm
  iwfm.download_dll("2025.0.1747")   # → ~/.iwfm/dlls/2025.0.1747/IWFM_C_x64.dll
  ```

  Other builds ship with IWFM from the [DWR IWFM site](https://water.ca.gov/Library/Modeling-and-Analysis/Modeling-Platforms/Integrated-Water-Flow-Model) — place them in `dlls/<version>/` or `~/.iwfm/dlls/<version>/` and select with `load_dll(version=...)` / `IWFMModel(..., dll_version=...)`. The DLL is version-sensitive: match it to your model's IWFM version.

### Install

```bash
pip install iwfm-io          # core: file I/O, DLL wrapper, plotting
pip install iwfm-io[geo]     # + geopandas/shapely for GeoDataFrame output
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
from iwfm.io import open_model

model = open_model(".assets/sample_model")

print(model.describe())            # what does this model contain?
model.nodes_df()                   # grid nodes (GeoDataFrame)
model.heads_df(layer=1)            # simulated heads, one column per node
model.budget_df("GW", location=1)  # groundwater budget time series

from iwfm.plots import maps
fig, ax = maps.plot_gw_head_contour(model, layer=1)
```

### Read Individual Files

```python
from iwfm.io import read_preprocessor, read_simulation

pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")
pp.nodes           # GeoDataFrame: node_id, x, y, geometry
pp.elements        # GeoDataFrame: element_id, node1-4, subregion, geometry
pp.stratigraphy    # DataFrame: elevation, layer thicknesses

sim = read_simulation(".assets/sample_model/Simulation/Simulation_MAIN.IN")
print(f"{len(pp.nodes)} nodes, sim runs {sim.sim_begin} → {sim.sim_end}")

# Or any file directly, without going through the main file
from iwfm.io import read_budget_hdf, read_head_hdf

gw_bud  = read_budget_hdf(".assets/sample_model/Results/GW.hdf")
head_df = read_head_hdf(".assets/sample_model/Results/GWHeadAll.hdf", n_nodes=441, n_layers=2)
```

See `examples/01_read_inputs.py` for a complete walkthrough of all input file readers, and `docs/agents.md` for compact recipes aimed at scripts and AI agents.

### Using the DLL Wrapper (Windows only)
```python
import iwfm

with iwfm.IWFMModel(
    preprocessor_file=".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN",
    simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
    is_for_inquiry=True,
) as model:
    x, y = model.get_node_coordinates()
    print(f"{model.n_nodes} nodes, {model.n_elements} elements")
```

### Run a Scenario (Windows)
```python
from iwfm import run_model
from iwfm.io import create_scenario, set_keyed_value, compare_models

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
from iwfm.plots import maps, timeseries

# Works with IWFMModel or IOModelAdapter
maps.plot_stream_network(model_or_adapter)
timeseries.plot_gw_head_hydrographs(
    model_or_adapter, node_indices=[1, 50, 100], layer=1,
    begin_date="10/01/1990_24:00", end_date="09/30/2000_24:00",
)
```

## Examples

| File | Requires | Description |
|------|----------|-------------|
| `examples/01_read_inputs.py` | .assets/sample_model | Reading all IWFM input files via `iwfm.io` |
| `examples/02_read_outputs.py` | .assets/sample_model/Results | Reading HDF5 and text output files |
| `examples/03_roundtrip.py` | .assets/sample_model | Read → modify → write input files |
| `examples/04_dll_wrapper.py` | Windows + DLL | `IWFMModel`, `IWFMBudget`, `IWFMZBudget` |
| `examples/05_plotting.py` | .assets/sample_model | Plotting gallery — all 13 modules |
| `examples/06_multi_run_budgets.py` | .assets/sample_model/Results | Multi-run unified budget DataFrame |
| `examples/07_compare_models.py` | .assets/sample_model | File diff + comparison report between model versions |
| `examples/08_run_scenario.py` | Windows + sample_model/Bin | Full loop: create scenario → run IWFM → compare |
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

See `docs/TEST_PLOTS_RESULTS.md` for detailed plot-test results: 48 of 58 pass through the DLL in inquiry mode (all failures are DLL/inquiry-mode limitations, not wrapper bugs), and every failing function also renders DLL-free through `IOModelAdapter` — run `python examples/test_plots_dllfree.py` to verify.

## Project Structure

```
iwfm-io/
├── iwfm/                        # Python package
│   ├── model.py                 # IWFMModel — DLL wrapper (Windows only)
│   ├── budget.py / zbudget.py   # Budget/ZBudget DLL wrappers
│   ├── _dll.py / _marshal.py / _errors.py
│   ├── plots/                   # 58 plot functions across 13 modules
│   └── io/                      # Pure-Python file I/O (cross-platform)
│       ├── _tokens.py           # Date/line parsing primitives
│       ├── _parser.py           # IWFMFileReader
│       ├── _writer.py           # IWFMFileWriter
│       ├── _validation.py       # Cross-file consistency checks
│       ├── model_adapter.py     # IOModelAdapter (DLL-free DataFrame API)
│       ├── models/              # Dataclasses for each subsystem
│       ├── readers/             # read_* functions
│       └── writers/             # write_* functions
├── examples/
│   ├── 01_read_inputs.py …      # Numbered examples 01–06 (see table above)
│   └── test_plots.py            # 58-function plot test suite
├── tests/
│   └── io/                      # pytest suite for iwfm.io
├── .assets/
│   └── sample_model/            # Reference model — download from the GitHub
│                                #   release assets and unzip here (not in git)
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
- 12 of 58 plot tests fail on the sample model due to DLL inquiry-mode limitations (spurious duplicate-node error, partial instantiation) — not wrapper bugs

**`iwfm.io` (cross-platform):**
- `IOModelAdapter.wells_df()` and `diversions_df()` return empty DataFrames — the raw pump/diver data is read but not yet normalized into a clean per-well/diversion table
- `IOModelAdapter.subsidence_df()` returns an empty DataFrame (per-node subsidence exists only as DLL state; observation-point series are readable via `read_hydrograph_out`)
- `stream_flows_df()` needs a stream *node budget* HDF in Results (returns empty otherwise); `supply_demand_df()`/land-use areas need the L&WU or RootZone budget HDF; aquifer parameters need a per-node (NGROUP=0) parameter block — parametric-grid models require the DLL
- HEC-DSS file reading is not supported (DSS pathnames are stored but not parsed)
- Binary `PreProcessor.bin` files cannot be read — only the text input files

See `docs/TEST_PLOTS_RESULTS.md` for detailed plot-test results and known issues.

## License

GPL v2+ (matches IWFM license)

## Credits

- **IWFM**: California Department of Water Resources
- **iwfm-io**: Python file I/O, DLL wrapper, and visualization toolkit (2026)

## Version History

- **v1.3.0** (2026-07-08) - `iwfm.download_dll(version)`: one-line install of official IWFM DLL builds from the project's GitHub releases (sha256-verified, GPLv2 with corresponding source attached) into `~/.iwfm/dlls/`. `IOModelAdapter.get_zbudget_timeseries()`: DLL-free zone-budget time series (zones = subregions), so `plot_zbudget_timeseries` works without the DLL. `examples/test_plots.py` now runs against any model root. New [example plot gallery](docs/GALLERY.md) — all 58 plot functions rendered from DWR's C2VSimFG v1.5.
- **v1.2.0** (2026-07-08) - DLL-free plotting for everything inquiry mode can't do: `IOModelAdapter` now serves tile drains, bypasses, aquifer parameters (per-node NGROUP=0 blocks), supply requirement/shortage, land-use areas, and per-node stream–GW exchange from the model's input and budget-output files. `open_model()` follows the GW/stream mains to their child files. DLL wrapper hardening: `get_hydrograph` masks the DLL's invalid trailing dates *and* the uninitialized values that accompany them; stream-state getters raise a clean `IWFMError` in inquiry mode instead of letting older DLL builds crash Python (root-cause analyses in `docs/DLL_INQUIRY_MODE_LIMITS.md`). Fixed component child-file path resolution (relative to the simulation folder, not the component file's folder).
- **v1.1.1** (2026-07-07) - Fix two budget HDF reader bugs found by validating against a full C2VSimFG v1.5 simulation run: budget column labels were shifted one column left of the data (the first data column was silently dropped as a supposed time marker), and monthly/annual output DatetimeIndexes drifted by using fixed 30-day steps instead of calendar months. All budget HDF users should upgrade.
- **v1.1.0** (2026-07-07) - `open_model()` one-call model opening, `describe()` model summaries, direct data properties on parsed files; scenario loop: `create_scenario()` input editing, `run_model()` executable driver (Windows), `compare_models()`/`head_difference()`/`budget_difference()` comparison tools, multi-run budget collection; readers validated against C2VSimFG v1.5 and handle IWFM 2024.x format variants (keyword-driven parsing); plotting library moved into the package (`iwfm.plots`), geopandas made optional, modern packaging (pyproject.toml)
- **v1.0** (2026-02-15) - Initial release with full plotting library and DLL wrapper
