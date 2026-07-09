"""Tests for text output file readers."""

import pytest
from pathlib import Path

from tests.io.conftest import RESULTS_DIR, BUDGET_DIR


class TestHydrographOut:
    def test_read_gw_hydrograph_out(self):
        from iwfm_io.readers.text_output import read_hydrograph_out

        path = RESULTS_DIR / "GWHyd.out"
        if path.exists():
            df = read_hydrograph_out(path)
            assert len(df) > 0
            assert "date" in df.columns
            assert len(df.columns) > 1

    def test_read_strm_hydrograph_out(self):
        from iwfm_io.readers.text_output import read_hydrograph_out

        path = RESULTS_DIR / "StrmHyd.out"
        if path.exists():
            df = read_hydrograph_out(path)
            assert len(df) > 0
            assert "date" in df.columns

    def test_read_with_metadata(self):
        from iwfm_io.readers.text_output import read_hydrograph_out_with_metadata

        path = RESULTS_DIR / "GWHyd.out"
        if path.exists():
            result = read_hydrograph_out_with_metadata(path)
            assert "metadata" in result
            assert "data" in result
            assert len(result["data"]) > 0

    def test_read_subsidence_out(self):
        from iwfm_io.readers.text_output import read_hydrograph_out

        path = RESULTS_DIR / "Subsidence.out"
        if path.exists():
            df = read_hydrograph_out(path)
            assert len(df) > 0


class TestFlowOut:
    def test_read_boundary_flow(self):
        from iwfm_io.readers.text_output import read_flow_out

        path = RESULTS_DIR / "BoundaryFlow.out"
        if path.exists():
            df = read_flow_out(path)
            assert len(df) > 0
            assert "date" in df.columns

    def test_read_tile_drain_flows(self):
        from iwfm_io.readers.text_output import read_flow_out

        path = RESULTS_DIR / "TileDrainFlows.out"
        if path.exists():
            df = read_flow_out(path)
            assert len(df) > 0


class TestHeadAllOut:
    def test_read_head_all(self):
        from iwfm_io.readers.text_output import read_head_all_out

        path = RESULTS_DIR / "GWHeadAll.out"
        if path.exists():
            df = read_head_all_out(path)
            assert len(df) > 0
            assert "date" in df.columns
            # Should have many columns (nodes * layers)
            assert len(df.columns) > 100


class TestFinalState:
    def test_read_final_gw_heads(self):
        from iwfm_io.readers.text_output import read_final_state_out

        path = RESULTS_DIR / "FinalGWHeads.out"
        if path.exists():
            df = read_final_state_out(path)
            assert len(df) > 0
            # Should have at least 441 rows (one per node)
            assert len(df) >= 400

    def test_read_final_lake_elev(self):
        from iwfm_io.readers.text_output import read_final_state_out

        path = RESULTS_DIR / "FinalLakeElev.out"
        if path.exists():
            df = read_final_state_out(path)
            assert len(df) > 0


class TestBudgetText:
    def test_read_gw_budget(self):
        from iwfm_io.readers.text_output import read_budget_text

        path = BUDGET_DIR / "GW.bud"
        if path.exists():
            result = read_budget_text(path)
            assert len(result) > 0
            # Should have sections for subregions
            for name, df in result.items():
                assert "date" in df.columns
                assert len(df) > 0

    def test_read_strm_budget(self):
        from iwfm_io.readers.text_output import read_budget_text

        path = BUDGET_DIR / "Strm.bud"
        if path.exists():
            result = read_budget_text(path)
            assert len(result) > 0

    def test_read_rootzone_budget(self):
        from iwfm_io.readers.text_output import read_budget_text

        path = BUDGET_DIR / "RootZone.bud"
        if path.exists():
            result = read_budget_text(path)
            assert len(result) > 0
