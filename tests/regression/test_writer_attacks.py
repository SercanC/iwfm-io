"""Hostile-QA regressions: writers / round-trip / validation.

Imported from the 2026-09-09 hostile-QA pass. Every test asserts the
EXPECTED behaviour; ``xfail(strict=True)`` marks the ones that still
reproduce a defect on the current code. Reads only from the sample
model, writes only to ``tmp_path``.
"""
import datetime as dt
import shutil

import numpy as np
import pandas as pd
import pytest

from iwfm_io import (
    read_nodes, write_nodes, read_elements, write_elements, read_strata, write_strata,
    read_stream_geom, write_stream_geom, read_gw_main, write_gw_main, read_et, write_et,
    read_lake_main, write_lake_main, read_stream_main, write_stream_main,
    read_nonponded_ag_main, write_nonponded_ag_main, read_unsatzone,
    write_unsatzone, read_swshed, write_swshed, read_simulation, write_simulation,
    read_irigfrac, write_irigfrac, read_land_use_area, write_land_use_area, IWFMFileWriter,
    validate_nodes, validate_elements, validate_stratigraphy, validate_preprocessor,
    read_preprocessor,
)
from iwfm_io.readers.preprocessor import read_preprocessor_main
from iwfm_io.writers.preprocessor import write_preprocessor_main
from iwfm_io.writers.groundwater import write_gw_initial_conditions
from iwfm_io.readers.text_output import read_final_state_out

pytestmark = [pytest.mark.regression, pytest.mark.sample_model]


@pytest.fixture(scope="module")
def PP(sample_model):
    return sample_model / "Preprocessor"


@pytest.fixture(scope="module")
def SIM(sample_model):
    return sample_model / "Simulation"


@pytest.fixture(scope="module")
def GW(SIM):
    return SIM / "GW/GW_MAIN.dat"


# 1. NaN in an Int64 hydrograph cell -> blank token -> columns shift silently
def test_01_hydrograph_nan_layer_shifts_columns(tmp_path, GW, SIM):
    gw = read_gw_main(GW)
    gw.hydrographs.loc[0, "layer"] = pd.NA          # was 1, x=574000
    with pytest.raises(ValueError):                 # expected: writer refuses NaN
        write_gw_main(gw, tmp_path / "gw.dat", base_dir=SIM)
    # observed instead: file written, re-read row0 layer == 574000 (the x coordinate)


# 2. NaN in node-layer parameter tables -> blank cell (bypasses write_table_rows guard)
def test_02_nan_param_cell_writes_blank_cell(tmp_path, GW, SIM):
    gw = read_gw_main(GW)
    ap = pd.DataFrame([(n, L, float(n) + L / 10, 1e-5, .25, .2, 1.0) for n in range(1, 442) for L in (1, 2)],
                      columns=["node_id", "layer", "kh", "ss", "sy", "aquitard_kv", "kv"])
    ap.loc[3, "kh"] = np.nan                        # node 2, layer 2
    gw.ngroup, gw.parametric_grids, gw.aquifer_params = 0, [], ap
    with pytest.raises(ValueError):
        write_gw_main(gw, tmp_path / "gw.dat", base_dir=SIM)
    # observed: written; read_gw_main returns 3 of 882 parameter rows, no error


def test_02b_strata_nan_writes_short_row(tmp_path, PP):
    st = read_strata(PP / "Strata.dat")
    st.data.loc[0, "aquifer_1"] = np.nan
    with pytest.raises(ValueError):
        write_strata(st, tmp_path / "s.dat")
    # observed: row "1  500  0  <blank>  10  100" written; IWFM would pull node 2's tokens


# 3. Newline inside a name/notes field injects rows that are read back as data
def test_03_newline_in_notes_injects_hydrograph(tmp_path, GW, SIM):
    gw = read_gw_main(GW)
    gw.hydrographs.loc[0, "notes"] = "obs\n  999  0  1  1.0  1.0  0  Injected"
    with pytest.raises(ValueError):
        write_gw_main(gw, tmp_path / "gw.dat", base_dir=SIM)
    # observed: re-read hydrograph ids == [1, 999, 2, 3] with no error


def test_03b_newline_in_lake_name_injects_lake(tmp_path, SIM):
    lk = read_lake_main(SIM / "Lake/Lake_MAIN.dat")
    lk.lake_params.loc[0, "name"] = "Lake A\n  2  1.0  1.0  1  1  1  Injected"
    with pytest.raises(ValueError):
        write_lake_main(lk, tmp_path / "lk.dat", base_dir=SIM)
    # observed: re-read lake_params has 2 rows ['Lake A', 'Injected']


# 4. Positionally-written tables silently permute when DataFrame columns are reordered
def test_04_et_columns_reordered_permute_silently(tmp_path, SIM):
    et = read_et(SIM / "ET.dat")
    et.data = et.data[["date"] + sorted([c for c in et.data.columns if c != "date"], reverse=True)]
    write_et(et, tmp_path / "et.dat")
    r = read_et(tmp_path / "et.dat")
    assert r.data.col_1.iloc[0] == read_et(SIM / "ET.dat").data.col_1.iloc[0]   # observed: 3.7 != 3.4


def test_04b_rootzone_initial_conditions_reordered(tmp_path, SIM):
    npf = SIM / "RootZone/NonPondedAg/NonPondedAg_MAIN.dat"
    ag = read_nonponded_ag_main(npf)
    ic = ag.initial_conditions
    ag.initial_conditions = ic[["element_id", "AL", "TO", "fsoilmp"]]
    write_nonponded_ag_main(ag, tmp_path / "np.dat", base_dir=SIM)
    r = read_nonponded_ag_main(tmp_path / "np.dat")
    assert r.initial_conditions.fsoilmp.iloc[0] == ic.fsoilmp.iloc[0]         # observed: 0.2 != 0.9


def test_04c_initial_heads_layers_swapped(tmp_path, GW, SIM):
    gw = read_gw_main(GW)
    ih = gw.initial_heads
    gw.initial_heads = ih[["node_id", "head_layer_2", "head_layer_1"]]
    write_gw_main(gw, tmp_path / "gw.dat", base_dir=SIM)
    r = read_gw_main(tmp_path / "gw.dat")
    assert r.initial_heads.head_layer_1.equals(ih.head_layer_1)               # observed: == orig head_layer_2


# 5. Timestamp / datetime dates are written verbatim -> re-read returns zero rows
def test_05_timestamp_dates_lose_all_data(tmp_path, SIM):
    """Timestamp / datetime dates are formatted with the 24:00 convention
    (decided behaviour) -- the written file must round-trip every row."""
    et = read_et(SIM / "ET.dat")
    n = len(et.data)
    et.data["date"] = [pd.Timestamp(1990, 10, 1) + pd.DateOffset(months=i)
                       for i in range(n)]
    write_et(et, tmp_path / "et.dat")
    back = read_et(tmp_path / "et.dat").data
    assert len(back) == n
    assert back["date"].iloc[0] == "09/30/1990_24:00"


def test_05b_simulation_datetime_bdt(tmp_path, SIM):
    sim = read_simulation(SIM / "Simulation_MAIN.IN", follow_references=False)
    sim.sim_begin = dt.datetime(1990, 10, 1)
    with pytest.raises((ValueError, TypeError)):
        write_simulation(sim, tmp_path / "s.in", base_dir=SIM)
    # observed: "1990-10-01 00:00:00 /BDT"


# 6. Missing per-layer rows accepted; NL-rows-per-node contract not enforced
def test_06_unsatzone_missing_layer_row(tmp_path, SIM):
    uz = read_unsatzone(SIM / "UnsatZone.dat")
    ep = uz.element_params
    uz.element_params = ep[~((ep.element_id == 5) & (ep.layer == uz.n_unsat_layers))]
    with pytest.raises(ValueError):
        write_unsatzone(uz, tmp_path / "uz.dat")
    # observed: written; read_unsatzone returns 8 of 800 rows silently


def test_06b_gw_missing_layer_row(tmp_path, GW, SIM):
    gw = read_gw_main(GW)
    ap = pd.DataFrame([(n, L, 1.0, 1e-5, .25, .2, 1.0) for n in range(1, 442) for L in (1, 2)],
                      columns=["node_id", "layer", "kh", "ss", "sy", "aquitard_kv", "kv"])
    gw.ngroup, gw.parametric_grids = 0, []
    gw.aquifer_params = ap[~((ap.node_id == 10) & (ap.layer == 2))]
    with pytest.raises(ValueError):
        write_gw_main(gw, tmp_path / "gw.dat", base_dir=SIM)
    # observed: node 10 written with one row; IWFM reads NL rows per node -> whole table shifts


# 7. Header comment lines are written verbatim; write_comment treats '/' as a comment char
def test_07_header_comment_without_comment_char_becomes_data(tmp_path, PP):
    nf = read_nodes(PP / "NodeXY.dat")
    nf.header.comment_lines = ["C ok", "My model notes"]
    write_nodes(nf, tmp_path / "n.dat")
    assert read_nodes(tmp_path / "n.dat").n_nodes == 441     # observed: int('My model notes') ValueError


def test_07b_restart_header_slash_line_becomes_data(tmp_path, GW):
    ih = read_gw_main(GW).initial_heads
    write_gw_initial_conditions(tmp_path / "ic.dat", ih, header=["/ generated by scenario X"])
    r = read_final_state_out(tmp_path / "ic.dat")
    assert len(r) == 441                                     # observed: 443 rows, first is "/ generated by ..."


# 8. FileHeader.version is never written; version and the '#' comment line disagree silently
def test_08_version_two_sources_of_truth(tmp_path, SIM):
    sm = read_stream_main(SIM / "Stream/Stream_MAIN.dat")
    rp = sm.reach_params.copy()
    rp["gw_node_id"] = range(1, len(rp) + 1)
    rp["wetted_perimeter"] = 150.0
    rp["conductance"] = 10.0
    sm.reach_params, sm.header.version = rp, "4.2"          # comment_lines still carries '#4.0'
    write_stream_main(sm, tmp_path / "sm.dat", base_dir=SIM)
    r = read_stream_main(tmp_path / "sm.dat")
    assert r.header.version == "4.2"                          # observed: '4.0'
    assert r.reach_params.conductance.iloc[0] == 10.0         # observed: 150.0 (wetted perimeter)


def test_08b_version_line_dropped_when_removed_from_comments(tmp_path, SIM):
    sm = read_stream_main(SIM / "Stream/Stream_MAIN.dat")
    sm.header.comment_lines = [ln for ln in sm.header.comment_lines if not ln.startswith("#")]
    write_stream_main(sm, tmp_path / "sm.dat", base_dir=SIM)
    assert read_stream_main(tmp_path / "sm.dat").header.version == "4.0"   # observed: None


# 9. '..\Results\x' references corrupted when the Results folder does not exist yet
def test_09_results_path_drift_without_results_dir(tmp_path, SIM):
    shutil.copytree(SIM, tmp_path / "Simulation",
                    ignore=shutil.ignore_patterns("*.bin", "*.DSS", "*.hdf", "*.out", "*.log"))
    p = tmp_path / "Simulation/GW/GW_MAIN.dat"
    write_gw_main(read_gw_main(p), p, base_dir=tmp_path / "Simulation")
    line = [ln for ln in p.read_text().splitlines() if "/GWBUDFL" in ln][0]
    assert "..\\Results\\GW.hdf" in line                      # observed: 'Results\GW.hdf'; next cycle 'GW\Results\GW.hdf'


# 10. Empty title lines silently shift the title block; 4th title dropped
def test_10_empty_title_shifts_titles(tmp_path, PP):
    pp = read_preprocessor_main(PP / "PreProcessor_MAIN.IN", follow_references=False)
    pp.titles = ["", "Second", "Third"]
    write_preprocessor_main(pp, tmp_path / "m.in", base_dir=PP)
    # decided behaviour: an empty title is written as "." (a blank line
    # would be skipped by IWFM and shift the file list); nothing is lost
    assert read_preprocessor_main(tmp_path / "m.in", follow_references=False).titles == [".", "Second", "Third"]


# 11. None / inf / strings written verbatim by write_keyed_value and fmt_num
@pytest.mark.parametrize("mutate", [
    lambda nf: setattr(nf.factor, "value", None),
    lambda nf: nf.data.__setitem__("x", nf.data["x"].astype(object)) or nf.data.loc.__setitem__((0, "x"), "1,000"),
    lambda nf: nf.data.loc.__setitem__((0, "x"), float("inf")),
], ids=["factor_None", "x_comma_string", "x_inf"])
def test_11_scalar_garbage_written_verbatim(tmp_path, PP, mutate):
    nf = read_nodes(PP / "NodeXY.dat")
    mutate(nf)
    with pytest.raises((ValueError, TypeError)):
        write_nodes(nf, tmp_path / "n.dat")
    # observed: 'None /FACT', '1,000' (a comma is a Fortran list separator!), 'inf' all written


def test_11b_dss_file_none_written_as_None(tmp_path, SIM):
    et = read_et(SIM / "ET.dat")
    et.spec.dss_file = None
    write_et(et, tmp_path / "et.dat")
    r = read_et(tmp_path / "et.dat")                          # observed: reader sees DSSFL='None' -> int('10/31/4000_24:00')
    assert r.spec.dss_file == ""


# 12. Integer fields given as floats are written with a decimal point
@pytest.mark.parametrize("field,value", [("n_nodes", 441.0), ("n_nodes", np.float64(441))],
                         ids=["py_float", "np_float64"])
def test_12_integer_count_written_as_float(tmp_path, PP, field, value):
    nf = read_nodes(PP / "NodeXY.dat")
    setattr(nf, field, value)
    write_nodes(nf, tmp_path / "n.dat")
    assert read_nodes(tmp_path / "n.dat").n_nodes == 441     # observed: int('441.0') ValueError


def test_12b_simulation_cache_float(tmp_path, SIM):
    sim = read_simulation(SIM / "Simulation_MAIN.IN", follow_references=False)
    sim.output["cache"] = 500000.0
    write_simulation(sim, tmp_path / "s.in", base_dir=SIM)
    assert read_simulation(tmp_path / "s.in", follow_references=False).output["cache"] == 500000
    # observed: int('500000.0')


# 13. Non-integral IDs silently truncated by int()
def test_13_float_node_id_truncated_into_duplicate(tmp_path, PP):
    nf = read_nodes(PP / "NodeXY.dat")
    nf.data["node_id"] = nf.data["node_id"].astype(float)
    nf.data.loc[0, "node_id"] = 2.9
    with pytest.raises(ValueError):
        write_nodes(nf, tmp_path / "n.dat")
    # observed: node ids [2, 2, 3, ...] written


# 14. NaN / None names written as the literal strings 'nan' / 'None'
def test_14_nan_names_written_literally(tmp_path, PP):
    sg = read_stream_geom(PP / "Stream.dat")
    sg.reaches["name"] = sg.reaches["name"].astype(object)
    sg.reaches.loc[0, "name"] = np.nan
    sg.reaches.loc[1, "name"] = None
    write_stream_geom(sg, tmp_path / "s.dat")
    assert read_stream_geom(tmp_path / "s.dat").reaches.name[:2].tolist() == ["", ""]   # observed: ['nan', 'None']


# 15. Names containing ' / ' are silently truncated on re-read
def test_15_slash_in_subregion_name(tmp_path, PP):
    ef = read_elements(PP / "Element.dat")
    ef.subregions.loc[0, "name"] = "North / South"
    # decided: refused at write time -- IWFM itself reads the name up to
    # the first '/', so the name cannot survive a round-trip; was:
    # written, read back as 'North'
    with pytest.raises(ValueError, match="'/'"):
        write_elements(ef, tmp_path / "e.dat")


# 16. Structural count gaps not enforced by writers
def test_16_missing_rating_table_accepted(tmp_path, PP):
    sg = read_stream_geom(PP / "Stream.dat")
    sg.rating_tables = sg.rating_tables[sg.rating_tables.stream_node_id != 5]
    with pytest.raises(ValueError):
        write_stream_geom(sg, tmp_path / "s.dat")            # observed: written; re-read IndexError


def test_16b_swshed_orphan_node_silently_dropped(tmp_path, SIM):
    sw = read_swshed(SIM / "SWShed.dat")
    sw.watershed_nodes.loc[len(sw.watershed_nodes)] = {"watershed_id": 99, "gw_node": 1, "qmax": 0.0}
    with pytest.raises(ValueError):
        write_swshed(sw, tmp_path / "sw.dat")                # observed: written with 7 of 8 node rows


def test_16c_irigfrac_dss_pathname_count_unchecked(tmp_path, SIM):
    ir = read_irigfrac(SIM / "IrigFrac.dat")
    ir.dss_file, ir.dss_pathnames = "x.dss", [(1, "/A/B/C//1MON/F/")]   # NCOL is 2
    with pytest.raises(ValueError):
        write_irigfrac(ir, tmp_path / "i.dat")               # observed: written (write_timeseries_spec's check bypassed)


# 17. validate_* gaps
def test_17_validate_nodes_inf(PP):
    nf = read_nodes(PP / "NodeXY.dat")
    nf.data.loc[0, "x"] = float("inf")
    assert validate_nodes(nf)                                 # observed: []


def test_17b_validate_elements_zero_node(PP):
    nf = read_nodes(PP / "NodeXY.dat")
    ef = read_elements(PP / "Element.dat")
    ef.data.loc[0, "node1"] = 0
    assert validate_elements(ef, nf)                          # observed: [] (0 is whitelisted for every column)


def test_17c_validate_stratigraphy_nan(PP):
    st = read_strata(PP / "Strata.dat")
    st.data.loc[0, "aquifer_1"] = np.nan
    assert validate_stratigraphy(st)                          # observed: []  (NaN < 0 is False)


def test_17d_validate_preprocessor_declared_count(PP):
    pp = read_preprocessor(PP / "PreProcessor_MAIN.IN")
    pp.children["node"].n_nodes = 999
    assert validate_preprocessor(pp)                          # observed: []


# 18. cp1252 bytes in header comments are replaced with U+FFFD
def test_18_cp1252_header_mangled(tmp_path, PP):
    p = tmp_path / "latin.dat"
    p.write_bytes(b"C  Zone \xe9t\xe9\n" + (PP / "NodeXY.dat").read_bytes())
    write_nodes(read_nodes(p), tmp_path / "rt.dat")
    assert b"\xef\xbf\xbd" not in (tmp_path / "rt.dat").read_bytes()   # observed: 'C  Zone \xef\xbf\xbdt\xef\xbf\xbd'


# 19. Hand-set relative path + base_dir is relativised against the CWD
def test_19_relative_path_with_base_dir_mangled(PP):
    w = IWFMFileWriter()
    w.write_keyed_path("NodeXY.dat", "KW", base_dir=PP)
    assert w.lines[-1].split("/")[0].strip() == "NodeXY.dat"   # observed: '..\..\..\Projects\...\NodeXY.dat'


# 20. Land-use writer emits a date on every row when rows are not grouped by date
def test_20_landuse_interleaved_dates(tmp_path, SIM):
    lu = read_land_use_area(SIM / "RootZone/NonPondedAg/CropAreas.dat")
    b = lu.data.copy()
    b["date"] = "09/30/2501_24:00"
    lu.data = pd.concat([lu.data, b]).sort_values("element_id", kind="stable")
    write_land_use_area(lu, tmp_path / "lu.dat")
    n_date_rows = sum("_24:00" in ln for ln in (tmp_path / "lu.dat").read_text().splitlines())
    assert n_date_rows == 2                                   # observed: 800 (one block per row)


# 21. Extra stratigraphy layer columns silently dropped when NL is not bumped
def test_21_strata_extra_layer_silently_dropped(tmp_path, PP):
    st = read_strata(PP / "Strata.dat")
    st.data["aquitard_3"] = 5.0
    st.data["aquifer_3"] = 50.0
    with pytest.raises(ValueError):
        write_strata(st, tmp_path / "s.dat")                 # observed: written with 2 layers, no warning
