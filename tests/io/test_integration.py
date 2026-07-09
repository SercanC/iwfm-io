"""Integration test: load the entire sample model via iwfm_io."""

import pytest
from pathlib import Path

from tests.io.conftest import (
    SAMPLE_MODEL, PREPROCESSOR_DIR, SIMULATION_DIR, RESULTS_DIR, BUDGET_DIR,
)


class TestFullModelLoad:
    """Test loading all major components of the sample model."""

    def test_preprocessor_full_load(self):
        from iwfm_io.readers.preprocessor import read_preprocessor_main

        path = PREPROCESSOR_DIR / "PreProcessor_MAIN.IN"
        if not path.exists():
            pytest.skip("Sample model not available")
        pp = read_preprocessor_main(path, follow_references=True)
        assert pp.header is not None

        children = pp.children or {}
        # Should have loaded node, element, strata, stream files
        if "node" in children:
            assert children["node"].data is not None
            assert len(children["node"].data) == 441  # 441 nodes
        if "element" in children:
            assert children["element"].data is not None
            assert len(children["element"].data) == 400  # 400 elements
        if "strata" in children:
            assert children["strata"].data is not None
            assert len(children["strata"].data) == 441  # one per node

    def test_simulation_full_load(self):
        from iwfm_io.readers.simulation import read_simulation_main

        path = SIMULATION_DIR / "Simulation_MAIN.IN"
        if not path.exists():
            pytest.skip("Sample model not available")
        sim = read_simulation_main(path)
        assert sim.header is not None
        assert sim.sim_begin is not None
        assert sim.sim_end is not None
        assert len(sim.file_paths) >= 10

    def test_gw_component(self):
        from iwfm_io.readers.groundwater import read_gw_main

        path = SIMULATION_DIR / "GW" / "GW_MAIN.dat"
        if not path.exists():
            pytest.skip("GW files not available")
        gw = read_gw_main(path)
        assert gw.n_hydrographs > 0
        assert len(gw.aquifer_param_raw) > 0

    def test_stream_component(self):
        from iwfm_io.readers.stream import read_stream_main

        path = SIMULATION_DIR / "Stream" / "Stream_MAIN.dat"
        if not path.exists():
            pytest.skip("Stream files not available")
        sm = read_stream_main(path)
        assert sm.config["n_hydrographs"] > 0
        assert sm.reach_params is not None

    def test_rootzone_component(self):
        from iwfm_io.readers.rootzone import read_rootzone_main

        path = SIMULATION_DIR / "RootZone" / "RootZone_MAIN.dat"
        if not path.exists():
            pytest.skip("RootZone files not available")
        rz = read_rootzone_main(path)
        assert len(rz.file_paths) == 14

    def test_hdf5_output_files(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf, read_hydrograph_hdf, read_head_hdf

        # GW budget
        gw_path = RESULTS_DIR / "GW.hdf"
        if gw_path.exists():
            result = read_budget_hdf(gw_path)
            assert len(result["locations"]) == 3  # 2 subregions + entire model

        # GW hydrographs
        gwhyd_path = RESULTS_DIR / "GWHyd.hdf"
        if gwhyd_path.exists():
            df = read_hydrograph_hdf(gwhyd_path)
            assert len(df) > 3000  # ~10 years of monthly data

        # GW heads at all nodes
        head_path = RESULTS_DIR / "GWHeadAll.hdf"
        if head_path.exists():
            df = read_head_hdf(head_path, n_nodes=441, n_layers=2)
            assert len(df.columns) == 882

    def test_text_output_files(self):
        from iwfm_io.readers.text_output import (
            read_hydrograph_out, read_final_state_out, read_budget_text,
        )

        # GW hydrograph text
        gwhyd_path = RESULTS_DIR / "GWHyd.out"
        if gwhyd_path.exists():
            df = read_hydrograph_out(gwhyd_path)
            assert len(df) > 3000

        # Final GW heads
        final_path = RESULTS_DIR / "FinalGWHeads.out"
        if final_path.exists():
            df = read_final_state_out(final_path)
            assert len(df) >= 441  # one per node

        # GW budget text
        bud_path = BUDGET_DIR / "GW.bud"
        if bud_path.exists():
            result = read_budget_text(bud_path)
            assert len(result) > 0
