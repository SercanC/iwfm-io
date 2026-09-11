"""Working-directory dependence of the result getters (script a08).

The DLL opens the Results HDFs lazily, relative to the process CWD at the
first query — not relative to the simulation main it was opened with.
Expected: the same heads from any CWD, and a model with no Results must
never serve another model's files just because the CWD points there.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GW_BUDGET, GW_HYD, attempt, frame_stats, main, paths  # noqa: E402


def _heads_from_cwd(model_dir, cwd):
    from iwfm_io.dll import IWFMModel
    p = paths(model_dir)

    def go():
        os.chdir(cwd)
        m = IWFMModel(p["pp"], p["sim"], is_for_inquiry=True)
        os.chdir(cwd)
        r = frame_stats(m.heads_df(1))
        r["cwd_after"] = os.getcwd()
        m.close()
        return r
    return attempt(go)


def case_heads_cwd_simulation(model_dir):
    """Control: CWD = Simulation/ (what the executables do)."""
    return _heads_from_cwd(model_dir, paths(model_dir)["sim_dir"])


def case_heads_cwd_model_root(model_dir):
    return _heads_from_cwd(model_dir, str(paths(model_dir)["root"]))


def case_heads_cwd_preprocessor(model_dir):
    return _heads_from_cwd(model_dir, str(Path(paths(model_dir)["pp"]).parent))


def case_heads_cwd_system_root(model_dir):
    return _heads_from_cwd(model_dir, os.environ.get("SystemRoot", "C:\\Windows"))


def case_heads_cwd_temp(model_dir):
    """A CWD that is writable but unrelated to the model."""
    d = Path(model_dir).parent / "elsewhere"
    d.mkdir(exist_ok=True)
    return _heads_from_cwd(model_dir, str(d))


def case_cross_model_leak(model_dir):
    """A second model copy with NO Results, queried while the CWD is the
    first copy's Simulation folder: it must raise (or serve nothing), and
    must not produce the first model's heads."""
    from iwfm_io.dll import IWFMModel
    p = paths(model_dir)
    m2 = Path(model_dir).parent / "model_no_results"
    if m2.exists():
        shutil.rmtree(m2)
    shutil.copytree(p["root"] / "Preprocessor", m2 / "Preprocessor")
    shutil.copytree(p["root"] / "Simulation", m2 / "Simulation")
    (m2 / "Results").mkdir()

    def go():
        m = IWFMModel(str(m2 / "Preprocessor" / "PreProcessor_MAIN.IN"),
                      str(m2 / "Simulation" / "Simulation_MAIN.IN"), is_for_inquiry=True)
        os.chdir(p["sim_dir"])
        r = {"heads": attempt(lambda: frame_stats(m.heads_df(1))),
             "budget": attempt(lambda: frame_stats(m.budget_df(GW_BUDGET, 1))),
             "hyd": attempt(lambda: frame_stats(m.hydrograph_df(GW_HYD, 1, 1)))}
        r["model2_results_after"] = sorted(x.name for x in (m2 / "Results").iterdir())
        m.close()
        return r
    return attempt(go)


def case_files_modified_by_inquiry(model_dir):
    """Which files does an inquiry open + a heads/budget/hydrograph query
    rewrite? (Documents why every case works on a copy.)"""
    root = paths(model_dir)["root"]

    def snapshot():
        return {str(f.relative_to(root)): (f.stat().st_size, f.stat().st_mtime_ns)
                for f in root.rglob("*") if f.is_file()}

    def go():
        from common import open_model
        before = snapshot()
        m = open_model(model_dir)
        m.heads_df(1)
        m.budget_df(GW_BUDGET, 1)
        m.hydrograph_df(GW_HYD, 1, 1)
        m.close()
        after = snapshot()
        changed = sorted(k for k in after if k not in before or after[k] != before[k])
        return {"changed": changed, "n_changed": len(changed)}
    return attempt(go)


if __name__ == "__main__":
    main(globals())
