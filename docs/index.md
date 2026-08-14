# iwfm-io Documentation

Python file I/O, DLL wrapper, and visualization library for the **Integrated Water Flow Model (IWFM)**.

## Contents

| Document | Description |
|----------|-------------|
| [Quick Start Tutorial](quickstart.md) | Install, read files, query the DLL, and make your first plot |
| [API Reference](api-reference.md) | Full listing of all public functions and classes (incl. `iwfm_io.pest` and `iwfm_io.dss`) |
| [Agents & Scripting Guide](agents.md) | Compact recipes for driving iwfm-io from code or AI agents |
| [Plot Gallery](plotting.md) | 58 visualization functions across 13 modules |
| [Example Gallery](GALLERY.md) | All 58 plots rendered from DWR's C2VSimFG v1.5 |
| [Package Comparison](COMPARISON.md) | iwfm-io vs PyWFM vs cfbrush/iwfm |
| [TEST_PLOTS_RESULTS.md](TEST_PLOTS_RESULTS.md) | Detailed plot-test pass/fail results |
| [DLL_INQUIRY_MODE_LIMITS.md](DLL_INQUIRY_MODE_LIMITS.md) | DLL inquiry-mode limitations and file-based workarounds |
| [DLL_RETURN_FLOW_SKIP_BUG.md](DLL_RETURN_FLOW_SKIP_BUG.md) | Known DLL bug documentation |

## Package Overview

`iwfm-io` has four layers that can be used independently:

```
┌───────────────────────────────────────────────────────┐
│  iwfm_io.plots    58 matplotlib visualization fns     │
├───────────────────────────────────────────────────────┤
│  iwfm_io.pest     PEST(++) calibration support        │
│                   obs codec · IES loader · stats ·    │
│                   parameterization · PestSetup        │
├───────────────────────────────────────────────────────┤
│  iwfm_io.dll      DLL wrapper (Windows x64 only)      │
│                   IWFMModel · IWFMBudget · IWFMZBudget│
├───────────────────────────────────────────────────────┤
│  iwfm_io          Pure-Python file I/O                │
│                   Readers · Writers · IOModelAdapter ·│
│                   wells/gauges metadata · HEC-DSS     │
│                   (cross-platform, no DLL needed)     │
└───────────────────────────────────────────────────────┘
```

**Choose your path:**

- **Just need to read/write IWFM files?** Use `iwfm_io` — works on any OS, no DLL required.
- **Need live model queries?** Use `iwfm_io.dll.IWFMModel` — requires Windows + the IWFM DLL.
- **Want visualizations?** The plot library works with either `IWFMModel` or `IOModelAdapter`.
- **Calibrating with PEST(++)?** `iwfm_io.pest` builds the interface and post-processes the results; `iwfm_io.dss` (optional `[dss]` extra) reads CalSim/HEC-DSS streamflows.

## Examples

Runnable scripts in the `examples/` directory:

| File | Requires | What it shows |
|------|----------|---------------|
| `01_read_inputs.py` | .assets/sample_model | All `iwfm_io` input file readers |
| `02_read_outputs.py` | .assets/sample_model/Results | HDF5 and text output readers |
| `03_roundtrip.py` | .assets/sample_model | Read → modify → write round-trips |
| `04_dll_wrapper.py` | Windows + DLL | `IWFMModel`, `IWFMBudget`, `IWFMZBudget` |
| `05_plotting.py` | .assets/sample_model | Plotting gallery — all 13 modules |
| `06_multi_run_budgets.py` | multiple runs | Multi-run unified budget DataFrames |
| `07_compare_models.py` | .assets/sample_model | `compare_models()` baseline vs scenario diffs |
| `08_run_scenario.py` | Windows + sample_model/Bin | `create_scenario()` + `run_model()` loop |
| `09_full_input_datasets.py` | .assets/sample_model | Every input dataset as a DataFrame; edit + write back |
