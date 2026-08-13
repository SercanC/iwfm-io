"""Tests for derived observation types (iwfm_io.pest.derived)."""

import numpy as np
import pandas as pd
import pytest


def _heads():
    """w1: monthly heads Jan 2000 .. Dec 2001, value = linear +1/month
    with a +5 bump every March."""
    dates = pd.date_range("2000-01-31", periods=24, freq="ME")
    vals = np.arange(24, dtype=float)
    vals[dates.month == 3] += 5.0
    return pd.DataFrame({"site": "w1", "datetime": dates, "value": vals})


class TestHeadChanges:
    def test_successive(self):
        from iwfm_io.pest import head_changes

        out = head_changes(_heads(), "successive")
        assert len(out) == 23                       # first month has no prior
        # Feb->Mar jump: +1 +5 bump = +6; Mar->Apr: +1 -5 = -4
        by_t = out.set_index("datetime")["value"]
        assert by_t[pd.Timestamp("2000-03-31")] == pytest.approx(6.0)
        assert by_t[pd.Timestamp("2000-04-30")] == pytest.approx(-4.0)
        assert by_t[pd.Timestamp("2000-06-30")] == pytest.approx(1.0)

    def test_successive_max_gap(self):
        from iwfm_io.pest import head_changes

        df = _heads().iloc[[0, 1, 6]]               # gap Feb -> Jul
        out = head_changes(df, "successive", max_gap="45D")
        assert len(out) == 1                        # only Jan->Feb survives

    def test_seasonal_march_over_march(self):
        from iwfm_io.pest import head_changes

        out = head_changes(_heads(), "seasonal", month=3)
        # Mar2001 (idx 14 +5) - Mar2000 (idx 2 +5) = 12
        assert len(out) == 1
        assert out.loc[0, "value"] == pytest.approx(12.0)
        assert out.loc[0, "datetime"] == pd.Timestamp("2001-03-31")

    def test_seasonal_requires_consecutive_years(self):
        from iwfm_io.pest import head_changes

        df = _heads()
        df = df[df["datetime"].dt.year != 2001]     # only 2000 left
        assert len(head_changes(df, "seasonal", month=3)) == 0

    def test_drawdown_spring_minus_fall(self):
        from iwfm_io.pest import head_changes

        out = head_changes(_heads(), "drawdown", from_month=3, to_month=9)
        # 2000: Mar (2+5) - Sep (8) = -1 ; stamped at the Sep record
        by_y = out.set_index(out["datetime"].dt.year)["value"]
        assert by_y[2000] == pytest.approx(-1.0)
        assert by_y[2001] == pytest.approx(-1.0)
        assert out["datetime"].dt.month.unique().tolist() == [9]

    def test_multiple_values_in_month_averaged(self):
        from iwfm_io.pest import head_changes

        df = pd.DataFrame({
            "site": "w1",
            "datetime": pd.to_datetime(
                ["2000-01-10", "2000-01-20", "2000-02-15"]),
            "value": [10.0, 12.0, 14.0],
        })
        out = head_changes(df, "successive")
        assert out.loc[0, "value"] == pytest.approx(14.0 - 11.0)

    def test_obs_type_adds_names(self):
        from iwfm_io.pest import head_changes

        out = head_changes(_heads(), "successive", obs_type="del")
        assert out.loc[0, "obsnme"].startswith("del_w1_")

    def test_bad_kind_raises(self):
        from iwfm_io.pest import head_changes

        with pytest.raises(ValueError, match="kind"):
            head_changes(_heads(), "monthly")


class TestPairDifferences:
    def _two_sites(self):
        dates = pd.date_range("2000-01-31", periods=3, freq="ME")
        return pd.DataFrame({
            "site": ["shallow"] * 3 + ["deep"] * 3,
            "datetime": list(dates) * 2,
            "value": [10.0, 11.0, 12.0, 7.0, 9.0, 12.5],
        })

    def test_vertical_head_difference(self):
        from iwfm_io.pest import vertical_head_difference

        out = vertical_head_difference(self._two_sites(),
                                       [("shallow", "deep")])
        assert out["value"].tolist() == pytest.approx([3.0, 2.0, -0.5])
        assert set(out["site"]) == {"shallow_deep"}

    def test_labeled_pairs_and_names(self):
        from iwfm_io.pest import vertical_head_difference

        out = vertical_head_difference(
            self._two_sites(), {"w9pair": ("shallow", "deep")},
            obs_type="vhd")
        assert set(out["site"]) == {"w9pair"}
        assert out.loc[0, "obsnme"] == "vhd_w9pair_20000131"

    def test_missing_site_skipped_with_warning(self, caplog):
        from iwfm_io.pest import vertical_head_difference

        with caplog.at_level("WARNING"):
            out = vertical_head_difference(
                self._two_sites(), [("shallow", "nope")])
        assert len(out) == 0
        assert "absent" in caplog.text

    def test_accretion_downstream_minus_upstream(self):
        from iwfm_io.pest import accretion_depletion

        dates = pd.date_range("2000-01-31", periods=2, freq="ME")
        flows = pd.DataFrame({
            "site": ["up"] * 2 + ["down"] * 2,
            "datetime": list(dates) * 2,
            "value": [100.0, 100.0, 130.0, 90.0],
        })
        out = accretion_depletion(flows, [("up", "down")])
        assert out["value"].tolist() == pytest.approx([30.0, -10.0])
        assert set(out["site"]) == {"up_down"}     # upstream-first label

    def test_no_common_timestamps_skipped(self, caplog):
        from iwfm_io.pest import vertical_head_difference

        df = pd.DataFrame({
            "site": ["a", "b"],
            "datetime": pd.to_datetime(["2000-01-31", "2000-02-29"]),
            "value": [1.0, 2.0],
        })
        with caplog.at_level("WARNING"):
            out = vertical_head_difference(df, [("a", "b")])
        assert len(out) == 0
        assert "common" in caplog.text


class TestLongTermStats:
    def test_mean_and_min_n(self):
        from iwfm_io.pest import long_term_stats

        df = pd.DataFrame({
            "site": ["a"] * 3 + ["b"],
            "datetime": pd.to_datetime(
                ["2000-01-31", "2000-02-29", "2000-03-31", "2000-01-31"]),
            "value": [1.0, 2.0, 3.0, 99.0],
        })
        out = long_term_stats(df, min_n=2)
        assert out.set_index("site").loc["a", "value"] == pytest.approx(2.0)
        assert "b" not in set(out["site"])
        assert out["datetime"].isna().all()

    def test_dateless_names(self):
        from iwfm_io.pest import long_term_stats

        df = pd.DataFrame({
            "site": ["a"], "datetime": pd.to_datetime(["2000-01-31"]),
            "value": [1.0]})
        out = long_term_stats(df, obs_type="ltm")
        assert out.loc[0, "obsnme"] == "ltm_a"

    def test_other_stat(self):
        from iwfm_io.pest import long_term_stats

        df = pd.DataFrame({
            "site": ["a"] * 3,
            "datetime": pd.date_range("2000-01-31", periods=3, freq="ME"),
            "value": [1.0, 5.0, 3.0]})
        assert long_term_stats(df, stat="median").loc[0, "value"] == 3.0


class TestObsSimSymmetry:
    def test_same_transform_both_sides_pairs_cleanly(self):
        from iwfm_io.pest import head_changes, residual_stats

        obs = _heads()
        sim = _heads()
        sim["value"] = sim["value"] + 0.5           # constant bias
        d_obs = head_changes(obs, "successive")
        d_sim = head_changes(sim, "successive")
        paired = d_obs.merge(d_sim, on=["site", "datetime"],
                             suffixes=("_obs", "_sim"))
        st = residual_stats(paired, by="site", observed="value_obs",
                            simulated="value_sim")
        # constant bias cancels in successive differences
        assert st.loc["w1", "rmse"] == pytest.approx(0.0, abs=1e-12)
