"""Tests that every dataset in the model input files lands in DataFrames.

Covers the sections that used to be stored only as raw text: the GW
main aquifer-parameter tail, subsidence parameters, tile drain
hydrograph specs, well pumping configuration, small watersheds,
unsaturated zone, root zone soil table, the root-zone sub-component
mains, and the stream evaporation table.
"""

import pytest

from tests.io.conftest import SIMULATION_DIR

GW_DIR = SIMULATION_DIR / "GW"
RZ_DIR = SIMULATION_DIR / "RootZone"


class TestGWMainTail:
    def test_parametric_grid_and_initial_heads(self):
        from iwfm_io import read_gw_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        # Sample model uses one parametric grid group over all nodes
        assert gw.ngroup == 1
        assert gw.param_factors["fx"] == pytest.approx(3.2808)
        assert gw.param_factors["fs"] == pytest.approx(1e-6)
        assert gw.param_time_units["TUNITKH"] == "1day"
        assert len(gw.parametric_grids) == 1
        grid = gw.parametric_grids[0]
        assert grid["node_range"] == "1-441"
        assert len(grid["nodes"]) == 441
        assert grid["ndp"] == 1 and grid["nep"] == 0
        # One parametric node x 2 layers
        assert len(grid["params"]) == 2
        assert grid["params"]["kh"].iloc[0] == pytest.approx(50.0)

        # No anomalies; return-flow section present but off
        assert gw.anomaly_nebk == 0
        assert gw.kh_anomalies is None
        assert gw.iflagrf == 0

        # Initial heads at every node
        assert gw.facthp == pytest.approx(1.0)
        assert len(gw.initial_heads) == 441
        assert gw.initial_heads["head_layer_1"].iloc[0] == pytest.approx(280.0)
        assert gw.initial_heads["head_layer_2"].iloc[0] == pytest.approx(290.0)


class TestSubsidenceTail:
    def test_parametric_params(self):
        from iwfm_io import read_subsidence

        sub = read_subsidence(GW_DIR / "Subsidence.dat")
        assert sub.ngroup == 1
        assert sub.param_factors["fsce"] == pytest.approx(1e-6)
        grid = sub.parametric_grids[0]
        assert grid["node_range"] == "1-441"
        assert grid["params"]["hc"].iloc[0] == pytest.approx(99999.0)


class TestTileDrainHydrographs:
    def test_hydrograph_table(self):
        from iwfm_io import read_tile_drain

        td = read_tile_drain(GW_DIR / "TileDrain.dat")
        assert td.n_hydrographs == 6
        assert td.hyd_out_file.endswith("TileDrainFlows.out")
        assert len(td.hydrographs) == 6
        assert list(td.hydrographs["id"]) == [1, 4, 7, 10, 13, 16]
        assert (td.hydrographs["idtyp"] == 1).all()


class TestElementGroupsDF:
    def test_elem_pump_groups_df(self):
        from iwfm_io import read_elem_pump

        ep = read_elem_pump(GW_DIR / "ElemPump.dat")
        df = ep.element_groups_df
        assert list(df.columns) == ["group_id", "element_id"]


class TestSWShed:
    def test_all_tables(self):
        from iwfm_io import read_swshed

        sw = read_swshed(SIMULATION_DIR / "SWShed.dat")
        assert sw.n_watersheds == 3
        assert len(sw.watershed_data) == 3
        assert list(sw.watershed_data["stream_node"]) == [1, 3, 21]
        # 2 + 3 + 2 receiving GW nodes
        assert len(sw.watershed_nodes) == 7
        assert sw.watershed_nodes["gw_node"].iloc[0] == 432
        assert len(sw.rootzone_params) == 3
        # irns/icets are lookup columns into Precip/ET files
        assert (sw.rootzone_params["irns"] == 2).all()
        assert (sw.rootzone_params["icets"] == 6).all()
        assert len(sw.aquifer_params) == 3
        assert len(sw.initial_conditions) == 3
        assert sw.config["itermax"] == 150


class TestUnsatZone:
    def test_element_params_and_ic(self):
        from iwfm_io import read_unsatzone

        uz = read_unsatzone(SIMULATION_DIR / "UnsatZone.dat")
        assert uz.ngroup == 0
        # 400 elements x 2 unsaturated layers, long format
        assert len(uz.element_params) == 800
        assert uz.element_params["thickness"].iloc[0] == pytest.approx(20.0)
        assert set(uz.element_params["layer"]) == {1, 2}
        # Single IC row with element_id 0 = all elements
        assert len(uz.initial_moisture) == 1
        assert uz.initial_moisture["element_id"].iloc[0] == 0


class TestRootZoneSoilTable:
    def test_soil_params(self):
        from iwfm_io import read_rootzone_main

        rz = read_rootzone_main(RZ_DIR / "RootZone_MAIN.dat")
        df = rz.element_params
        assert len(df) == 400
        # v4.12 layout with per-destination lookup columns into DESTFL
        assert "icdstag" in df.columns
        assert df["k"].iloc[0] == pytest.approx(2.60)
        assert rz.config["factk"] == pytest.approx(0.03281)
        assert rz.file_paths["surface_flow_dest"].endswith(
            "SurfaceFlowDest.dat")


class TestRootZoneSubMains:
    def test_nonponded_ag(self):
        from iwfm_io import read_nonponded_ag_main

        np_ = read_nonponded_ag_main(
            RZ_DIR / "NonPondedAg" / "NonPondedAg_MAIN.dat")
        assert np_.n_crops == 2
        assert np_.crop_codes == ["TO", "AL"]
        assert len(np_.root_depths) == 2
        assert len(np_.curve_numbers) == 400
        # Pointer tables with element_id 0 apply to all elements
        assert len(np_.et_columns) == 1
        assert np_.et_columns["element_id"].iloc[0] == 0
        assert list(np_.et_columns[["TO", "AL"]].iloc[0]) == [1, 2]
        # TRGSMFL and DPFL are blank, so their tables are absent
        assert np_.target_moisture_columns is None
        assert np_.min_perc_columns is None
        assert len(np_.initial_conditions) == 400

    def test_ponded_ag(self):
        from iwfm_io import read_ponded_ag_main

        pa = read_ponded_ag_main(RZ_DIR / "PondedAg" / "PondedAg_MAIN.dat")
        assert pa.root_depths["rice_fl"] == pytest.approx(2.0)
        assert len(pa.curve_numbers) == 400
        assert len(pa.ponding_depth_columns) == 1
        assert list(pa.ponding_depth_columns.iloc[0])[1:] == [1, 2, 3, 4, 5]
        assert len(pa.initial_conditions) == 400

    def test_urban(self):
        from iwfm_io import read_urban_main

        ur = read_urban_main(RZ_DIR / "Urban" / "Urban_MAIN.dat")
        assert ur.root_depth == pytest.approx(2.0)
        assert len(ur.element_params) == 400
        assert ur.element_params["perv_fraction"].iloc[0] == pytest.approx(0.5)
        assert ur.element_params["iceturb"].iloc[0] == 4
        assert len(ur.initial_conditions) == 400

    def test_native_veg(self):
        from iwfm_io import read_native_veg_main

        nv = read_native_veg_main(
            RZ_DIR / "NativeVeg" / "NativeVeg_MAIN.dat")
        assert nv.root_depth_native == pytest.approx(3.0)
        assert len(nv.element_params) == 400
        assert nv.element_params["istrmrv"].iloc[0] == 0
        assert len(nv.initial_conditions) == 400


class TestStreamEvaporation:
    def test_sample_has_no_evaporation(self):
        from iwfm_io import read_stream_main

        sm = read_stream_main(
            SIMULATION_DIR / "Stream" / "Stream_MAIN.dat")
        assert sm.evaporation is None


def _frames_equal(a, b):
    from pandas.testing import assert_frame_equal
    assert (a is None) == (b is None)
    if a is not None:
        assert_frame_equal(a.reset_index(drop=True),
                           b.reset_index(drop=True), check_dtype=False)


class TestWriterRoundTrips:
    """Writers regenerate every section from the parsed DataFrames —
    write → re-read must reproduce the data exactly.  (The full proof
    is examples-level: IWFM executables reproduce baseline heads from
    regenerated inputs.)"""

    def test_gw_main(self, tmp_output):
        from iwfm_io import read_gw_main, write_gw_main

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        out = tmp_output / "GW_MAIN.dat"
        write_gw_main(gw, out)
        gw2 = read_gw_main(out)
        assert gw2.ngroup == gw.ngroup
        assert gw2.param_factors == gw.param_factors
        assert gw2.param_time_units == gw.param_time_units
        assert gw2.iflagrf == gw.iflagrf
        assert len(gw2.parametric_grids) == len(gw.parametric_grids)
        for g1, g2 in zip(gw.parametric_grids, gw2.parametric_grids):
            assert g2["node_range"] == g1["node_range"]
            assert g2["ndp"] == g1["ndp"] and g2["nep"] == g1["nep"]
            _frames_equal(g1["params"], g2["params"])
        _frames_equal(gw.initial_heads, gw2.initial_heads)
        _frames_equal(gw.hydrographs, gw2.hydrographs)

    def test_subsidence(self, tmp_output):
        from iwfm_io import read_subsidence
        from iwfm_io.writers.groundwater import write_subsidence

        sub = read_subsidence(GW_DIR / "Subsidence.dat")
        out = tmp_output / "Subsidence.dat"
        write_subsidence(sub, out)
        sub2 = read_subsidence(out)
        assert sub2.ngroup == sub.ngroup
        assert sub2.param_factors == sub.param_factors
        _frames_equal(sub.parametric_grids[0]["params"],
                      sub2.parametric_grids[0]["params"])

    def test_tile_drain(self, tmp_output):
        from iwfm_io import read_tile_drain, write_tile_drain

        td = read_tile_drain(GW_DIR / "TileDrain.dat")
        out = tmp_output / "TileDrain.dat"
        write_tile_drain(td, out)
        td2 = read_tile_drain(out)
        _frames_equal(td.data, td2.data)
        _frames_equal(td.hydrographs, td2.hydrographs)
        assert td2.hyd_factvlou == td.hyd_factvlou
        assert td2.hyd_out_file == td.hyd_out_file

    def test_elem_pump_groups(self, tmp_output):
        from iwfm_io import read_elem_pump, write_elem_pump

        ep = read_elem_pump(GW_DIR / "ElemPump.dat")
        out = tmp_output / "ElemPump.dat"
        write_elem_pump(ep, out)
        ep2 = read_elem_pump(out)
        assert ep2.element_groups == ep.element_groups

    def test_diver_specs(self, tmp_output):
        from iwfm_io import read_diver_specs, write_diver_specs

        ds = read_diver_specs(SIMULATION_DIR / "Stream" / "DiverSpecs.dat")
        out = tmp_output / "DiverSpecs.dat"
        write_diver_specs(ds, out)
        ds2 = read_diver_specs(out)
        _frames_equal(ds.data, ds2.data)
        assert ds2.delivery_groups == ds.delivery_groups
        assert ds2.recharge_zones == ds.recharge_zones
        assert ds2.spill_locations == ds.spill_locations

    def test_swshed(self, tmp_output):
        from iwfm_io import read_swshed, write_swshed

        sw = read_swshed(SIMULATION_DIR / "SWShed.dat")
        out = tmp_output / "SWShed.dat"
        write_swshed(sw, out)
        sw2 = read_swshed(out)
        _frames_equal(sw.watershed_data, sw2.watershed_data)
        _frames_equal(sw.watershed_nodes, sw2.watershed_nodes)
        _frames_equal(sw.rootzone_params, sw2.rootzone_params)
        _frames_equal(sw.aquifer_params, sw2.aquifer_params)
        _frames_equal(sw.initial_conditions, sw2.initial_conditions)
        assert sw2.config == sw.config

    def test_unsatzone(self, tmp_output):
        from iwfm_io import read_unsatzone, write_unsatzone

        uz = read_unsatzone(SIMULATION_DIR / "UnsatZone.dat")
        out = tmp_output / "UnsatZone.dat"
        write_unsatzone(uz, out)
        uz2 = read_unsatzone(out)
        _frames_equal(uz.element_params, uz2.element_params)
        _frames_equal(uz.initial_moisture, uz2.initial_moisture)
        assert uz2.config == uz.config

    def test_rootzone_main(self, tmp_output):
        from iwfm_io import read_rootzone_main, write_rootzone_main

        rz = read_rootzone_main(RZ_DIR / "RootZone_MAIN.dat")
        out = tmp_output / "RootZone_MAIN.dat"
        write_rootzone_main(rz, out)
        rz2 = read_rootzone_main(out)
        _frames_equal(rz.element_params, rz2.element_params)
        assert rz2.config == rz.config
        assert rz2.path_order == rz.path_order

    def test_gw_main_written_node_list_is_comment_terminated(
            self, tmp_output):
        # IWFM's READCH keeps consuming data lines after the parametric
        # grid node list until a comment line ends it — the writer must
        # emit that comment or IWFM misreads NDP as more node numbers.
        from iwfm_io import read_gw_main, write_gw_main
        from iwfm_io._tokens import is_comment

        gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
        out = tmp_output / "GW_MAIN.dat"
        write_gw_main(gw, out)
        lines = out.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines)
                   if l.strip() == "1-441")
        assert is_comment(lines[idx + 1])

    def test_rootzone_written_file_list_is_comment_terminated(
            self, tmp_output):
        # Same READCH-style behavior for the root-zone sub-file list:
        # a comment line must separate the last file entry from FACTK.
        from iwfm_io import read_rootzone_main, write_rootzone_main
        from iwfm_io._tokens import is_comment

        rz = read_rootzone_main(RZ_DIR / "RootZone_MAIN.dat")
        out = tmp_output / "RootZone_MAIN.dat"
        write_rootzone_main(rz, out)
        lines = out.read_text().splitlines()
        idx = next(i for i, l in enumerate(lines) if "/ARSCLFL" in l)
        assert is_comment(lines[idx + 1])
