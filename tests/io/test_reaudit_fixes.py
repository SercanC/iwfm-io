"""Regression tests for the second-audit fix batch: v4.2 stream bed
layout, 7-token hydrograph rows, FCHYDOUTFL presence, title padding,
TS precision, TUNITZ fallback, NaN guards, and annotation handling."""

import warnings

import pandas as pd
import pytest

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(),
    reason="sample model not present (.assets/sample_model)")


class TestStreamBedV42:
    DECK = (
        "#4.2\n"
        "C  test v4.2 stream main\n"
        "         / INFLOWFL\n"
        "         / DIVSPECFL\n"
        "         / BYPSPECFL\n"
        "         / DIVFL\n"
        "         / STRMRCHBUDFL\n"
        "         / DIVDTLBUDFL\n"
        "   0     / NOUTR\n"
        "   0     / IHSQR\n"
        "   1.0   / FACTVROU\n"
        "   cfs   / UNITVROU\n"
        "   1.0   / FACTLTOU\n"
        "   ft    / UNITLTOU\n"
        "         / STHYDOUTFL\n"
        "   0     / NBUDR\n"
        "         / STNDBUDFL\n"
        "   1.0   / FACTK\n"
        "   1day  / TUNITSK\n"
        "   1.0   / FACTL\n"
        "   1   500.0   30039   0.452   1.0   /Reach 1 - Kern River\n"
        "   2   400.0   29998   0.500   1.0\n"
        "       350.0   29957   0.600   1.0\n"
        "   1     / INTRCTYPE\n"
        "         / STARFL\n"
    )

    def test_v42_layout_and_continuation(self, tmp_output):
        from iwfm_io.readers.stream import read_stream_main
        from iwfm_io.writers.stream import write_stream_main

        path = tmp_output / "stream_v42.dat"
        path.write_text(self.DECK)
        st = read_stream_main(path)
        rp = st.reach_params
        assert len(rp) == 3  # node 2 has a continuation row
        r0 = rp.iloc[0]
        assert r0["stream_node_id"] == 1
        assert r0["wetted_perimeter"] == 500.0
        assert r0["gw_node_id"] == 30039
        assert r0["conductance"] == 0.452
        assert r0["bed_thickness"] == 1.0
        assert r0["notes"] == "Reach 1 - Kern River"
        # continuation row repeats the stream node id
        assert list(rp["stream_node_id"]) == [1, 2, 2]
        assert rp.iloc[2]["gw_node_id"] == 29957

        out = tmp_output / "stream_v42_out.dat"
        write_stream_main(st, out)
        st2 = read_stream_main(out)
        pd.testing.assert_frame_equal(st2.reach_params, rp)

    def test_v40_layout_unchanged(self):
        from iwfm_io.readers.stream import read_stream_main

        st = read_stream_main(
            SIMULATION_DIR / "Stream" / "Stream_MAIN.dat")
        assert list(st.reach_params.columns[:4]) == [
            "stream_node_id", "conductance", "bed_thickness",
            "wetted_perimeter"]


class TestHydrographSevenTokens:
    def test_xy_row_with_placeholder_node(self, tmp_output):
        # C2VSimFG-subsidence style: ID TYPE LAYER X Y NODE NAME
        from iwfm_io import read_bc_main  # noqa: F401 (import check)
        from iwfm_io.readers.groundwater import read_subsidence
        from iwfm_io.writers.groundwater import write_subsidence

        deck = (
            "#4.0\n"
            "C  test subsidence\n"
            "         / INISUBFL\n"
            "         / TPSOUTFL\n"
            "         / FNSUBFL\n"
            "   1.0   / FACTLTOU\n"
            "   ft    / UNITLTOU\n"
            "   2     / NOUTS\n"
            "   1.0   / FACTXY\n"
            "         / SUBHYDOUTFL\n"
            "   153  0  2  624221.7  4190333.7  0  InSAR01  / InSAR near X\n"
            "   154  1  1  0  0  4123  OBS2\n"
            "   0     / NGROUP\n"
            "   1.0  1.0  1.0  1.0  1.0  1.0\n"
            "   1  1e-05  5e-05  10.0  2.0  99999.0\n"
        )
        path = tmp_output / "subsidence7.dat"
        path.write_text(deck)
        sub = read_subsidence(path)
        h = sub.hydrographs
        assert h["name"].iloc[0] == "InSAR01"
        assert h["node"].iloc[0] == 0
        assert h["x"].iloc[0] == 624221.7
        assert h["notes"].iloc[0] == "InSAR near X"
        assert h["name"].iloc[1] == "OBS2"

        out = tmp_output / "subsidence7_out.dat"
        write_subsidence(sub, out)
        sub2 = read_subsidence(out)
        pd.testing.assert_frame_equal(sub2.hydrographs, h)


class TestGwMainFchydoutfl:
    def test_blank_line_always_emitted(self, tmp_output):
        from iwfm_io import read_gw_main, write_gw_main

        gw = read_gw_main(SIMULATION_DIR / "GW" / "GW_MAIN.dat")
        gw.n_face_flows = 0
        gw.face_flows = gw.face_flows.iloc[:0]
        gw.face_flow_out_file = None
        out = tmp_output / "GW_MAIN.dat"
        write_gw_main(gw, out)
        text = out.read_text()
        assert "/FCHYDOUTFL" in text  # IWFM reads the line unconditionally


class TestTitlePadding:
    def test_writer_pads_to_three_titles(self, tmp_output):
        from iwfm_io import read_simulation, write_simulation

        sim = read_simulation(SIMULATION_DIR / "Simulation_MAIN.IN")
        sim.titles = ["Only one"]
        out = tmp_output / "Simulation_MAIN.IN"
        write_simulation(sim, out)
        sim2 = read_simulation(out)
        # IWFM reads exactly 3 title lines positionally
        assert len(sim2.titles) == 3
        assert sim2.titles[0] == "Only one"
        assert sim2.file_paths["gw_main"] is not None


class TestTsPrecision:
    def test_ten_significant_digits(self, tmp_output):
        from iwfm_io import read_timeseries_file, write_timeseries_file

        ts = read_timeseries_file(
            SIMULATION_DIR / "RootZone" / "Urban" / "Population.dat")
        ts.data.loc[0, "col_1"] = 1234567.75
        out = tmp_output / "Population.dat"
        write_timeseries_file(ts, out)
        ts2 = read_timeseries_file(out)
        assert ts2.data["col_1"].iloc[0] == 1234567.75


class TestUnsatZoneTunitzFallback:
    def test_missing_keyword_comment(self, tmp_output):
        from iwfm_io.readers.misc import read_unsatzone

        deck = (
            "C  test\n"
            "   1 / NUNSAT\n"
            "   0.001 / UZCONV\n"
            "   150 / UZITERMX\n"
            "         / UZBUDFL\n"
            "         / UZZBUDFL\n"
            "         / UZFNFL\n"
            "   0 / NGROUP\n"
            "   1.0  1.0  1.0\n"
            "   1DAY\n"  # no "/ TUNITZ" tag — legal IWFM input
            "   1  10.0  0.3  0.2  1.0  1\n"
            "   2  12.0  0.35  0.25  1.5  1\n"
            "   0  0.1\n"
        )
        path = tmp_output / "unsat_no_tag.dat"
        path.write_text(deck)
        uz = read_unsatzone(path)
        assert uz.config["tunitz"] == "1DAY"
        assert uz.element_params is not None
        assert len(uz.element_params) == 2
        assert uz.initial_moisture is not None


class TestNanGuards:
    def test_write_table_rows_raises_on_nan(self, tmp_output):
        from iwfm_io._writer import IWFMFileWriter
        from iwfm_io.writers._param_blocks import write_table_rows

        w = IWFMFileWriter(tmp_output / "x.dat")
        df = pd.DataFrame({"a": [1, 2], "b": [1.0, float("nan")]})
        with pytest.raises(ValueError, match="NaN"):
            write_table_rows(w, df, ["a", "b"])

    def test_elem_pump_middle_nan_raises(self, tmp_output):
        from iwfm_io import read_elem_pump, write_elem_pump

        ep = read_elem_pump(SIMULATION_DIR / "GW" / "ElemPump.dat")
        ep.data.loc[0, "fracsk"] = float("nan")  # middle column
        with pytest.raises(ValueError, match="TRAILING"):
            write_elem_pump(ep, tmp_output / "ElemPump.dat")


class TestDiversionNameSemantics:
    def test_positional_name_and_comment_notes(self, tmp_output):
        from iwfm_io import read_diver_specs, write_diver_specs

        deck = (
            "C  test\n"
            "        1   / NRDV\n"
            "  1  0  1  1.0  1  0.03  1  0.54  6  1  1  0.43  2  2"
            "  DIV_001   / Kern River delivery\n"
            "        0   / NGRP\n"
        )
        path = tmp_output / "divspec_sem.dat"
        path.write_text(deck)
        ds = read_diver_specs(path)
        # positional NAME is the field IWFM reads; the annotation is notes
        assert ds.data["name"].iloc[0] == "DIV_001"
        assert ds.data["notes"].iloc[0] == "Kern River delivery"

        out = tmp_output / "divspec_sem_out.dat"
        write_diver_specs(ds, out)
        text = out.read_text()
        # NAME must stay positional (before any slash)
        data_line = [ln for ln in text.splitlines()
                     if "DIV_001" in ln][0]
        assert data_line.index("DIV_001") < data_line.index("/")
        ds2 = read_diver_specs(out)
        assert ds2.data["name"].iloc[0] == "DIV_001"
        assert ds2.data["notes"].iloc[0] == "Kern River delivery"


class TestBypassRobustness:
    def test_elements_on_next_line_and_notes(self, tmp_output):
        from iwfm_io.readers.stream import read_bypass_specs
        from iwfm_io.writers.stream import write_bypass_specs

        deck = (
            "C  test\n"
            "   1     / NDIVS\n"
            "   1.0   / FACTX\n"
            "   1DAY  / TUNITX\n"
            "   1.0   / FACTY\n"
            "   1DAY  / TUNITY\n"
            "   1  5  2  10  6  0.1  0.2  Colusa Weir  / Bypass 1 note\n"
            "   1  2\n"
            "      101  0.5\n"
            "      102  0.5\n"
        )
        path = tmp_output / "bypass_next.dat"
        path.write_text(deck)
        bs = read_bypass_specs(path)
        assert bs.bypass_data["name"].iloc[0] == "Colusa Weir"
        assert bs.bypass_data["notes"].iloc[0] == "Bypass 1 note"
        zone = bs.seepage_zones[0]
        assert zone["n_elements"] == 2
        assert [e["element_id"] for e in zone["elements"]] == [101, 102]

        out = tmp_output / "bypass_next_out.dat"
        write_bypass_specs(bs, out)
        bs2 = read_bypass_specs(out)
        assert bs2.bypass_data["notes"].iloc[0] == "Bypass 1 note"
        assert bs2.seepage_zones[0]["n_elements"] == 2


class TestLakeRowAnnotation:
    def test_lake_row_with_comment(self, tmp_output):
        from iwfm_io import read_lake_main

        deck = (
            "C  test\n"
            "         / MXLKELVFL\n"
            "         / LKBUDFL\n"
            "         / FNLKELVFL\n"
            "   1.0   / FACTK\n"
            "   1day  / TUNITK\n"
            "   1.0   / FACTL\n"
            "   1  2.0  1.0  1  7  2  Clear Lake   / lake one\n"
            "   1.0   / FACT\n"
            "   1  280.0\n"
        )
        path = tmp_output / "lake_note.dat"
        path.write_text(deck)
        lake = read_lake_main(path)
        assert lake.n_lakes == 1
        assert lake.lake_params["name"].iloc[0] == "Clear Lake"
        assert lake.lake_params["notes"].iloc[0] == "lake one"


class TestStrataContract:
    def test_short_row_raises(self, tmp_output):
        from iwfm_io import read_strata

        deck = (
            "C  test\n"
            "   1   / NL\n"
            "   1.0 / FACT\n"
            "   1  100.0  0.0  50.0\n"
            "   2  100.0  0.0\n"  # short row
        )
        path = tmp_output / "strata_short.dat"
        path.write_text(deck)
        with pytest.raises(ValueError, match="expected values"):
            read_strata(path)

    def test_n_nodes_stored_and_checked(self, tmp_output):
        from iwfm_io import read_strata, write_strata

        st = read_strata(SAMPLE_MODEL / "Preprocessor" / "Strata.dat")
        assert st.n_nodes == 441
        st.data = st.data.iloc[:-1]
        with pytest.raises(ValueError, match="node rows"):
            write_strata(st, tmp_output / "Strata.dat")


class TestTimeseriesColumnsParam:
    def test_named_columns(self):
        from iwfm_io import read_timeseries_file

        ts = read_timeseries_file(
            SIMULATION_DIR / "RootZone" / "ReturnFlowFrac.dat",
            columns=["ag", "urban"])
        assert list(ts.data.columns) == ["date", "ag", "urban"]
