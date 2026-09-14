# iwfm-io notebooks

Twelve executable Jupyter notebooks covering every feature area of
`iwfm-io`, in the order a new user would adopt the library: read →
write → run → calibrate. Each notebook is self-contained, states its
requirements in the first cell, and ships fully executed so it can be
read on GitHub without running anything.

| # | Notebook | Covers | Requires |
|---|----------|--------|----------|
| 01 | [Quickstart](01_quickstart.ipynb) | `open_model`, `describe`, grid/heads/budget DataFrames, first maps | sample model |
| 02 | [Reading input files](02_reading_input_files.ipynb) | every `read_*` input reader — preprocessor, GW, streams, root zone, small watersheds, unsat zone, time series; pointer columns; validation | sample model |
| 03 | [Reading output files](03_reading_output_files.ipynb) | budget/head/hydrograph/zone-budget HDF readers, text-output readers, `collect_budgets` multi-run frame | sample model + Results |
| 04 | [Writing & round-trips](04_writing_and_roundtrips.ipynb) | `write_*` mirrors, read → edit DataFrame → write, `base_dir`, the IWFM writer quirks, exe round-trip proof | sample model |
| 05 | [DLL wrapper](05_dll_wrapper.ipynb) | DLL version management + `download_dll`, `IWFMModel`, `IWFMBudget`, `IWFMZBudget`, type IDs, inquiry-mode limits | **Windows x64** + sample model |
| 06 | [Scenarios & running models](06_scenarios_and_running_models.ipynb) | `create_scenario` + change factories, `link_unchanged` hardlinks, `run_model`, `compare_models`, head/budget differences | **Windows** + sample model Bin |
| 07 | [Plotting gallery](07_plotting_gallery.ipynb) | curated tour of the 66-function plot library + the reusable map primitives | sample model + Results |
| 08 | [Wells, gauges & metadata](08_wells_gauges_metadata.ipynb) | `gwl_metadata`/`gauge_metadata` schemas, hydrograph linking, compositing, `build_well_mapping`, flow/stage extraction | sample model + Results |
| 09 | [PEST part 1 — building](09_pest_iwfm_setup.ipynb) | `pest_setup_from_model` one-call quickstart (+ `iwfm-io pest` CLI), then the pieces: obs names, SMP, `match_sim_to_obs`, budget obs, `ParamSpec` zones, `apply_parameters`, pilot points, `RatioChain`, `ObsFileSpec`, `balance_weights`, `PestSetup`, `setup_agents` | sample model + Results |
| 10 | [PEST part 2 — results](10_pest_results_analysis.ipynb) | `load_ies_ensembles`, phi/ensemble access, `ies_stats`/`rei_stats`, `diagnose_ies`, calibration figures, derived observations, finals reruns | none (self-generating) |
| 11 | [CalSim / HEC-DSS](11_calsim_dss.ipynb) | writing + cataloging DSS, `read_dss_timeseries`, end-of-period convention, `cfs_to_taf`, `link_calsim_channels`, `calsim_streamflow_series`, PEST wiring | `pip install iwfm-io[dss]` |
| 12 | [GIS & VTK exports](12_gis_exports.ipynb) | `export_gis`/`to_gis` to GeoPackage & shapefiles, per-layer `*_gdf` builders, CRS, joining heads/DTW/zonations onto layers, spatial joins; `export_vtk`/`to_vtk` 3D layered mesh + `export_vtk_timeseries` heads animation for ParaView | sample model + `pip install iwfm-io[geo]` (VTK part needs no extra) |

## Getting the sample model

Notebooks 01–09 use the IWFM sample model (441 nodes, 400 elements,
2 layers, 10-year daily run). In the development repo it lives at
`.assets/sample_model/`. Otherwise download `sample_model.zip` from the
[GitHub releases](https://github.com/SercanC/iwfm-io/releases), extract
it anywhere, and point the environment variable at it:

```
set IWFM_SAMPLE_MODEL=C:\path\to\sample_model     (Windows)
export IWFM_SAMPLE_MODEL=/path/to/sample_model    (bash)
```

Every notebook also finds `.assets/sample_model/` automatically when run
from inside the repo.

## Running

```
pip install iwfm-io[geo] jupyterlab
jupyter lab notebooks/
```

Notebooks 05 and 06 require Windows (the DLL and the IWFM executables);
everything else is cross-platform. All notebooks write scratch files to
a temporary directory and clean up after themselves.
