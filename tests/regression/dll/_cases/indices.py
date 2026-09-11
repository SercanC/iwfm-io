"""Bad IDs, indices, column lists and buffer sizes (scripts a05-a07, a09,
a13, a15, a16, a19).

Out-of-range layers/locations reach the Fortran unchecked: layer 3 of a
2-layer model is an access violation, budget location 0 corrupts the
heap, and several structure getters return garbage instead of raising.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (B, E, GW_BUDGET, GW_HYD, LWU_BUDGET, N_ELEMENTS, N_NODES,  # noqa: E402
                    STREAM_HYD, attempt, frame_stats, main, open_model, paths, stats)


# -- heads: layer -------------------------------------------------------------

def _heads_layer(model_dir, layer):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.heads_df(layer)))


def case_heads_layer_0(model_dir):
    return _heads_layer(model_dir, 0)


def case_heads_layer_neg1(model_dir):
    return _heads_layer(model_dir, -1)


def case_heads_layer_3(model_dir):
    """Layer 3 of a 2-layer model."""
    return _heads_layer(model_dir, 3)


def case_heads_layer_99(model_dir):
    return _heads_layer(model_dir, 99)


def case_heads_date_1000_chars(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.heads_df(1, "1" * 1000, "1" * 1000)))


def case_heads_begin_len_ne_end_len(model_dir):
    """The DLL takes ONE length for both date strings."""
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.heads_df(1, B, "09/30/2000")))


# -- hydrographs ------------------------------------------------------------------

def _hyd(model_dir, t=GW_HYD, i=1, layer=1, interval="1DAY", **kw):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.hydrograph_df(t, i, layer, B, E, interval=interval, **kw)))


def case_hyd_type_0(model_dir):
    return _hyd(model_dir, t=0)


def case_hyd_type_neg1(model_dir):
    return _hyd(model_dir, t=-1)


def case_hyd_type_999(model_dir):
    return _hyd(model_dir, t=999)


def case_hyd_type_subregion(model_dir):
    """Location type 4 (subregion) is not a hydrograph type."""
    return _hyd(model_dir, t=4)


def case_hyd_index_0(model_dir):
    return _hyd(model_dir, i=0)


def case_hyd_index_neg1(model_dir):
    return _hyd(model_dir, i=-1)


def case_hyd_index_999(model_dir):
    return _hyd(model_dir, i=999)


def case_hyd_index_n_plus_1(model_dir):
    m = open_model(model_dir)
    n = m.get_n_hydrographs(GW_HYD)
    return attempt(lambda: frame_stats(m.hydrograph_df(GW_HYD, n + 1, 1, B, E, interval="1DAY")))


def _hyd_layer(model_dir, layer):
    """GW-head hydrograph with an impossible layer: either rejected or the
    layer is ignored (the hydrograph spec carries its own layer) and the
    result equals the layer-1 control — never a third answer."""
    m = open_model(model_dir)
    control = frame_stats(m.hydrograph_df(GW_HYD, 1, 1, B, E, interval="1DAY"))
    r = attempt(lambda: frame_stats(m.hydrograph_df(GW_HYD, 1, layer, B, E, interval="1DAY")))
    if r["outcome"] == "returned":
        r["value"] = {"attack": r["value"], "control": control, "same_as_control": r["value"] == control}
    return r


def case_hyd_layer_0(model_dir):
    return _hyd_layer(model_dir, 0)


def case_hyd_layer_neg1(model_dir):
    return _hyd_layer(model_dir, -1)


def case_hyd_layer_99(model_dir):
    return _hyd_layer(model_dir, 99)


def case_hyd_stream_index_999(model_dir):
    return _hyd(model_dir, t=STREAM_HYD, i=999)


def case_hyd_interval_1000_chars(model_dir):
    return _hyd(model_dir, interval="1" * 1000)


def case_hyd_fact_nan(model_dir):
    return _hyd(model_dir, fact_lt=float("nan"))


def case_n_hydrographs_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_n_hydrographs(999))


def case_hydrograph_ids_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_hydrograph_ids(999).tolist())


def case_hydrograph_coordinates_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: [stats(a) for a in m.get_hydrograph_coordinates(0)])


def case_hydrograph_coordinates_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: [stats(a) for a in m.get_hydrograph_coordinates(999)])


def case_hyd_monthly_stamps_vs_daily(model_dir):
    """1MON stamps of a daily GW-head hydrograph: every monthly stamp must
    be a stamp of the daily series (month ends), never a fixed 31-day
    stride, and the monthly value must equal the daily value at that
    stamp (heads are stocks -> the DLL returns the value at the stamp)."""
    import numpy as np
    m = open_model(model_dir)

    def go():
        d1, v1 = m.get_hydrograph(GW_HYD, 1, 1, B, E, "1DAY")
        dm, vm = m.get_hydrograph(GW_HYD, 1, 1, B, E, "1MON")
        daily = dict(zip(np.round(d1, 6).tolist(), v1.tolist()))
        idx = m._excel_dates_to_index(dm)
        days = idx.day.tolist()
        strides = np.diff(dm).tolist()
        in_daily = [round(float(d), 6) in daily for d in dm]
        value_match = [bool(np.isclose(daily.get(round(float(d), 6), np.nan), v))
                       for d, v in zip(dm, vm)]
        return {
            "n_monthly": int(len(dm)),
            "stamps_first": [str(x) for x in idx[:4]],
            "days_of_month": sorted(set(days)),
            "strides_first": strides[:6],
            "all_stamps_in_daily": all(in_daily),
            "all_values_match_daily": all(value_match),
            "n_value_mismatch": int(sum(not x for x in value_match)),
        }
    return attempt(go)


def case_stream_hyd_dates_sane(model_dir):
    """Stream hydrograph (type 12) raw dates must all lie in the simulation
    window (Excel serial 33000..37000) and values must be finite."""
    import numpy as np
    m = open_model(model_dir)

    def go():
        out = {}
        for iv in ("1DAY", "1MON", "1YEAR"):
            d, v = m.get_hydrograph(STREAM_HYD, 1, 1, B, E, iv)
            bad = (d < 33000) | (d > 37000)
            out[iv] = {"n": int(len(d)), "n_bad_dates": int(bad.sum()),
                       "any_nonfinite": bool(~np.isfinite(v).all()),
                       "vmax_abs": float(np.abs(v).max()) if len(v) else None}
        return out
    return attempt(go)


# -- budgets through the model -----------------------------------------------

def _budget(model_dir, t=GW_BUDGET, loc=1, cols=(1, 2), interval="1DAY", **kw):
    m = open_model(model_dir)

    def go():
        r = m.get_budget_timeseries(t, loc, list(cols), B, E, interval, **kw)
        return {"n": int(len(r["dates"])), "values": stats(r["values"]),
                "data_types": r["data_types"].tolist()}
    return attempt(go)


def case_budget_type_0(model_dir):
    return _budget(model_dir, t=0)


def case_budget_type_neg1(model_dir):
    return _budget(model_dir, t=-1)


def case_budget_type_999(model_dir):
    return _budget(model_dir, t=999)


def case_budget_loc_0(model_dir):
    """Location 0 -> heap corruption in the Fortran (a07/a14/a18)."""
    return _budget(model_dir, loc=0)


def case_budget_loc_neg1(model_dir):
    return _budget(model_dir, loc=-1)


def case_budget_loc_999(model_dir):
    return _budget(model_dir, loc=999)


def case_budget_loc_n_plus_1(model_dir):
    """GW budget has 3 locations (2 subregions + entire model)."""
    return _budget(model_dir, loc=4)


def case_budget_lwu_loc_999(model_dir):
    return _budget(model_dir, t=LWU_BUDGET, loc=999)


def case_budget_cols_0(model_dir):
    return _budget(model_dir, cols=(0,))


def case_budget_cols_neg1(model_dir):
    return _budget(model_dir, cols=(-1,))


def case_budget_cols_999(model_dir):
    return _budget(model_dir, cols=(999,))


def case_budget_cols_empty(model_dir):
    return _budget(model_dir, cols=())


def case_budget_cols_duplicate(model_dir):
    return _budget(model_dir, cols=(1, 1))


def case_budget_cols_ncol_plus_1(model_dir):
    m = open_model(model_dir)
    n = m.get_budget_n_columns(GW_BUDGET, 1)
    return attempt(lambda: stats(m.get_budget_timeseries(GW_BUDGET, 1, [n + 1], B, E, "1MON")["values"]))


def case_budget_fact_vl_nan(model_dir):
    return _budget(model_dir, fact_vl=float("nan"))


def case_budget_df_loc_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.budget_df(GW_BUDGET, 0)))


def case_budget_df_loc_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: frame_stats(m.budget_df(GW_BUDGET, 999)))


def case_budget_df_cols_swapped(model_dir):
    """columns=[2, 1] must return column 2's data under column 2's title."""
    import numpy as np
    m = open_model(model_dir)

    def go():
        a = m.budget_df(GW_BUDGET, 1, columns=[2, 1])
        b = m.budget_df(GW_BUDGET, 1, columns=[1, 2])
        return {"cols_a": a.columns.tolist(), "cols_b": b.columns.tolist(),
                "a0_is_b1": bool(np.allclose(a.iloc[:, 0], b.iloc[:, 1])),
                "a1_is_b0": bool(np.allclose(a.iloc[:, 1], b.iloc[:, 0]))}
    return attempt(go)


def case_budget_n_columns_loc_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_n_columns(GW_BUDGET, 999))


def case_budget_n_columns_loc_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_n_columns(GW_BUDGET, 0))


def case_budget_n_columns_type_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_n_columns(999, 1))


def case_budget_column_titles_type_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_column_titles(0, 1))


def case_budget_column_titles_loc_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: m.get_budget_column_titles(GW_BUDGET, 999))


def case_budget_monthly_avg_loc_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_monthly_average(GW_BUDGET, 999, B, E)["flows"]))


def case_budget_monthly_avg_type_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_monthly_average(999, 1, B, E)["flows"]))


def case_budget_annual_loc_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_annual(GW_BUDGET, 0, B, E)["flows"]))


def case_budget_annual_type_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_annual(999, 1, B, E)["flows"]))


def case_cum_gw_storage_subregion_0(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_cum_gw_storage_change(0, B, E, "1MON")[1]))


def case_cum_gw_storage_subregion_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_cum_gw_storage_change(999, B, E, "1MON")[1]))


def case_annual_cum_gw_storage_subregion_999(model_dir):
    m = open_model(model_dir)
    return attempt(lambda: stats(m.get_budget_annual_cum_gw_storage_change(999, B, E)[0]))


# -- standalone budget file --------------------------------------------------------

def _bud(model_dir):
    from iwfm_io.dll import IWFMBudget
    return IWFMBudget(str(paths(model_dir)["results"] / "GW.hdf"))


def _bud_values(model_dir, loc=1, cols=(1, 2), interval="1DAY", **kw):
    b = _bud(model_dir)
    return attempt(lambda: stats(b.get_values(loc, list(cols), B, E, interval, **kw)))


def case_budget_file_loc_0(model_dir):
    return _bud_values(model_dir, loc=0)


def case_budget_file_loc_neg1(model_dir):
    return _bud_values(model_dir, loc=-1)


def case_budget_file_loc_999(model_dir):
    return _bud_values(model_dir, loc=999)


def case_budget_file_col_0(model_dir):
    return _bud_values(model_dir, cols=(0,))


def case_budget_file_col_neg1(model_dir):
    return _bud_values(model_dir, cols=(-1,))


def case_budget_file_col_999(model_dir):
    return _bud_values(model_dir, cols=(999,))


def case_budget_file_col_ncol_plus_1(model_dir):
    b = _bud(model_dir)
    n = b.get_n_columns(1)
    return attempt(lambda: stats(b.get_values(1, [n + 1], B, E, "1MON")))


def case_budget_file_cols_empty(model_dir):
    return _bud_values(model_dir, cols=())


def case_budget_file_cols_duplicate(model_dir):
    return _bud_values(model_dir, cols=(1, 1))


def case_budget_file_fact_vl_nan(model_dir):
    return _bud_values(model_dir, fact_vl=float("nan"))


def case_budget_file_values_for_column_999(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: stats(b.get_values_for_column(1, 999, "1MON", B, E)[1]))


def case_budget_file_values_for_column_0(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: stats(b.get_values_for_column(1, 0, "1MON", B, E)[1]))


def case_budget_file_values_for_column_loc_999(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: stats(b.get_values_for_column(999, 2, "1MON", B, E)[1]))


def case_budget_file_n_columns_0(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_n_columns(0))


def case_budget_file_n_columns_999(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_n_columns(999))


def case_budget_file_column_headers_0(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_column_headers(0))


def case_budget_file_column_headers_999(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_column_headers(999))


def case_budget_file_title_lines_0(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_title_lines(0))


def case_budget_file_title_lines_999(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_title_lines(999))


def case_budget_file_title_unit_200_chars(model_dir):
    b = _bud(model_dir)
    return attempt(lambda: b.get_title_lines(1, length_unit="F" * 200))


def case_budget_file_header_units_mixed_lengths(model_dir):
    """The DLL takes ONE length for the three unit strings."""
    b = _bud(model_dir)
    return attempt(lambda: b.get_column_headers(1, length_unit="FT", area_unit="ACRES", volume_unit="AF")[:3])


# -- structure getters ------------------------------------------------------------

def _model_call(model_dir, fn):
    m = open_model(model_dir)
    return attempt(lambda: fn(m))


def case_element_config_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_element_config(0).tolist())


def case_element_config_neg1(model_dir):
    return _model_call(model_dir, lambda m: m.get_element_config(-1).tolist())


def case_element_config_n_plus_1(model_dir):
    return _model_call(model_dir, lambda m: m.get_element_config(N_ELEMENTS + 1).tolist())


def case_element_config_999999(model_dir):
    return _model_call(model_dir, lambda m: m.get_element_config(999999).tolist())


def case_elements_df_sane(model_dir):
    """elements_df is built from get_element_config: every vertex must be a
    real node id (1..441) and node1..node3 nonzero."""
    def go(m):
        df = m.elements_df()
        v = df[["node1", "node2", "node3", "node4"]].values
        return {"shape": list(df.shape),
                "sane": bool((v[:, :3] > 0).all() and (v <= N_NODES).all() and (v >= 0).all())}
    return _model_call(model_dir, go)


def case_subregion_name_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_subregion_name(0))


def case_subregion_name_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_subregion_name(999))


def case_reach_n_nodes_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_reach_n_nodes(0))


def case_reach_n_nodes_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_reach_n_nodes(999))


def case_reach_stream_nodes_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_reach_stream_nodes(999).tolist())


def case_reach_gw_nodes_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_reach_gw_nodes(0).tolist())


def case_n_rating_table_points_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_n_rating_table_points(999))


def case_stream_rating_table_999(model_dir):
    return _model_call(model_dir, lambda m: [stats(a) for a in m.get_stream_rating_table(999)])


def case_stream_upstream_nodes_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_stream_upstream_nodes(999).tolist())


def case_is_stream_upstream_node_999(model_dir):
    return _model_call(model_dir, lambda m: m.is_stream_upstream_node(999, 1))


def case_reach_upstream_reaches_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_reach_upstream_reaches(999).tolist())


def case_reaches_for_stream_nodes_bad(model_dir):
    return _model_call(model_dir, lambda m: m.get_reaches_for_stream_nodes([0, 999, -1]).tolist())


def case_n_elements_in_lake_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_n_elements_in_lake(0))


def case_n_elements_in_lake_99(model_dir):
    return _model_call(model_dir, lambda m: m.get_n_elements_in_lake(99))


def case_elements_in_lake_99(model_dir):
    return _model_call(model_dir, lambda m: m.get_elements_in_lake(99).tolist())


def case_well_n_elements_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_well_n_elements(999))


def case_well_elements_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_well_elements(0).tolist())


def case_diversion_n_elements_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_diversion_n_elements(999))


def case_diversion_elements_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_diversion_elements(999).tolist())


def case_diversion_export_nodes_bad(model_dir):
    return _model_call(model_dir, lambda m: m.get_diversion_export_nodes([0, 999]).tolist())


def case_diversion_recharge_zone_elements_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_diversion_recharge_zone_elements(999))


def case_bypass_export_nodes_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_bypass_export_nodes([999]).tolist())


def case_bypass_export_dest_data_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_bypass_export_dest_data([0]))


def case_bypass_recoverable_loss_factor_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_bypass_recoverable_loss_factor(999))


def case_stratigraphy_at_xy_far_outside(model_dir):
    return _model_call(model_dir, lambda m: m.get_stratigraphy_at_xy(-1e9, -1e9))


def case_stratigraphy_at_xy_nan(model_dir):
    return _model_call(model_dir, lambda m: m.get_stratigraphy_at_xy(float("nan"), float("nan")))


def case_parametric_nodes_grid_99(model_dir):
    return _model_call(model_dir, lambda m: (m.get_n_parametric_grids(), m.get_n_parametric_nodes(99)))


def case_parametric_node_xy_99(model_dir):
    return _model_call(model_dir, lambda m: m.get_parametric_node_xy(99))


def case_parametric_element_config_99(model_dir):
    return _model_call(model_dir, lambda m: m.get_parametric_element_config(99, 1).tolist())


def case_parametric_aquifer_parameters_99(model_dir):
    return _model_call(model_dir, lambda m: {k: list(v.shape) for k, v in m.get_parametric_aquifer_parameters(99).items()})


def case_n_locations_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_n_locations(0))


def case_n_locations_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_n_locations(999))


def case_location_ids_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_location_ids(999).tolist()[:5])


def case_names_0(model_dir):
    return _model_call(model_dir, lambda m: m.get_names(0)[:5])


def case_names_999(model_dir):
    return _model_call(model_dir, lambda m: m.get_names(999)[:5])


def case_land_use_areas_undersized_buffer(model_dir):
    """n_elements=1 hands the DLL a 1-element buffer for a 400-element write."""
    return _model_call(model_dir, lambda m: list(m.get_land_use_areas(B, "10/31/1990_24:00", 1, 1, n_elements=1).shape))


def case_land_use_areas_control(model_dir):
    return _model_call(model_dir, lambda m: list(m.get_land_use_areas(B, "10/31/1990_24:00", 1, 1).shape))


def case_zbudget_list(model_dir):
    """Known-issue #5: the sample model's zbudget list needs a None guard."""
    return _model_call(model_dir, lambda m: m.get_zbudget_list())


def case_zbudget_n_columns_bogus(model_dir):
    return _model_call(model_dir, lambda m: m.get_zbudget_n_columns(999, 1, 1, [1], [1], [1]))


if __name__ == "__main__":
    main(globals())
