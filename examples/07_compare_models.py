"""Example 07 — Comparing two model versions.

Demonstrates the three levels of model comparison:

1. diff_model_files()  — which files differ between two model folders?
2. compare_models()    — one-call report: files + grid + head statistics
3. head_difference() / budget_difference() — aligned B − A DataFrames

The sample model is compared against a scratch copy with one edited
input file, so the file diff has something to find. With two real model
versions, just point the functions at the two root folders.

Usage:
    python examples/07_compare_models.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from iwfm_io import (
    budget_difference,
    compare_models,
    diff_model_files,
    head_difference,
    open_model,
)

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"

if not SAMPLE_MODEL.exists():
    raise SystemExit(f"Sample model not found: {SAMPLE_MODEL}")


# ── Make a "version 2" of the model inputs (edit one value) ──────────────────

workdir = Path(tempfile.mkdtemp(prefix="iwfm_compare_"))
model_v2 = workdir / "sample_model_v2"
for sub in ("Preprocessor", "Simulation"):
    shutil.copytree(SAMPLE_MODEL / sub, model_v2 / sub)

strata = model_v2 / "Preprocessor" / "Strata.dat"
strata.write_text(strata.read_text().replace("1.0", "2.0", 1))
print(f"Created modified copy: {model_v2}")


# ── 1. Which files differ? ────────────────────────────────────────────────────

print("\n=== diff_model_files (inputs only) ===")
d = diff_model_files(SAMPLE_MODEL, model_v2,
                     subdirs=["Preprocessor", "Simulation"])
print(f"  compared:  {d['n_compared']} files")
print(f"  changed:   {d['changed']}")
print(f"  only in a: {d['only_in_a']}")
print(f"  only in b: {d['only_in_b']}")


# ── 2. One-call comparison report ────────────────────────────────────────────

print("\n=== compare_models ===")
report = compare_models(SAMPLE_MODEL, model_v2,
                        file_subdirs=["Preprocessor", "Simulation"])
print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))
print("  changed files:", report["files"]["changed"])
# heads is None here because the modified copy has no Results folder.


# ── 3. Numeric differences (self-comparison for demonstration) ───────────────

print("\n=== head_difference / budget_difference ===")
diff = head_difference(SAMPLE_MODEL, SAMPLE_MODEL, layer=1)
print(f"  head difference frame: {diff.shape} (max |diff| = "
      f"{abs(diff.values).max():.3f} — identical runs)")

bdiff = budget_difference(SAMPLE_MODEL, SAMPLE_MODEL, "GW",
                          location="ENTIRE MODEL AREA", interval="1YEAR")
print(f"  annual GW budget difference: {bdiff.shape}")

# To map a head difference between two real runs:
#
#   from iwfm_io.plots import plot_contour_map
#   diff = head_difference("runs/baseline", "runs/scenario", layer=1)
#   plot_contour_map(open_model("runs/baseline"), diff.iloc[-1].values,
#                    cmap="coolwarm", label="Head change (ft)",
#                    title="Scenario minus Baseline — end of simulation")

shutil.rmtree(workdir)
print("\nDone.")
