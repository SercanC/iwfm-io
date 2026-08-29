"""Dimension variables are a contract: readers store the declared
counts, writers emit the STORED count and raise on any mismatch with
the table it sizes (IWFM reads tables BY these counts, so a silent
mismatch would produce a file the model reads wrong)."""

import pytest

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

PP_DIR = SAMPLE_MODEL / "Preprocessor"

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(),
    reason="sample model not present (.assets/sample_model)")


class TestDeclaredCountsStored:
    def test_preprocessor_counts(self):
        from iwfm_io import read_nodes, read_elements, read_stream_geom
        from iwfm_io.readers.preprocessor import read_lake_geom

        nodes = read_nodes(PP_DIR / "NodeXY.dat")
        assert nodes.n_nodes == 441 == len(nodes.data)

        elems = read_elements(PP_DIR / "Element.dat")
        assert elems.n_elements == 400 == len(elems.data)
        assert elems.n_subregions == 2 == len(elems.subregions)

        sg = read_stream_geom(PP_DIR / "Stream.dat")
        assert sg.n_reaches == 3 == len(sg.reaches)

        lg = read_lake_geom(PP_DIR / "Lake.dat")
        assert lg.n_lakes == 1 == len(lg.data)


class TestWriterRaisesOnMismatch:
    def test_nodes_count_mismatch(self, tmp_output):
        from iwfm_io import read_nodes, write_nodes

        nodes = read_nodes(PP_DIR / "NodeXY.dat")
        nodes.data = nodes.data.iloc[:-1]  # drop a row, keep the count
        with pytest.raises(ValueError, match="ND"):
            write_nodes(nodes, tmp_output / "NodeXY.dat")

    def test_elem_pump_count_mismatch(self, tmp_output):
        from iwfm_io import read_elem_pump, write_elem_pump

        ep = read_elem_pump(SIMULATION_DIR / "GW" / "ElemPump.dat")
        ep.n_sinks += 1
        with pytest.raises(ValueError, match="NSINK"):
            write_elem_pump(ep, tmp_output / "ElemPump.dat")

    def test_diver_specs_count_mismatch(self, tmp_output):
        from iwfm_io import read_diver_specs, write_diver_specs

        ds = read_diver_specs(SIMULATION_DIR / "Stream" / "DiverSpecs.dat")
        ds.data = ds.data.iloc[:-1]
        with pytest.raises(ValueError, match="NRDV"):
            write_diver_specs(ds, tmp_output / "DiverSpecs.dat")

    def test_swshed_per_watershed_mismatch(self, tmp_output):
        from iwfm_io import read_swshed, write_swshed

        sw = read_swshed(SIMULATION_DIR / "SWShed.dat")
        # drop one receiving-node row without updating that
        # watershed's NWB
        sw.watershed_nodes = sw.watershed_nodes.iloc[:-1]
        with pytest.raises(ValueError, match="NWB"):
            write_swshed(sw, tmp_output / "SWShed.dat")

    def test_lake_main_mismatch(self, tmp_output):
        from iwfm_io import read_lake_main, write_lake_main

        lake = read_lake_main(
            SIMULATION_DIR / "Lake" / "Lake_MAIN.dat")
        lake.n_lakes += 1
        with pytest.raises(ValueError, match="lake parameter rows"):
            write_lake_main(lake, tmp_output / "Lake_MAIN.dat")

    def test_timeseries_width_mismatch(self, tmp_output):
        from iwfm_io import read_timeseries_file, write_timeseries_file

        ts = read_timeseries_file(
            SIMULATION_DIR / "RootZone" / "ReturnFlowFrac.dat")
        ts.data = ts.data.drop(columns=["col_2"])
        with pytest.raises(ValueError, match="NCOL"):
            write_timeseries_file(ts, tmp_output / "ReturnFlowFrac.dat")

    def test_gw_hydrograph_mismatch(self, tmp_output):
        from iwfm_io import read_gw_main, write_gw_main

        gw = read_gw_main(SIMULATION_DIR / "GW" / "GW_MAIN.dat")
        gw.hydrographs = gw.hydrographs.iloc[:-1]
        with pytest.raises(ValueError, match="NOUTH"):
            write_gw_main(gw, tmp_output / "GW_MAIN.dat")


class TestCrossFileCounts:
    def test_read_strata_with_expected_count(self):
        from iwfm_io import read_strata

        st = read_strata(PP_DIR / "Strata.dat", n_nodes=441)
        assert len(st.data) == 441

    def test_read_strata_wrong_expected_count(self):
        from iwfm_io import read_strata

        with pytest.raises(ValueError, match="n_nodes=442"):
            read_strata(PP_DIR / "Strata.dat", n_nodes=442)

    def test_read_elem_pump_explicit_layers(self):
        from iwfm_io import read_elem_pump

        ep = read_elem_pump(SIMULATION_DIR / "GW" / "ElemPump.dat",
                            n_layers=2)
        assert "fracskl_2" in ep.data.columns
        assert "fracskl_3" not in ep.data.columns

    def test_preprocessor_passes_node_count_to_strata(self):
        from iwfm_io import read_preprocessor

        pp = read_preprocessor(PP_DIR / "PreProcessor_MAIN.IN")
        assert len(pp.stratigraphy) == pp.children["node"].n_nodes
