"""Hostile-QA regressions: iwfm_io.pest.

Imported from the 2026-09-09 hostile-QA pass. Every test asserts the
EXPECTED behaviour; ``xfail(strict=True)`` marks the ones that still
reproduce a defect on the current code.
"""
import numpy as np
import pandas as pd
import pytest

from tests.regression._helpers import copy_model, rmtree_deep, run_python

pytestmark = [pytest.mark.regression, pytest.mark.sample_model]

GW = "Simulation/GW/GW_MAIN.dat"


@pytest.fixture
def model_copy(tmp_path):
    """Inputs-only copy of the sample model (no Results)."""
    return copy_model(tmp_path / "m")


def _action(**kw):
    from iwfm_io.pest.apply import ApplyAction
    base = dict(reader="gw_main", path=GW, table="parametric_grids.0.params",
                column="kh", values_file="mult_kh.csv",
                key_cols=("node_id", "layer"), base_dir="Simulation")
    base.update(kw)
    return ApplyAction(**base)


# 1 ---------------------------------------------------------------- kriging NaN
def test_apply_kriging_factors_nan_pilot_value_is_not_silently_zero():
    from iwfm_io.pest.pilot_points import (ExpVariogram, apply_kriging_factors,
                                           compute_kriging_factors,
                                           place_pilot_points_grid)
    nodes = pd.DataFrame({"node_id": np.arange(1, 26),
                          "x": np.tile(np.arange(5) * 1000.0, 5),
                          "y": np.repeat(np.arange(5) * 1000.0, 5)})
    pp = place_pilot_points_grid(nodes, 2000)
    fac = compute_kriging_factors(pp, nodes, ExpVariogram(a=3000.0))
    vals = pd.Series(50.0, index=pp["pp_id"])
    vals.iloc[0] = np.nan
    # decided behaviour (2.13.0): a NaN pilot value is an error, never a
    # silent zero contribution
    with pytest.raises(ValueError, match="NaN"):
        apply_kriging_factors(fac, vals)


# 2 ------------------------------------------------------- apply: NaN multiplier
def test_apply_parameters_nan_multiplier_raises(model_copy):
    from iwfm_io.pest.apply import apply_parameters
    d = model_copy
    pd.DataFrame([(1, 1, np.nan), (1, 2, 2.0)],
                 columns=["node_id", "layer", "value"]).to_csv(d / "mult_kh.csv", index=False)
    with pytest.raises(ValueError):
        apply_parameters(d, [_action()])   # observed: n_applied=1, row 1 silently kept at base


# 3 ------------------------------------------------ apply: header-only value file
def test_apply_parameters_header_only_value_file_raises(model_copy):
    from iwfm_io.pest.apply import apply_parameters
    d = model_copy
    (d / "mult_kh.csv").write_text("node_id,layer,value\n")
    with pytest.raises(ValueError):
        apply_parameters(d, [_action()])   # observed: n_applied=0, no error, log min/max NaN


# 4 ---------------------------------------- apply: base_dir=None -> absolute paths
def test_apply_parameters_without_base_dir_keeps_relative_paths(model_copy):
    from iwfm_io.pest.apply import apply_parameters
    d = model_copy
    pd.DataFrame([(1, 1, 1.0), (1, 2, 1.0)],
                 columns=["node_id", "layer", "value"]).to_csv(d / "mult_kh.csv", index=False)
    # decided behaviour (2.13.0): base_dir is required for component mains
    # (without it the writer emitted absolute paths IWFM rejects); the
    # file must be left untouched
    before = (d / GW).read_text()
    with pytest.raises(ValueError, match="base_dir"):
        apply_parameters(d, [_action(base_dir=None)])
    assert (d / GW).read_text() == before


# 5 -------------------------------------------- setup_agents nested dest_root hang
def test_setup_agents_dest_inside_template_terminates(tmp_path):
    """``dest_root`` inside the template replicates the tree into itself.

    Run in a subprocess with a hard timeout so a hang cannot wedge the
    suite; the nested tree is removed with a long-path-safe rmtree.
    """
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    (tpl / "c.pst").write_text("pcf\n")
    (tpl / "Results").mkdir()
    code = ("from iwfm_io.pest.orchestrate import setup_agents;"
            f"setup_agents(r'{tpl}', 1, dest_root=r'{tpl}')")
    try:
        result = run_python(code, timeout=10)
    finally:
        rmtree_deep(tpl)
    if not hasattr(result, "returncode"):
        pytest.fail("setup_agents hung (replicated the template into itself until killed)")
    # decided behaviour (2.13.0): a nested dest_root is refused up front
    assert result.returncode != 0
    assert "inside the template" in (result.stderr or "")


# 6 -------------------------------------- quickstart ignores per-obs weight column
def test_quickstart_honours_obs_weight_column(tmp_path, sample_model):
    from iwfm_io.pest.quickstart import pest_setup_from_model
    obs = pd.DataFrame({"site": ["GWHyd2"] * 2,
                        "datetime": pd.to_datetime(["1995-01-15", "1995-02-15"]),
                        "value": [1.0, 2.0], "weight": [0.0, 5.0]})
    qs = pest_setup_from_model(sample_model, obs, tmp_path / "t", link_model=False)
    assert sorted(qs.obs_data["weight"]) == [0.0, 5.0]   # observed: [1.0, 1.0]


# 7 ------------------------------------------------- write_smp NaT / inf literals
def test_write_smp_rejects_nat_and_inf(tmp_path):
    from iwfm_io.pest.smp import write_smp
    with pytest.raises(ValueError):
        write_smp(pd.DataFrame({"site": ["w1"], "datetime": [pd.NaT], "value": [1.0]}),
                  tmp_path / "a.smp")          # observed: line 'w1  nan  1.000000E+00'
    with pytest.raises(ValueError):
        write_smp(pd.DataFrame({"site": ["w1"], "datetime": [pd.Timestamp("2000-01-13")],
                                "value": [np.inf]}), tmp_path / "b.smp")   # observed: 'INF'


# 8 --------------------------------------------------- read_smp 24:00:00 stamps
def test_read_smp_accepts_iwfm_2400_stamp(tmp_path):
    from iwfm_io.pest.smp import read_smp
    p = tmp_path / "a.smp"
    p.write_text("w1 13/01/2000 24:00:00 10.0\n")
    df = read_smp(p)   # observed: ValueError (does not match %H:%M:%S)
    assert df["datetime"].iloc[0] == pd.Timestamp("2000-01-14")


# 9 ------------------------------------------------ parrep_v2 NaN / fixed / case
def _pst(tmp_path, noptmax_kw="noptmax"):
    d = tmp_path / "p"
    d.mkdir()
    (d / "c.pst").write_text(f"pcf version=2\n* control data keyword\n{noptmax_kw} 3\n"
                             "* parameter data external\nc_par.csv\n")
    (d / "c_par.csv").write_text("parnme,partrans,parval1\nkh_a,log,1.0\nkh_b,fixed,1.0\n")
    return d


def test_parrep_v2_rejects_nan_value(tmp_path):
    from iwfm_io.pest.orchestrate import parrep_v2
    d = _pst(tmp_path)
    with pytest.raises(ValueError):
        parrep_v2(d / "c.pst", pd.Series({"kh_a": np.nan}))   # observed: 'kh_a,log,' (empty cell)


def test_parrep_v2_does_not_overwrite_fixed(tmp_path):
    from iwfm_io.pest.orchestrate import parrep_v2
    d = _pst(tmp_path)
    parrep_v2(d / "c.pst", pd.Series({"kh_a": 2.0, "kh_b": 99.0}))
    par = pd.read_csv(d / "c_par.csv").set_index("parnme")["parval1"]
    assert par["kh_b"] == 1.0   # observed: 99.0


def test_parrep_v2_noptmax_case_insensitive(tmp_path):
    from iwfm_io.pest.orchestrate import parrep_v2
    d = _pst(tmp_path, "NOPTMAX")
    parrep_v2(d / "c.pst", pd.Series({"kh_a": 2.0}))   # observed: ValueError no 'noptmax' line


# 10 -------------------------------- PestSetup: two obs blocks share an output file
def test_pestsetup_rejects_duplicate_output_file(tmp_path):
    from iwfm_io.pest.obsfiles import ObsFileSpec
    from iwfm_io.pest.params import ParamSpec, build_parameters
    from iwfm_io.pest.setup import PestSetup
    s = PestSetup("c", command="x")
    s.add_parameters(build_parameters([ParamSpec("kh", "m.csv", pd.DataFrame({"n": [1]}))]))
    for nm in ("o1", "o2"):
        spec = ObsFileSpec([nm])
        s.add_observations(spec.obs_data(pd.Series({nm: 1.0})), spec, "o.pout")
    with pytest.raises(ValueError):
        s.write(tmp_path / "t")   # observed: 'o.pout.ins  o.pout' listed twice, ins holds only o2


# 11 ------------------------------ PestSetup: pestpp_options overrides control_data
def test_pestsetup_control_data_not_shadowed(tmp_path):
    from iwfm_io.pest.obsfiles import ObsFileSpec
    from iwfm_io.pest.params import ParamSpec, build_parameters
    from iwfm_io.pest.setup import PestSetup
    s = PestSetup("c", command="x")
    s.add_parameters(build_parameters([ParamSpec("kh", "m.csv", pd.DataFrame({"n": [1]}))]))
    spec = ObsFileSpec(["o1"])
    s.add_observations(spec.obs_data(pd.Series({"o1": 1.0})), spec, "o.pout")
    s.control_data["noptmax"] = 0
    s.pestpp_options["noptmax"] = 3
    with pytest.raises(ValueError):
        s.write(tmp_path / "t")   # observed: writes noptmax 3 (pestpp-ies happily iterates)


# 12 --------------------------------------------- balance_weights degenerate inputs
def test_balance_weights_negative_target_rejected():
    from iwfm_io.pest.weights import balance_weights
    obs = pd.DataFrame({"obsnme": ["a1", "a2"], "weight": [1, 1], "obgnme": ["ga", "ga"]})
    with pytest.raises(ValueError):
        balance_weights(obs, pd.Series({"a1": 1.0, "a2": 2.0}), {"ga": -10})  # observed: weights NaN


def test_balance_weights_inf_residual_does_not_zero_group():
    from iwfm_io.pest.weights import balance_weights
    obs = pd.DataFrame({"obsnme": ["a1", "a2"], "weight": [1, 1], "obgnme": ["ga", "ga"]})
    with pytest.raises(ValueError):
        balance_weights(obs, pd.Series({"a1": np.inf, "a2": 2.0}), {"ga": 10})  # observed: [0.0, 0.0]


# 13 ------------------------------------------------------- names codec edge cases
def test_decode_round_trips_what_encode_produces():
    from iwfm_io.pest.names import decode_obs_name, encode_obs_name
    n = encode_obs_name("gwh", "w1", "9999-12-31")          # 'gwh_w1_99991231'
    decode_obs_name(n)                                     # observed: OutOfBoundsDatetime


def test_grouped_scheme_two_digit_year_no_collision():
    from iwfm_io.pest.names import encode_obs_name
    # decided: the legacy 2-digit stamp only round-trips for 1969-2068;
    # a year outside that window is refused instead of colliding
    # (was: both 'gwh670001_681031')
    b = encode_obs_name("gwh", "670001", "2068-10-31", scheme="grouped")
    assert b == "gwh670001_681031"
    with pytest.raises(ValueError, match="round-trip"):
        encode_obs_name("gwh", "670001", "1968-10-31", scheme="grouped")


# 14 ---------------------------------------------------- ParamSpec zone handling
def test_paramspec_nan_zone_rejected():
    from iwfm_io.pest.params import ParamSpec, build_parameters
    keys = pd.DataFrame({"node_id": [1, 1], "layer": [1, 2], "zone": [np.nan, "a"]})
    with pytest.raises(ValueError):
        build_parameters([ParamSpec("kh", "m.csv", keys, zone_col="zone")])  # observed: 'kh_nan'


def test_paramspec_zone_slug_collision_rejected():
    from iwfm_io.pest.params import ParamSpec, build_parameters
    keys = pd.DataFrame({"node_id": [1, 1], "layer": [1, 2], "zone": ["A-1", "a_1"]})
    with pytest.raises(ValueError):
        build_parameters([ParamSpec("kh", "m.csv", keys, zone_col="zone")])  # observed: one param 'kh_a_1'


def test_paramspec_tie_cycle_rejected():
    from iwfm_io.pest.params import ParamSpec, build_parameters
    keys = pd.DataFrame({"node_id": [1, 1], "layer": [1, 2], "zone": ["a", "b"]})
    with pytest.raises(ValueError):
        build_parameters([ParamSpec("kh", "m.csv", keys, zone_col="zone",
                                    tied={"a": "b", "b": "a"})])   # observed: both rows 'tied'


# 15 ----------------------------------------------- quickstart weight validation
def test_quickstart_rejects_nan_weight(tmp_path, sample_model):
    from iwfm_io.pest.quickstart import pest_setup_from_model
    obs = pd.DataFrame({"site": ["GWHyd2"], "datetime": pd.to_datetime(["1995-01-15"]), "value": [1.0]})
    with pytest.raises(ValueError):
        pest_setup_from_model(sample_model, obs, tmp_path / "t", weight=float("nan"), link_model=False)
    # observed: obs_data weight NaN; pestpp-ies then dies with 'missing_val' at parse time


# 16 --------------------------------------------- setup_agents stale agent dirs
def test_setup_agents_overwrite_removes_stale_agents(tmp_path):
    from iwfm_io.pest.orchestrate import setup_agents
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    (tpl / "c.pst").write_text("pcf\n")
    root = tmp_path / "agents"
    setup_agents(tpl, 3, dest_root=root)
    setup_agents(tpl, 1, dest_root=root, overwrite=True)
    assert sorted(p.name for p in root.iterdir()) == ["agent_01"]   # observed: agent_02, agent_03 remain


# 17 --------------------------------------------- opaque apply/parse error paths
def test_apply_parameters_duplicate_value_rows_clear_error(model_copy):
    from iwfm_io.pest.apply import apply_parameters
    d = model_copy
    pd.DataFrame([(1, 1, 2.0), (1, 1, 3.0), (1, 2, 2.0)],
                 columns=["node_id", "layer", "value"]).to_csv(d / "mult_kh.csv", index=False)
    with pytest.raises(ValueError, match="duplicate"):
        apply_parameters(d, [_action()])   # observed: 'Length of values (3) does not match length of index (2)'


def test_apply_parameters_unbounded_inf_multiplier_rejected(model_copy):
    from iwfm_io.pest.apply import apply_parameters
    d = model_copy
    pd.DataFrame([(1, 1, np.inf), (1, 2, 1.0)],
                 columns=["node_id", "layer", "value"]).to_csv(d / "mult_kh.csv", index=False)
    with pytest.raises(ValueError):
        apply_parameters(d, [_action()])   # observed: 'inf' literally written into GW_MAIN.dat


# 18 -------------------------------------------------- read_smp degenerate files
def test_read_smp_empty_file_message(tmp_path):
    from iwfm_io.pest.smp import read_smp
    p = tmp_path / "e.smp"
    p.write_text("")
    with pytest.raises(ValueError, match="(?i)empty|no records"):
        read_smp(p)   # observed: 'cannot auto-detect the date convention ... every component <= 12'


# 19 --------------------------------------- budget_observations duplicate names
def test_budget_observations_duplicate_names_rejected():
    from iwfm_io.pest.budget_obs import budget_observations
    df = pd.DataFrame({"location": ["1", 1], "component": ["c", "c"],
                       "datetime": pd.to_datetime(["2000-01-01"] * 2), "value": [1.0, 3.0]})
    out = budget_observations(df, aggregate="mean")
    assert not out["obsnme"].duplicated().any()   # observed: 'bud_c_1' twice
