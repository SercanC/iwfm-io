"""Tests for the cross-file relationship layer: lazy component/leaf
loading, series resolution (factor + recurring expansion), reverse
column usage, and reference validation."""

import pandas as pd
import pytest

from tests.io.conftest import SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(),
    reason="sample model not present (.assets/sample_model)")


@pytest.fixture()
def model():
    import iwfm_io
    return iwfm_io.open_model(SAMPLE_MODEL)


class TestLazyLoading:
    def test_components(self, model):
        np_ag = model.component("nonponded_ag")
        assert np_ag.crop_codes == ["TO", "AL"]
        assert model.component("bc_main") is not None
        assert model.component("lake_main") is not None
        # cached: same object back
        assert model.component("nonponded_ag") is np_ag

    def test_timeseries_roles(self, model):
        assert model.timeseries("irig_period").n_columns == 4
        assert model.timeseries("et").spec.n_columns == 7
        assert model.timeseries("return_flow").n_columns == 2

    def test_unknown_role_raises(self, model):
        with pytest.raises(KeyError, match="known roles"):
            model.timeseries("nope")


class TestSeries:
    def test_factor_applied_and_expanded(self, model):
        # ET col 1 = tomatoes; file stores inches, FACTET converts
        s = model.series("et", 1)
        raw = model.series("et", 1, raw=True, expand=False)
        factor = model.timeseries("et").spec.factor
        assert len(raw) == 12  # the year-4000 monthly pattern
        assert isinstance(raw["date"].iloc[0], str)
        # expanded onto the 10/1990–9/2000 simulation period
        assert len(s) == 121
        assert s["date"].dtype.kind == "M"
        # the first expanded stamp is Oct 1 1990 — i.e. the September
        # pattern row (09/30_24:00 = end of September) mapped to 1990
        assert s["date"].iloc[0] == pd.Timestamp("1990-10-01")
        sept = raw.loc[raw["date"] == "09/30/4000_24:00", "value"].iloc[0]
        assert s["value"].iloc[0] == pytest.approx(sept * factor)

    def test_flags_never_scaled(self, model):
        flags = model.series("irig_period", 1)
        assert set(flags["value"].unique()) <= {0, 1}

    def test_column_out_of_range(self, model):
        with pytest.raises(IndexError, match="1..7"):
            model.series("et", 99)

    def test_dest_pairs_refused(self, model):
        with pytest.raises(ValueError, match="type, dest"):
            model.series("surface_flow_dest", 1)


class TestColumnUsage:
    def test_et_usage_matches_lost_column_labels(self, model):
        # the ET file's comment named its columns Tomatoes Alfalfa Rice
        # Urban Native SmallWatershed Lake — the reverse lookup
        # reconstructs that mapping from the pointer tables
        u = model.column_usage("et")
        by_col = {c: set(g["source"]) for c, g in u.groupby("column")}
        assert by_col[1] == {"nonponded_ag"}
        assert by_col[3] == {"ponded_ag"}
        assert by_col[4] == {"urban"}
        assert by_col[5] == {"native_veg"}
        assert by_col[6] == {"swshed"}
        assert by_col[7] == {"lake_main"}

    def test_all_irig_period_columns_referenced(self, model):
        u = model.column_usage("irig_period")
        assert u["column"].nunique() == 4


class TestValidateReferences:
    def test_sample_model_is_clean(self, model):
        findings = model.validate_references()
        assert len(findings) == 0, findings.to_string()

    def test_out_of_range_pointer_is_found(self, model):
        np_ag = model.component("nonponded_ag")
        np_ag.et_columns.loc[0, "TO"] = 99  # ET has 7 columns
        findings = model.validate_references()
        hit = findings[(findings["source"] == "nonponded_ag")
                       & (findings["column"] == "TO")]
        assert len(hit) == 1
        assert hit["severity"].iloc[0] == "error"
        assert "column count (7)" in hit["issue"].iloc[0]

    def test_unknown_element_id_is_found(self, model):
        urban = model.component("urban")
        urban.element_params.loc[0, "element_id"] = 99999
        findings = model.validate_references()
        hit = findings[(findings["source"] == "urban")
                       & (findings["column"] == "element_id")]
        assert len(hit) == 1
        assert "unknown element" in hit["issue"].iloc[0]

    def test_bad_destination_is_found(self, model):
        ds = model.component("diver_specs")
        ds.data.loc[0, "dest_type"] = 4      # subregion
        ds.data.loc[0, "dest_id"] = 99       # only 2 subregions exist
        findings = model.validate_references()
        hit = findings[(findings["source"] == "diver_specs")
                       & (findings["column"] == "dest_id")]
        assert len(hit) == 1
        assert "subregion" in hit["issue"].iloc[0]


class TestExpandRecurring:
    def test_single_sentinel_row_becomes_constant(self):
        from iwfm_io import expand_recurring

        df = pd.DataFrame({"date": ["09/30/2500_24:00"], "v": [3.5]})
        out = expand_recurring(df, "10/01/1990_00:00", "09/30/2000_24:00")
        assert len(out) == 1
        assert out["date"].iloc[0] == pd.Timestamp("1990-10-01")
        assert out["v"].iloc[0] == 3.5

    def test_real_years_pass_through_filtered(self):
        from iwfm_io import expand_recurring

        df = pd.DataFrame({
            "date": ["09/30/1989_24:00", "10/31/1990_24:00",
                     "11/30/1990_24:00"],
            "v": [1.0, 2.0, 3.0]})
        out = expand_recurring(df, "10/01/1990_00:00",
                               "09/30/2000_24:00")
        assert list(out["v"]) == [2.0, 3.0]

    def test_leap_day_fallback(self):
        from iwfm_io import expand_recurring

        df = pd.DataFrame({"date": ["02/29/4000_24:00",
                                    "08/31/4000_24:00"],
                           "v": [1.0, 2.0]})
        out = expand_recurring(df, "01/01/1995_00:00",
                               "12/31/1995_24:00")
        # 1995 is not a leap year: the Feb stamp falls back to Mar 1
        # minus nothing — 28 Feb + the 24:00 day-end convention
        feb = out[out["v"] == 1.0]["date"].iloc[0]
        assert (feb.month, feb.day) == (3, 1)


class TestConvenienceAccessors:
    def test_crop_series_matches_manual_resolution(self, model):
        et = model.crop_series("et", "TO", element=12)
        manual = model.series("et", 1)
        pd.testing.assert_frame_equal(et, manual)

    def test_crop_series_ponded_and_native(self, model):
        rice = model.crop_series("et", "rice_fl", expand=False)
        assert len(rice) == 12
        rip = model.crop_series("et", "riparian", element=1,
                                expand=False)
        pd.testing.assert_frame_equal(
            rip, model.series("et", 5, expand=False))

    def test_crop_series_zero_pointer_raises(self, model):
        # the sample's ICAW columns are all 0 = computed internally
        with pytest.raises(ValueError, match="computed internally"):
            model.crop_series("supply_requirement", "TO")

    def test_crop_series_unknown_crop(self, model):
        with pytest.raises(KeyError, match="known"):
            model.crop_series("et", "XX")

    def test_urban_series(self, model):
        pop = model.urban_series("population", element=5, expand=False)
        assert pop["value"].iloc[0] == 1000.0

    def test_element_pumping_scaled(self, model):
        # element 73: TSPumping col 1 x fracsk 1.0, FACTPUMP applied
        s = model.element_pumping(73, expand=False)
        raw = model.element_pumping(73, raw=True, scaled=False,
                                    expand=False)
        factor = model.timeseries("ts_pumping").spec.factor
        nz = raw["value"] != 0
        assert (s.loc[nz, "value"]
                == raw.loc[nz, "value"] * factor).all()

    def test_element_pumping_unknown(self, model):
        with pytest.raises(KeyError, match="no element pumping"):
            model.element_pumping(1)

    def test_well_pumping_without_wells(self, model):
        with pytest.raises(FileNotFoundError, match="well"):
            model.well_pumping(1)

    def test_bc_series_constant(self, model):
        const = model.bc_series(1, layer=1)
        assert len(const) == 1
        assert const["value"].iloc[0] == 290.0

    def test_bc_series_timeseries_driven(self, model):
        row = model.component("spec_head").data.query("itscol > 0") \
            .iloc[0]
        ts = model.bc_series(int(row["node_id"]),
                             layer=int(row["layer"]))
        assert len(ts) > 1

    def test_bc_series_missing(self, model):
        with pytest.raises(KeyError, match="no boundary condition"):
            model.bc_series(999)

    def test_diversion_series_scaled(self, model):
        dv = model.diversion_series(1, expand=False)
        un = model.diversion_series(1, scaled=False, expand=False)
        nz = un["value"] != 0
        ratio = dv.loc[nz, "value"] / un.loc[nz, "value"]
        assert (ratio.round(6) == 0.98).all()

    def test_diversion_series_no_max_column(self, model):
        with pytest.raises(ValueError, match="pointer is 0"):
            model.diversion_series(1, kind="max")

    def test_lake_max_elevation(self, model):
        lme = model.lake_max_elevation()
        assert lme["value"].iloc[0] == 285.0
