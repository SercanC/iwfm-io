"""Tests for stream component readers and writers."""

import pytest
from pathlib import Path

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
        assert "reach_id" in sm.reach_params.columns
        assert "conductance" in sm.reach_params.columns

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
