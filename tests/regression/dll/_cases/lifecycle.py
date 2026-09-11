"""Open / close / inquiry-mode state attacks (scripts a03, a04, a09, a11,
a13, a17, a19).

Post-close calls, malformed open arguments, non-budget files handed to
``IWFMBudget``, the model's internal HDF handles colliding with the
standalone readers, use after a caught access violation, and the
inquiry-mode getters that are not guarded by ``_require_full_instantiation``.
"""
from __future__ import annotations

import gc
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (B, E, GW_BUDGET, GW_HYD, N_ELEMENTS, attempt, frame_stats,  # noqa: E402
                    main, open_model, paths, scratch_dir, stats)


def _closed(model_dir):
    m = open_model(model_dir)
    m.close()
    return m


def _after_close(model_dir, fn):
    m = _closed(model_dir)
    return attempt(lambda: fn(m))


# -- post-close --------------------------------------------------------------------

def case_close_twice(model_dir):
    m = open_model(model_dir)
    m.close()
    return attempt(lambda: (m.close(), "ok")[1])


def case_kill_after_close_raw(model_dir):
    """A second raw IW_Model_Kill after close: status must be an error, not a crash."""
    from ctypes import byref, c_int
    m = _closed(model_dir)

    def go():
        st = c_int(0)
        m._dll.IW_Model_Kill(byref(st))
        return st.value
    return attempt(go)


def case_kill_never_opened(model_dir):
    from ctypes import byref, c_int
    from iwfm_io.dll import load_dll
    dll = load_dll()

    def go():
        st = c_int(0)
        dll.IW_Model_Kill(byref(st))
        return st.value
    return attempt(go)


def case_ctx_exception_closes(model_dir):
    """Leaving the ``with`` block through an exception must close the model."""
    def go():
        try:
            with open_model(model_dir) as m:
                raise ValueError("boom")
        except ValueError:
            pass
        return {"open": m._open, "repr": repr(m)}
    return attempt(go)


def case_ctx_exception_then_reopen(model_dir):
    def go():
        try:
            with open_model(model_dir):
                raise ValueError("boom")
        except ValueError:
            pass
        m2 = open_model(model_dir)
        r = {"n_nodes": m2.n_nodes, "model_id": m2._model_id}
        m2.close()
        return r
    return attempt(go)


def case_del_gc_then_reopen(model_dir):
    def go():
        m = open_model(model_dir)
        mid = m._model_id
        del m
        gc.collect()
        m2 = open_model(model_dir)
        r = {"first_id": mid, "second_id": m2._model_id, "n_nodes": m2.n_nodes}
        m2.close()
        return r
    return attempt(go)


def case_scalars_after_close(model_dir):
    """Every scalar property of a closed model must raise (IWFMError), never
    return stale or garbage numbers."""
    m = _closed(model_dir)
    out = {}
    for name in ("n_nodes", "n_elements", "n_layers", "n_timesteps", "current_date_time",
                 "n_stream_nodes", "n_wells", "n_lakes", "n_diversions", "is_end_of_simulation"):
        out[name] = attempt(lambda: getattr(m, name))
    return {"outcome": "returned", "value": out}


def case_nodes_df_after_close(model_dir):
    return _after_close(model_dir, lambda m: list(m.nodes_df().shape))


def case_elements_df_after_close(model_dir):
    return _after_close(model_dir, lambda m: list(m.elements_df().shape))


def case_time_specs_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.get_time_specs()["dates"][:2])


def case_heads_df_after_close(model_dir):
    return _after_close(model_dir, lambda m: frame_stats(m.heads_df(1)))


def case_budget_df_after_close(model_dir):
    return _after_close(model_dir, lambda m: frame_stats(m.budget_df(GW_BUDGET, 1)))


def case_budget_list_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.get_budget_list())


def case_describe_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.describe())


def case_hydrograph_after_close(model_dir):
    return _after_close(model_dir, lambda m: stats(m.get_hydrograph(GW_HYD, 1, 1, B, E, "1MON")[1]))


def case_gw_heads_all_after_close(model_dir):
    return _after_close(model_dir, lambda m: stats(m.get_gw_heads_all()))


def case_aquifer_top_after_close(model_dir):
    return _after_close(model_dir, lambda m: stats(m.get_aquifer_top_elevation()))


def case_stream_nodes_df_after_close(model_dir):
    return _after_close(model_dir, lambda m: list(m.stream_nodes_df().shape))


def case_hydrograph_type_list_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.get_hydrograph_type_list())


def case_subregion_name_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.get_subregion_name(1))


def case_element_config_after_close(model_dir):
    return _after_close(model_dir, lambda m: m.get_element_config(1).tolist())


def case_budget_file_after_close(model_dir):
    from iwfm_io.dll import IWFMBudget
    b = IWFMBudget(str(paths(model_dir)["results"] / "GW.hdf"))
    b.close()
    return attempt(lambda: b.n_locations)


def case_budget_file_close_twice(model_dir):
    from iwfm_io.dll import IWFMBudget
    b = IWFMBudget(str(paths(model_dir)["results"] / "GW.hdf"))
    b.close()
    return attempt(lambda: (b.close(), "ok")[1])


# -- bad open arguments (IWFMModel) --------------------------------------------------

def _open_args(model_dir, *args, **kw):
    from iwfm_io.dll import IWFMModel
    kw.setdefault("is_for_inquiry", True)

    def go():
        m = IWFMModel(*args, **kw)
        r = {"n_nodes": m.n_nodes, "n_elements": m.n_elements, "model_id": m._model_id}
        m.close()
        return r
    return attempt(go)


def case_open_control(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"])


def case_open_pp_bin_instead_of_in(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, str(Path(p["sim_dir"]) / "PreProcessor.bin"), p["sim"])


def case_open_swapped_args(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["sim"], p["pp"])


def case_open_sim_missing(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], str(Path(p["sim_dir"]) / "nope.IN"))


def case_open_pp_missing(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, str(Path(p["pp"]).parent / "nope.IN"), p["sim"])


def case_open_pp_only_inquiry(model_dir):
    return _open_args(model_dir, paths(model_dir)["pp"])


def case_open_pp_directory(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, str(Path(p["pp"]).parent), p["sim"])


def case_open_pp_empty_string(model_dir):
    return _open_args(model_dir, "", paths(model_dir)["sim"])


def case_open_pp_none(model_dir):
    return _open_args(model_dir, None, paths(model_dir)["sim"])


def case_open_sim_none(model_dir):
    return _open_args(model_dir, paths(model_dir)["pp"], None)


def case_open_run_dir_wrong(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"], run_dir=os.environ.get("SystemRoot", "C:\\Windows"))


def case_open_run_dir_missing(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"], run_dir=str(Path(model_dir) / "nope" / "nope"))


def case_open_run_dir_missing_cwd_restored(model_dir):
    """A failed open must not leave the process in another directory."""
    p = paths(model_dir)
    cwd = os.getcwd()
    r = _open_args(model_dir, p["pp"], p["sim"], run_dir=str(Path(model_dir) / "nope" / "nope"))
    return {"outcome": "returned", "value": {"open": r, "cwd_restored": os.getcwd() == cwd}}


def case_open_wsa_bogus(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"], wsa_file=str(Path(model_dir) / "nope.wsa"))


def case_open_wsa_is_sim_main(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"], wsa_file=p["sim"])


def case_open_is_for_inquiry_string(model_dir):
    """``is_for_inquiry="no"`` is truthy — must not silently mean full mode."""
    p = paths(model_dir)
    r = _open_args(model_dir, p["pp"], p["sim"], is_for_inquiry="no")
    return r


def case_open_dll_version_unknown(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"], p["sim"], dll_version="9.9.9")


def case_open_pp_trailing_spaces(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, p["pp"] + "   ", p["sim"])


def case_open_pp_300_chars(model_dir):
    return _open_args(model_dir, "x" * 300 + ".IN", paths(model_dir)["sim"])


def case_open_pp_1500_chars(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, str(Path(p["pp"]).parent / ("x" * 1500 + ".IN")), p["sim"])


def case_open_pp_zero_byte(model_dir):
    p = paths(model_dir)
    empty = Path(model_dir) / "empty.IN"
    empty.write_bytes(b"")
    return _open_args(model_dir, str(empty), p["sim"])


def case_open_pp_binary_hdf(model_dir):
    p = paths(model_dir)
    return _open_args(model_dir, str(p["results"] / "GW.hdf"), p["sim"])


# -- bad files handed to IWFMBudget ------------------------------------------------------

def _open_budget(model_dir, path):
    from iwfm_io.dll import IWFMBudget

    def go():
        b = IWFMBudget(path)
        r = {"n_loc": b.n_locations, "n_ts": b.n_timesteps,
             "names": b.get_location_names()[:3], "ncol1": b.get_n_columns(1)}
        b.close()
        return r
    return attempt(go)


def case_budget_open_control(model_dir):
    return _open_budget(model_dir, str(paths(model_dir)["results"] / "GW.hdf"))


def case_budget_open_missing(model_dir):
    return _open_budget(model_dir, str(paths(model_dir)["results"] / "nope.hdf"))


def case_budget_open_zero_byte(model_dir):
    p = scratch_dir(model_dir) / "zero.hdf"
    p.write_bytes(b"")
    return _open_budget(model_dir, str(p))


def case_budget_open_truncated(model_dir):
    src = paths(model_dir)["results"] / "GW.hdf"
    p = scratch_dir(model_dir) / "trunc.hdf"
    data = src.read_bytes()
    p.write_bytes(data[: len(data) // 2])
    return _open_budget(model_dir, str(p))


def case_budget_open_heads_hdf(model_dir):
    return _open_budget(model_dir, str(paths(model_dir)["results"] / "GWHeadAll.hdf"))


def case_budget_open_hydrograph_hdf(model_dir):
    return _open_budget(model_dir, str(paths(model_dir)["results"] / "GWHyd.hdf"))


def case_budget_open_text_bud(model_dir):
    p = scratch_dir(model_dir) / "fake.bud"
    p.write_text("GW BUDGET\n1 2 3\n")
    return _open_budget(model_dir, str(p))


def case_budget_open_path_with_spaces(model_dir):
    import shutil
    d = scratch_dir(model_dir) / "path with spaces"
    d.mkdir(exist_ok=True)
    p = d / "GW copy.hdf"
    shutil.copy2(paths(model_dir)["results"] / "GW.hdf", p)
    return _open_budget(model_dir, str(p))


def case_budget_open_directory(model_dir):
    return _open_budget(model_dir, str(paths(model_dir)["results"]))


def case_budget_open_sim_main(model_dir):
    return _open_budget(model_dir, paths(model_dir)["sim"])


def case_budget_open_preprocessor_bin(model_dir):
    return _open_budget(model_dir, str(Path(paths(model_dir)["sim_dir"]) / "PreProcessor.bin"))


# -- model-internal HDF handles vs standalone readers ---------------------------------------

def case_model_then_standalone_budget(model_dir):
    from iwfm_io.dll import IWFMBudget
    gw = str(paths(model_dir)["results"] / "GW.hdf")

    def go():
        m = open_model(model_dir)
        r = {"model_budget": list(m.budget_df(GW_BUDGET, 1).shape)}
        b = IWFMBudget(gw)
        r["standalone_nloc"] = b.n_locations
        r["model_again"] = list(m.budget_df(GW_BUDGET, 1).shape)
        b.close()
        r["model_after_standalone_close"] = list(m.budget_df(GW_BUDGET, 1).shape)
        m.close()
        return r
    return attempt(go)


def case_standalone_then_model_budget(model_dir):
    from iwfm_io.dll import IWFMBudget
    gw = str(paths(model_dir)["results"] / "GW.hdf")

    def go():
        b = IWFMBudget(gw)
        m = open_model(model_dir)
        r = {"standalone_nloc": b.n_locations}
        r["model_budget"] = attempt(lambda: list(m.budget_df(GW_BUDGET, 1).shape))
        m.close()
        r["standalone_after_model_close"] = attempt(lambda: b.n_locations)
        r["standalone_values"] = attempt(lambda: stats(b.get_values(1, [1], B, E, "1MON")))
        b.close()
        return r
    return attempt(go)


def case_standalone_survives_model_open_close(model_dir):
    from iwfm_io.dll import IWFMBudget
    gw = str(paths(model_dir)["results"] / "GW.hdf")

    def go():
        b = IWFMBudget(gw)
        m = open_model(model_dir)
        m.close()
        return {"n_loc": b.n_locations, "values": stats(b.get_values(1, [1], B, E, "1MON"))}
    return attempt(go)


def case_two_models_sequential(model_dir):
    def go():
        m1 = open_model(model_dir)
        h1 = frame_stats(m1.heads_df(1))
        m1.close()
        m2 = open_model(model_dir)
        h2 = frame_stats(m2.heads_df(1))
        m2.close()
        return {"h1": h1, "h2": h2, "same": h1 == h2}
    return attempt(go)


def case_two_models_open_no_close(model_dir):
    def go():
        m1 = open_model(model_dir)
        h1 = frame_stats(m1.heads_df(1))
        m2 = open_model(model_dir)
        h2 = attempt(lambda: frame_stats(m2.heads_df(1)))
        return {"h1": h1, "h2": h2, "id1": m1._model_id, "id2": m2._model_id}
    return attempt(go)


# -- use after a caught access violation (needs a fresh copy) --------------------------------

def case_av_layer3_then_valid_calls(model_dir):
    """After ctypes catches the layer-3 access violation the same model
    must still serve correct heads/budgets and reopen cleanly."""
    import numpy as np

    def go():
        m = open_model(model_dir)
        base = m.heads_df(1)
        av = attempt(lambda: frame_stats(m.heads_df(3)))
        after = m.heads_df(1)
        r = {"av": av, "same_heads": bool(np.allclose(base.values, after.values)),
             "n_nodes": m.n_nodes, "budget": list(m.budget_df(GW_BUDGET, 1).shape)}
        m.close()
        m2 = open_model(model_dir)
        r["reopen_nodes"] = m2.n_nodes
        m2.close()
        return r
    return attempt(go)


def case_av_gw_heads_all_then_valid_calls(model_dir):
    def go():
        m = open_model(model_dir)
        av = attempt(lambda: stats(m.get_gw_heads_all()))
        r = {"av": av, "n_nodes": m.n_nodes, "heads": list(m.heads_df(1).shape),
             "hyd": list(m.hydrograph_df(GW_HYD, 1, 1).shape)}
        m.close()
        return r
    return attempt(go)


# -- inquiry-mode getters --------------------------------------------------------------

def _inq(model_dir, fn):
    m = open_model(model_dir)
    return attempt(lambda: fn(m))


def case_inquiry_stream_flows_guarded(model_dir):
    """Control: the guarded getter raises a clean IWFMError in inquiry mode."""
    return _inq(model_dir, lambda m: stats(m.get_stream_flows()))


def case_inquiry_stream_inflows_at(model_dir):
    return _inq(model_dir, lambda m: m.get_stream_inflows_at([1]).tolist())


def case_inquiry_stream_inflows_at_999(model_dir):
    return _inq(model_dir, lambda m: m.get_stream_inflows_at([999]).tolist())


def case_inquiry_stream_inflow_nodes(model_dir):
    return _inq(model_dir, lambda m: m.get_stream_inflow_nodes().tolist())


def case_inquiry_required_diversions(model_dir):
    return _inq(model_dir, lambda m: m.get_required_diversions([1]).tolist())


def case_inquiry_actual_diversions(model_dir):
    return _inq(model_dir, lambda m: m.get_actual_diversions([1]).tolist())


def case_inquiry_actual_diversions_999(model_dir):
    return _inq(model_dir, lambda m: m.get_actual_diversions([999]).tolist())


def case_inquiry_bypass_outflows(model_dir):
    return _inq(model_dir, lambda m: m.get_bypass_outflows().tolist())


def case_inquiry_supply_requirement_ag(model_dir):
    return _inq(model_dir, lambda m: m.get_supply_requirement_ag(4, [1, 2]).tolist())


def case_inquiry_supply_requirement_urban(model_dir):
    return _inq(model_dir, lambda m: m.get_supply_requirement_urban(2, [1]).tolist())


def case_inquiry_supply_short_ag(model_dir):
    return _inq(model_dir, lambda m: m.get_supply_short_at_origin_ag(2, [1]).tolist())


def case_inquiry_supply_demand_df(model_dir):
    return _inq(model_dir, lambda m: m.supply_demand_df(4, [1, 2]).to_dict("list"))


def case_inquiry_supply_purpose(model_dir):
    return _inq(model_dir, lambda m: m.get_supply_purpose(1, [1]).tolist())


def case_inquiry_subregion_ag_pumping_depth(model_dir):
    return _inq(model_dir, lambda m: m.get_subregion_ag_pumping_avg_depth_to_gw().tolist())


def case_inquiry_zone_ag_pumping_depth(model_dir):
    return _inq(model_dir, lambda m: m.get_zone_ag_pumping_avg_depth_to_gw(
        list(range(1, N_ELEMENTS + 1)), [1] * N_ELEMENTS, 1).tolist())


def case_inquiry_n_ag_crops(model_dir):
    return _inq(model_dir, lambda m: m.get_n_ag_crops())


def case_inquiry_future_water_demand(model_dir):
    return _inq(model_dir, lambda m: m.get_future_water_demand_for_diversion(1, B))


def case_inquiry_subsidence_all(model_dir):
    return _inq(model_dir, lambda m: stats(m.get_subsidence_all()))


def case_inquiry_current_date_time(model_dir):
    return _inq(model_dir, lambda m: {"date": m.current_date_time, "end": m.is_end_of_simulation})


def case_inquiry_gw_heads_all(model_dir):
    return _inq(model_dir, lambda m: stats(m.get_gw_heads_all()))


def case_inquiry_gw_heads_all_previous(model_dir):
    return _inq(model_dir, lambda m: stats(m.get_gw_heads_all(previous=True)))


def case_inquiry_gw_heads_initial(model_dir):
    return _inq(model_dir, lambda m: stats(m.get_gw_heads_initial()))


def case_inquiry_aquifer_parameters(model_dir):
    """Known issue #1: spurious 'Duplicate Node ID' fatal on the sample model."""
    return _inq(model_dir, lambda m: {k: stats(v) for k, v in m.get_aquifer_parameters().items()})


def case_inquiry_aquifer_horizontal_k(model_dir):
    return _inq(model_dir, lambda m: stats(m.get_aquifer_horizontal_k()))


def case_inquiry_simulate_timestep(model_dir):
    return _inq(model_dir, lambda m: m.simulate_timestep())


def case_inquiry_advance_time(model_dir):
    return _inq(model_dir, lambda m: m.advance_time())


def case_inquiry_read_timeseries_data(model_dir):
    return _inq(model_dir, lambda m: m.read_timeseries_data())


def case_inquiry_print_results(model_dir):
    return _inq(model_dir, lambda m: m.print_results())


def case_inquiry_simulate(model_dir):
    return _inq(model_dir, lambda m: m.simulate())


def case_inquiry_simulate_interval(model_dir):
    return _inq(model_dir, lambda m: m.simulate_interval("1MON"))


def case_inquiry_compute_future_water_demands(model_dir):
    return _inq(model_dir, lambda m: m.compute_future_water_demands(E))


def case_delete_inquiry_data_file_bogus(model_dir):
    """A bogus file name must not delete the active model's inquiry file
    (the Fortran ignores its argument)."""
    import os
    m = open_model(model_dir)
    inq = os.path.join(paths(model_dir)["sim_dir"], "IW_ModelData_ForInquiry.bin")
    exists_before = os.path.isfile(inq)
    call = attempt(lambda: m.delete_inquiry_data_file(m._dll, "nope.IN"))
    return {"exists_before": exists_before, "exists_after": os.path.isfile(inq),
            "call": call}


def case_switch_to_999(model_dir):
    return _inq(model_dir, lambda m: m.switch_to(m._dll, 999))


def case_switch_to_0(model_dir):
    return _inq(model_dir, lambda m: m.switch_to(m._dll, 0))


def case_switch_to_999_then_n_nodes(model_dir):
    def go(m):
        sw = attempt(lambda: m.switch_to(m._dll, 999))
        return {"switch": sw, "n_nodes": attempt(lambda: m.n_nodes)}
    return _inq(model_dir, go)


# -- enums / logging (no model) --------------------------------------------------------

def case_enum_before_load(model_dir):
    """``BudgetTypeID.GW`` is None until ``load_all_type_ids``; passing it
    into a getter must fail with a clear error, not ``c_int(None)``."""
    from iwfm_io.dll import BudgetTypeID
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_n_columns(BudgetTypeID.GW, 1))


def case_enum_after_load(model_dir):
    from iwfm_io.dll import BudgetTypeID, LocationTypeID, ZoneExtentID, load_dll, misc

    def go():
        misc.load_all_type_ids(load_dll())
        return {"GW": BudgetTypeID.GW, "LWU": BudgetTypeID.LWU, "Zone": LocationTypeID.Zone,
                "Horizontal": ZoneExtentID.Horizontal, "Vertical": ZoneExtentID.Vertical}
    return attempt(go)


def case_get_version_none(model_dir):
    from iwfm_io.dll import get_version
    return attempt(lambda: get_version(None))


def case_set_log_file_directory(model_dir):
    from iwfm_io.dll import load_dll, set_log_file
    return attempt(lambda: (set_log_file(load_dll(), str(scratch_dir(model_dir))), "accepted")[1])


def case_set_log_file_then_open(model_dir):
    from iwfm_io.dll import close_log_file, load_dll, set_log_file
    p = scratch_dir(model_dir) / "qa log.txt"

    def go():
        dll = load_dll()
        set_log_file(dll, str(p))
        m = open_model(model_dir)
        m.close()
        close_log_file(dll)
        return {"exists": p.exists(), "size": p.stat().st_size if p.exists() else None}
    return attempt(go)


def case_close_log_file_never_opened(model_dir):
    from iwfm_io.dll import close_log_file, load_dll
    return attempt(lambda: (close_log_file(load_dll()), close_log_file(load_dll()), "ok")[2])


def case_get_last_message_fresh(model_dir):
    from iwfm_io.dll import get_last_message, load_dll
    return attempt(lambda: get_last_message(load_dll()))


def case_log_last_message_no_log(model_dir):
    from iwfm_io.dll import load_dll, log_last_message
    return attempt(lambda: log_last_message(load_dll()))


def case_open_after_bad_open(model_dir):
    """A failed open (missing sim main) must not poison the next good open."""
    from iwfm_io.dll import IWFMModel
    p = paths(model_dir)

    def go():
        bad = attempt(lambda: IWFMModel(p["pp"], str(Path(p["sim_dir"]) / "nope.IN"), is_for_inquiry=True))
        m = open_model(model_dir)
        r = {"bad": bad, "n_nodes": m.n_nodes, "heads": frame_stats(m.heads_df(1))}
        m.close()
        return r
    return attempt(go)


if __name__ == "__main__":
    main(globals())
