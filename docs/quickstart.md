# Quick Start Tutorial

This tutorial walks through the three main workflows of `iwfm-io`:

1. **Reading and writing IWFM files** (cross-platform, no DLL)
2. **Querying a live model via the DLL** (Windows only)
3. **Creating visualizations** (works with either approach)

---

## Installation

```bash
pip install iwfm-io          # core: file I/O, DLL wrapper, plotting
pip install iwfm-io[geo]     # + geopandas/shapely for GeoDataFrame output
```

Or from a source checkout:

```bash
cd iwfm-io
pip install -e .
```

### DLL setup (Windows only, optional)

If you want to use the DLL wrapper, place DLL builds under `dlls/`:

```
dlls/
  default_version.txt     ← e.g. "2015.0.1248"
  2015.0.1248/
    IWFM_C_x64.dll
```

The package resolves the DLL automatically. You can also set the `IWFM_DLL_VERSION` environment variable or pass an explicit path.

---

## 1. Reading IWFM Files (no DLL required)

The `iwfm.io` subpackage reads and writes all IWFM text input files and HDF5/text output files. It returns pandas DataFrames and (optionally) geopandas GeoDataFrames.

### Open a model in one call

The easiest way to start: point `open_model` at the model's root folder
(the one containing `Preprocessor/`, `Simulation/` and `Results/`). It
finds the main input files and all HDF5 result files for you:

```python
from iwfm.io import open_model

model = open_model(".assets/sample_model")

# What does this model contain? (JSON-serializable summary)
import json
print(json.dumps(model.describe(), indent=2))

model.nodes_df()                   # grid nodes (GeoDataFrame)
model.elements_df()                # elements (GeoDataFrame)
model.heads_df(layer=1)            # simulated heads, one column per node
model.budget_df("GW", location=1)  # groundwater budget time series
```

`describe()` lists every budget that was found and its locations, so you
never have to guess what to pass to `budget_df()`.

### Read the preprocessor

```python
from iwfm.io import read_preprocessor

pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")

# Parsed data is available directly as DataFrames
pp.nodes            # GeoDataFrame: node_id, x, y, geometry
pp.elements         # GeoDataFrame: element_id, node1-4, subregion, geometry
pp.stratigraphy     # DataFrame: elevation and layer thicknesses per node
pp.stream_reaches   # DataFrame: reach_id, n_nodes, outflow_dest, name
pp.lakes            # DataFrame: lake_id, dest_type, dest_id, elements

print(pp.nodes.head())
#    node_id         x          y                   geometry
# 0        1  1828567.0  14693949.0  POINT (1828567 14693949)
# ...
```

### Read individual files

You don't have to go through the main file — read any file directly:

```python
from iwfm.io import read_nodes, read_elements, read_strata

nodes    = read_nodes(".assets/sample_model/Preprocessor/NodeXY.dat")
elements = read_elements(".assets/sample_model/Preprocessor/Element.dat")
strata   = read_strata(".assets/sample_model/Preprocessor/Strata.dat")

print(f"{len(nodes.data)} nodes, {len(elements.data)} elements")
print(f"{strata.n_layers} aquifer layers")
```

### Read the simulation configuration

```python
from iwfm.io import read_simulation

sim = read_simulation(".assets/sample_model/Simulation/Simulation_MAIN.IN")
print(f"Period: {sim.sim_begin} → {sim.sim_end}")
print(f"Time step: {sim.time_step}")
```

### Read groundwater and stream files

```python
from iwfm.io import read_gw_main, read_stream_main

gw = read_gw_main(".assets/sample_model/Simulation/GW/GW_MAIN.dat")
print(f"{gw.n_hydrographs} GW hydrograph sites")

sm = read_stream_main(".assets/sample_model/Simulation/Stream/Stream_MAIN.dat")
print(f"{sm.reach_params.shape[0]} stream reaches")
```

### Read HDF5 output files

```python
from iwfm.io import read_budget_hdf, read_head_hdf

# Groundwater budget
gw_bud = read_budget_hdf(".assets/sample_model/Results/GW.hdf")
print(gw_bud["locations"])  # e.g. ['Subregion 1', 'Subregion 2', ...]

df = gw_bud["data"]["Subregion 1"]
print(df.columns.tolist())  # budget columns
print(df.head())

# Groundwater heads at all nodes
head_df = read_head_hdf(
    ".assets/sample_model/Results/GWHeadAll.hdf",
    n_nodes=441,
    n_layers=2,
)
print(head_df.shape)  # (timesteps, nodes)
```

### Read text output files

```python
from iwfm.io import read_hydrograph_out, read_final_state_out

# GW hydrograph text file
hyd = read_hydrograph_out(".assets/sample_model/Results/GWHyd.out")
print(hyd.shape)

# Final groundwater heads
final = read_final_state_out(".assets/sample_model/Results/FinalGWHeads.out")
print(final.head())
```

### Date utilities

IWFM uses the format `MM/DD/YYYY_HH:MM` where `24:00` means end of day:

```python
from iwfm.io import parse_iwfm_date, format_iwfm_date
from datetime import datetime

dt = parse_iwfm_date("09/30/1990_24:00")
print(dt)  # 1990-10-01 00:00:00

s = format_iwfm_date(datetime(1990, 10, 1))
print(s)   # "10/01/1990_00:00"
```

### Write files back (round-trip)

Every reader has a matching writer. Read a file, modify it, write it back:

```python
from iwfm.io import read_nodes, write_nodes
import tempfile, os

nodes = read_nodes(".assets/sample_model/Preprocessor/NodeXY.dat")

# Shift all X coordinates by 100
nodes.data["x"] += 100

out_path = os.path.join(tempfile.mkdtemp(), "NodeXY_shifted.dat")
write_nodes(nodes, out_path)
print(f"Written to {out_path}")
```

### Validate model files

```python
from iwfm.io import read_preprocessor, validate_preprocessor

pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")
errors = validate_preprocessor(pp)

if errors:
    for e in errors:
        print(f"  ERROR: {e}")
else:
    print("No validation errors.")
```

---

## 2. Using the DLL Wrapper (Windows only)

The `iwfm` package wraps the IWFM Fortran DLL via ctypes. All calls go through `IWFMModel`, `IWFMBudget`, or `IWFMZBudget`.

### Check available DLL versions

```python
import iwfm

print(iwfm.list_dll_versions())
# ['2015.0.1248', '2020.0.1193']
```

### Open a model

```python
import iwfm

with iwfm.IWFMModel(
    preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
    simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
    is_for_inquiry=True,
) as model:
    print(f"Nodes: {model.n_nodes}")
    print(f"Elements: {model.n_elements}")
    print(f"Layers: {model.n_layers}")
    print(f"Subregions: {model.n_subregions}")

    # Node coordinates
    x, y = model.get_node_coordinates()

    # Element connectivity
    elem_ids, elem_nodes = model.get_element_config()

    # Stratigraphy
    gse = model.get_ground_surface_elevation()
    tops, bots = model.get_aquifer_top_elev(), model.get_aquifer_bottom_elev()
```

### Query time-series data

```python
with iwfm.IWFMModel(..., is_for_inquiry=True) as model:
    # GW heads at specific nodes
    dates, heads = model.get_gw_heads_at_node(
        node_id=50, layer=1,
        begin_date="10/01/1990_24:00",
        end_date="09/30/2000_24:00",
    )

    # Stream flow at a reach
    dates, flows = model.get_stream_flows(
        reach_id=1,
        begin_date="10/01/1990_24:00",
        end_date="09/30/2000_24:00",
    )
```

### Read budget files standalone

You don't need to open the full model to read budget HDF files:

```python
import iwfm

with iwfm.IWFMBudget(".assets/sample_model/Results/GW.hdf") as bud:
    n_loc = bud.get_n_locations()
    names = bud.get_location_names()
    print(f"{n_loc} locations: {names}")

    # Get budget data for first location
    cols = bud.get_column_headers(location=1)
    dates, values = bud.get_values(
        location=1,
        begin_date="10/01/1990_24:00",
        end_date="09/30/2000_24:00",
    )
```

### Read zone budgets

```python
import iwfm

with iwfm.IWFMZBudget(".assets/sample_model/Results/GW_ZBud.hdf") as zb:
    zone_names = zb.get_zone_names(
        zone_def_file=".assets/sample_model/ZBudget/ZoneDef_SRs.dat"
    )
    cols = zb.get_column_headers(
        zone_def_file=".assets/sample_model/ZBudget/ZoneDef_SRs.dat",
        zone=1,
    )
    dates, values = zb.get_values(
        zone_def_file=".assets/sample_model/ZBudget/ZoneDef_SRs.dat",
        zone=1,
        begin_date="10/01/1990_24:00",
        end_date="09/30/2000_24:00",
    )
```

### Pin a specific DLL version

```python
# On the model
with iwfm.IWFMModel(..., dll_version="2015.0.1248") as model:
    ...

# On budget readers
with iwfm.IWFMBudget("GW.hdf", dll_version="2015.0.1248") as bud:
    ...

# Or pass an explicit path
with iwfm.IWFMModel(..., dll_path="/path/to/IWFM_C_x64.dll") as model:
    ...
```

---

## 3. Creating Visualizations

The `iwfm/plots/` library has 58 plotting functions across 13 modules. They work with either `IWFMModel` (DLL) or `IOModelAdapter` (pure Python).

### Set up IOModelAdapter (no DLL)

```python
from iwfm.io import read_preprocessor, IOModelAdapter

pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")

adapter = IOModelAdapter(
    preprocessor=pp,
    heads_hdf=".assets/sample_model/Results/GWHeadAll.hdf",
    budget_hdfs={
        "GW": ".assets/sample_model/Results/GW.hdf",
        "Stream": ".assets/sample_model/Results/StrmBud.hdf",
    },
)

print(f"Nodes: {adapter.n_nodes}, Elements: {adapter.n_elements}")
```

### Plot the model grid

```python
from iwfm.plots import maps

fig, ax = maps.plot_element_map(adapter)
fig.savefig("grid.png", dpi=150)
```

### Plot the stream network

```python
fig, ax = maps.plot_stream_network(adapter)
fig.savefig("streams.png", dpi=150)
```

### Plot groundwater head hydrographs

```python
from iwfm.plots import timeseries

fig, ax = timeseries.plot_gw_head_hydrographs(
    adapter,
    node_indices=[1, 50, 100],
    layer=1,
    begin_date="10/01/1990_24:00",
    end_date="09/30/2000_24:00",
)
fig.savefig("head_hydrographs.png", dpi=150)
```

### Plot a water budget

```python
from iwfm.plots import water_balance

fig, ax = water_balance.plot_budget_sankey(adapter, budget_type="GW", location=1)
fig.savefig("sankey.png", dpi=150)
```

### Available plot modules

| Module | Functions | Description |
|--------|-----------|-------------|
| `maps` | 11 | Grid, heads, streams, wells, lakes, tile drains |
| `profiles` | 2 | Cross-sections, longitudinal profiles |
| `timeseries` | 7 | Hydrographs, budgets, land use |
| `trends` | 4 | Long-term trends, seasonal patterns, drought |
| `seasonal` | 4 | Ridgelines, heatmaps, polar plots |
| `spatial_patterns` | 3 | Sparklines, small multiples, scatter plots |
| `summary` | 7 | Rating curves, histograms, pie charts |
| `water_balance` | 5 | Sankey diagrams, butterfly charts |
| `animations` | 3 | GIF animations of heads, flows, depth-to-water |
| `subsidence` | 2 | Subsidence bowls and correlations |
| `supply_demand` | 4 | Gap analysis, shortage plots |
| `cross_sections` | 2 | Multi-layer panels, animations |
| `connectivity` | 2 | Diversion networks, bypass diagrams |

Run all 58 plots against the sample model:

```bash
python examples/test_plots.py
# Output goes to test_output/
```

---

## 4. Comparing Multiple Runs

Use `collect_budgets` to build a unified DataFrame from multiple model runs:

```python
from iwfm.io import collect_budgets

runs = {
    "baseline": "runs/baseline/Results/GW.hdf",
    "scenario_a": "runs/scenario_a/Results/GW.hdf",
    "scenario_b": "runs/scenario_b/Results/GW.hdf",
}

combined = collect_budgets(runs, location=1)
# DataFrame with a 'run' column identifying each scenario
print(combined.head())
```

See `examples/06_multi_run_budgets.py` for a full example.

---

## Next Steps

- Browse the [API Reference](api-reference.md) for all public functions
- Explore the [Plot Gallery](plotting.md) for visualization examples
- Run `examples/01_read_inputs.py` through `06_multi_run_budgets.py` for hands-on demos
- See `docs/TEST_PLOTS_RESULTS.md` for known DLL/inquiry-mode limitations
