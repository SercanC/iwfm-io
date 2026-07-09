"""Tests for groundwater component readers and writers."""

import pytest
from pathlib import Path

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")

GW_DIR = SIMULATION_DIR / "GW"


class TestGWMain:
    def test_read_gw_main(self):
        from iwfm_io.readers.groundwater import read_gw_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        assert gw.header is not None
        assert len(gw.file_paths) == 13
        assert gw.n_hydrographs > 0
        assert gw.hydrographs is not None
        assert len(gw.hydrographs) == gw.n_hydrographs

    def test_gw_main_file_paths(self):
        from iwfm_io.readers.groundwater import read_gw_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        assert "bc_main" in gw.file_paths
        assert "pump_main" in gw.file_paths
        assert "tile_drain" in gw.file_paths

    def test_gw_main_round_trip(self, tmp_output):
        from iwfm_io.readers.groundwater import read_gw_main
        from iwfm_io.writers.groundwater import write_gw_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        out_path = tmp_output / "GW_MAIN.dat"
        write_gw_main(gw, out_path)
        assert out_path.exists()

        gw2 = read_gw_main(out_path)
        assert gw2.n_hydrographs == gw.n_hydrographs
        assert gw2.n_face_flows == gw.n_face_flows


class TestBCMain:
    def test_read_bc_main(self):
        from iwfm_io.readers.groundwater import read_gw_main, read_bc_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        bc_path = gw.file_paths.get("bc_main")
        if bc_path and Path(bc_path).exists():
            bc = read_bc_main(bc_path)
            assert bc.header is not None
            assert len(bc.file_paths) == 5


class TestSpecHeadBC:
    def test_read_spec_head_bc(self):
        from iwfm_io.readers.groundwater import read_spec_head_bc

        path = GW_DIR / "SpecHeadBC.dat"
        if path.exists():
            shbc = read_spec_head_bc(path)
            assert shbc.n_nodes > 0
            assert shbc.data is not None
            assert len(shbc.data) == shbc.n_nodes

    def test_spec_head_round_trip(self, tmp_output):
        from iwfm_io.readers.groundwater import read_spec_head_bc
        from iwfm_io.writers.groundwater import write_spec_head_bc

        path = GW_DIR / "SpecHeadBC.dat"
        if path.exists():
            shbc = read_spec_head_bc(path)
            out = tmp_output / "SpecHeadBC.dat"
            write_spec_head_bc(shbc, out)
            shbc2 = read_spec_head_bc(out)
            assert shbc2.n_nodes == shbc.n_nodes


class TestTileDrain:
    def test_read_tile_drain(self):
        from iwfm_io.readers.groundwater import read_tile_drain

        path = GW_DIR / "TileDrain.dat"
        if path.exists():
            td = read_tile_drain(path)
            assert td.n_tile_drains > 0
            assert td.data is not None
            assert len(td.data) == td.n_tile_drains

    def test_tile_drain_round_trip(self, tmp_output):
        from iwfm_io.readers.groundwater import read_tile_drain
        from iwfm_io.writers.groundwater import write_tile_drain

        path = GW_DIR / "TileDrain.dat"
        if path.exists():
            td = read_tile_drain(path)
            out = tmp_output / "TileDrain.dat"
            write_tile_drain(td, out)
            td2 = read_tile_drain(out)
            assert td2.n_tile_drains == td.n_tile_drains


class TestElemPump:
    def test_read_elem_pump(self):
        from iwfm_io.readers.groundwater import read_elem_pump

        path = GW_DIR / "ElemPump.dat"
        if path.exists():
            ep = read_elem_pump(path)
            assert ep.n_sinks > 0
            assert ep.data is not None


class TestSubsidence:
    def test_read_subsidence(self):
        from iwfm_io.readers.groundwater import read_subsidence

        path = GW_DIR / "Subsidence.dat"
        if path.exists():
            sub = read_subsidence(path)
            assert sub.header is not None
            assert len(sub.file_paths) > 0
