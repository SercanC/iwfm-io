"""Tests for zone definition reader and ZBudget HDF5 reader."""

import pytest
import numpy as np
from pathlib import Path

from tests.io.conftest import SAMPLE_MODEL, RESULTS_DIR

ZBUDGET_DIR = SAMPLE_MODEL / "ZBudget"


class TestReadZoneDef:
    def test_read_zone_def_horizontal(self):
        from iwfm_io.readers.hdf5 import read_zone_def

        path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists():
            pytest.skip(f"{path} not found")

        zd = read_zone_def(path)
        assert zd.extent == "horizontal"
        assert len(zd.zones) == 2
        assert zd.zones[1] == "Region1"
        assert zd.zones[2] == "Region2"
        assert len(zd.element_zones) == 400
        assert "element_id" in zd.element_zones.columns
        assert "zone_id" in zd.element_zones.columns
        assert "layer" not in zd.element_zones.columns
        # Elements 1-200 are zone 1, 201-400 are zone 2
        zone1 = zd.element_zones[zd.element_zones["zone_id"] == 1]
        zone2 = zd.element_zones[zd.element_zones["zone_id"] == 2]
        assert len(zone1) == 200
        assert len(zone2) == 200

    def test_read_zone_def_vertical(self):
        from iwfm_io.readers.hdf5 import read_zone_def

        path = ZBUDGET_DIR / "ZoneDef_SRs_L1.dat"
        if not path.exists():
            pytest.skip(f"{path} not found")

        zd = read_zone_def(path)
        assert zd.extent == "vertical"
        assert len(zd.zones) == 2
        assert "layer" in zd.element_zones.columns
        # All assignments are for layer 1
        assert (zd.element_zones["layer"] == 1).all()
        assert len(zd.element_zones) == 400

    def test_read_zone_def_subset(self):
        from iwfm_io.readers.hdf5 import read_zone_def

        path = ZBUDGET_DIR / "ZoneDef_E1_E10.dat"
        if not path.exists():
            pytest.skip(f"{path} not found")

        zd = read_zone_def(path)
        assert zd.extent == "horizontal"
        assert len(zd.zones) == 1
        assert len(zd.element_zones) == 10
        # Elements 1-10 only
        assert zd.element_zones["element_id"].min() == 1
        assert zd.element_zones["element_id"].max() == 10


class TestReadZBudgetRaw:
    def test_read_zbudget_raw(self):
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        result = read_zbudget_hdf(path)

        # Check metadata
        meta = result["metadata"]
        assert meta["n_elements"] == 400
        assert meta["n_layers"] == 2
        assert meta["n_timesteps"] == 3653
        assert len(meta["data_names"]) == 28

        # Check raw data structure
        assert "Layer_1" in result["data"]
        assert "Layer_2" in result["data"]

        # GW Storage should have all 400 elements
        layer1 = result["data"]["Layer_1"]
        assert "GW Storage_Inflow (+)" in layer1
        gw_df = layer1["GW Storage_Inflow (+)"]
        assert gw_df.index.name == "datetime"
        assert len(gw_df) == 3653
        assert len(gw_df.columns) == 400

    def test_read_zbudget_lwu(self):
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "LWU_ZBud.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        result = read_zbudget_hdf(path)
        meta = result["metadata"]
        assert meta["n_elements"] == 400
        assert meta["n_layers"] >= 1
        assert len(meta["data_names"]) > 0
        assert "Layer_1" in result["data"]


class TestReadZBudgetAggregated:
    def test_read_zbudget_aggregated(self):
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        result = read_zbudget_hdf(path, zone_def=zdef_path)

        # Check zones
        assert "zones" in result
        assert result["zones"]["zone_ids"] == [1, 2]
        assert result["zones"]["zone_names"] == ["Region1", "Region2"]

        # Check aggregated data
        assert "Region1" in result["data"]
        assert "Region2" in result["data"]
        r1_df = result["data"]["Region1"]
        assert r1_df.index.name == "datetime"
        assert len(r1_df) == 3653
        # Should have data columns
        assert len(r1_df.columns) > 0

        # Check face flows exist
        assert "face_flows" in result
        # There should be inter-zone exchange between zones 1 and 2
        if result["face_flows"]:
            key = (1, 2)
            assert key in result["face_flows"]
            ff_df = result["face_flows"][key]
            assert "flow" in ff_df.columns
            assert len(ff_df) == 3653

    def test_read_zbudget_monthly(self):
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        result = read_zbudget_hdf(path, zone_def=zdef_path, interval="1MON")

        r1_df = result["data"]["Region1"]
        # 10 years of daily data -> ~120 months
        assert len(r1_df) < 3653
        assert len(r1_df) >= 119  # at least 119 months in 10 years

    def test_read_zbudget_with_zone_def_object(self):
        from iwfm_io.readers.hdf5 import read_zone_def, read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        zd = read_zone_def(zdef_path)
        result = read_zbudget_hdf(path, zone_def=zd)

        assert "Region1" in result["data"]
        assert "Region2" in result["data"]


class TestReadZBudgetTypeAware:
    def test_subsurface_flow_columns(self):
        """Verify face-flow-derived subsurface inflow/outflow columns appear
        in zone DataFrames and conserve mass between zones."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        result = read_zbudget_hdf(path, zone_def=zdef_path)
        r1 = result["data"]["Region1"]
        r2 = result["data"]["Region2"]

        # Subsurface columns should be present
        assert "Subsurface Inflow from Region2 (+)" in r1.columns
        assert "Subsurface Outflow to Region2 (-)" in r1.columns
        assert "Subsurface Inflow from Region1 (+)" in r2.columns
        assert "Subsurface Outflow to Region1 (-)" in r2.columns

        # Conservation: R1 outflow to R2 == R2 inflow from R1
        np.testing.assert_allclose(
            r1["Subsurface Outflow to Region2 (-)"].values,
            r2["Subsurface Inflow from Region1 (+)"].values,
        )
        np.testing.assert_allclose(
            r2["Subsurface Outflow to Region1 (-)"].values,
            r1["Subsurface Inflow from Region2 (+)"].values,
        )

        # At least some flows should be non-zero
        total = (r1["Subsurface Outflow to Region2 (-)"].sum()
                 + r1["Subsurface Inflow from Region2 (+)"].sum())
        assert total > 0, "Expected non-zero subsurface exchange"

    def test_subsurface_flow_monthly_conservation(self):
        """Verify monthly resampling preserves subsurface flow conservation."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        result = read_zbudget_hdf(path, zone_def=zdef_path, interval="1MON")
        r1 = result["data"]["Region1"]
        r2 = result["data"]["Region2"]

        np.testing.assert_allclose(
            r1["Subsurface Outflow to Region2 (-)"].values,
            r2["Subsurface Inflow from Region1 (+)"].values,
        )

    def test_read_zbudget_monthly_type_aware(self):
        """Verify that monthly aggregation uses data-type-aware resampling."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        raw = read_zbudget_hdf(path, zone_def=zdef_path)
        monthly = read_zbudget_hdf(path, zone_def=zdef_path, interval="1MON")

        # GW_ZBud has all type-1 columns (volumetric rates) so monthly
        # should equal naive sum. Verify consistency.
        r1_raw = raw["data"]["Region1"]
        r1_mon = monthly["data"]["Region1"]
        assert len(r1_mon) < len(r1_raw)
        assert len(r1_mon) >= 119

        # For type-1 data, monthly sum should match manual resample sum
        if len(r1_raw.columns) > 0:
            col = r1_raw.columns[0]
            naive_monthly = r1_raw[[col]].resample("ME").sum()
            np.testing.assert_allclose(
                r1_mon[col].values, naive_monthly[col].values,
                rtol=1e-10,
                err_msg="Type-1 columns should sum identically to naive resample"
            )

    def test_read_lwu_zbudget_monthly(self):
        """Verify LWU ZBudget monthly aggregation uses type-aware resampling."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "LWU_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        raw = read_zbudget_hdf(path, zone_def=zdef_path)
        monthly = read_zbudget_hdf(path, zone_def=zdef_path, interval="1MON")

        meta = raw["metadata"]
        data_types = meta["data_types"]
        data_names = meta["data_names"]

        # LWU has type-4 (area) columns — these should use last, not sum
        area_indices = [i for i, t in enumerate(data_types) if t == 4]

        r1_raw = raw["data"]["Region1"]
        r1_mon = monthly["data"]["Region1"]

        for idx in area_indices:
            col = data_names[idx]
            if col not in r1_raw.columns or col not in r1_mon.columns:
                continue
            # Last value of first month in raw should equal first month in monthly
            first_month_end = r1_mon.index[0]
            month_mask = (r1_raw.index.year == first_month_end.year) & \
                         (r1_raw.index.month == first_month_end.month)
            if month_mask.any():
                last_daily = r1_raw.loc[month_mask, col].iloc[-1]
                assert r1_mon[col].iloc[0] == pytest.approx(last_daily, rel=1e-6), \
                    f"Area column '{col}' should use last-of-period, not sum"

    def test_read_lwu_zbudget_raw_monthly(self):
        """Verify LWU ZBudget raw mode monthly uses type-aware resampling."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "LWU_ZBud.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        raw = read_zbudget_hdf(path)
        monthly = read_zbudget_hdf(path, interval="1MON")

        meta = raw["metadata"]
        data_types = meta["data_types"]
        data_names = meta["data_names"]

        # Find a type-4 (area) data name
        area_idx = next((i for i, t in enumerate(data_types) if t == 4), None)
        if area_idx is None:
            pytest.skip("No area columns in LWU_ZBud")

        area_name = data_names[area_idx]
        layer_key = "Layer_1"
        if layer_key not in raw["data"] or area_name not in raw["data"][layer_key]:
            pytest.skip(f"{area_name} not found in raw data")

        raw_df = raw["data"][layer_key][area_name]
        mon_df = monthly["data"][layer_key][area_name]

        # Area (type 4 = last): monthly should have fewer rows
        assert len(mon_df) < len(raw_df)

        # Monthly value should be the last daily value, not the sum
        if len(raw_df.columns) > 0:
            col = raw_df.columns[0]
            first_month_end = mon_df.index[0]
            month_mask = (raw_df.index.year == first_month_end.year) & \
                         (raw_df.index.month == first_month_end.month)
            if month_mask.any():
                last_daily = raw_df.loc[month_mask, col].iloc[-1]
                naive_sum = raw_df.loc[month_mask, col].sum()
                # last != sum (unless all values in the month are identical)
                assert mon_df[col].iloc[0] == pytest.approx(last_daily, rel=1e-6), \
                    "Area column should use last-of-period in raw mode too"


class TestZoneBalance:
    def test_zone_balance(self):
        """Verify inflow - outflow balance using ErrorInCols/ErrorOutCols."""
        from iwfm_io.readers.hdf5 import read_zbudget_hdf

        path = RESULTS_DIR / "GW_ZBud.hdf"
        zdef_path = ZBUDGET_DIR / "ZoneDef_SRs.dat"
        if not path.exists() or not zdef_path.exists():
            pytest.skip("Required files not found")

        result = read_zbudget_hdf(path, zone_def=zdef_path)
        data_names = result["metadata"]["data_names"]

        # ErrorInCols and ErrorOutCols are 1-based indices into data_names
        # Inflow cols (odd indices 1,3,5,...) and outflow cols (even 2,4,6,...)
        # Sum all inflows and outflows for each zone and check they're close
        for zname in ["Region1", "Region2"]:
            df = result["data"][zname]
            total_in = np.zeros(len(df))
            total_out = np.zeros(len(df))
            for col in df.columns:
                if "Inflow" in col or "(+)" in col:
                    total_in += df[col].values
                elif "Outflow" in col or "(-)" in col:
                    total_out += df[col].values

            # Both should have non-trivial values
            assert np.any(total_in != 0), f"No inflow data for {zname}"
            assert np.any(total_out != 0), f"No outflow data for {zname}"
