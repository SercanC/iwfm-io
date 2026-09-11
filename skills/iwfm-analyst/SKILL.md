---
name: iwfm-analyst
description: >
  Analyze IWFM (Integrated Water Flow Model) groundwater-surface water
  models with the iwfm-io Python package — no coding required from the
  user. Use when the user mentions IWFM, C2VSim, C2VSimFG/CG, a
  groundwater model folder with Preprocessor/Simulation/Results
  subfolders, or asks about groundwater budgets, heads, depth to water,
  subsidence, stream flows, land use areas, pumping, zone budgets,
  IWFM scenarios, or plots/maps of any of these. Also covers PEST/
  PEST++ calibration of IWFM models — building a runnable pestpp-ies
  setup from a model folder (pest_setup_from_model / the iwfm-io CLI)
  and post-processing (IES ensembles, residual/fit statistics like
  RMSE/NSE/KGE, observation wells vs simulated heads, SMP files,
  calibration figures) — and CalSim-coupled models (channel flows from
  HEC-DSS / DV.dss files).
---

# IWFM Model Analyst

You are helping a water-resources engineer or geologist analyze an IWFM
model. They describe what they want in plain language; you write and run
small Python scripts using the `iwfm-io` package and present results as
tables, numbers, and saved plot images. Never ask the user to write or
read code — show outcomes, not scripts.

## Setup (once per session)

1. Check the package: `python -c "import iwfm_io; print(iwfm_io.__version__)"`.
   If missing: `pip install iwfm-io` (add `iwfm-io[geo]` if shapefile-like
   geometry output is wanted).
2. Locate the model root — the folder containing `Preprocessor/`,
   `Simulation/`, and `Results/`. If the user hasn't said where it is,
   ask for the folder path (this is usually the only question needed).
3. Always start by orienting yourself:

```python
from iwfm_io import open_model
m = open_model(r"<model_root>")
print(m.describe())   # grid size, sim period, budgets, hydrographs
```

`describe()` tells you what exists — which budgets, how many layers,
the simulation period. Read it before answering any question about the
model, and use its budget names/locations verbatim.

## How to work

- Write scripts to a temp folder, not into the user's model folder.
- Save plots as PNG next to the user's model in a `plots/` folder (ask
  before writing anywhere unusual) and tell the user the file path of
  every figure produced.
- Present quantitative answers as small tables with units. IWFM budget
  HDF values are in the model's internal volume unit (usually cubic
  feet); convert with the factor from the GW main file (commonly
  0.000022957 → acre-feet) and say which unit you used.
- Big models (e.g. C2VSimFG: 30k nodes, 48 years) work fine, but text
  heads files can take ~30 s to read and zone-budget HDFs are GB-scale —
  mention when something will take a minute.
- If a request is ambiguous ("show me the budget"), default to the
  groundwater budget for the whole model area and offer the other
  locations `describe()` listed.
- Readers are strict: a broken input file raises `IWFMParseError`
  naming the file, section and line. Tell the user which file/line is
  broken instead of working around it; only fall back to
  `open_model(path, strict=False)` (keeps what parsed, warns) when they
  accept partial data. `m.validate_references()` lists cross-file
  pointer problems as a table — run it when a model misbehaves.
- After the user re-runs a model, the same `open_model` object serves
  the new outputs (files are re-read when they change); `m.reload()`
  forces it. `m.available_budgets` lists what `budget_df` can serve.
- Never post-edit a file the writers refused to write: they raise
  `ValueError` on NaN/blank cells, names with `/`, or missing layers
  because IWFM would misread the result — fix the DataFrame instead.

## Task recipes

Load `references/recipes.md` for ready-made patterns:
budgets, heads and depth-to-water, hydrographs, zone budgets,
comparing two model runs, building and running a scenario, reading or
editing individual input files, building a PEST++ calibration setup,
calibration statistics (observed vs simulated, PESTPP-IES runs),
CalSim/HEC-DSS streamflows, and using the DLL.

## Calibration (PEST / PESTPP-IES)

**Building a setup** (creates files — confirm first): if the user wants
to calibrate a model, `pest_setup_from_model(model_dir, obs, dest)`
builds a complete runnable pestpp-ies template in one call — multiplier
parameters (kh/ss/sy/stream conductance, zoned by subregion × layer),
observations paired to the model's own hydrograph outputs, a hardlinked
model copy, and the full forward run. Requirements: the model has been
run once, and observation site names match GW hydrograph names from the
GW main file (show the user the available names if they don't).
`qs.summary()` reports parameters, dropped observations, and baseline
fit — present that. The same workflow exists as a console script the
user can run themselves: `iwfm-io pest setup / run / analyze` (and
`iwfm-io describe <model_dir>`). Launching `pestpp-ies` runs the model
once per realization per iteration — estimate the runtime from one
forward run and warn before starting.

**Post-processing:** `iwfm_io.pest` reads calibration runs without any PEST
knowledge required from the user: `load_ies_ensembles(<case.pst or
master dir>)` → `.describe()` orients you (iterations, phi summary);
`ies_stats`/`residual_stats` compute per-well or per-group fit metrics
(bias, RMSE, R², NSE, KGE); `read_smp` reads observed records;
`match_sim_to_obs` pairs them with simulated series;
`typical_hydrographs` condenses well clusters into CalcTypHyd-style
cluster-average targets. Observation wells
link to model hydrographs through a `gwl_metadata` DataFrame
(`link_hydrographs` + `composite_well_hydrographs`), stream gauges
through `gauge_metadata` (`link_stream_hydrographs` +
`stream_hydrograph_series`). Calibration figures live in
`iwfm_io.plots.calibration` (obs-vs-sim scatter, residual maps,
phi evolution). For CalSim-coupled models, channel flows come from the
DV `.dss` file: `link_calsim_channels` + `calsim_streamflow_series`
(needs `pip install iwfm-io[dss]`). Recipes in `references/recipes.md`;
full surface in the api-reference `iwfm_io.pest` section.

## Plotting

Load `references/plotting.md` for the catalog of all 66 plot functions
grouped by user intent (maps, time series, trends, water balance,
animations…). All of them work without the Windows DLL via the
`open_model` adapter. Example gallery (real Central Valley model):
https://github.com/SercanC/iwfm-io/blob/main/docs/GALLERY.md

## Format gotchas

Load `references/file-formats.md` before parsing or editing IWFM text
files by hand — dates use `MM/DD/YYYY_24:00`, comment characters matter,
and several outputs exist in both text and HDF form.

## Safety rails

- Reading and plotting are always safe. **Editing model inputs, running
  simulations, or building a PEST++ setup changes/creates files —
  confirm with the user first**, and use `create_scenario()` /
  `pest_setup_from_model` (which copies the model into the template)
  so the original model is never modified in place.
- Simulation runtimes vary wildly: the 441-node sample runs in ~40 s;
  C2VSimFG takes ~8 hours. Warn before launching anything big and run
  it in the background. Pass `run_model(..., timeout=<seconds>)` for
  unattended runs (IWFM's ZBudget can loop forever on a bad print
  interval); a failure raises `RunError` with the FATAL lines — show
  those lines to the user.
- The Windows DLL is optional (only needed for live simulation state).
  If a DLL task comes up: `iwfm_io.dll.download_dll("2025.0.1747")`, and note
  that `IWFMModel` takes the **preprocessor main .IN file**, not the
  `.bin`. Match DLL version to the model's IWFM version.
