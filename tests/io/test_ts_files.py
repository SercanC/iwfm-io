"""Tests for the generic time-series file reader and the audit fixes:
root-zone leaf TS files, SurfaceFlowDest, elem-pump layer inference,
UnsatZone parametric grids, DELTAT, stream-geometry partial interaction,
and DSS-mode IrigFrac."""

import pandas as pd
import pytest

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

RZ_DIR = SIMULATION_DIR / "RootZone"

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(),
    reason="sample model not present (.assets/sample_model)")

# (path, n_columns, has_factor, factor)
LEAF_FILES = [
    (RZ_DIR / "NonPondedAg" / "RootDepthFrac.dat", 1, False, None),
    (RZ_DIR / "NonPondedAg" / "MinMoist.dat", 2, False, None),
    (RZ_DIR / "PondedAg" / "PondDepth.dat", 5, True, 0.083333),
    (RZ_DIR / "PondedAg" / "RiceOps.dat", 2, True, 0.08333),
    (RZ_DIR / "Urban" / "Population.dat", 1, False, None),
    (RZ_DIR / "Urban" / "PerCapWaterUse.dat", 1, True, 43560000.0),
    (RZ_DIR / "ReturnFlowFrac.dat", 2, False, None),
    (RZ_DIR / "ReuseFrac.dat", 2, False, None),
]


class TestGenericTimeSeriesFile:
    @pytest.mark.parametrize(
        "path,ncol,has_factor,factor", LEAF_FILES,
        ids=[p[0].name for p in LEAF_FILES])
    def test_read_leaf_file(self, path, ncol, has_factor, factor):
        from iwfm_io import read_timeseries_file

        ts = read_timeseries_file(path)
        assert ts.n_columns == ncol
        assert (ts.factor is not None) == has_factor
        if factor is not None:
            assert ts.factor == factor
        assert ts.data is not None
        assert len(ts.data) >= 1
        assert list(ts.data.columns) == (
            ["date"] + [f"col_{i}" for i in range(1, ncol + 1)])

    @pytest.mark.parametrize(
        "path,ncol,has_factor,factor", LEAF_FILES,
        ids=[p[0].name for p in LEAF_FILES])
    def test_round_trip(self, tmp_output, path, ncol, has_factor, factor):
        from iwfm_io import read_timeseries_file, write_timeseries_file

        ts = read_timeseries_file(path)
        out = tmp_output / path.name
        write_timeseries_file(ts, out)

        ts2 = read_timeseries_file(out)
        assert ts2.n_columns == ts.n_columns
        assert ts2.factor == ts.factor
        assert ts2.n_steps_update == ts.n_steps_update
        assert ts2.repeat_freq == ts.repeat_freq
        assert ts2.keywords == ts.keywords
        pd.testing.assert_frame_equal(ts2.data, ts.data)

    def test_dss_backed_file(self, tmp_output):
        # UrbanWaterUseSpecs is DSS-backed in the sample model
        from iwfm_io import read_timeseries_file, write_timeseries_file

        path = RZ_DIR / "Urban" / "UrbanWaterUseSpecs.dat"
        ts = read_timeseries_file(path)
        assert ts.n_columns == 1
        assert ts.dss_file == "TSDATA_IN.DSS"
        assert ts.data is None
        assert len(ts.dss_pathnames) == 1
        assert ts.dss_pathnames[0][0] == 1
        assert "URB_SPEC" in ts.dss_pathnames[0][1]

        out = tmp_output / "UrbanWaterUseSpecs.dat"
        write_timeseries_file(ts, out)
        ts2 = read_timeseries_file(out)
        assert ts2.dss_file == ts.dss_file
        assert ts2.dss_pathnames == ts.dss_pathnames


class TestSurfaceFlowDest:
    def test_read(self):
        from iwfm_io import read_surface_flow_dest

        sfd = read_surface_flow_dest(RZ_DIR / "SurfaceFlowDest.dat")
        assert sfd.n_columns == 2
        assert sfd.data is not None
        row = sfd.data.iloc[0]
        # sample: 12/31/2500_24:00  (1,18)  (1,6)
        assert row["date"] == "12/31/2500_24:00"
        assert row["type_1"] == 1 and row["dest_1"] == 18
        assert row["type_2"] == 1 and row["dest_2"] == 6

    def test_round_trip(self, tmp_output):
        from iwfm_io import read_surface_flow_dest, write_surface_flow_dest

        sfd = read_surface_flow_dest(RZ_DIR / "SurfaceFlowDest.dat")
        out = tmp_output / "SurfaceFlowDest.dat"
        write_surface_flow_dest(sfd, out)

        sfd2 = read_surface_flow_dest(out)
        assert sfd2.n_columns == sfd.n_columns
        pd.testing.assert_frame_equal(sfd2.data, sfd.data)

    def test_spaced_tuples(self, tmp_output):
        from iwfm_io import read_surface_flow_dest

        deck = (
            "C  test\n"
            "   2 / NDSTN\n"
            "   1 / NSPDSTN\n"
            "   0 / NFQDSTN\n"
            "C  end of specification\n"
            "   12/31/2500_24:00  ( 1, 18 )  (5,0)\n"
        )
        path = tmp_output / "sfd_spaced.dat"
        path.write_text(deck)
        sfd = read_surface_flow_dest(path)
        row = sfd.data.iloc[0]
        assert row["type_1"] == 1 and row["dest_1"] == 18
        assert row["type_2"] == 5 and row["dest_2"] == 0


class TestElemPumpLayers:
    def test_three_layer_deck(self, tmp_output):
        # NL != 2 must not misassign columns (issue found on 4-layer
        # C2VSimFG; the old reader hard-coded fracskl_1/fracskl_2).
        from iwfm_io.readers.groundwater import read_elem_pump
        from iwfm_io.writers.groundwater import write_elem_pump

        deck = (
            "C  test\n"
            "   2 / NSINK\n"
            "   1  1  1.0  3  0.5  0.3  0.2  0  0  -1  0  1  3.0"
            "    /AgWell\n"
            "   2  1  1.0  3  0.6  0.2  0.2  4  2  -1  0  1  3.0\n"
            "   0 / NGRP\n"
        )
        path = tmp_output / "elempump3.dat"
        path.write_text(deck)
        ep = read_elem_pump(path)
        assert "fracskl_3" in ep.data.columns
        row = ep.data.iloc[0]
        assert row["fracskl_1"] == 0.5
        assert row["fracskl_3"] == 0.2
        assert row["typdstsk"] == 0
        assert row["fskmax"] == 3.0
        assert row["name"] == "AgWell"
        assert ep.data.iloc[1]["typdstsk"] == 4
        assert ep.data.iloc[1]["dstsk"] == 2

        out = tmp_output / "elempump3_out.dat"
        write_elem_pump(ep, out)
        ep2 = read_elem_pump(out)
        pd.testing.assert_frame_equal(ep2.data, ep.data)

    def test_sample_model_still_two_layers(self):
        from iwfm_io.readers.groundwater import read_elem_pump

        path = SIMULATION_DIR / "GW" / "ElemPump.dat"
        if path.exists():
            ep = read_elem_pump(path)
            assert "fracskl_2" in ep.data.columns
            assert "fracskl_3" not in ep.data.columns


class TestUnsatZoneParametric:
    def test_ngroup_parametric(self, tmp_output):
        from iwfm_io.readers.misc import read_unsatzone
        from iwfm_io.writers.misc import write_unsatzone

        deck = (
            "C  test\n"
            "   1 / NUNSAT\n"
            "   0.001 / UZCONV\n"
            "   150 / UZITERMX\n"
            "         / UZBUDFL\n"
            "         / UZZBUDFL\n"
            "         / UZFNFL\n"
            "   1 / NGROUP\n"
            "   1.0  1.0  1.0\n"
            "   1DAY / TUNITZ\n"
            "   1-4\n"
            "C  end of element list\n"
            "   2 / NDP\n"
            "   0 / NEP\n"
            "   1        0.0      0.0   10.0  0.3   0.2   1.0   1\n"
            "   2      100.0      0.0   12.0  0.35  0.25  1.5   1\n"
            "   0  0.1\n"
        )
        path = tmp_output / "unsat_param.dat"
        path.write_text(deck)
        uz = read_unsatzone(path)
        assert uz.ngroup == 1
        assert len(uz.parametric_grids) == 1
        grid = uz.parametric_grids[0]
        assert grid["node_range"] == "1-4"
        assert grid["nodes"] == [1, 2, 3, 4]
        assert grid["ndp"] == 2
        params = grid["params"]
        assert len(params) == 2
        assert params["thickness"].tolist() == [10.0, 12.0]
        assert uz.initial_moisture is not None
        assert uz.initial_moisture["element_id"].iloc[0] == 0

        out = tmp_output / "unsat_param_out.dat"
        write_unsatzone(uz, out)
        uz2 = read_unsatzone(out)
        assert uz2.ngroup == 1
        pd.testing.assert_frame_equal(
            uz2.parametric_grids[0]["params"], params)
        pd.testing.assert_frame_equal(uz2.initial_moisture,
                                      uz.initial_moisture)


class TestSimulationDeltat:
    def test_deltat_round_trip(self, tmp_output):
        from iwfm_io import read_simulation, write_simulation

        deck = (
            "C  test\n"
            "    Title line\n"
            "        PreProcessor.bin        / 1: BINARY INPUT\n"
            "        0.0      / BDT\n"
            "        0        / RESTART\n"
            "        1.0      / DELTAT\n"
            "        1DAY     / UNITT\n"
            "        100.0    / EDT\n"
            "        0        / ISTRT\n"
            "        0        / KDEB\n"
            "        500000   / CACHE\n"
            "        2        / MSOLVE\n"
            "        1.0      / RELAX\n"
            "        1500     / MXITER\n"
            "        50       / MXITERSP\n"
            "        0.0001   / STOPC\n"
            "        0.001    / STOPCSP\n"
            "        11       / KOPTDV\n"
        )
        path = tmp_output / "sim_deltat.in"
        path.write_text(deck)
        sim = read_simulation(path)
        assert sim.time_step == 1.0
        assert sim.titles == ["Title line"]

        out = tmp_output / "sim_deltat_out.in"
        write_simulation(sim, out)
        sim2 = read_simulation(out)
        assert sim2.time_step == 1.0

    def test_tracked_deck_has_no_deltat(self):
        from iwfm_io import read_simulation

        path = SIMULATION_DIR / "Simulation_MAIN.IN"
        if path.exists():
            sim = read_simulation(path)
            assert sim.time_step is None


class TestStreamGeomPartialInteraction:
    def test_partial_rows_round_trip(self, tmp_output):
        from iwfm_io.readers.preprocessor import read_stream_geom
        from iwfm_io.writers.preprocessor import write_stream_geom

        deck = (
            "C  test\n"
            "   1  / NRH\n"
            "   2  / NRTB\n"
            "   1   1   0   Reach One\n"
            "   1        1\n"
            "   1.0  / FACTLT\n"
            "   60.0 / FACTQ\n"
            "   1min / TUNIT\n"
            "   1   100.0   0.5   10.0\n"
            "       1.0   20.0\n"
            "   1  / NSTRPINT\n"
            "   1   0.5\n"
        )
        path = tmp_output / "stream_geom_pint.dat"
        path.write_text(deck)
        sg = read_stream_geom(path)
        assert sg.n_partial_interaction == 1
        assert sg.partial_interaction is not None
        assert sg.partial_interaction["stream_node_id"].iloc[0] == 1
        assert sg.partial_interaction["fraction"].iloc[0] == 0.5
        assert sg.reaches["name"].iloc[0] == "Reach One"

        out = tmp_output / "stream_geom_pint_out.dat"
        write_stream_geom(sg, out)
        sg2 = read_stream_geom(out)
        assert sg2.n_partial_interaction == 1
        pd.testing.assert_frame_equal(sg2.partial_interaction,
                                      sg.partial_interaction)


class TestIrigFracDss:
    def test_dss_mode(self, tmp_output):
        from iwfm_io import read_irigfrac, write_irigfrac

        deck = (
            "C  test\n"
            "   2 / NCOLIRF\n"
            "   1 / NSPIRF\n"
            "   0 / NFQIRF\n"
            "   TSDATA.DSS / DSSFL\n"
            "   1  /A/B/C//1MON/F1/\n"
            "   2  /A/B/C//1MON/F2/\n"
        )
        path = tmp_output / "irigfrac_dss.dat"
        path.write_text(deck)
        irf = read_irigfrac(path)
        assert irf.dss_file == "TSDATA.DSS"
        assert len(irf.dss_pathnames) == 2
        assert irf.data is None

        out = tmp_output / "irigfrac_dss_out.dat"
        write_irigfrac(irf, out)
        irf2 = read_irigfrac(out)
        assert irf2.dss_file == "TSDATA.DSS"
        assert irf2.dss_pathnames == irf.dss_pathnames
