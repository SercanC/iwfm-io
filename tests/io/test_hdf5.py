"""Tests for HDF5 output file readers."""

import pytest
import numpy as np
from pathlib import Path

from tests.io.conftest import BUDGET_DIR, RESULTS_DIR


class TestBudgetHDF:
    def test_budget_hdf_columns_align_with_text_budget(self):
        """Regression: labels were shifted one column left (the reader
        wrongly dropped the first data column as a 'time marker'), so
        e.g. 'Percolation' held Beginning Storage. Totals per column must
        match the Budget post-processor's text output."""
        from iwfm_io.readers.hdf5 import read_budget_hdf
        from iwfm_io.readers.text_output import read_budget_text

        hdf_path = RESULTS_DIR / "GW.hdf"
        txt_path = BUDGET_DIR / "GW.bud"
        if not (hdf_path.exists() and txt_path.exists()):
            pytest.skip("sample GW budget outputs not present")

        hdf = read_budget_hdf(hdf_path)
        txt = read_budget_text(txt_path)

        loc = hdf["locations"][0]
        hdf_df = hdf["data"][loc]
        txt_key = next((k for k in txt if k.upper() in loc.upper()
                        or loc.upper() in k.upper()), list(txt)[0])
        txt_df = txt[txt_key]

        # Text output is unit-converted (FACTVLOU) and may be aggregated
        # to a coarser interval, so compare column *totals*: the sum of
        # the first data column must match within text rounding.
        fact = 2.29568e-5  # sample GW main FACTVLOU (cu.ft -> ac.ft)
        hdf_total = float(hdf_df.iloc[:, 0].sum()) * fact
        txt_total = float(np.nansum(
            np.asarray(txt_df["col_1"], dtype=float)))
        assert hdf_total == pytest.approx(txt_total, rel=1e-3)


    def test_read_gw_budget(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if path.exists():
            result = read_budget_hdf(path)
            assert "locations" in result
            assert "data" in result
            assert len(result["locations"]) > 0
            # Check first location has a DataFrame
            first_loc = result["locations"][0]
            df = result["data"][first_loc]
            assert len(df) > 0
            assert df.index.name == "datetime"

    def test_native_interval_and_location_order(self):
        """The native output interval is exposed and locations follow the
        file's cLocationNames (DLL) order, not h5py's alphabetical order."""
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        result = read_budget_hdf(path)
        assert result["interval"] == "1DAY"
        # DLL order: subregions first, ENTIRE MODEL AREA last (alphabetical
        # iteration would put ENTIRE MODEL AREA first)
        assert result["locations"] == [
            "Region1 (SR1)", "Region2 (SR2)", "ENTIRE MODEL AREA"]
        assert list(result["data"].keys()) == result["locations"]
        # Resampling must not change the reported native interval
        monthly = read_budget_hdf(path, interval="1MON")
        assert monthly["interval"] == "1DAY"

    def test_location_order_numeric_names(self):
        """StrmNodeBud: numeric DLL order NODE 1, 8, 19 (alphabetical would
        yield NODE 1, 19, 8)."""
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "StrmNodeBud.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        result = read_budget_hdf(path)
        assert result["locations"] == ["NODE 1", "NODE 8", "NODE 19"]

    def test_read_strm_budget(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "StrmBud.hdf"
        if path.exists():
            result = read_budget_hdf(path)
            assert len(result["locations"]) > 0

    def test_read_rootzone_budget(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "RootZone.hdf"
        if path.exists():
            result = read_budget_hdf(path)
            assert len(result["locations"]) > 0

    def test_read_lake_budget(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "LakeBud.hdf"
        if path.exists():
            result = read_budget_hdf(path)
            assert len(result["locations"]) > 0

    def test_read_gw_budget_data_types(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        result = read_budget_hdf(path)
        dt = result["data_types"]
        assert len(dt) > 0
        # GW budget: Beginning Storage should be type 2 (VLB),
        # Ending Storage should be type 3 (VLE)
        beg_cols = [c for c in dt if "Beginning" in c]
        end_cols = [c for c in dt if "Ending" in c]
        assert all(dt[c] == 2 for c in beg_cols), "Beginning Storage should be VLB (2)"
        assert all(dt[c] == 3 for c in end_cols), "Ending Storage should be VLE (3)"

    def test_read_gw_budget_monthly(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        raw = read_budget_hdf(path)
        monthly = read_budget_hdf(path, interval="1MON")

        first_loc = raw["locations"][0]
        raw_df = raw["data"][first_loc]
        mon_df = monthly["data"][first_loc]

        # Monthly should have fewer rows than daily
        assert len(mon_df) < len(raw_df)
        # Approximately 120 months for 10 years of daily data
        assert len(mon_df) >= 119

        # Beginning Storage (type 2 = first): monthly value should equal
        # the first daily value of that month, NOT the sum.
        beg_col = [c for c in raw_df.columns if "Beginning" in c]
        if beg_col:
            col = beg_col[0]
            # Check first month: monthly value == first daily value
            first_month_end = mon_df.index[0]
            month_mask = (raw_df.index.year == first_month_end.year) & \
                         (raw_df.index.month == first_month_end.month)
            first_daily = raw_df.loc[month_mask, col].iloc[0]
            assert mon_df[col].iloc[0] == pytest.approx(first_daily), \
                "Beginning Storage should use first-of-period, not sum"

        # Ending Storage (type 3 = last): monthly value should equal
        # the last daily value of that month.
        end_col = [c for c in raw_df.columns if "Ending" in c]
        if end_col:
            col = end_col[0]
            first_month_end = mon_df.index[0]
            month_mask = (raw_df.index.year == first_month_end.year) & \
                         (raw_df.index.month == first_month_end.month)
            last_daily = raw_df.loc[month_mask, col].iloc[-1]
            assert mon_df[col].iloc[0] == pytest.approx(last_daily), \
                "Ending Storage should use last-of-period, not sum"

        # A volumetric rate column (type 1 = sum): monthly value should
        # equal the sum of daily values.
        vr_cols = [c for c in raw_df.columns
                   if raw["data_types"].get(c) == 1]
        if vr_cols:
            col = vr_cols[0]
            first_month_end = mon_df.index[0]
            month_mask = (raw_df.index.year == first_month_end.year) & \
                         (raw_df.index.month == first_month_end.month)
            daily_sum = raw_df.loc[month_mask, col].sum()
            assert mon_df[col].iloc[0] == pytest.approx(daily_sum), \
                "Volumetric rate should be summed"

    def test_read_gw_budget_yearly(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        yearly = read_budget_hdf(path, interval="1YEAR")
        first_loc = yearly["locations"][0]
        yr_df = yearly["data"][first_loc]
        # 10 years of daily data (1990-2000) -> 11 calendar years
        assert len(yr_df) == 11

    def test_read_lwu_budget_monthly(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "LWU.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        raw = read_budget_hdf(path)
        monthly = read_budget_hdf(path, interval="1MON")

        dt = raw["data_types"]
        first_loc = raw["locations"][0]
        raw_df = raw["data"][first_loc]
        mon_df = monthly["data"][first_loc]

        # Area columns (type 4) should use last value
        area_cols = [c for c in dt if dt[c] == 4]
        if area_cols:
            col = area_cols[0]
            first_month_end = mon_df.index[0]
            month_mask = (raw_df.index.year == first_month_end.year) & \
                         (raw_df.index.month == first_month_end.month)
            last_daily = raw_df.loc[month_mask, col].iloc[-1]
            assert mon_df[col].iloc[0] == pytest.approx(last_daily), \
                "Area should use last-of-period"

        # Supply Requirement columns (type 7): should differ from naive sum
        # due to carry-over logic (when there are shortages)
        req_cols = [c for c in dt if dt[c] == 7]
        if req_cols:
            col = req_cols[0]
            # Verify that monthly has correct number of rows
            assert len(mon_df) >= 119

    def test_read_budget_invalid_interval(self):
        from iwfm_io.readers.hdf5 import read_budget_hdf

        path = RESULTS_DIR / "GW.hdf"
        if not path.exists():
            pytest.skip(f"{path} not found")

        with pytest.raises(ValueError, match="Unsupported interval"):
            read_budget_hdf(path, interval="1WEEK")


class TestHydrographHDF:
    def test_read_gw_hydrograph(self):
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf

        path = RESULTS_DIR / "GWHyd.hdf"
        if path.exists():
            df = read_hydrograph_hdf(path)
            assert len(df) > 0
            assert df.index.name == "datetime"
            assert len(df.columns) > 0

    def test_read_strm_hydrograph(self):
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf

        path = RESULTS_DIR / "StrmHyd.hdf"
        if path.exists():
            df = read_hydrograph_hdf(path)
            assert len(df) > 0

    def test_read_subsidence_hdf(self):
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf

        path = RESULTS_DIR / "Subsidence.hdf"
        if path.exists():
            df = read_hydrograph_hdf(path)
            assert len(df) > 0

    def test_read_tiledrain_hdf(self):
        from iwfm_io.readers.hdf5 import read_hydrograph_hdf

        path = RESULTS_DIR / "TileDrainFlows.hdf"
        if path.exists():
            df = read_hydrograph_hdf(path)
            assert len(df) > 0


class TestHeadHDF:
    def test_read_head_generic(self):
        from iwfm_io.readers.hdf5 import read_head_hdf

        path = RESULTS_DIR / "GWHeadAll.hdf"
        if path.exists():
            df = read_head_hdf(path)
            assert len(df) > 0
            assert df.index.name == "datetime"

    def test_read_head_named_columns(self):
        from iwfm_io.readers.hdf5 import read_head_hdf

        path = RESULTS_DIR / "GWHeadAll.hdf"
        if path.exists():
            df = read_head_hdf(path, n_nodes=441, n_layers=2)
            assert len(df.columns) == 882
            assert "node_1_layer_1" in df.columns
            assert "node_441_layer_2" in df.columns
