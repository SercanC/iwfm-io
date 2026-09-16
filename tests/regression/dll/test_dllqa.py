"""Hostile-QA regressions for the DLL wrapper (``iwfm_io.dll``).

Imported from the 2026-09-09 hostile-QA pass (attack scripts a00-a20).
Every case is ONE attack, implemented as ``case_<name>(model_dir)`` in a
module under ``_cases/`` and executed in a FRESH interpreter: the attacks
reproduced here kill the process (Fortran ``STOP`` exits 0 with a FATAL
banner, access violations, heap corruption) or hang it, and none of that
can be caught in-process.

Each test asserts the EXPECTED behaviour — a clean ``IWFMError`` /
``ValueError`` instead of a crash, no garbage numbers from bad IDs, the
same data from any working directory, ... ``xfail(strict=True)`` marks the
attacks that still reproduce on the current code (reason ``dll#<n>``: the
a-script number the attack came from).

Every case works on a COPY of the sample model because inquiry-mode opens
rewrite Results HDFs in place. One copy serves the module (a second one
carries the optional zone-budget HDF); cases that corrupt the copy's
state (use after an access violation, deleting the inquiry data file) get
their own.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.conftest import SAMPLE_MODEL, copy_sample_model

pytestmark = [pytest.mark.regression, pytest.mark.dll, pytest.mark.sample_model]

CASES_DIR = Path(__file__).resolve().parent / "_cases"
TIMEOUT = 180
HANG_TIMEOUT = 60
N_NODES, N_ELEMENTS, N_STREAM_NODES = 441, 400, 23

#: Exception types that count as a clean, catchable failure.
CLEAN = {"IWFMError", "ValueError", "TypeError", "AttributeError", "OverflowError",
         "UnicodeEncodeError", "IndexError", "KeyError", "RuntimeError", "OSError",
         "FileNotFoundError", "NotADirectoryError", "FileExistsError", "PermissionError",
         "IsADirectoryError", "ConnectionResetError"}


# ----------------------------------------------------------------------
# Subprocess runner
# ----------------------------------------------------------------------

class CaseRun:
    """Outcome of one case subprocess."""

    def __init__(self, name, proc, timed_out):
        self.name = name
        self.timed_out = timed_out
        self.returncode = None if timed_out else proc.returncode

        def _text(x):
            return x if isinstance(x, str) else (x or b"").decode("utf-8", "replace")
        self.stdout, self.stderr = _text(proc.stdout), _text(proc.stderr)
        self.result = None
        banner = []
        for line in self.stdout.splitlines():
            if line.startswith("RESULT: "):
                self.result = json.loads(line[len("RESULT: "):])
            else:
                banner.append(line)
        # The Fortran STOP banner goes to the console; a caught IWFMError
        # only carries the text inside the RESULT json.
        self.fatal = any("FATAL" in x for x in banner) or "FATAL" in self.stderr

    def tail(self, n=12):
        lines = [x for x in (self.stdout + self.stderr).splitlines()
                 if x.strip() and "skipping registration" not in x]
        return "\n".join(lines[-n:])

    # -- assertions ------------------------------------------------------------
    def survived(self):
        """The interpreter finished the case and reported a result."""
        assert not self.timed_out, f"{self.name}: timed out (hang)\n{self.tail()}"
        assert self.result is not None, \
            f"{self.name}: no RESULT line (process died, exit {self.returncode})\n{self.tail()}"
        assert self.returncode == 0, f"{self.name}: exit {self.returncode:#x}\n{self.tail()}"
        assert not self.fatal, f"{self.name}: FATAL banner\n{self.tail()}"
        if self.result["outcome"] == "skipped":
            pytest.skip(self.result["reason"])
        assert self.result["outcome"] != "setup_error", \
            f"{self.name}: case setup failed\n{self.result.get('traceback')}"
        return self.result

    def raised(self, *types):
        r = self.survived()
        assert r["outcome"] == "raised", f"{self.name}: expected a clean exception, got {r}"
        assert not r["access_violation"], f"{self.name}: access violation: {r['exc_msg']}"
        allowed = set(types) or CLEAN
        assert r["exc_type"] in allowed, f"{self.name}: {r['exc_type']}: {r['exc_msg']}"
        return r

    def returned(self):
        r = self.survived()
        assert r["outcome"] == "returned", f"{self.name}: {r}"
        return r["value"]

    def returned_or_raised(self):
        r = self.survived()
        return self.raised() if r["outcome"] == "raised" else self.returned()


def run_case(module, name, model_dir, timeout=TIMEOUT):
    cmd = [sys.executable, str(CASES_DIR / f"{module}.py"), name, str(model_dir)]
    try:
        proc = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=str(CASES_DIR))
        return CaseRun(name, proc, timed_out=False)
    except subprocess.TimeoutExpired as exc:
        return CaseRun(name, exc, timed_out=True)


# ----------------------------------------------------------------------
# Expectations (each takes a CaseRun and asserts)
# ----------------------------------------------------------------------

def raised(run):
    """A clean, catchable exception — no crash, no STOP, no garbage."""
    run.raised()


def ok(run):
    run.returned()


def ok_or_raised(run):
    run.returned_or_raised()


def no_garbage(pred, what="value"):
    """Returned value satisfies *pred*, or a clean exception."""
    def _check(run):
        r = run.survived()
        if r["outcome"] == "raised":
            run.raised()
            return
        assert pred(r["value"]), f"{run.name}: garbage {what}: {json.dumps(r['value'])[:300]}"
    return _check


def same_as_control(run):
    """Attack result identical to the in-case control, or a clean exception."""
    r = run.survived()
    if r["outcome"] == "raised":
        run.raised()
        return
    assert r["value"]["same_as_control"], f"{run.name}: differs from control: {r['value']}"


def raised_or_empty(run):
    """Windows outside the simulation / begin > end: reject or return nothing."""
    r = run.survived()
    if r["outcome"] == "raised":
        run.raised()
        return
    v = r["value"]
    n = v.get("n", v.get("shape", [0])[0]) if isinstance(v, dict) else len(v)
    assert n == 0, f"{run.name}: silent data for an impossible window: {v}"


def all_raised(keys=None):
    """Every sub-attempt in the returned dict raised cleanly (post-close scalars)."""
    def _check(run):
        v = run.returned()
        bad = {k: x for k, x in v.items() if (keys is None or k in keys)
               and not (x["outcome"] == "raised" and x["exc_type"] in CLEAN)}
        assert not bad, f"{run.name}: {bad}"
    return _check


def _ids_in(lo, hi):
    return lambda v: all(lo <= x <= hi for x in v)


def _finite_heads(v):
    return v.get("shape", [0])[0] > 0 and not v["any_nan"] and -1e4 < v["min"] and v["max"] < 1e4


# -- composite checks ----------------------------------------------------------

def hyd_monthly_stamps(run):
    v = run.returned()
    assert v["all_stamps_in_daily"] and v["all_values_match_daily"], v
    assert set(v["days_of_month"]) <= {28, 29, 30, 31}, \
        f"1MON stamps are not month ends (31-day stride): {v['stamps_first']} {v['strides_first']}"


def stream_hyd_dates(run):
    v = run.returned()
    bad = {iv: d for iv, d in v.items() if d["n_bad_dates"] or d["any_nonfinite"]}
    assert not bad, bad


def budget_cols_swapped(run):
    v = run.returned()
    assert v["a0_is_b1"] and v["a1_is_b0"] and v["cols_a"] == list(reversed(v["cols_b"])), v


def elements_sane(run):
    v = run.returned()
    assert v["sane"] and v["shape"][0] == N_ELEMENTS, v


def cwd_same_heads(run):
    v = run.returned()
    assert v["shape"] == [3653, N_NODES] and _finite_heads(v), v


def cross_model_no_leak(run):
    v = run.returned()
    leaked = {k: x for k, x in v.items() if isinstance(x, dict) and x.get("outcome") == "returned"
              and x["value"].get("shape", [0])[0] > 0}
    assert not leaked, f"model without Results served the CWD model's files: {leaked}"


def no_files_modified(run):
    v = run.returned()
    assert v["n_changed"] == 0, v["changed"]


def threads_consistent(key):
    def _check(run):
        v = run.returned()
        assert not v["errors"] and not any(v["alive"]), v
        counts = v[key].values() if isinstance(v[key], dict) else [v[key]]
        assert all(n == 1 for n in counts), f"mixed-up answers across threads: {v}"
    return _check


def ctx_closed(run):
    v = run.returned()
    assert v["open"] is False and "closed" in v["repr"], v


def reopen_ok(run):
    v = run.returned()
    assert v["n_nodes"] == N_NODES, v


def cwd_restored(run):
    v = run.returned()
    assert v["cwd_restored"], v
    assert v["open"]["outcome"] == "raised" and v["open"]["exc_type"] in CLEAN, v


def after_av_ok(run):
    v = run.returned()
    assert v["n_nodes"] == N_NODES and v.get("same_heads", True), v
    assert v.get("reopen_nodes", N_NODES) == N_NODES, v


def standalone_ok(run):
    v = run.returned()
    for k, x in v.items():
        if isinstance(x, dict) and "outcome" in x:
            assert x["outcome"] == "returned", f"{run.name}: {k}: {x}"


def two_models_ok(run):
    v = run.returned()
    assert v["h1"]["shape"] == [3653, N_NODES], v
    h2 = v["h2"]
    if "outcome" in h2:
        assert h2["outcome"] == "returned" or h2["exc_type"] in CLEAN, v
    else:
        assert v["same"], v


def switch_then_n_nodes(run):
    v = run.returned()
    assert v["switch"]["outcome"] == "raised" and v["switch"]["exc_type"] == "IWFMError", v
    assert v["n_nodes"] == {"outcome": "returned", "value": N_NODES}, v


def inquiry_file_kept(run):
    v = run.returned()
    assert v["exists_after"], "a bogus file name deleted the active model's inquiry data file"


def dl_nothing_installed(run):
    v = run.returned()
    assert v["call"]["outcome"] == "raised" and v["call"]["exc_type"] in CLEAN, v
    assert not [f for f in (v["dest_files"] or []) if f.lower().endswith(".dll")], v


def dl_no_escape(run):
    v = run.returned()
    assert not v["escaped"], v
    assert v["call"]["outcome"] == "raised" or v["dest_files"] == ["IWFM_C_x64.dll"], v


def dl_fake_rejected(run):
    v = run.returned()
    assert v["download"]["outcome"] == "raised" or not v.get("still_on_disk"), \
        f"non-DLL payload installed and left on disk: {v}"


def dl_intact(run):
    v = run.returned()
    assert v["intact"], v
    s = v["second"]
    assert s["outcome"] == "returned" or s["exc_type"] in CLEAN, v


def dl_no_leftovers(run):
    """An interrupted fetch installs nothing and leaks nothing into the
    system temp dir.  Since 2.15 the partial archive is deliberately kept
    in dest_dir as ``<name>.zip.part`` so the next call resumes it; a
    *complete* archive that fails its hash is still always discarded."""
    v = run.returned()
    assert v["call"]["outcome"] == "raised" and v["call"]["exc_type"] == "ConnectionResetError", v
    assert v["new_tmp_zips"] == [], v
    left = v["dest_files"] or []
    assert not [f for f in left if f.lower().endswith(".dll")], v
    assert all(f.endswith(".zip.part") for f in left), v


def dl_not_installed(run):
    v = run.returned()
    assert v["load"]["outcome"] == "raised" and v["load"]["exc_type"] in CLEAN, v
    assert not v["installed"] and not v["listed"], f"fake DLL left installed: {v}"


def loaded_version(version):
    def _check(run):
        v = run.returned()
        assert version in v, v
    return _check


def foreign_dll_rejected(run):
    v = run.returned()
    assert v["load"]["outcome"] == "raised" and v["load"]["exc_type"] in CLEAN, \
        f"non-IWFM DLL accepted by load_dll: {v}"


# ----------------------------------------------------------------------
# The attack table
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Case:
    module: str
    name: str
    expect: object
    xfail: str = ""                 # "dll#<n>: <title>" when the attack still reproduces
    copy: str = "module"            # module | zbudget | fresh
    timeout: int = TIMEOUT

    @property
    def id(self):
        return f"{self.module}/{self.name}"


_STOP = "dll#18: bad date/interval string -> Fortran STOP (FATAL banner, exit 0)"
_SILENT_WINDOW = "dll#5: window outside the simulation returns silent zeros"
_HEAP0 = "dll#7: budget location 0 corrupts the heap (0xc0000374)"
_GARBAGE = "dll#13: bad ID returns garbage instead of raising"

CASES = [
    # ---------------- dates / intervals ----------------
    Case("dates", "heads_garbage_date", raised),
    Case("dates", "heads_iso_date", raised),
    Case("dates", "heads_empty_date", raised),
    Case("dates", "heads_impossible_date", raised),
    Case("dates", "heads_hour_25", raised),
    Case("dates", "heads_date_without_time", same_as_control),
    Case("dates", "heads_begin_after_end", raised_or_empty),
    Case("dates", "heads_window_before_sim", raised_or_empty),
    Case("dates", "heads_window_straddles_end", no_garbage(lambda v: v["idxN"] <= "2000-09-30 00:00:00", "stamps past the end")),
    Case("dates", "heads_window_straddles_begin", no_garbage(_finite_heads)),
    Case("dates", "budget_interval_3mon", raised),
    Case("dates", "budget_interval_empty", raised),
    Case("dates", "budget_interval_garbage", raised),
    Case("dates", "budget_interval_lowercase", ok),
    Case("dates", "budget_interval_trailing_space", ok),
    Case("dates", "budget_interval_1year_control", ok),
    Case("dates", "budget_garbage_dates", raised),
    Case("dates", "hydrograph_garbage_date", raised),
    Case("dates", "hydrograph_interval_garbage", raised),
    Case("dates", "hydrograph_window_before_sim", raised_or_empty),
    Case("dates", "budget_file_interval_garbage", raised),
    Case("dates", "budget_file_garbage_dates", raised),
    Case("dates", "zbudget_garbage_dates", raised),
    Case("dates", "n_intervals_control", no_garbage(lambda v: v == 119)),
    Case("dates", "n_intervals_bad_date", raised),
    Case("dates", "n_intervals_bad_interval", raised),
    Case("dates", "n_intervals_begin_after_end", no_garbage(lambda v: v == -120)),
    Case("dates", "increment_time_garbage_interval", raised),
    Case("dates", "increment_time_bad_date", raised),
    Case("dates", "increment_time_year_9999", raised),
    Case("dates", "is_time_greater_than_garbage", raised),

    # ---------------- indices / IDs ----------------
    Case("indices", "heads_layer_0", raised),
    Case("indices", "heads_layer_neg1", raised),
    Case("indices", "heads_layer_3", raised),
    Case("indices", "heads_layer_99", raised),
    Case("indices", "heads_date_1000_chars", raised),
    Case("indices", "heads_begin_len_ne_end_len", no_garbage(lambda v: v["shape"] == [3653, N_NODES], "truncated window")),
    Case("indices", "hyd_type_0", raised),
    Case("indices", "hyd_type_neg1", raised),
    Case("indices", "hyd_type_999", raised),
    Case("indices", "hyd_type_subregion", raised),
    Case("indices", "hyd_index_0", raised),
    Case("indices", "hyd_index_neg1", raised),
    Case("indices", "hyd_index_999", raised),
    Case("indices", "hyd_index_n_plus_1", raised),
    Case("indices", "hyd_layer_0", same_as_control),
    Case("indices", "hyd_layer_neg1", same_as_control),
    Case("indices", "hyd_layer_99", same_as_control),
    Case("indices", "hyd_stream_index_999", raised),
    Case("indices", "hyd_interval_1000_chars", raised),
    Case("indices", "hyd_fact_nan", ok_or_raised),
    Case("indices", "n_hydrographs_999", raised),
    Case("indices", "hydrograph_ids_999", raised),
    Case("indices", "hydrograph_coordinates_0", raised),
    Case("indices", "hydrograph_coordinates_999", raised),
    # decided (2.13.0): non-native hydrograph intervals are rejected --
    # the DLL strides fixed day counts; resample the native series in
    # pandas instead
    Case("indices", "hyd_monthly_stamps_vs_daily", raised),
    Case("indices", "stream_hyd_dates_sane", raised),
    Case("indices", "budget_type_0", raised),
    Case("indices", "budget_type_neg1", raised),
    Case("indices", "budget_type_999", raised),
    Case("indices", "budget_loc_0", raised),
    Case("indices", "budget_loc_neg1", raised),
    Case("indices", "budget_loc_999", raised),
    Case("indices", "budget_loc_n_plus_1", raised),
    Case("indices", "budget_lwu_loc_999", raised),
    Case("indices", "budget_cols_0", raised),
    Case("indices", "budget_cols_neg1", raised),
    Case("indices", "budget_cols_999", raised),
    Case("indices", "budget_cols_ncol_plus_1", raised),
    Case("indices", "budget_cols_empty", raised_or_empty),
    Case("indices", "budget_cols_duplicate", ok),
    Case("indices", "budget_fact_vl_nan", ok_or_raised),
    Case("indices", "budget_df_loc_0", raised),
    Case("indices", "budget_df_loc_999", raised_or_empty),
    Case("indices", "budget_df_cols_swapped", budget_cols_swapped),
    Case("indices", "budget_n_columns_loc_0", raised),
    Case("indices", "budget_n_columns_loc_999", no_garbage(lambda v: v == 0)),
    Case("indices", "budget_n_columns_type_999", raised),
    Case("indices", "budget_column_titles_type_0", raised),
    Case("indices", "budget_column_titles_loc_999", no_garbage(lambda v: v == [])),
    Case("indices", "budget_monthly_avg_loc_999", raised),
    Case("indices", "budget_monthly_avg_type_999", raised),
    Case("indices", "budget_annual_loc_0", raised),
    Case("indices", "budget_annual_type_999", raised),
    Case("indices", "cum_gw_storage_subregion_0", raised),
    Case("indices", "cum_gw_storage_subregion_999", raised),
    Case("indices", "annual_cum_gw_storage_subregion_999", raised),
    Case("indices", "budget_file_loc_0", raised),
    Case("indices", "budget_file_loc_neg1", raised),
    Case("indices", "budget_file_loc_999", raised),
    Case("indices", "budget_file_col_0", raised),
    Case("indices", "budget_file_col_neg1", raised),
    Case("indices", "budget_file_col_999", raised),
    Case("indices", "budget_file_col_ncol_plus_1", raised),
    Case("indices", "budget_file_cols_empty", raised_or_empty),
    Case("indices", "budget_file_cols_duplicate", ok),
    Case("indices", "budget_file_fact_vl_nan", ok_or_raised),
    Case("indices", "budget_file_values_for_column_0", raised),
    Case("indices", "budget_file_values_for_column_999", raised),
    Case("indices", "budget_file_values_for_column_loc_999", raised),
    Case("indices", "budget_file_n_columns_0", raised),
    Case("indices", "budget_file_n_columns_999", raised),
    Case("indices", "budget_file_column_headers_0", raised),
    Case("indices", "budget_file_column_headers_999", raised),
    Case("indices", "budget_file_title_lines_0", raised),
    Case("indices", "budget_file_title_lines_999", raised),
    Case("indices", "budget_file_title_unit_200_chars", ok),
    Case("indices", "budget_file_header_units_mixed_lengths", ok),
    Case("indices", "element_config_0", raised),
    Case("indices", "element_config_neg1", raised),
    Case("indices", "element_config_n_plus_1", raised),
    Case("indices", "element_config_999999", raised),
    Case("indices", "elements_df_sane", elements_sane),
    Case("indices", "subregion_name_0", raised),
    Case("indices", "subregion_name_999", raised),
    Case("indices", "reach_n_nodes_0", no_garbage(lambda v: 0 <= v <= N_STREAM_NODES)),
    Case("indices", "reach_n_nodes_999", no_garbage(lambda v: 0 <= v <= N_STREAM_NODES)),
    Case("indices", "reach_stream_nodes_999", no_garbage(_ids_in(1, N_STREAM_NODES))),
    Case("indices", "reach_gw_nodes_0", no_garbage(_ids_in(1, N_NODES))),
    Case("indices", "n_rating_table_points_999", no_garbage(lambda v: v == 0)),
    Case("indices", "stream_rating_table_999", no_garbage(lambda v: all(s["n"] == 0 for s in v))),
    Case("indices", "stream_upstream_nodes_999", no_garbage(lambda v: v == [])),
    Case("indices", "is_stream_upstream_node_999", no_garbage(lambda v: v is False)),
    Case("indices", "reach_upstream_reaches_999", raised),
    Case("indices", "reaches_for_stream_nodes_bad", no_garbage(_ids_in(0, 10))),
    Case("indices", "n_elements_in_lake_0", no_garbage(lambda v: 0 <= v <= N_ELEMENTS)),
    Case("indices", "n_elements_in_lake_99", no_garbage(lambda v: v == 0)),
    Case("indices", "elements_in_lake_99", no_garbage(lambda v: v == [])),
    Case("indices", "well_n_elements_999", no_garbage(lambda v: 0 <= v <= N_ELEMENTS)),
    Case("indices", "well_elements_0", raised),
    Case("indices", "diversion_n_elements_999", no_garbage(lambda v: 0 <= v <= N_ELEMENTS)),
    Case("indices", "diversion_elements_999", no_garbage(lambda v: v == [])),
    Case("indices", "diversion_export_nodes_bad", no_garbage(_ids_in(0, N_STREAM_NODES))),
    Case("indices", "diversion_recharge_zone_elements_999", raised),
    Case("indices", "bypass_export_nodes_999", raised),
    Case("indices", "bypass_export_dest_data_0", raised),
    Case("indices", "bypass_recoverable_loss_factor_999", raised),
    Case("indices", "stratigraphy_at_xy_far_outside", raised),
    Case("indices", "stratigraphy_at_xy_nan", raised),
    Case("indices", "parametric_nodes_grid_99", raised),
    Case("indices", "parametric_node_xy_99", raised),
    Case("indices", "parametric_element_config_99", raised),
    Case("indices", "parametric_aquifer_parameters_99", raised),
    Case("indices", "n_locations_0", no_garbage(lambda v: v == 0)),
    Case("indices", "n_locations_999", no_garbage(lambda v: v == 0)),
    Case("indices", "location_ids_999", no_garbage(lambda v: v == [])),
    Case("indices", "names_0", no_garbage(lambda v: v == [])),
    Case("indices", "names_999", no_garbage(lambda v: v == [])),
    Case("indices", "land_use_areas_control", no_garbage(lambda v: v == [N_ELEMENTS, 1])),
    Case("indices", "land_use_areas_undersized_buffer", raised),
    Case("indices", "zbudget_list", no_garbage(lambda v: isinstance(v, list))),
    Case("indices", "zbudget_n_columns_bogus", raised),

    # ---------------- zone budgets ----------------
    Case("zbudget", "open_missing", raised, copy="zbudget"),
    Case("zbudget", "open_budget_file_as_zbudget", raised, copy="zbudget"),
    Case("zbudget", "open_heads_file_as_zbudget", raised, copy="zbudget"),
    Case("zbudget", "open_text_file_as_zbudget", raised, copy="zbudget"),
    Case("zbudget", "open_zero_byte", raised, copy="zbudget"),
    Case("zbudget", "gen_default_unnamed", ok),
    Case("zbudget", "gen_named_control", ok, copy="zbudget"),
    Case("zbudget", "no_zone_list_n_zones", no_garbage(lambda v: v == 0), copy="zbudget"),
    Case("zbudget", "no_zone_list_values", raised),
    Case("zbudget", "no_zone_list_headers_general", ok, copy="zbudget"),
    Case("zbudget", "gen_elements_empty", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_element_0", raised, copy="zbudget"),
    Case("zbudget", "gen_element_999", raised, copy="zbudget"),
    Case("zbudget", "gen_element_neg1", raised, copy="zbudget"),
    Case("zbudget", "gen_zones_all_0", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_zones_all_neg1", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_layer_0", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_layer_99", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_extent_99", raised, copy="zbudget"),
    Case("zbudget", "gen_duplicate_elements", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_names_mismatch_2_ids_1_name", raised),
    Case("zbudget", "gen_names_mismatch_1_id_2_names", raised, copy="zbudget"),
    Case("zbudget", "gen_name_for_unknown_zone", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_name_300_chars", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_name_non_ascii", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_zone_id_int32_max", ok_or_raised, copy="zbudget"),
    Case("zbudget", "gen_zone_id_int32_overflow", raised, copy="zbudget"),
    Case("zbudget", "gen_twice", no_garbage(lambda v: v["second"]["n_zones"] == 3), copy="zbudget"),
    Case("zbudget", "gen_from_file_missing", raised, copy="zbudget"),
    Case("zbudget", "gen_from_file_sim_main", raised, copy="zbudget"),
    Case("zbudget", "gen_from_file_vs_arrays", no_garbage(lambda v: v["close"]), copy="zbudget"),
    Case("zbudget", "values_control", ok, copy="zbudget"),
    Case("zbudget", "values_zone_not_in_list", raised, copy="zbudget"),
    Case("zbudget", "values_zone_0", raised, copy="zbudget"),
    Case("zbudget", "values_zone_neg1", raised, copy="zbudget"),
    Case("zbudget", "values_zone_999", raised, copy="zbudget"),
    Case("zbudget", "values_cols_empty", raised_or_empty, copy="zbudget"),
    Case("zbudget", "values_cols_999", raised, copy="zbudget"),
    Case("zbudget", "values_cols_0", raised),
    Case("zbudget", "values_cols_neg1", raised),
    Case("zbudget", "values_cols_no_time", raised, copy="zbudget"),
    Case("zbudget", "values_cols_duplicate", ok, copy="zbudget"),
    Case("zbudget", "values_interval_3mon", raised, copy="zbudget"),
    Case("zbudget", "values_interval_empty", ok_or_raised, copy="zbudget"),
    Case("zbudget", "values_interval_trailing_space", ok, copy="zbudget"),
    Case("zbudget", "values_interval_1year_control", ok, copy="zbudget"),
    Case("zbudget", "values_begin_after_end", raised_or_empty),
    Case("zbudget", "values_window_before_sim", raised, copy="zbudget"),
    Case("zbudget", "values_fact_nan", ok_or_raised, copy="zbudget"),
    Case("zbudget", "headers_general", ok, copy="zbudget"),
    Case("zbudget", "headers_general_max_columns_1", ok, copy="zbudget"),   # a floor, all headers returned
    Case("zbudget", "headers_general_max_columns_0", raised, copy="zbudget"),
    # long recorded as a DLL hang: it was the wrapper's own default column
    # list (1..500) indexing the general headers out of bounds -- fixed 2.15.3
    Case("zbudget", "headers_for_zone", ok, copy="zbudget", timeout=HANG_TIMEOUT),
    Case("zbudget", "title_lines_zone_1", ok, copy="zbudget"),
    Case("zbudget", "title_lines_zone_999", raised, copy="zbudget"),
    Case("zbudget", "zones_interval_control", ok, copy="zbudget"),
    Case("zbudget", "zones_interval_zone_999", raised, copy="zbudget"),
    Case("zbudget", "zones_interval_date_outside", raised, copy="zbudget"),
    Case("zbudget", "zones_interval_zones_empty", raised_or_empty, copy="zbudget"),
    Case("zbudget", "after_close_n_zones", raised),
    Case("zbudget", "close_twice", ok, copy="zbudget"),
    Case("zbudget", "budget_and_zbudget_together", ok, copy="zbudget"),
    Case("zbudget", "budget_reader_on_zbudget_file", raised, copy="zbudget"),

    # ---------------- lifecycle: post-close ----------------
    Case("lifecycle", "close_twice", ok),
    Case("lifecycle", "kill_after_close_raw", ok_or_raised),
    Case("lifecycle", "kill_never_opened", ok_or_raised),
    Case("lifecycle", "ctx_exception_closes", ctx_closed),
    Case("lifecycle", "ctx_exception_then_reopen", reopen_ok),
    Case("lifecycle", "del_gc_then_reopen", reopen_ok),
    Case("lifecycle", "scalars_after_close", all_raised()),
    Case("lifecycle", "nodes_df_after_close", raised),
    Case("lifecycle", "elements_df_after_close", raised),
    Case("lifecycle", "time_specs_after_close", raised),
    Case("lifecycle", "heads_df_after_close", raised),
    Case("lifecycle", "budget_df_after_close", raised),
    Case("lifecycle", "budget_list_after_close", raised),
    Case("lifecycle", "describe_after_close", raised),
    Case("lifecycle", "hydrograph_after_close", raised),
    Case("lifecycle", "gw_heads_all_after_close", raised),
    Case("lifecycle", "aquifer_top_after_close", raised),
    Case("lifecycle", "stream_nodes_df_after_close", raised),
    Case("lifecycle", "hydrograph_type_list_after_close", raised),
    Case("lifecycle", "subregion_name_after_close", raised),
    Case("lifecycle", "element_config_after_close", raised),
    Case("lifecycle", "budget_file_after_close", raised),
    Case("lifecycle", "budget_file_close_twice", ok),

    # ---------------- lifecycle: bad open arguments ----------------
    Case("lifecycle", "open_control", reopen_ok),
    Case("lifecycle", "open_pp_bin_instead_of_in", raised),
    Case("lifecycle", "open_swapped_args", raised),
    Case("lifecycle", "open_sim_missing", raised),
    Case("lifecycle", "open_pp_missing", raised),
    Case("lifecycle", "open_pp_only_inquiry", reopen_ok),
    Case("lifecycle", "open_pp_directory", raised),
    Case("lifecycle", "open_pp_empty_string", raised),
    Case("lifecycle", "open_pp_none", raised),
    Case("lifecycle", "open_sim_none", raised),
    Case("lifecycle", "open_run_dir_wrong", ok_or_raised),
    Case("lifecycle", "open_run_dir_missing", raised),
    Case("lifecycle", "open_run_dir_missing_cwd_restored", cwd_restored),
    Case("lifecycle", "open_wsa_bogus", raised),
    Case("lifecycle", "open_wsa_is_sim_main", ok_or_raised),
    Case("lifecycle", "open_is_for_inquiry_string", ok_or_raised),
    Case("lifecycle", "open_dll_version_unknown", raised),
    Case("lifecycle", "open_pp_trailing_spaces", ok_or_raised),
    Case("lifecycle", "open_pp_300_chars", raised),
    Case("lifecycle", "open_pp_1500_chars", raised),
    Case("lifecycle", "open_pp_zero_byte", raised),
    Case("lifecycle", "open_pp_binary_hdf", raised),
    Case("lifecycle", "open_after_bad_open", no_garbage(lambda v: v["n_nodes"] == N_NODES)),

    # ---------------- lifecycle: IWFMBudget on bad files ----------------
    Case("lifecycle", "budget_open_control", no_garbage(lambda v: v["n_loc"] == 3)),
    Case("lifecycle", "budget_open_missing", raised),
    Case("lifecycle", "budget_open_zero_byte", raised),
    Case("lifecycle", "budget_open_truncated", raised),
    Case("lifecycle", "budget_open_heads_hdf", raised),
    Case("lifecycle", "budget_open_hydrograph_hdf", raised),
    Case("lifecycle", "budget_open_text_bud", raised),
    Case("lifecycle", "budget_open_path_with_spaces", no_garbage(lambda v: v["n_loc"] == 3)),
    Case("lifecycle", "budget_open_directory", raised),
    Case("lifecycle", "budget_open_sim_main", raised),
    Case("lifecycle", "budget_open_preprocessor_bin", raised),

    # ---------------- lifecycle: handle collisions / after AV ----------------
    Case("lifecycle", "model_then_standalone_budget", ok),
    Case("lifecycle", "standalone_then_model_budget", standalone_ok),
    Case("lifecycle", "standalone_survives_model_open_close", ok),
    Case("lifecycle", "two_models_sequential", two_models_ok),
    Case("lifecycle", "two_models_open_no_close", two_models_ok),
    Case("lifecycle", "av_layer3_then_valid_calls", after_av_ok),
    Case("lifecycle", "av_gw_heads_all_then_valid_calls", after_av_ok, copy="fresh"),
    Case("lifecycle", "delete_inquiry_data_file_bogus", inquiry_file_kept, copy="fresh"),

    # ---------------- lifecycle: inquiry-mode getters ----------------
    Case("lifecycle", "inquiry_stream_flows_guarded", raised),
    Case("lifecycle", "inquiry_stream_inflows_at", raised),
    Case("lifecycle", "inquiry_stream_inflows_at_999", raised),
    Case("lifecycle", "inquiry_stream_inflow_nodes", raised),
    Case("lifecycle", "inquiry_required_diversions", raised),
    Case("lifecycle", "inquiry_actual_diversions", raised),
    Case("lifecycle", "inquiry_actual_diversions_999", raised),
    Case("lifecycle", "inquiry_bypass_outflows", raised),
    Case("lifecycle", "inquiry_supply_requirement_ag", raised),
    Case("lifecycle", "inquiry_supply_requirement_urban", raised),
    Case("lifecycle", "inquiry_supply_short_ag", raised),
    Case("lifecycle", "inquiry_supply_demand_df", raised),
    Case("lifecycle", "inquiry_supply_purpose", raised),
    Case("lifecycle", "inquiry_subregion_ag_pumping_depth", raised),
    Case("lifecycle", "inquiry_zone_ag_pumping_depth", raised),
    Case("lifecycle", "inquiry_n_ag_crops", raised),
    Case("lifecycle", "inquiry_future_water_demand", raised),
    Case("lifecycle", "inquiry_subsidence_all", raised),
    Case("lifecycle", "inquiry_current_date_time", ok),
    Case("lifecycle", "inquiry_gw_heads_all", raised),
    Case("lifecycle", "inquiry_gw_heads_all_previous", raised),
    Case("lifecycle", "inquiry_gw_heads_initial", ok, "dll#13: known issue #1 spurious 'Duplicate Node ID' (return-flow skip)"),
    Case("lifecycle", "inquiry_aquifer_parameters", ok, "dll#13: known issue #1 spurious 'Duplicate Node ID' (return-flow skip)"),
    Case("lifecycle", "inquiry_aquifer_horizontal_k", ok, "dll#13: known issue #1 spurious 'Duplicate Node ID' (return-flow skip)"),
    Case("lifecycle", "inquiry_simulate_timestep", raised),
    Case("lifecycle", "inquiry_advance_time", raised),
    Case("lifecycle", "inquiry_read_timeseries_data", raised),
    Case("lifecycle", "inquiry_print_results", raised),
    Case("lifecycle", "inquiry_simulate", raised),
    Case("lifecycle", "inquiry_simulate_interval", raised),
    Case("lifecycle", "inquiry_compute_future_water_demands", raised),
    Case("lifecycle", "switch_to_999", raised),
    Case("lifecycle", "switch_to_0", raised),
    Case("lifecycle", "switch_to_999_then_n_nodes", switch_then_n_nodes),

    # ---------------- lifecycle: enums / logging ----------------
    Case("lifecycle", "enum_before_load", raised),
    Case("lifecycle", "enum_after_load", no_garbage(lambda v: v["GW"] == 3001 and v["LWU"] == 4001)),
    Case("lifecycle", "get_version_none", raised),
    Case("lifecycle", "set_log_file_directory", raised),
    Case("lifecycle", "set_log_file_then_open", no_garbage(lambda v: v["exists"])),
    Case("lifecycle", "close_log_file_never_opened", ok),
    Case("lifecycle", "get_last_message_fresh", ok),
    Case("lifecycle", "log_last_message_no_log", ok_or_raised),

    # ---------------- threads ----------------
    Case("threads", "threads_nodes_elements", threads_consistent("distinct_xsum")),
    Case("threads", "threads_heads", threads_consistent("distinct_means_per_layer")),
    Case("threads", "threads_budget_hydrograph", threads_consistent("distinct_means_per_thread")),

    # ---------------- working directory ----------------
    Case("cwd", "heads_cwd_simulation", cwd_same_heads),
    Case("cwd", "heads_cwd_model_root", cwd_same_heads),
    Case("cwd", "heads_cwd_preprocessor", cwd_same_heads),
    Case("cwd", "heads_cwd_system_root", cwd_same_heads),
    Case("cwd", "heads_cwd_temp", cwd_same_heads),
    Case("cwd", "cross_model_leak", cross_model_no_leak),
    Case("cwd", "files_modified_by_inquiry", no_files_modified),

    # ---------------- download / loader ----------------
    Case("download", "dl_hash_mismatch", dl_nothing_installed),
    Case("download", "dl_zip_entry_traversal", dl_no_escape),
    Case("download", "dl_fake_payload_rejected", dl_fake_rejected),
    Case("download", "dl_force_over_loaded_dll", dl_intact),
    Case("download", "dl_fetch_raises_no_leftovers", dl_no_leftovers),
    Case("download", "dl_version_traversal", raised),
    Case("download", "dl_dest_dir_is_file", raised),
    Case("download", "dl_autodownload_fake_via_load_dll", dl_not_installed),
    Case("download", "load_version_unknown_no_download", raised),
    Case("download", "load_version_unknown_download_default", no_garbage(lambda v: v == [], "fetch attempted")),
    Case("download", "load_version_empty", raised),
    Case("download", "load_version_traversal", raised),
    Case("download", "load_version_traversal_to_other_version", raised),
    Case("download", "load_version_absolute_path", raised),
    Case("download", "load_version_int", raised),
    Case("download", "load_path_non_dll_file", raised),
    Case("download", "load_path_directory", raised),
    Case("download", "load_path_missing", raised),
    Case("download", "load_path_foreign_dll", foreign_dll_rejected),
    Case("download", "load_env_version_garbage", loaded_version("2025.0.1747")),
    Case("download", "load_env_version_traversal", loaded_version("2025.0.1747")),
    Case("download", "load_env_version_2015", loaded_version("2015.0.1403")),
]

assert len({c.id for c in CASES}) == len(CASES), "duplicate case ids"


# ----------------------------------------------------------------------
# Model copies
# ----------------------------------------------------------------------

def _copy(dest, zbudget=False):
    copy_sample_model(dest)
    if zbudget:
        zb = SAMPLE_MODEL / "Results" / "UnsatZone_ZBud.hdf"
        if zb.is_file():
            shutil.copy2(zb, dest / "Results" / zb.name)
    return dest


@pytest.fixture(scope="module")
def model_copy(sample_model, tmp_path_factory):
    """One sample-model copy shared by every case of this module."""
    return _copy(tmp_path_factory.mktemp("dllqa") / "model")


@pytest.fixture(scope="module")
def zbudget_copy(sample_model, tmp_path_factory):
    """A copy that also carries the 100 MB UnsatZone zone-budget HDF."""
    return _copy(tmp_path_factory.mktemp("dllqa_zb") / "model", zbudget=True)


@pytest.fixture
def fresh_copy(sample_model, tmp_path):
    """A private copy for cases that leave the model state corrupted."""
    return _copy(tmp_path / "model")


def _params():
    for c in CASES:
        marks = [pytest.mark.xfail(strict=True, reason=c.xfail)] if c.xfail else []
        yield pytest.param(c, id=c.id, marks=marks)


@pytest.mark.parametrize("case", list(_params()))
def test_dllqa(case, request):
    fixture = {"module": "model_copy", "zbudget": "zbudget_copy", "fresh": "fresh_copy"}[case.copy]
    model_dir = request.getfixturevalue(fixture)
    run = run_case(case.module, case.name, model_dir, timeout=case.timeout)
    case.expect(run)
