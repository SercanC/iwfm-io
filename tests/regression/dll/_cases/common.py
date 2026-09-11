"""Shared helpers for the DLL hostile-QA regression cases.

Every case module in this folder is a *script*: ``test_dllqa.py`` runs
``python <module>.py <case_name> <model_dir>`` in a fresh interpreter,
because the attacks reproduced here can kill the process (access
violations, heap corruption, Fortran ``STOP``).  The script prints a
single ``RESULT: <json>`` line describing what happened and exits 0;
anything else (no RESULT line, nonzero exit, timeout) is a crash.

Nothing here imports the DLL wrapper at module level, so the modules
stay importable on every platform.
"""
from __future__ import annotations

import faulthandler
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]          # _cases -> dll -> regression -> tests -> repo
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Simulation window of the sample model (first output stamp .. last).
B, E = "10/01/1990_24:00", "09/30/2000_24:00"
#: Budget type ids (``BudgetTypeID.GW`` / ``.LWU``) — constant across every
#: published IWFM build, so the cases need not run ``load_all_type_ids``.
GW_BUDGET = 3001
LWU_BUDGET = 4001
#: Hydrograph location types of the sample model.
GW_HYD, STREAM_HYD = 9, 12
N_NODES, N_ELEMENTS, N_LAYERS = 441, 400, 2

_ACCESS_VIOLATION_MARK = "exception:"   # ctypes renders every SEH fault as OSError("exception: ...")


# ----------------------------------------------------------------------
# Model helpers
# ----------------------------------------------------------------------

def paths(model_dir):
    """Return the main-file paths of a sample-model copy."""
    root = Path(model_dir)
    return {
        "root": root,
        "pp": str(root / "Preprocessor" / "PreProcessor_MAIN.IN"),
        "sim": str(root / "Simulation" / "Simulation_MAIN.IN"),
        "sim_dir": str(root / "Simulation"),
        "results": root / "Results",
    }


def open_model(model_dir, chdir=True, **kw):
    """Open the copy in inquiry mode (the DLL opens Results HDFs lazily,
    relative to the CWD at first query — so chdir to Simulation/ like
    the real executables do)."""
    from iwfm_io.dll import IWFMModel
    p = paths(model_dir)
    kw.setdefault("is_for_inquiry", True)
    m = IWFMModel(p["pp"], p["sim"], **kw)
    if chdir:
        os.chdir(p["sim_dir"])
    return m


def scratch_dir(model_dir, name="scratch"):
    """A writable folder next to the model copy (inside the test's tmp tree)."""
    d = Path(model_dir).parent / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def zbudget_file(model_dir):
    """Path of the (optional, 100 MB) UnsatZone zone-budget HDF, or None."""
    f = Path(model_dir) / "Results" / "UnsatZone_ZBud.hdf"
    return str(f) if f.is_file() else None


def skipped(reason):
    return {"outcome": "skipped", "reason": reason}


# ----------------------------------------------------------------------
# Result helpers
# ----------------------------------------------------------------------

def jsonable(v):
    """Convert numpy / pandas / tuple values into JSON-serialisable ones."""
    import numpy as np
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [jsonable(x) for x in (sorted(v, key=repr) if isinstance(v, (set, frozenset)) else v)]
    if isinstance(v, np.ndarray):
        return jsonable(v.tolist())
    if isinstance(v, np.generic):
        return jsonable(v.item())
    if isinstance(v, float):
        if v != v:
            return "nan"
        if v in (float("inf"), float("-inf")):
            return "inf" if v > 0 else "-inf"
        return v
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    if isinstance(v, Path):
        return str(v)
    return repr(v)


def describe_exc(e):
    msg = str(e)
    return {
        "outcome": "raised",
        "exc_type": type(e).__name__,
        "exc_msg": msg[:400],
        "access_violation": isinstance(e, OSError) and msg.startswith(_ACCESS_VIOLATION_MARK),
    }


def attempt(fn):
    """Run *fn* and describe the outcome (never raises)."""
    try:
        return {"outcome": "returned", "value": jsonable(fn())}
    except BaseException as e:      # noqa: BLE001 — the point is to record anything
        return describe_exc(e)


def stats(arr):
    """Compact numeric summary of an array."""
    import numpy as np
    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "shape": list(a.shape),
        "mean": float(np.nanmean(a)),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
        "any_nan": bool(np.isnan(a).any()),
    }


def frame_stats(df):
    out = {"shape": list(df.shape)}
    if len(df):
        out["idx0"] = str(df.index[0])
        out["idxN"] = str(df.index[-1])
    if df.size:
        out.update({k: v for k, v in stats(df.values).items() if k in ("mean", "min", "max", "any_nan")})
    return out


# ----------------------------------------------------------------------
# Script entry point
# ----------------------------------------------------------------------

def main(namespace):
    """``python <case_module>.py <case_name> <model_dir>`` -> ``RESULT: {...}``."""
    faulthandler.enable()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "--list"):
        names = sorted(k[len("case_"):] for k in namespace if k.startswith("case_"))
        print("\n".join(names))
        return
    name = sys.argv[1]
    model_dir = sys.argv[2] if len(sys.argv) > 2 else ""
    fn = namespace.get(f"case_{name}")
    if fn is None:
        print(f"RESULT: {json.dumps({'outcome': 'no_such_case', 'name': name})}", flush=True)
        os._exit(0)
    t0 = time.time()
    try:
        result = fn(model_dir)
        if not isinstance(result, dict) or "outcome" not in result:
            result = {"outcome": "returned", "value": jsonable(result)}
    except BaseException as e:      # noqa: BLE001
        result = describe_exc(e)
        result["outcome"] = "setup_error"
        result["traceback"] = traceback.format_exc()[-2000:]
    result["elapsed"] = round(time.time() - t0, 2)
    sys.stdout.flush()
    print("RESULT: " + json.dumps(jsonable(result)), flush=True)
    # os._exit: skip interpreter teardown — a wedged HDF5 library or a
    # stuck worker thread must not turn a recorded result into a hang.
    os._exit(0)
