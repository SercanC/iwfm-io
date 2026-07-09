# Using iwfm-io Programmatically (AI Agents & Scripts)

This page is a compact orientation for driving `iwfm-io` from code —
written with AI agents in mind, but equally useful for scripted analysis.

## Orient first: open the model and describe it

```python
from iwfm_io import open_model

model = open_model("path/to/model_root")   # no DLL, any OS
summary = model.describe()                 # JSON-serializable dict
```

`describe()` returns everything needed to plan further queries:

```json
{
  "grid":       {"n_nodes": 441, "n_elements": 400, "n_layers": 2,
                 "n_subregions": 2, "subregion_names": {"1": "Region1"}},
  "streams":    {"n_reaches": 3, "n_stream_nodes": 23},
  "lakes":      {"n_lakes": 1},
  "simulation": {"begins": "09/30/1990_24:00", "ends": "09/30/2000_24:00",
                 "timestep": "1DAY"},
  "results": {
    "heads": ".../Results/GWHeadAll.hdf",
    "budgets": {"GW": {"path": "...", "locations": ["ENTIRE MODEL AREA",
                                                    "Region1 (SR1)"]}},
    "hydrographs": {"GWHyd": "..."},
    "zbudgets": {"GW_ZBud": "..."}
  }
}
```

Use the `budgets.*.locations` lists verbatim as the `location` argument
to `budget_df()` — never guess location names.

## Query data (everything returns pandas/geopandas)

```python
model.nodes_df()                    # GeoDataFrame: node_id, x, y, geometry
model.elements_df()                 # GeoDataFrame: element polygons
model.stratigraphy_df()             # DataFrame: layer geometry per node
model.heads_df(layer=1)             # DataFrame(DatetimeIndex), col per node
model.budget_df("GW", location=1)   # DataFrame(DatetimeIndex) budget terms
model.budget_df("GW", location="Region1 (SR1)", interval="1MON")
model.hydrograph_df("GWHyd")        # DataFrame(DatetimeIndex)
```

## Modify a model (read → change → write)

Every reader in `iwfm_io` has a matching writer for round-trips:

```python
from iwfm_io import read_nodes, write_nodes

nodes = read_nodes("Preprocessor/NodeXY.dat")
nodes.data["x"] += 100.0
write_nodes(nodes, "Preprocessor/NodeXY_shifted.dat")
```

Validate cross-file consistency before running IWFM:

```python
from iwfm_io import read_preprocessor, validate_preprocessor
errors = validate_preprocessor(read_preprocessor("Preprocessor/PreProcessor_MAIN.IN"))
```

## Run a scenario (Windows only)

The full what-if loop — copy, modify, run, compare:

```python
from iwfm_io import run_model
from iwfm_io import create_scenario, set_keyed_value, compare_models

scenario = create_scenario(
    "runs/baseline", "runs/scenario_a",
    changes=[set_keyed_value("Simulation/Simulation_MAIN.IN",
                             "EDT", "09/30/1995_24:00")],
)
results = run_model(scenario, steps=("preprocessor", "simulation", "budget"))
# each RunResult has .success, .elapsed, .errors; run_model raises on failure

report = compare_models("runs/baseline", scenario)
```

`open_model` reads fresh run outputs directly — heads fall back to
`GWHeadAll.out` (text) when no HDF version exists yet.

## Compare two model versions

```python
from iwfm_io import compare_models, diff_model_files, head_difference

report = compare_models("runs/baseline", "runs/scenario")
report["files"]["changed"]        # input files that were edited (checksums)
report["grid"]["identical"]       # same mesh?
report["heads"]["layer_1"]        # rmse, max_abs_diff + node/date where it occurs
report["budgets"]["common"]       # budgets available in both

# Aligned B − A frames for analysis or difference maps:
diff = head_difference("runs/baseline", "runs/scenario", layer=1)
from iwfm_io.plots import plot_contour_map
plot_contour_map(open_model("runs/baseline"), diff.iloc[-1].values,
                 cmap="coolwarm", label="Head change (ft)")
```

For many runs at once, the `collect_*` functions return tidy long-form
DataFrames (`run, location, datetime, component, value`) ready for
`groupby`/pivot; pass `max_workers=8` to read runs concurrently.

## Plot

All 58 functions in `iwfm_io.plots` accept the object returned by
`open_model()` (or a DLL `IWFMModel`) and return `(fig, ax)`; most take
`save_path=` to write a PNG directly:

```python
from iwfm_io.plots import maps, timeseries
maps.plot_gw_head_contour(model, layer=1, save_path="heads.png")
```

## Live DLL queries (Windows only)

For solver-state data the file readers can't provide (stream flows at a
timestep, supply/demand adjustment), use the DLL wrapper — it has the
same `describe()` / `*_df()` interface:

```python
import iwfm_io

with iwfm_io.dll.IWFMModel(
    preprocessor_file="Simulation/PreProcessor.bin",
    simulation_file="Simulation/Simulation_MAIN.IN",
    is_for_inquiry=True,
) as m:
    m.describe()
    m.heads_df(layer=1)  # via wrapper methods
```

## Conventions and gotchas

- **Dates** are strings in `MM/DD/YYYY_HH:MM` format; hour `24:00`
  means end of day (`"09/30/1990_24:00"` is the instant 1990-10-01 00:00).
  Convert with `iwfm_io.parse_iwfm_date` / `format_iwfm_date`.
- **Indices are 1-based** everywhere the IWFM file formats and DLL are
  involved (node IDs, layer numbers, budget locations).
- **Element connectivity** is 4 node IDs; `node4 == 0` means a triangle.
- **Inquiry mode** (`is_for_inquiry=True`) cannot provide tile drains,
  ag crops, supply requirements, or bypass counts — the DLL raises
  `IWFMError` ("partially instantiated"). `describe()` reports those
  sections as `None` instead of raising.
- `iwfm_io` never loads the DLL; it is safe on any OS and in sandboxes.
