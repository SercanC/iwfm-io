"""Tests for iwfm_io simulation and timeseries readers/writers."""

from pathlib import Path

import pandas as pd
import pytest

from tests.io.conftest import SAMPLE_MODEL, SIMULATION_DIR

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")

from iwfm_io.readers.simulation import read_simulation_main
from iwfm_io.readers.timeseries import (
    read_et,
    read_irigfrac,
    read_precip,
    read_supply_adjust,
)
from iwfm_io.writers.simulation import write_simulation_main
from iwfm_io.writers.timeseries import (
    write_et,
    write_irigfrac,
    write_supply_adjust,
)


# ------------------------------------------------------------------
# Simulation Main
# ------------------------------------------------------------------

class TestSimulationMain:
    def test_read_simulation_main(self):
        sm = read_simulation_main(SIMULATION_DIR / "Simulation_MAIN.IN")
        assert len(sm.titles) == 3
        assert sm.sim_begin == "09/30/1990_24:00"
        assert sm.sim_end == "09/30/2000_24:00"
        assert sm.time_unit == "1DAY"
        assert sm.restart == 0

    def test_simulation_file_paths(self):
        sm = read_simulation_main(SIMULATION_DIR / "Simulation_MAIN.IN")
        assert sm.file_paths["gw_main"] is not None
        assert sm.file_paths["stream_main"] is not None
        assert sm.file_paths["precip"] is not None
        assert sm.file_paths["et"] is not None

    def test_simulation_solver(self):
        sm = read_simulation_main(SIMULATION_DIR / "Simulation_MAIN.IN")
        assert sm.solver["msolve"] == 2
        assert sm.solver["relax"] == pytest.approx(1.0)
        assert sm.solver["mxiter"] == 1500
        assert sm.solver["stopc"] == pytest.approx(0.0001)

    def test_simulation_supply_adjust(self):
        sm = read_simulation_main(SIMULATION_DIR / "Simulation_MAIN.IN")
        assert sm.supply_adjust_flag == 11

    def test_simulation_round_trip(self, tmp_output):
        sm = read_simulation_main(SIMULATION_DIR / "Simulation_MAIN.IN")
        out = tmp_output / "Simulation_MAIN_rt.IN"
        write_simulation_main(sm, out)
        sm2 = read_simulation_main(out)
        assert sm2.sim_begin == sm.sim_begin
        assert sm2.sim_end == sm.sim_end
        assert sm2.time_unit == sm.time_unit
        # Solver values should match (comparing individual keys to avoid
        # float formatting differences)
        for key in sm.solver:
            assert sm2.solver[key] == pytest.approx(sm.solver[key]), f"solver[{key}] mismatch"
        assert sm2.supply_adjust_flag == sm.supply_adjust_flag

    def test_simulation_with_children(self):
        sm = read_simulation_main(
            SIMULATION_DIR / "Simulation_MAIN.IN",
            follow_references=True,
        )
        assert "et" in sm.children
        assert "irigfrac" in sm.children
        assert "supply_adjust" in sm.children


# ------------------------------------------------------------------
# ET
# ------------------------------------------------------------------

class TestET:
    def test_read_et_shape(self):
        et = read_et(SIMULATION_DIR / "ET.dat")
        assert et.spec.n_columns == 7
        assert et.spec.factor == pytest.approx(0.083333)
        assert len(et.data) == 12  # 12 monthly values

    def test_read_et_values(self):
        et = read_et(SIMULATION_DIR / "ET.dat")
        row = et.data.iloc[0]
        assert "10/31/4000_24:00" in row["date"]
        assert row["col_1"] == pytest.approx(3.4)
        assert row["col_7"] == pytest.approx(3.7)

    def test_et_round_trip(self, tmp_output):
        et = read_et(SIMULATION_DIR / "ET.dat")
        out = tmp_output / "ET_rt.dat"
        write_et(et, out)
        et2 = read_et(out)
        assert et2.spec.n_columns == et.spec.n_columns
        assert len(et2.data) == len(et.data)
        # Compare value columns (not date strings, which may differ in whitespace)
        value_cols = [c for c in et.data.columns if c != "date"]
        pd.testing.assert_frame_equal(
            et.data[value_cols].reset_index(drop=True),
            et2.data[value_cols].reset_index(drop=True),
            atol=0.01,
        )


# ------------------------------------------------------------------
# Precip
# ------------------------------------------------------------------

class TestPrecip:
    def test_read_precip_dss(self):
        pf = read_precip(SIMULATION_DIR / "Precip.dat")
        assert pf.spec.n_columns == 2
        assert pf.spec.factor == pytest.approx(0.0833333)
        assert pf.spec.dss_file == "TSDATA_IN.DSS"
        assert len(pf.dss_pathnames) == 2

    def test_precip_pathnames(self):
        pf = read_precip(SIMULATION_DIR / "Precip.dat")
        assert pf.dss_pathnames[0][0] == 1
        assert "GAGE1" in pf.dss_pathnames[0][1]
        assert pf.dss_pathnames[1][0] == 2
        assert "GAGE2" in pf.dss_pathnames[1][1]


# ------------------------------------------------------------------
# IrigFrac
# ------------------------------------------------------------------

class TestIrigFrac:
    def test_read_irigfrac(self):
        irf = read_irigfrac(SIMULATION_DIR / "IrigFrac.dat")
        assert irf.n_columns == 2
        assert len(irf.data) == 1

    def test_irigfrac_values(self):
        irf = read_irigfrac(SIMULATION_DIR / "IrigFrac.dat")
        row = irf.data.iloc[0]
        assert row["col_1"] == pytest.approx(0.0)
        assert row["col_2"] == pytest.approx(1.0)

    def test_irigfrac_round_trip(self, tmp_output):
        irf = read_irigfrac(SIMULATION_DIR / "IrigFrac.dat")
        out = tmp_output / "IrigFrac_rt.dat"
        write_irigfrac(irf, out)
        irf2 = read_irigfrac(out)
        assert irf2.n_columns == irf.n_columns
        value_cols = [c for c in irf.data.columns if c != "date"]
        pd.testing.assert_frame_equal(
            irf.data[value_cols].reset_index(drop=True),
            irf2.data[value_cols].reset_index(drop=True),
            atol=0.01,
        )


# ------------------------------------------------------------------
# SupplyAdjust
# ------------------------------------------------------------------

class TestSupplyAdjust:
    def test_read_supply_adjust(self):
        sa = read_supply_adjust(SIMULATION_DIR / "SupplyAdjust.dat")
        assert sa.n_columns == 3
        assert len(sa.data) == 1

    def test_supply_adjust_values(self):
        sa = read_supply_adjust(SIMULATION_DIR / "SupplyAdjust.dat")
        row = sa.data.iloc[0]
        assert row["col_1"] == pytest.approx(10.0)
        assert row["col_2"] == pytest.approx(1.0)
        assert row["col_3"] == pytest.approx(0.0)

    def test_supply_adjust_round_trip(self, tmp_output):
        sa = read_supply_adjust(SIMULATION_DIR / "SupplyAdjust.dat")
        out = tmp_output / "SupplyAdjust_rt.dat"
        write_supply_adjust(sa, out)
        sa2 = read_supply_adjust(out)
        assert sa2.n_columns == sa.n_columns
        value_cols = [c for c in sa.data.columns if c != "date"]
        pd.testing.assert_frame_equal(
            sa.data[value_cols].reset_index(drop=True),
            sa2.data[value_cols].reset_index(drop=True),
            atol=0.01,
        )
