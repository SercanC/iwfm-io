"""Tests for sim-to-obs time matching (iwfm_io.pest.sim2obs)."""

import numpy as np
import pandas as pd
import pytest


def _sim_long():
    # site w1: linear ramp 100..103 over four month-ends
    dates = pd.to_datetime(
        ["2000-01-31", "2000-02-29", "2000-03-31", "2000-04-30"])
    return pd.DataFrame({
        "site": ["w1"] * 4 + ["w2"] * 4,
        "datetime": list(dates) * 2,
        "value": [100.0, 101.0, 102.0, 103.0, 50.0, 55.0, 60.0, 65.0],
    })


def _obs(site, when, value=0.0):
    return pd.DataFrame({
        "site": [site], "datetime": pd.to_datetime([when]),
        "value": [value]})


class TestLinear:
    def test_exact_time_matches_exactly(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("w1", "2000-02-29", 99.0))
        assert out.loc[0, "simulated"] == pytest.approx(101.0)
        assert out.loc[0, "observed"] == pytest.approx(99.0)

    def test_interpolates_between_samples(self):
        from iwfm_io.pest import match_sim_to_obs

        # midpoint of Feb 29 -> Mar 31 (31 days): Mar 15.5 -> 101.5
        out = match_sim_to_obs(
            _sim_long(), _obs("w1", "2000-03-15 12:00"))
        assert out.loc[0, "simulated"] == pytest.approx(101.5, abs=1e-6)

    def test_never_extrapolates(self):
        from iwfm_io.pest import match_sim_to_obs

        obs = pd.concat([_obs("w1", "1999-12-15"),
                         _obs("w1", "2000-06-15")], ignore_index=True)
        out = match_sim_to_obs(_sim_long(), obs)
        assert out["simulated"].isna().all()

    def test_max_gap_blocks_wide_brackets(self):
        from iwfm_io.pest import match_sim_to_obs

        # remove Feb/Mar: bracketing points Jan 31 and Apr 30 (90 days)
        sim = _sim_long()
        sim = sim[~((sim.site == "w1")
                    & sim.datetime.isin(pd.to_datetime(
                        ["2000-02-29", "2000-03-31"])))]
        obs = _obs("w1", "2000-03-01")
        assert np.isnan(match_sim_to_obs(sim, obs, max_gap="30D")
                        .loc[0, "simulated"])
        assert not np.isnan(match_sim_to_obs(sim, obs, max_gap="90D")
                            .loc[0, "simulated"])

    def test_exact_sample_passes_gap_check(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("w1", "2000-03-31"),
                               max_gap="1D")
        assert out.loc[0, "simulated"] == pytest.approx(102.0)


class TestExtrapolate:
    def test_endpoint_values_within_window(self):
        from iwfm_io.pest import match_sim_to_obs

        # w1 spans Jan 31 .. Apr 30 (100 .. 103)
        obs = pd.concat([_obs("w1", "2000-01-10"),    # 21 d before start
                         _obs("w1", "2000-05-15")],   # 15 d after end
                        ignore_index=True)
        out = match_sim_to_obs(_sim_long(), obs, extrapolate="30D")
        assert out.loc[0, "simulated"] == pytest.approx(100.0)
        assert out.loc[1, "simulated"] == pytest.approx(103.0)

    def test_beyond_window_stays_nan(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("w1", "2000-06-15"),
                               extrapolate="30D")
        assert np.isnan(out.loc[0, "simulated"])

    def test_interior_gap_still_guarded(self):
        from iwfm_io.pest import match_sim_to_obs

        # remove Feb/Mar: interior 90-day gap; obs past the end
        sim = _sim_long()
        sim = sim[~((sim.site == "w1")
                    & sim.datetime.isin(pd.to_datetime(
                        ["2000-02-29", "2000-03-31"])))]
        obs = pd.concat([_obs("w1", "2000-03-01"),    # inside the gap
                         _obs("w1", "2000-06-15")],   # 46 d past the end
                        ignore_index=True)
        out = match_sim_to_obs(sim, obs, max_gap="30D", extrapolate="60D")
        assert np.isnan(out.loc[0, "simulated"])
        assert out.loc[1, "simulated"] == pytest.approx(103.0)

    def test_error_with_nearest(self):
        from iwfm_io.pest import match_sim_to_obs

        with pytest.raises(ValueError, match="extrapolate"):
            match_sim_to_obs(_sim_long(), _obs("w1", "2000-03-15"),
                             method="nearest", extrapolate="30D")


class TestNearest:
    def test_nearest_value(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("w1", "2000-03-05"),
                               method="nearest")
        # Mar 5 is closer to Feb 29 than Mar 31
        assert out.loc[0, "simulated"] == pytest.approx(101.0)

    def test_nearest_respects_max_gap(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("w1", "2000-03-15"),
                               method="nearest", max_gap="3D")
        assert np.isnan(out.loc[0, "simulated"])

    def test_bad_method_raises(self):
        from iwfm_io.pest import match_sim_to_obs

        with pytest.raises(ValueError, match="method"):
            match_sim_to_obs(_sim_long(), _obs("w1", "2000-03-15"),
                             method="cubic")


class TestInputsAndSites:
    def test_wide_sim_accepted(self):
        from iwfm_io.pest import match_sim_to_obs

        wide = _sim_long().pivot(index="datetime", columns="site",
                                 values="value")
        out = match_sim_to_obs(wide, _obs("w2", "2000-02-29"))
        assert out.loc[0, "simulated"] == pytest.approx(55.0)

    def test_unknown_site_dropped_with_warning(self, caplog):
        from iwfm_io.pest import match_sim_to_obs

        obs = pd.concat([_obs("w1", "2000-02-29"),
                         _obs("nope", "2000-02-29")], ignore_index=True)
        with caplog.at_level("WARNING"):
            out = match_sim_to_obs(_sim_long(), obs)
        assert set(out["site"]) == {"w1"}
        assert "nope" in caplog.text

    def test_empty_result_when_no_common_sites(self):
        from iwfm_io.pest import match_sim_to_obs

        out = match_sim_to_obs(_sim_long(), _obs("nope", "2000-02-29"))
        assert len(out) == 0
        assert list(out.columns) == ["site", "datetime", "observed",
                                     "simulated"]

    def test_feeds_residual_stats(self):
        from iwfm_io.pest import match_sim_to_obs, residual_stats

        obs = pd.DataFrame({
            "site": ["w1", "w1", "w2"],
            "datetime": pd.to_datetime(
                ["2000-01-31", "2000-02-29", "2000-01-31"]),
            "value": [101.0, 102.0, 51.0],
        })
        paired = match_sim_to_obs(_sim_long(), obs)
        st = residual_stats(paired, by="site")
        assert st.loc["w1", "mean_res"] == pytest.approx(1.0)
        assert st.loc["w2", "mean_res"] == pytest.approx(1.0)


class TestResampleMonthEnd:
    def test_mean_by_month(self):
        from iwfm_io.pest import resample_month_end

        df = pd.DataFrame({
            "site": ["w1"] * 4,
            "datetime": pd.to_datetime(
                ["2000-01-05", "2000-01-25", "2000-02-10", "2000-02-20"]),
            "value": [1.0, 3.0, 10.0, 20.0],
        })
        out = resample_month_end(df)
        assert out.loc[0, "value"] == pytest.approx(2.0)
        assert out.loc[0, "datetime"] == pd.Timestamp("2000-01-31")
        assert out.loc[1, "value"] == pytest.approx(15.0)

    def test_iwfm_24h_convention(self):
        from iwfm_io.pest import resample_month_end

        # 10/31/2000_24:00 parses as 11/01 00:00 — belongs to October
        df = pd.DataFrame({
            "site": ["w1"], "datetime": pd.to_datetime(["2000-11-01 00:00"]),
            "value": [7.0]})
        out = resample_month_end(df)
        assert out.loc[0, "datetime"] == pd.Timestamp("2000-10-31")
        # and with the convention off it stays in November
        out2 = resample_month_end(df, iwfm_convention=False)
        assert out2.loc[0, "datetime"] == pd.Timestamp("2000-11-30")

    def test_other_aggregations(self):
        from iwfm_io.pest import resample_month_end

        df = pd.DataFrame({
            "site": ["w1"] * 3,
            "datetime": pd.to_datetime(
                ["2000-01-05", "2000-01-15", "2000-01-25"]),
            "value": [1.0, 5.0, 3.0],
        })
        assert resample_month_end(df, how="max").loc[0, "value"] == 5.0
        assert resample_month_end(df, how="last").loc[0, "value"] == 3.0
