"""Tests for budget-component observations (iwfm_io.pest.budget_obs)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"


def _long_frame():
    """Two locations x two components x 24 months (WY2000, WY2001)."""
    dates = pd.date_range("1999-10-31", periods=24, freq="ME")
    rows = []
    for loc in ["Region1 (SR1)", "Region2 (SR2)"]:
        for comp in ["Deep Percolation", "Pumping"]:
            base = 10.0 if comp == "Deep Percolation" else -5.0
            for i, d in enumerate(dates):
                rows.append((loc, comp, d, base + i * 0.0))
    return pd.DataFrame(rows, columns=["location", "component",
                                       "datetime", "value"])


class TestFrameSource:
    def test_mean_aggregation(self):
        from iwfm_io.pest import budget_observations

        out = budget_observations(_long_frame(), aggregate="mean")
        assert len(out) == 4
        assert out["datetime"].isna().all()
        row = out.set_index("obsnme").loc["bud_deep_percolation_region1_sr1"]
        assert row["value"] == pytest.approx(10.0)
        assert row["location"] == "Region1 (SR1)"

    def test_annual_water_year_sums(self):
        from iwfm_io.pest import budget_observations

        out = budget_observations(_long_frame(), aggregate="annual",
                                  components=["Pumping"])
        # 2 locations x 2 water years
        assert len(out) == 4
        sub = out.set_index("obsnme")
        # WY2000 = Oct 1999..Sep 2000 = 12 months x -5
        assert sub.loc["bud_pumping_region1_sr1_20000930",
                       "value"] == pytest.approx(-60.0)
        assert sub.loc["bud_pumping_region1_sr1_20010930",
                       "value"] == pytest.approx(-60.0)

    def test_full_series(self):
        from iwfm_io.pest import budget_observations

        out = budget_observations(_long_frame(), aggregate="none")
        assert len(out) == 96
        assert out["obsnme"].str.match(r"bud_[a-z0-9_]+_\d{8}$").all()

    def test_filters_accept_labels_or_slugs(self):
        from iwfm_io.pest import budget_observations

        a = budget_observations(_long_frame(), aggregate="mean",
                                locations=["Region1 (SR1)"])
        b = budget_observations(_long_frame(), aggregate="mean",
                                locations=["region1_sr1"])
        pd.testing.assert_frame_equal(a, b)
        assert set(a["location"]) == {"Region1 (SR1)"}

    def test_unknown_component_raises(self):
        from iwfm_io.pest import budget_observations

        with pytest.raises(KeyError, match="not found"):
            budget_observations(_long_frame(), components=["Nope"])

    def test_bad_aggregate_raises(self):
        from iwfm_io.pest import budget_observations

        with pytest.raises(ValueError, match="aggregate"):
            budget_observations(_long_frame(), aggregate="median")

    def test_frame_missing_columns_raises(self):
        from iwfm_io.pest import budget_observations

        with pytest.raises(ValueError, match="columns"):
            budget_observations(pd.DataFrame({"x": [1]}))

    def test_names_validate_clean(self):
        from iwfm_io.pest import budget_observations, validate_obs_names

        out = budget_observations(_long_frame(), aggregate="annual")
        assert validate_obs_names(out["obsnme"]) == []

    def test_annual_storage_stocks_first_last_not_summed(self):
        from iwfm_io.pest import budget_observations

        dates = pd.date_range("1999-10-31", periods=24, freq="ME")
        rows = []
        for comp, values in [
            ("Beginning Storage (+)", 1000.0 + np.arange(24)),
            ("Ending Storage (-)", 1001.0 + np.arange(24)),
            ("Cumulative Subsidence", np.linspace(0.1, 2.4, 24)),
            ("Pumping (-)", np.full(24, -5.0)),
        ]:
            for d, v in zip(dates, values):
                rows.append(("r1", comp, d, v))
        frame = pd.DataFrame(rows, columns=["location", "component",
                                            "datetime", "value"])

        out = budget_observations(frame, aggregate="annual")
        sub = out.set_index("obsnme")
        # WY2000 = the first 12 monthly values
        assert sub.loc["bud_beginning_storage_r1_20000930",
                       "value"] == 1000.0                      # first
        assert sub.loc["bud_ending_storage_r1_20000930",
                       "value"] == 1012.0                      # last
        assert sub.loc["bud_cumulative_subsidence_r1_20000930",
                       "value"] == pytest.approx(
                           np.linspace(0.1, 2.4, 24)[11])      # last
        assert sub.loc["bud_pumping_r1_20000930",
                       "value"] == pytest.approx(-60.0)        # sum
        # stock continuity across the two water years
        assert sub.loc["bud_beginning_storage_r1_20010930", "value"] == \
            sub.loc["bud_ending_storage_r1_20000930", "value"]

    def test_annual_unsorted_input_stocks_chronological(self):
        from iwfm_io.pest import budget_observations

        dates = pd.date_range("1999-10-31", periods=12, freq="ME")
        frame = pd.DataFrame({
            "location": "r1",
            "component": "Beginning Storage (+)",
            "datetime": dates,
            "value": 100.0 + np.arange(12),
        }).iloc[::-1]                       # reversed order
        out = budget_observations(frame, aggregate="annual")
        assert out["value"].iloc[0] == 100.0   # chronological first

    def test_iwfm_midnight_stamp_buckets_to_prior_wy(self):
        from iwfm_io.pest import budget_observations

        # 9/30 24:00 == 10/01 00:00 -> belongs to the WY ending that 9/30
        df = pd.DataFrame({
            "location": ["r1"], "component": ["pumping"],
            "datetime": pd.to_datetime(["2000-10-01 00:00"]),
            "value": [3.0]})
        out = budget_observations(df, aggregate="annual")
        assert out.loc[0, "datetime"] == pd.Timestamp("2000-09-30")


class TestSlugify:
    def test_examples(self):
        from iwfm_io.pest import slugify_label

        assert slugify_label("Region1 (SR1)") == "region1_sr1"
        assert slugify_label("Deep Percolation") == "deep_percolation"
        assert slugify_label("GAIN FROM STREAM ") == "gain_from_stream"


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestModelSource:
    def test_gw_budget_means_from_adapter(self):
        from iwfm_io import open_model
        from iwfm_io.pest import budget_observations, validate_obs_names

        out = budget_observations(open_model(SAMPLE_MODEL), budget="GW",
                                  aggregate="mean")
        assert len(out) > 0
        assert validate_obs_names(out["obsnme"]) == []
        assert out["value"].notna().any()

    def test_budget_required_for_model_source(self):
        from iwfm_io import open_model
        from iwfm_io.pest import budget_observations

        with pytest.raises(ValueError, match="budget="):
            budget_observations(open_model(SAMPLE_MODEL))

    def test_unknown_budget_lists_available(self):
        from iwfm_io import open_model
        from iwfm_io.pest import budget_observations

        with pytest.raises(KeyError, match="available"):
            budget_observations(open_model(SAMPLE_MODEL), budget="nope")

    def test_direct_hdf_path(self):
        from iwfm_io.pest import budget_observations

        out = budget_observations(SAMPLE_MODEL / "Results" / "GW.hdf",
                                  aggregate="mean")
        assert len(out) > 0
