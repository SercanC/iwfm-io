"""Example 10 — PEST++ calibration setup in one call (+ the iwfm-io CLI).

Builds a runnable pestpp-ies template from the sample model with
``pest_setup_from_model``: multiplier parameters (kh/ss/sy zoned by
subregion x layer, one global stream-conductance multiplier),
observations paired to the model's own GW hydrograph output, a
hardlinked model copy, and a generated forward run (apply -> run IWFM ->
extract). The observation-extraction step is then demonstrated against
the baseline Results — no IWFM executable run needed, so this example is
cross-platform and fast.

The same build is available from the command line::

    iwfm-io pest setup --model-dir .assets/sample_model \\
        --obs obs_heads.smp --dest pest_template --parameters kh ss sy strk
    iwfm-io pest run --template pest_template          # single check run
    iwfm-io pest run --template pest_template -n 8     # manager + 8 agents
    iwfm-io pest analyze pest_template

For the underlying building blocks (names, SMP, zones, pilot points,
weights, PestSetup, ...) see notebooks 09-10.

Usage:
    python examples/10_pest_calibration.py
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
if not (SAMPLE_MODEL / "Results" / "GWHyd.out").is_file():
    raise SystemExit("Sample model Results/GWHyd.out not found — run the "
                     "sample simulation once first (see example 08).")

import numpy as np
import pandas as pd


# ── 1. Observed heads ─────────────────────────────────────────────────────────
# In a real project these come from field measurements (an SMP or CSV
# with site, datetime, value — site names matching the GW main's
# hydrograph names). Here we synthesize them: sparse samples of the
# baseline hydrographs plus noise, so the "calibration" has a known
# answer (multipliers of 1.0).

from iwfm_io.readers.text_output import read_hydrograph_out
from iwfm_io.wells import normalize_hydrograph_output

hyd = normalize_hydrograph_output(
    read_hydrograph_out(SAMPLE_MODEL / "Results" / "GWHyd.out"))
rng = np.random.default_rng(42)
records = []
for site, hyd_id in [("GWHyd2", 2), ("GWHyd5", 5), ("GWHyd23", 23)]:
    series = hyd[hyd_id].iloc[10::45]          # sparse, irregular sampling
    records.append(pd.DataFrame({
        "site": site,
        "datetime": series.index,
        "value": series.values + rng.normal(0, 1.0, len(series)),
    }))
obs = pd.concat(records, ignore_index=True)
print(f"{len(obs)} observations at {obs['site'].nunique()} wells")


# ── 2. One call: model folder + observations → runnable template ──────────────

from iwfm_io.pest import pest_setup_from_model

template = Path(tempfile.mkdtemp(prefix="iwfm_pest_")) / "pest_template"
qs = pest_setup_from_model(
    SAMPLE_MODEL, obs, template,
    parameters=("kh", "ss", "sy", "strk"),   # aquifer multipliers + stream K
    zones="subregion",                       # one parameter per subregion x layer
    ies_num_reals=30,                        # pestpp-ies ensemble size
    noptmax=0,                               # first run = cheap check run
)

print("\nSetup summary:")
print(json.dumps(qs.summary(), indent=2, default=str))

print("\nParameters:")
print(qs.par_data[["parnme", "partrans", "parval1", "parlbnd",
                   "parubnd", "pargp"]].to_string(index=False))

print("\nBaseline fit per site (should be ~the injected noise):")
print(qs.stats[["n", "rmse", "mean_res", "r2", "nse"]].round(3))


# ── 3. What the template contains ─────────────────────────────────────────────

print("\nTemplate files:")
for p in sorted(template.iterdir()):
    print("  ", p.name + ("/" if p.is_dir() else ""))
# model/          — hardlinked copy of the model; the forward run modifies+runs it
# forward_run.py  — apply parameters -> run IWFM -> extract observations
# *.tpl / mult_*  — PEST templates + initial (all-1.0) multiplier value files
# *.pout.ins      — instruction file paired with the extract step's output


# ── 4. The extraction step, demonstrated against the baseline Results ─────────
# pestpp-ies invokes forward_run.py, whose last step re-extracts
# simulated values at the observation timestamps. Running IWFM takes
# ~9 minutes, so here we point the extract step at the baseline output
# instead — same code path, instant.

import shutil

shutil.copy(SAMPLE_MODEL / "Results" / "GWHyd.out",
            template / "model" / "Results" / "GWHyd.out")

from iwfm_io.pest import ObsFileSpec
from iwfm_io.pest.quickstart import run_extract

cwd = os.getcwd()
os.chdir(template)
try:
    run_extract()
finally:
    os.chdir(cwd)

extracted = ObsFileSpec(list(qs.paired["obsnme"])).read_output(
    template / "iwfm_cal_heads.pout")
match = np.allclose(extracted.values, qs.paired["simulated"].values,
                    rtol=1e-6)
print(f"\nextract step reproduces the setup-time pairing: {match}")


# ── 5. Next steps ─────────────────────────────────────────────────────────────

print(f"""
The template is ready to run (needs pestpp-ies on PATH + Windows for
the IWFM executables):

  iwfm-io pest run --template "{template}"          # noptmax=0 check run
  iwfm-io pest run --template "{template}" -n 8     # manager + 8 local agents
  iwfm-io pest analyze "{template}"                 # phi + diagnostics

To iterate: raise noptmax (edit the .pst or rebuild with noptmax=3),
adjust bounds/zones via pest_setup_from_model's arguments, or drop to
the full API (ParamSpec, ObsFileSpec, PestSetup — notebook 09) for
pilot points, budget observations, and weight balancing.
""")
