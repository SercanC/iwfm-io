# IWFM Python Packages — a Comparison

Three open-source Python packages work with IWFM models. They overlap
less than their names suggest, and many workflows benefit from more
than one. This page compares them factually so you can pick the right
tool; corrections are welcome via issues/PRs.

| | **iwfm-io** (this package) | **PyWFM** ([SGMOModeling/PyWFM](https://github.com/SGMOModeling/PyWFM)) | **iwfm** ([cfbrush/iwfm](https://github.com/cfbrush/iwfm)) |
|---|---|---|---|
| Author / origin | Sercan Ceyhan | Tyler Hatch — hosted by DWR's Sustainable Groundwater Management Office | Charles Brush (Hydrolytics; formerly DWR C2VSim lead) |
| Core approach | Library API: parse model **files** into pandas/GeoDataFrames; DLL optional | ctypes wrapper around the IWFM **DLL** — all data via DLL calls | Utility toolbox + CLI: ~180 single-purpose functions, mostly file→file converters |
| Import / install | `pip install iwfm-io` → `import iwfm_io` | PyPI `iwfm-pywfm` / conda `cadwr-sgmo::pywfm` → `import pywfm` | source install (`pip install -e`) → `import iwfm` |
| License | Apache-2.0 (DLL release assets: GPL-2.0, DWR) | MIT | see repo |
| **Platforms** | **any OS** for I/O, analysis, plotting (DLL wrapper Windows-only) | **Windows only** (DLL dependency; Linux experimental) | any OS |
| Reads IWFM text inputs without the DLL | ✅ all subsystems, 2015-era and 2024.x formats | ❌ (DLL required for everything) | ✅ broad coverage |
| Reads budget/zbudget/heads outputs without the DLL | ✅ HDF5 + text | ❌ (via `IW_Budget_*` DLL calls) | ✅ (HDF5 CLI group, headall tools) |
| Writes / edits input files | ✅ full reader↔writer round-trip | ❌ | partial (targeted writers/generators) |
| Scenario workflow | ✅ `create_scenario → run_model → compare_models` | ❌ (but can step a live simulation via DLL) | partial (new-file generators, land-use scenario tools) |
| Live simulation control (step a run from Python) | via DLL wrapper | ✅ (its core strength; `simulate_all`, per-interval stepping) | via its DLL subpackage |
| Plotting | 58 functions, 13 modules ([gallery](GALLERY.md)) | 2 (`plot_nodes`, `plot_elements`) | plot module (maps/hydrographs utilities) |
| Calibration / PEST utilities | ❌ (planned) | ❌ | ✅ 15 CLI commands (obs `.smp`, sim-vs-obs stats) |
| GIS export | ❌ (planned; GeoDataFrames via `[geo]` extra) | ❌ | ✅ (shapefiles, Surfer, webmaps) |
| Model subsetting (extract a submodel) | ❌ | ❌ | ✅ |
| DLL handling | optional; `download_dll()` (sha256-verified GitHub release assets), multi-version management | required; CLI downloads official builds from CNRA; one DLL per environment | bundles a 2015-era DLL in-repo |
| Pandas DataFrame outputs | ✅ throughout (+ GeoDataFrames) | ✅ for time series | mostly CSV/table files |
| AI/agent support | `describe()` summaries, agents guide, Claude Code skill | ❌ | LLM-supervisor optional extra |
| Validation story | tested against DWR C2VSimFG v1.5 incl. byte-identical rerun of the official simulation; CI on Ubuntu+Windows | DWR-org hosting; version-paired conda builds | ~4,760 tests |
| Docs | README, quickstart, API reference, plot gallery, agents guide | Sphinx site (tutorial + full API reference) | README + examples |

## Which should you use?

- **Analyze existing model runs, on any OS, with DataFrames** — iwfm-io.
- **Drive a live IWFM simulation step-by-step from Python on Windows**
  (couple IWFM to another model, adjust pumping mid-run) — PyWFM is
  purpose-built for that; iwfm-io's DLL wrapper covers similar ground
  with file-based fallbacks.
- **PEST calibration prep, shapefile exports, model subsetting, or
  California data plumbing (CDEC/DETAW)** — cfbrush/iwfm has mature
  utilities none of the others match.

They can coexist in one environment: the import names (`iwfm_io`,
`pywfm`, `iwfm`) no longer collide as of iwfm-io 2.0.

*Comparison last verified 2026-07-09 against PyWFM v0.2.6 and
cfbrush/iwfm as of July 2026. If you maintain one of these packages and
spot an error, please open an issue.*
