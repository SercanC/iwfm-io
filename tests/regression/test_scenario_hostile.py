"""Hostile-QA regressions: scenario / run / compare / collect_* / HDF readers.

Imported from the 2026-09-09 hostile-QA pass. Every test asserts the
EXPECTED behaviour; ``xfail(strict=True)`` marks the ones that still
reproduce a defect on the current code. Tests that run the IWFM
executables carry the ``exe`` marker (skipped unless IWFM_RUN_EXE_TESTS=1).
"""
import shutil

import h5py
import numpy as np
import pandas as pd
import pytest

pytestmark = [pytest.mark.regression, pytest.mark.sample_model]


@pytest.fixture(scope="module")
def RESULTS(sample_model):
    return sample_model / "Results"


# --- 1. stale baseline budgets served as scenario results ------------------
def test_scenario_never_run_serves_baseline_budgets(tmp_path, sample_model):
    from iwfm_io import create_scenario, open_model, set_keyed_value
    sc = create_scenario(sample_model, tmp_path / "s", changes=[
        set_keyed_value("Simulation/Simulation_MAIN.IN", "EDT", "12/31/1990_24:00")])
    assert not any((sc / "Results").iterdir())          # nothing was ever run
    m = open_model(sc)
    d = m.describe()
    # Expected: no budgets (or a clear 'stale/copied' flag). Observed: 11 text
    # budgets copied from the baseline's Budget/*.bud, 10 water years of data
    # for a scenario whose simulation period ends 12/31/1990.
    assert d["results"]["budgets"] == {}, d["results"]["budgets"]["GW"]


# --- 2. main-file discovery prefers 'X - Copy.IN' ---------------------------
def test_discovery_prefers_windows_copy_file(tmp_path, sample_model):
    from iwfm_io import create_scenario
    from iwfm_io.run import _find_input_file
    sc = create_scenario(sample_model, tmp_path / "s", subdirs=("Preprocessor", "Simulation"))
    main = sc / "Simulation" / "Simulation_MAIN.IN"
    shutil.copy(main, sc / "Simulation" / "Simulation_MAIN - Copy.IN")
    assert _find_input_file(sc, "simulation").name == "Simulation_MAIN.IN"


# --- 3. run_step(input_file=relative) resolves against CWD -------------------
@pytest.mark.exe
def test_run_step_relative_input_file_runs_other_model(tmp_path, sample_model, monkeypatch):
    from iwfm_io import create_scenario
    from iwfm_io.run import run_step
    victim = create_scenario(sample_model, tmp_path / "victim", subdirs=("Preprocessor", "Simulation", "Bin"))
    target = create_scenario(sample_model, tmp_path / "target", subdirs=("Preprocessor", "Simulation", "Bin"))
    vbin = victim / "Simulation" / "PreProcessor.bin"
    before = vbin.stat().st_mtime
    monkeypatch.chdir(victim)
    r = run_step("preprocessor", target, input_file="Preprocessor/PreProcessor_MAIN.IN", quiet=True, timeout=300)
    assert r.success
    assert vbin.stat().st_mtime == before, "preprocessor ran in the CWD model, not model_dir"


# --- 4. DLL parity: 1MON windows for daily data beginning on day 28-30 -------
def _small_budget(path, begin, n_rows):
    with h5py.File(path, "w") as f:
        a = f.create_group("Attributes")
        a.attrs["NTimeSteps"] = np.int32(n_rows)
        a.attrs["TimeStep%BeginDateAndTime"] = np.bytes_(begin)
        a.attrs["TimeStep%DeltaT_InMinutes"] = np.int32(1440)
        a.attrs["TimeStep%Unit"] = np.bytes_(b"1DAY")
        a.attrs["LocationData1%NDataColumns"] = np.int32(1)
        a.attrs["LocationData1%iDataColumnTypes"] = np.array([1], dtype=np.int32)
        a.attrs["LocationData1%cFullColumnHeaders"] = np.array([b"Time", b"Flow"], dtype="S20")
        a.create_dataset("cLocationNames", data=np.array([b"LOC"], dtype="S20"))
        f.create_dataset("LOC", data=np.ones((n_rows, 1)))


def test_1mon_windows_daily_begin_jan30(tmp_path):
    """First output stamp 01/31/1991_24:00 (sim began 01/30_24:00).
    IWFM increments 01/30_24:00 by 1MON to 02/28_24:00 (stamp 1991-03-01 in
    the library's convention) — verified with the real DLL on a sample-model
    run (DLL stamps 03/01, 04/01, ...; library 02/28, 03/31, ...)."""
    from iwfm_io.readers.hdf5 import read_budget_hdf
    p = tmp_path / "b.hdf"
    _small_budget(p, b"01/31/1991_24:00", 120)
    df = read_budget_hdf(p, interval="1MON")["data"]["LOC"]
    assert str(df.index[0].date()) == "1991-03-01", df.index[:3]
    assert df["Flow"].iloc[0] == 29          # 01/30 24:00 .. 02/28 24:00 inclusive


# --- 5. ZBudget busy-loop hang on a shortened simulation ---------------------
@pytest.mark.exe
def test_zbudget_terminates_when_edt_shortened(tmp_path, sample_model):
    """Expected: ZBudget finishes (or fails cleanly) promptly on a scenario
    whose EDT was shortened. Observed: the exe spins forever because
    ZBudget.in still asks for 09/30/2000 — ``run_step``'s ``timeout`` kills
    it, so the suite cannot wedge."""
    import subprocess
    from iwfm_io import create_scenario, run_model, set_keyed_value
    from iwfm_io.run import run_step
    sc = create_scenario(sample_model, tmp_path / "s", changes=[
        set_keyed_value("Simulation/Simulation_MAIN.IN", "EDT", "12/31/1990_24:00")])
    run_model(sc, quiet=True, timeout=600)
    try:
        run_step("zbudget", sc, timeout=60, quiet=True)
    except subprocess.TimeoutExpired:
        pytest.fail("ZBudget did not terminate within 60 s on the shortened scenario")


# --- 6. collect_* date filters ignore the 24:00 convention --------------------
def test_collect_budgets_water_year_window_drops_last_day(RESULTS):
    from iwfm_io import collect_budgets
    df = collect_budgets({"a": RESULTS}, {"GW": "GW.hdf"}, locations=["ENTIRE MODEL AREA"],
                         begin_date="1990-10-01", end_date="1991-09-30")
    assert df.datetime.nunique() == 365      # observed 364 (09/30/1991_24:00 dropped)


def test_collect_gwheads_water_year_window_off_by_one(RESULTS):
    from iwfm_io import collect_gwheads
    df = collect_gwheads({"a": RESULTS}, n_nodes=441, n_layers=2, nodes=[1], layers=[1],
                         begin_date="1990-10-01", end_date="1991-09-30")
    # observed: includes 09/30/1990_24:00 (initial condition, WY1990),
    # excludes 09/30/1991_24:00
    assert df.datetime.min() == pd.Timestamp("1990-10-02")
    assert df.datetime.max() == pd.Timestamp("1991-10-01")


# --- 7. RunResult.errors loses the message text -----------------------------
def test_scan_for_errors_keeps_message_lines():
    from iwfm_io.run import _scan_for_errors
    text = ("*****\n* FATAL:\n*   Error in opening file .\\PreProcessor.bin!\n"
            "*   (Class_FortBinaryFileTypeNew_FortBinFile)\n*****\n")
    errs = _scan_for_errors(text)
    assert any("PreProcessor.bin" in e for e in errs), errs   # observed ['* FATAL:']


# --- 8. partial GWHeadAll.out -> KeyError ------------------------------------
def test_partial_head_all_out_gives_clear_error(tmp_path, sample_model, RESULTS):
    from iwfm_io import open_model
    sc = tmp_path / "m"
    shutil.copytree(sample_model / "Preprocessor", sc / "Preprocessor")
    shutil.copytree(sample_model / "Simulation", sc / "Simulation")
    (sc / "Results").mkdir()
    # header only (what a killed exe leaves behind: stdout buffer lost)
    lines = (RESULTS / "GWHeadAll.out").read_text(errors="replace").splitlines(True)
    # everything up to and including the "*   TIME ..." column header
    n_hdr = next(i for i, ln in enumerate(lines) if ln.startswith("*") and "TIME" in ln) + 1
    (sc / "Results" / "GWHeadAll.out").write_text("".join(lines[:n_hdr]))
    with pytest.raises((ValueError, RuntimeError)):   # observed: KeyError: 'date'
        open_model(sc).heads_df(1)


# --- 9. read_zone_def: '*' comment lines (legal IWFM comment char) ----------
def test_zone_def_star_comment(tmp_path):
    from iwfm_io.readers.hdf5 import read_zone_def
    p = tmp_path / "z.dat"
    p.write_text("* header\n  1  / ZEXTENT\n 1  A\n 5 1\n")
    z = read_zone_def(p)                                    # observed: ValueError
    assert z.zones == {1: "A"}


def test_zone_def_without_element_lines(tmp_path):
    from iwfm_io.readers.hdf5 import read_zone_def
    p = tmp_path / "z.dat"
    p.write_text("  1  / ZEXTENT\n 1  A\n")
    z = read_zone_def(p)                                    # observed: ValueError int('A')
    assert z.zones == {1: "A"} and len(z.element_zones) == 0


def test_zone_def_duplicate_element_silently_last_wins(tmp_path, RESULTS):
    from iwfm_io.readers.hdf5 import read_zbudget_hdf
    zb = RESULTS / "UnsatZone_ZBud.hdf"
    if not zb.is_file():
        pytest.skip("UnsatZone_ZBud.hdf not present (large, regenerable Results file)")
    p = tmp_path / "z.dat"
    p.write_text("  1  / ZEXTENT\n 1  A\n 2  B\n 1 1\n 1 2\n")
    # decided behaviour (2.13.0): an element assigned twice is a deck
    # error, reported with the file and line
    from iwfm_io import IWFMParseError
    with pytest.raises(IWFMParseError, match="assigned twice"):
        read_zbudget_hdf(zb, zone_def=p)


# --- 10. adapter argument validation gaps ------------------------------------
def test_heads_df_bad_layer_raises(open_sample):
    with pytest.raises((ValueError, IndexError)):            # observed: (3654, 0) frame
        open_sample.heads_df(3)


def test_budget_df_columns_zero_raises(open_sample):
    with pytest.raises((ValueError, IndexError)):            # observed: last column returned
        open_sample.budget_df("GW", 1, columns=[0])


# --- 11. read_budget_hdf NTimeSteps smaller than rows -> crash ---------------
def test_ntimesteps_attr_smaller_than_rows(tmp_path, RESULTS):
    from iwfm_io.readers.hdf5 import read_budget_hdf
    p = tmp_path / "gw.hdf"
    shutil.copy(RESULTS / "GW.hdf", p)
    with h5py.File(p, "r+") as f:
        f["Attributes"].attrs["NTimeSteps"] = np.int32(10)
    r = read_budget_hdf(p)                                   # observed: ValueError from DataFrame ctor
    assert len(r["data"]["ENTIRE MODEL AREA"]) in (10, 3653)


# --- 12. aggregate_budget: empty long frame crashes; NaN path inconsistency --
def test_aggregate_budget_empty_long_frame():
    from iwfm_io import aggregate_budget, collect_budgets
    empty = collect_budgets({}, {"GW": "GW.hdf"})
    out = aggregate_budget(empty)                            # observed: ValueError: No objects to concatenate
    assert len(out) == 0


def test_aggregate_budget_nan_consistent_between_paths(open_sample, RESULTS):
    from iwfm_io import aggregate_budget
    from iwfm_io.readers.hdf5 import read_budget_hdf
    df = open_sample.budget_df("GW", 1)
    df.iloc[5, 0] = np.nan
    dt = read_budget_hdf(RESULTS / "GW.hdf")["data_types"]
    a = aggregate_budget(df).iloc[0, 0]
    b = aggregate_budget(df, data_types=dt).iloc[0, 0]
    assert (np.isnan(a) and np.isnan(b)) or a == b           # observed: number vs NaN


# --- 13. set_keyed_value value containing newline injects lines -------------
def test_set_keyed_value_rejects_newline(tmp_path, sample_model):
    from iwfm_io import create_scenario, set_keyed_value
    sc = create_scenario(sample_model, tmp_path / "s", subdirs=("Simulation",))
    with pytest.raises(ValueError):                          # observed: applied, file now has an extra line
        set_keyed_value("Simulation/Simulation_MAIN.IN", "BDT", "10/01/1990_24:00\n 1 / RESTART")(sc)


# --- 14. partial scenario left behind after a failing change ----------------
def test_failed_change_leaves_partial_scenario(tmp_path, sample_model):
    from iwfm_io import create_scenario, set_keyed_value

    def boom(root):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        create_scenario(sample_model, tmp_path / "s", subdirs=("Simulation",), changes=[
            set_keyed_value("Simulation/Simulation_MAIN.IN", "EDT", "12/31/1990_24:00"), boom])
    assert not (tmp_path / "s").exists()                     # observed: half-applied scenario remains
