"""Tests for text output file readers."""


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
            # Columns carry the header node IDs, layer-major (441 nodes x
            # 2 layers in the sample model), mirroring read_head_hdf
            assert df.columns[1] == "node_1_layer_1"
            assert df.columns[441] == "node_441_layer_1"
            assert df.columns[442] == "node_1_layer_2"
            assert df.columns[-1] == "node_441_layer_2"


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


class TestBudgetTextColumnTitles:
    """Column titles are reconstructed from IWFM's fixed-width header.

    Regression for the 2.15.0 reader: group banners were sliced per
    column ("A" / "gricultural A" / "rea"), a group underline ended the
    header block early, and neighbouring titles a single space apart
    were glued together.
    """

    def _first(self, name):
        from iwfm_io.readers.text_output import read_budget_text
        import pytest
        path = BUDGET_DIR / name
        if not path.exists():
            pytest.skip(f"{name} not present")
        return next(iter(read_budget_text(path).values()))

    def test_no_generic_column_names(self):
        for name in ("GW.bud", "Strm.bud", "LWU.bud", "RootZone.bud",
                     "DiverDetail.bud"):
            df = self._first(name)
            generic = [c for c in df.columns if c.startswith("col_")]
            assert not generic, f"{name}: unrecovered titles {generic}"
            assert df.columns.is_unique, name

    def test_group_banner_disambiguates_repeated_titles(self):
        # the L&WU budget prints "Area" once per group; the banner is
        # what separates the agricultural one from the urban one
        cols = list(self._first("LWU.bud").columns)
        ag = [c for c in cols if c.startswith("Agricultural Area")]
        urban = [c for c in cols if c.startswith("Urban Area")]
        assert ag and urban, cols
        assert "Agricultural Area (acres)" in cols, cols
        # the banner must not be sliced into fragments
        assert not any(c.strip() in ("A", "rea", "Urba") for c in cols), cols

    def test_titles_one_space_apart_are_not_glued(self):
        # "inside Model outside Model" sits over two columns
        cols = list(self._first("Strm.bud").columns)
        assert "Gain from GW inside Model (+)" in cols, cols
        assert "Gain from GW outside Model (+)" in cols, cols

    def test_multi_word_titles_stay_with_their_column(self):
        cols = list(self._first("DiverDetail.bud").columns)
        assert "Actual Delivery to Subreg. 2" in cols, cols
        assert "Delivery Shortage for Subreg. 2" in cols, cols
