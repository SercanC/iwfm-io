"""Date / interval string attacks (hostile-QA F1, V22, W7; scripts a05-a07,
a09-a11, a14, a18).

A mistyped date or interval reaches the Fortran unvalidated; the DLL
executes ``STOP`` (FATAL banner, exit code 0, no Python exception).
Windows outside the simulation come back as silent zeros.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (B, E, GW_BUDGET, GW_HYD, attempt, frame_stats, main,  # noqa: E402
                    open_model, paths, skipped, zbudget_file)


# -- heads ---------------------------------------------------------------

def _heads(model_dir, layer=1, b=B, e=E):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.heads_df(layer, b, e)))


def case_heads_garbage_date(model_dir):
    return _heads(model_dir, b="garbage")


def case_heads_iso_date(model_dir):
    return _heads(model_dir, b="1990-10-01", e="2000-09-30")


def case_heads_empty_date(model_dir):
    return _heads(model_dir, b="", e="")


def case_heads_impossible_date(model_dir):
    return _heads(model_dir, b="13/45/1990_24:00", e="13/45/1990_24:00")


def case_heads_hour_25(model_dir):
    return _heads(model_dir, b="10/01/1990_25:00", e="09/30/2000_25:00")


def case_heads_date_without_time(model_dir):
    """``MM/DD/YYYY`` without ``_HH:MM``: either rejected or identical to
    the ``_24:00`` control (today the stamps shift by a day)."""
    m = open_model(model_dir)
    control = frame_stats(m.heads_df(1, B, E))
    r = attempt(lambda: frame_stats(m.heads_df(1, "10/01/1990", "09/30/2000")))
    if r["outcome"] == "returned":
        r["value"] = {"attack": r["value"], "control": control,
                      "same_as_control": r["value"] == control}
    return r


def case_heads_begin_after_end(model_dir):
    return _heads(model_dir, b=E, e=B)


def case_heads_window_before_sim(model_dir):
    return _heads(model_dir, b="10/01/1980_24:00", e="10/31/1980_24:00")


def case_heads_window_straddles_end(model_dir):
    return _heads(model_dir, b="09/01/2000_24:00", e="10/31/2005_24:00")


def case_heads_window_straddles_begin(model_dir):
    return _heads(model_dir, b="09/01/1990_24:00", e="10/31/1990_24:00")


# -- budgets through the model ---------------------------------------------

def _budget(model_dir, interval=None, b=None, e=None):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.budget_df(GW_BUDGET, 1, b, e, interval=interval)))


def case_budget_interval_3mon(model_dir):
    return _budget(model_dir, "3MON")


def case_budget_interval_empty(model_dir):
    return _budget(model_dir, "")


def case_budget_interval_garbage(model_dir):
    return _budget(model_dir, "garbage")


def case_budget_interval_lowercase(model_dir):
    return _budget(model_dir, "1year")


def case_budget_interval_trailing_space(model_dir):
    return _budget(model_dir, "1YEAR ")


def case_budget_interval_1year_control(model_dir):
    return _budget(model_dir, "1YEAR")


def case_budget_garbage_dates(model_dir):
    return _budget(model_dir, "1MON", "x", "y")


# -- hydrographs -------------------------------------------------------------

def _hyd(model_dir, b=B, e=E, interval="1DAY"):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.hydrograph_df(GW_HYD, 1, 1, b, e, interval=interval)))


def case_hydrograph_garbage_date(model_dir):
    return _hyd(model_dir, b="x", e="y")


def case_hydrograph_interval_garbage(model_dir):
    return _hyd(model_dir, interval="garbage")


def case_hydrograph_window_before_sim(model_dir):
    return _hyd(model_dir, b="10/01/1980_24:00", e="10/31/1980_24:00", interval="1MON")


# -- standalone budget / zbudget files ------------------------------------------

def _budget_file(model_dir, b=B, e=E, interval="1MON"):
    from iwfm_io.dll import IWFMBudget
    bud = IWFMBudget(str(paths(model_dir)["results"] / "GW.hdf"))
    return attempt(lambda: {"shape": list(bud.get_values(1, [1, 2], b, e, interval).shape)})


def case_budget_file_interval_garbage(model_dir):
    return _budget_file(model_dir, interval="garbage")


def case_budget_file_garbage_dates(model_dir):
    return _budget_file(model_dir, b="x", e="y")


def case_zbudget_garbage_dates(model_dir):
    from iwfm_io.dll import IWFMZBudget
    zb = zbudget_file(model_dir)
    if zb is None:
        return skipped("UnsatZone_ZBud.hdf not present")
    z = IWFMZBudget(zb)
    z.generate_zone_list(1, list(range(1, 401)), [1] * 400, [1] * 200 + [2] * 200, [1, 2], ["Z1", "Z2"])
    return attempt(lambda: {"shape": list(z.get_values_for_zone(1, [1, 2, 3], "x", "y", "1MON").shape)})


# -- module-level time utilities (no model needed) --------------------------------

def _dll():
    from iwfm_io.dll import load_dll
    return load_dll()


def case_n_intervals_control(model_dir):
    from iwfm_io.dll import get_n_intervals
    return attempt(lambda: get_n_intervals(_dll(), B, E, "1MON"))


def case_n_intervals_bad_date(model_dir):
    from iwfm_io.dll import get_n_intervals
    return attempt(lambda: get_n_intervals(_dll(), "garbage", E, "1MON"))


def case_n_intervals_bad_interval(model_dir):
    from iwfm_io.dll import get_n_intervals
    return attempt(lambda: get_n_intervals(_dll(), B, E, "3MON"))


def case_n_intervals_begin_after_end(model_dir):
    from iwfm_io.dll import get_n_intervals
    return attempt(lambda: get_n_intervals(_dll(), E, B, "1MON"))


def case_increment_time_garbage_interval(model_dir):
    from iwfm_io.dll import increment_time
    return attempt(lambda: increment_time(_dll(), B, "garbage"))


def case_increment_time_bad_date(model_dir):
    from iwfm_io.dll import increment_time
    return attempt(lambda: increment_time(_dll(), "garbage", "1MON"))


def case_increment_time_year_9999(model_dir):
    from iwfm_io.dll import increment_time
    return attempt(lambda: increment_time(_dll(), "12/31/9999_24:00", "1MON"))


def case_is_time_greater_than_garbage(model_dir):
    from iwfm_io.dll import is_time_greater_than
    return attempt(lambda: is_time_greater_than(_dll(), "x", "y"))


if __name__ == "__main__":
    main(globals())
