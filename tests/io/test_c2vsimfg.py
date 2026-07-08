"""Validation tests against C2VSimFG v1.5 (real DWR model, IWFM 2024.2).

C2VSimFG exercises format variants the small sample model doesn't:
11-entry simulation main without STOPCVL, commented-out optional output
lines (HTPOUTFL/VTPOUTFL/TPSOUTFL/FNSUBFL), no IHTPFLAG, bed-parameter
rows with trailing "/ comment" and a 5th column, single-token inflow
node assignments, omitted FCHYDOUTFL when NOUTF=0, and a model without
lakes.

All tests skip when the model folder is absent (it is too large to ship).
"""

from pathlib import Path

import pytest

C2VSIMFG = Path(__file__).resolve().parent.parent.parent / ".assets" / "c2vsimfg_v1.5"

pytestmark = pytest.mark.skipif(
    not C2VSIMFG.is_dir(), reason="C2VSimFG v1.5 model not present in .assets/"
)


@pytest.fixture(scope="module")
def model():
    from iwfm.io import open_model
    return open_model(C2VSIMFG)


class TestOpenModel:
    def test_discovers_simulation_main(self, model):
        # C2VSimFG's simulation main is "C2VSimFG.in" — found by content
        # sniffing, not by name patterns
        assert model._sim is not None
        assert model._sim.sim_begin == "09/30/1973_24:00"
        assert model._sim.sim_end == "09/30/2021_24:00"
        assert model._sim.time_unit == "1MON"

    def test_grid(self, model):
        assert len(model.nodes_df()) == 30179
        assert len(model.elements_df()) == 32537

    def test_describe(self, model):
        d = model.describe()
        assert d["grid"]["n_layers"] == 4
        assert d["grid"]["n_subregions"] == 21
        assert d["streams"]["n_reaches"] == 110
        assert d["simulation"] is not None


class TestPreprocessor:
    def test_lakes_none_when_absent(self):
        from iwfm.io import read_preprocessor
        pp = read_preprocessor(C2VSIMFG / "Preprocessor" / "C2VSimFG_Preprocessor.in")
        assert pp.lakes is None
        assert len(pp.nodes) == 30179
        assert len(pp.stratigraphy) == 30179
        assert len(pp.stream_reaches) == 110


class TestSimulationMain:
    def test_read(self):
        from iwfm.io.readers.simulation import read_simulation_main
        sm = read_simulation_main(C2VSIMFG / "Simulation" / "C2VSimFG.in")
        # 11-entry file list: no crop_coeff in 2024.x mains
        assert "crop_coeff" not in sm.file_paths
        assert sm.file_paths["lake_main"] is None
        assert sm.file_paths["gw_main"].endswith("C2VSimFG_Groundwater1974.dat")
        # No STOPCVL in 2024.x solver block
        assert "stopcvl" not in sm.solver
        assert sm.solver["mxiter"] == 5000
        assert sm.supply_adjust_flag == 11


class TestGroundwater:
    def test_gw_main(self):
        from iwfm.io.readers.groundwater import read_gw_main
        gw = read_gw_main(
            C2VSIMFG / "Simulation" / "Groundwater" / "C2VSimFG_Groundwater1974.dat")
        assert gw.n_hydrographs == 54544
        assert len(gw.hydrographs) == 54544
        # HTPOUTFL/VTPOUTFL commented out, IHTPFLAG absent in this file
        assert gw.file_paths["htp_out"] is None
        assert gw.config["ihtpflag"] is None
        assert gw.config["kdeb"] == 1
        # NOUTF=0 with no FCHYDOUTFL line
        assert gw.n_face_flows == 0
        assert gw.face_flow_out_file is None

    def test_subsidence(self):
        from iwfm.io.readers.groundwater import read_subsidence
        sb = read_subsidence(
            C2VSIMFG / "Simulation" / "Groundwater" / "C2VSimFG_Subsidence.dat")
        assert sb.n_hydrographs == 608
        assert len(sb.hydrographs) == 608
        # Trailing "/ comment" stripped from hydrograph names
        assert sb.hydrographs.iloc[0]["name"] == "InSAR01"


class TestStreams:
    def test_stream_main(self):
        from iwfm.io.readers.stream import read_stream_main
        st = read_stream_main(
            C2VSIMFG / "Simulation" / "Streams" / "C2VSimFG_Streams.dat")
        assert len(st.hydrograph_specs) == 63
        assert len(st.node_budget_nodes) == 4634
        # Bed rows have a trailing "/Reach ..." comment and a 5th column
        assert len(st.reach_params) == 4634
        assert "col_5" in st.reach_params.columns
        assert st.config["intrctype"] == 1

    def test_stream_inflow(self):
        from iwfm.io.readers.stream import read_stream_inflow
        si = read_stream_inflow(
            C2VSIMFG / "Simulation" / "Streams" / "C2VSimFG_StreamInflow.dat")
        # Single-token assignment lines: column ids are implicit
        assert len(si.node_assignments) == 58
        assert si.node_assignments[0] == (1, 2680)
        assert si.data.shape[0] == 576


class TestAdapterDllFree:
    """DLL-free adapter methods added so plots don't need the DLL."""

    def test_tile_drains_and_bypasses(self, model):
        td = model.tile_drains_df()
        assert len(td) == 1162
        assert {"id", "node", "x", "y"} <= set(td.columns)
        bp = model.bypasses_df()
        assert len(bp) == 18

    def test_aquifer_parameters(self, model):
        import numpy as np
        kh = model.get_aquifer_horizontal_k()
        assert kh.shape == (30179, 4)
        assert not np.isnan(kh).any()
        sy = model.get_aquifer_specific_yield()
        assert 0.0 <= np.nanmin(sy) and np.nanmax(sy) < 0.5

    def test_supply_demand(self, model):
        sd = model.supply_demand_df()
        assert len(sd) == 21
        assert list(sd["location_id"]) == list(range(1, 22))
        assert (sd["ag_requirement"] > 0).all()

    def test_land_use_areas(self, model):
        areas = model.get_land_use_areas(lu_type="AG")
        assert areas.shape == (21, 576)
        assert areas[:, -1].sum() > 0

    def test_stream_flows_from_node_budget(self, model):
        hdf = C2VSIMFG / "Results" / "C2VSimFG_Stream_NodeBudget.hdf"
        if not hdf.exists():
            pytest.skip("stream node budget HDF absent — run the simulation")
        sf = model.stream_flows_df()
        assert len(sf) == 4634
        assert (sf["gain_from_gw"] != 0).sum() > 4000

    def test_depth_to_gw(self, model):
        import numpy as np
        d = model.get_subregion_ag_pumping_avg_depth_to_gw()
        assert d.shape == (21,)
        assert np.isfinite(d).all()
        assert 0 < np.nanmin(d) < np.nanmax(d) < 1000  # feet, plausible


class TestResults:
    def test_budget_text(self):
        from iwfm.io.readers.text_output import read_budget_text
        b = read_budget_text(C2VSIMFG / "Results" / "C2VSimFG_GW_Budget.bud")
        assert len(b) == 22  # 21 subregions + entire model
        first = next(iter(b.values()))
        assert first.shape[0] == 576  # monthly, WY1974-2021


class TestResultsHDF:
    """Budget HDF validation — needs the .hdf outputs from a simulation
    run (the DWR download ships only post-processed text budgets)."""

    HDF = C2VSIMFG / "Results" / "C2VSimFG_GW_Budget.hdf"

    @pytest.fixture(scope="class")
    def gw_budget(self):
        if not self.HDF.exists():
            pytest.skip("budget HDFs absent — run the simulation to create them")
        from iwfm.io.readers.hdf5 import read_budget_hdf
        return read_budget_hdf(self.HDF)

    def test_monthly_index_uses_calendar_months(self, gw_budget):
        # Regression: 1MON steps were reconstructed as fixed 43200-minute
        # intervals, drifting ~250 days across the 48-year run
        df = gw_budget["data"]["Subregion 1 (SR1)"]
        assert df.index[0].date().isoformat() == "1973-11-01"
        assert df.index[-1].date().isoformat() == "2021-10-01"

    def test_columns_match_text_budget(self, gw_budget):
        # Regression: column labels were shifted one left vs the data
        import numpy as np
        import pandas as pd
        from iwfm.io.readers.text_output import read_budget_text
        txt = read_budget_text(C2VSIMFG / "Results" / "C2VSimFG_GW_Budget.bud")
        txt_sr1 = txt[next(k for k in txt if "Subregion 1 " in k)]
        hdf_sr1 = gw_budget["data"]["Subregion 1 (SR1)"]

        fact = 0.000022957  # FACTVLOU from the GW main (cu.ft -> AC.FT)
        h = hdf_sr1["Percolation"].to_numpy() * fact
        t = pd.to_numeric(txt_sr1["col_1"], errors="coerce").to_numpy()
        assert len(h) == len(t) == 576
        np.testing.assert_allclose(h, t, rtol=5e-4, atol=0.1)
