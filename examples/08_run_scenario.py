"""Example 08 — The full scenario loop: modify → run → compare.

Creates a scenario from the sample model (simulation shortened to two
years), runs the complete IWFM toolchain on it, and compares the results
against the baseline. Requires Windows and the sample-model executables
in .assets/sample_model/Bin/.

Usage:
    python examples/08_run_scenario.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"

if not SAMPLE_MODEL.exists():
    raise SystemExit(f"Sample model not found: {SAMPLE_MODEL}")
if os.name != "nt" or not (SAMPLE_MODEL / "Bin").is_dir():
    raise SystemExit("Running models requires Windows and the IWFM "
                     "executables in the sample model's Bin/ folder.")

from iwfm_io import run_model
from iwfm_io import compare_models, create_scenario, open_model, set_keyed_value


# ── 1. Create the scenario ────────────────────────────────────────────────────

scenario = create_scenario(
    SAMPLE_MODEL,
    Path(tempfile.mkdtemp(prefix="iwfm_")) / "two_year_run",
    changes=[
        set_keyed_value("Simulation/Simulation_MAIN.IN",
                        "EDT", "09/30/1992_24:00"),
    ],
)
print(f"Scenario created: {scenario}")


# ── 2. Run the IWFM toolchain ─────────────────────────────────────────────────

results = run_model(
    scenario,
    steps=("preprocessor", "simulation", "budget", "zbudget"),
    timeout=3600,
)


# ── 3. Open the results and compare with the baseline ────────────────────────

model = open_model(scenario)
print("\nScenario:", json.dumps(model.describe()["simulation"], indent=2))

report = compare_models(SAMPLE_MODEL, scenario,
                        file_subdirs=["Preprocessor", "Simulation"])
print("Changed input files:", report["files"]["changed"])
print("Head statistics (common period, layer 1):",
      json.dumps(report["heads"]["layer_1"], indent=2))
