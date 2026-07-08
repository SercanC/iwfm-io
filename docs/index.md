# iwfm-io Documentation

Python file I/O, DLL wrapper, and visualization library for the **Integrated Water Flow Model (IWFM)**.

## Contents

| Document | Description |
|----------|-------------|
| [Quick Start Tutorial](quickstart.md) | Install, read files, query the DLL, and make your first plot |
| [API Reference](api-reference.md) | Full listing of all public functions and classes |
| [Agents & Scripting Guide](agents.md) | Compact recipes for driving iwfm-io from code or AI agents |
| [Plot Gallery](plotting.md) | 58 visualization functions across 13 modules |
| [TEST_PLOTS_RESULTS.md](TEST_PLOTS_RESULTS.md) | Detailed plot-test pass/fail results |
| [DLL_RETURN_FLOW_SKIP_BUG.md](DLL_RETURN_FLOW_SKIP_BUG.md) | Known DLL bug documentation |

## Package Overview

`iwfm-io` has three layers that can be used independently:

```
┌──────────────────────────────────────────────────────┐
│  iwfm/plots/   58 matplotlib visualization fns   │
├──────────────────────────────────────────────────────┤
│  iwfm              DLL wrapper (Windows x64 only)    │
│                    IWFMModel · IWFMBudget · IWFMZBud │
├──────────────────────────────────────────────────────┤
│  iwfm.io           Pure-Python file I/O              │
│                    Readers · Writers · IOModelAdapter │
│                    (cross-platform, no DLL needed)    │
└──────────────────────────────────────────────────────┘
```

**Choose your path:**

- **Just need to read/write IWFM files?** Use `iwfm.io` — works on any OS, no DLL required.
- **Need live model queries?** Use `iwfm.IWFMModel` — requires Windows + the IWFM DLL.
- **Want visualizations?** The plot library works with either `IWFMModel` or `IOModelAdapter`.

## Examples

Runnable scripts in the `examples/` directory:

| File | Requires | What it shows |
|------|----------|---------------|
| `01_read_inputs.py` | .assets/sample_model | All `iwfm.io` input file readers |
| `02_read_outputs.py` | .assets/sample_model/Results | HDF5 and text output readers |
| `03_roundtrip.py` | .assets/sample_model | Read → modify → write round-trips |
| `04_dll_wrapper.py` | Windows + DLL | `IWFMModel`, `IWFMBudget`, `IWFMZBudget` |
| `05_plotting.py` | .assets/sample_model | Plotting gallery — all 13 modules |
| `06_multi_run_budgets.py` | multiple runs | Multi-run unified budget DataFrames |
