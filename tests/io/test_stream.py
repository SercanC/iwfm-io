"""Tests for stream component readers and writers."""

import pytest

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

STREAM_DIR = SIMULATION_DIR / "Stream"

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")


class TestStreamMain:
    def test_read_stream_main(self):
        from iwfm_io.readers.stream import read_stream_main

        sm = read_stream_main(STREAM_DIR / "Stream_MAIN.dat")
        assert sm.header is not None
        assert len(sm.file_paths) == 6
        assert sm.config["n_hydrographs"] > 0
        assert len(sm.hydrograph_specs) == sm.config["n_hydrographs"]

    def test_stream_main_reach_params(self):
        from iwfm_io.readers.stream import read_stream_main

        sm = read_stream_main(STREAM_DIR / "Stream_MAIN.dat")
        assert sm.reach_params is not None
        assert len(sm.reach_params) > 0
        # one row per stream NODE: IR CSTRM DSTRM WETPR
        assert "stream_node_id" in sm.reach_params.columns
        assert "conductance" in sm.reach_params.columns
        assert "bed_thickness" in sm.reach_params.columns
        assert "wetted_perimeter" in sm.reach_params.columns

    def test_stream_main_round_trip(self, tmp_output):
        from iwfm_io.readers.stream import read_stream_main
        from iwfm_io.writers.stream import write_stream_main

        sm = read_stream_main(STREAM_DIR / "Stream_MAIN.dat")
        out = tmp_output / "Stream_MAIN.dat"
        write_stream_main(sm, out)
        assert out.exists()

        sm2 = read_stream_main(out)
        assert sm2.config["n_hydrographs"] == sm.config["n_hydrographs"]
        assert len(sm2.hydrograph_specs) == len(sm.hydrograph_specs)


class TestStreamInflow:
    def test_read_stream_inflow(self):
        from iwfm_io.readers.stream import read_stream_inflow

        path = STREAM_DIR / "StreamInflow.dat"
        if path.exists():
            sf = read_stream_inflow(path)
            assert sf.spec.n_columns > 0
            assert len(sf.node_assignments) == sf.spec.n_columns
            assert sf.data is not None or sf.dss_pathnames

    def test_stream_inflow_round_trip(self, tmp_output):
        from iwfm_io.readers.stream import read_stream_inflow
        from iwfm_io.writers.stream import write_stream_inflow

        path = STREAM_DIR / "StreamInflow.dat"
        if path.exists():
            sf = read_stream_inflow(path)
            out = tmp_output / "StreamInflow.dat"
            write_stream_inflow(sf, out)

            sf2 = read_stream_inflow(out)
            assert sf2.spec.n_columns == sf.spec.n_columns
            assert len(sf2.node_assignments) == len(sf.node_assignments)


class TestDiverSpecs:
    def test_read_diver_specs(self):
        from iwfm_io.readers.stream import read_diver_specs

        path = STREAM_DIR / "DiverSpecs.dat"
        if path.exists():
            ds = read_diver_specs(path)
            assert ds.n_diversions >= 0
            assert ds.data is not None
            assert len(ds.data) == ds.n_diversions

    def test_diver_specs_round_trip(self, tmp_output):
        from iwfm_io.readers.stream import read_diver_specs
        from iwfm_io.writers.stream import write_diver_specs

        path = STREAM_DIR / "DiverSpecs.dat"
        if path.exists():
            ds = read_diver_specs(path)
            out = tmp_output / "DiverSpecs.dat"
            write_diver_specs(ds, out)

            ds2 = read_diver_specs(out)
            assert ds2.n_diversions == ds.n_diversions

    def test_trailing_text_after_name(self, tmp_output):
        # C2VSimFG v2.0-style rows: extra free text after the NAME
        # field must not break the positional parse (issue #30).
        from iwfm_io.readers.stream import read_diver_specs

        spec = (
            "C  test\n"
            "        2   / NRDV\n"
            "1\t0\t1\t1\t1\t0.03\t1\t0.54\t6\t1\t1\t0.43\t2\t2\t"
            "DIV_001\tD_WKYTN_WTPBUK\n"
            "2\t0\t2\t1\t2\t0.30\t2\t0.10\t4\t1\t2\t0.60\t1\t0\t"
            "DIV_002\tEXTRA\n"
            "        0   / NGRP\n"
        )
        path = tmp_output / "divspec_trailing.dat"
        path.write_text(spec)
        ds = read_diver_specs(path)
        assert ds.data is not None
        assert len(ds.data) == 2
        assert list(ds.data["diversion_id"]) == [1, 2]
        assert list(ds.data["dest_type"]) == [6, 4]
        assert ds.data["name"].iloc[0] == "DIV_001 D_WKYTN_WTPBUK"
        assert ds.data["spill_col"].isna().all()

    def test_spill_layout_still_parses(self, tmp_output):
        # Older 16-numeric-slot layout with the ICOLSL/FRACSL pair.
        from iwfm_io.readers.stream import read_diver_specs

        spec = (
            "C  test\n"
            "        1   / NRDV\n"
            "  1  0  1  1.0  1  0.03  1  0.54  3  0.1  6  1  1  0.43"
            "  2  2  DIV_001\n"
            "        0   / NGRP\n"
        )
        path = tmp_output / "divspec_spill.dat"
        path.write_text(spec)
        ds = read_diver_specs(path)
        assert ds.data is not None
        assert ds.data["spill_col"].iloc[0] == 3
        assert ds.data["spill_frac"].iloc[0] == 0.1
        assert ds.data["dest_type"].iloc[0] == 6
        assert ds.data["name"].iloc[0] == "DIV_001"

    def test_unparseable_rows_warn(self, tmp_output):
        # A spec table that cannot be parsed must warn, not silently
        # return data=None.
        from iwfm_io.readers.stream import read_diver_specs

        spec = (
            "C  test\n"
            "        2   / NRDV\n"
            "  1  0  garbage\n"
            "        0   / NGRP\n"
        )
        path = tmp_output / "divspec_bad.dat"
        path.write_text(spec)
        with pytest.warns(UserWarning, match="0 of 2"):
            ds = read_diver_specs(path)
        assert ds.data is None


class TestBypassSpecs:
    def test_read_bypass_specs(self):
        from iwfm_io.readers.stream import read_bypass_specs

        path = STREAM_DIR / "BypassSpecs.dat"
        if path.exists():
            bs = read_bypass_specs(path)
            assert bs.n_bypasses >= 0

    def test_bypass_specs_round_trip(self, tmp_output):
        from iwfm_io.readers.stream import read_bypass_specs
        from iwfm_io.writers.stream import write_bypass_specs

        path = STREAM_DIR / "BypassSpecs.dat"
        if path.exists():
            bs = read_bypass_specs(path)
            out = tmp_output / "BypassSpecs.dat"
            write_bypass_specs(bs, out)

            bs2 = read_bypass_specs(out)
            assert bs2.n_bypasses == bs.n_bypasses


class TestDiversions:
    def test_read_diversions(self):
        from iwfm_io.readers.stream import read_diversions

        path = STREAM_DIR / "Diversions.dat"
        if path.exists():
            dv = read_diversions(path)
            assert dv.spec.n_columns > 0
            assert dv.data is not None or dv.dss_pathnames

    def test_diversions_round_trip(self, tmp_output):
        from iwfm_io.readers.stream import read_diversions
        from iwfm_io.writers.stream import write_diversions

        path = STREAM_DIR / "Diversions.dat"
        if path.exists():
            dv = read_diversions(path)
            out = tmp_output / "Diversions.dat"
            write_diversions(dv, out)

            dv2 = read_diversions(out)
            assert dv2.spec.n_columns == dv.spec.n_columns
