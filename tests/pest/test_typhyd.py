"""Tests for typical (cluster-average) hydrographs (iwfm_io.pest.typhyd)."""

import numpy as np
import pandas as pd
import pytest


def _spring():
    from iwfm_io.pest import Period
    return [Period("spring", (3, 4, 5), "04/15")]


def _two_well_obs(w2_values=(100.0, 110.0)):
    # w1: spring-2000 avg 15, spring-2001 avg 25 -> mean 20, anomalies -5/+5
    # w2 (default): avgs 100/110 -> mean 105, anomalies -5/+5
    return pd.DataFrame({
        "site": ["w1", "w1", "w1", "w2", "w2"],
        "datetime": pd.to_datetime(
            ["2000-03-10", "2000-04-10", "2001-03-10",
             "2000-03-15", "2001-04-01"]),
        "value": [10.0, 20.0, 25.0, w2_values[0], w2_values[1]],
    })


class TestCore:
    def test_crisp_clusters_demeaned_average(self):
        from iwfm_io.pest import typical_hydrographs

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1", "w2": "c1"},
                                  periods=_spring())
        s = typ.series
        assert s["site"].tolist() == ["c1", "c1"]
        assert s["datetime"].tolist() == [pd.Timestamp("2000-04-15"),
                                          pd.Timestamp("2001-04-15")]
        assert s["value"].tolist() == pytest.approx([-5.0, 5.0])
        assert s["n_wells"].tolist() == [2, 2]
        assert typ.well_means["w1"] == pytest.approx(20.0)
        assert typ.well_means["w2"] == pytest.approx(105.0)

    def test_fuzzy_weights_wide_frame(self):
        from iwfm_io.pest import typical_hydrographs

        # w2 anomalies -10/+10; weights 0.75/0.25 -> -6.25/+6.25
        weights = pd.DataFrame({"c1": [0.75, 0.25]}, index=["w1", "w2"])
        typ = typical_hydrographs(_two_well_obs((100.0, 120.0)), weights,
                                  periods=_spring())
        assert typ.series["value"].tolist() == pytest.approx([-6.25, 6.25])

    def test_long_frame_with_well_id_and_weight(self):
        from iwfm_io.pest import typical_hydrographs

        cl = pd.DataFrame({"well_id": ["w1", "w2"], "cluster": ["c1", "c1"],
                           "weight": [0.75, 0.25]})
        typ = typical_hydrographs(_two_well_obs((100.0, 120.0)), cl,
                                  periods=_spring())
        assert typ.series["value"].tolist() == pytest.approx([-6.25, 6.25])

    def test_demean_false_gives_absolute_average(self):
        from iwfm_io.pest import typical_hydrographs

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1"},
                                  periods=_spring(), demean=False)
        assert typ.series["value"].tolist() == pytest.approx([15.0, 25.0])

    def test_wells_table(self):
        from iwfm_io.pest import typical_hydrographs

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1", "w2": "c1"},
                                  periods=_spring())
        w = typ.wells.set_index("site")
        assert sorted(typ.wells["site"]) == ["w1", "w2"]
        assert w.loc["w1", "n_slots"] == 2
        assert (typ.wells["cluster"] == "c1").all()


class TestSlotting:
    def test_december_joins_following_winter(self):
        from iwfm_io.pest import typical_hydrographs

        obs = pd.DataFrame({
            "site": ["w1", "w1"],
            "datetime": pd.to_datetime(["2000-12-20", "2001-01-10"]),
            "value": [5.0, 7.0],
        })
        typ = typical_hydrographs(obs, {"w1": "c1"})   # quarterly default
        # one winter slot, stamped at the 2001 representative date
        assert typ.series["datetime"].tolist() == [pd.Timestamp("2001-01-15")]
        assert typ.well_means["w1"] == pytest.approx(6.0)

    def test_min_obs_drops_sparse_slots(self):
        from iwfm_io.pest import typical_hydrographs

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1"},
                                  periods=_spring(), min_obs=2)
        # only spring-2000 has 2 obs for w1; the single slot demeans to 0
        assert typ.series["datetime"].tolist() == [pd.Timestamp("2000-04-15")]
        assert typ.series["value"].tolist() == pytest.approx([0.0])

    def test_start_end_trim_slots(self):
        from iwfm_io.pest import typical_hydrographs

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1", "w2": "c1"},
                                  periods=_spring(), end="2000-06-30")
        assert typ.series["datetime"].tolist() == [pd.Timestamp("2000-04-15")]

    def test_excluded_rows_dropped(self):
        from iwfm_io.pest import typical_hydrographs

        obs = _two_well_obs()
        obs["excluded"] = [False, True, False, False, False]
        typ = typical_hydrographs(obs, {"w1": "c1"}, periods=_spring())
        # w1 spring-2000 avg becomes 10 (the 20 is excluded); mean 17.5
        assert typ.series["value"].tolist() == pytest.approx([-7.5, 7.5])

    def test_empty_input(self):
        from iwfm_io.pest import typical_hydrographs

        obs = _two_well_obs().iloc[0:0]
        typ = typical_hydrographs(obs, {"w1": "c1"})
        assert len(typ.series) == 0
        assert list(typ.series.columns) == ["site", "datetime", "period",
                                            "value", "n_wells"]


class TestPairing:
    def test_obs_and_sim_align_point_for_point(self):
        from iwfm_io.pest import (match_sim_to_obs, residual_stats,
                                  typical_hydrographs)

        obs = _two_well_obs()
        sim = obs.assign(value=obs["value"] + 2.0)   # constant offset
        clusters = {"w1": "c1", "w2": "c1"}
        typ_obs = typical_hydrographs(obs, clusters, periods=_spring())
        typ_sim = typical_hydrographs(sim, clusters, periods=_spring())
        paired = match_sim_to_obs(typ_sim.series, typ_obs.series,
                                  method="nearest")
        # de-meaning removes the offset entirely
        st = residual_stats(paired)
        assert st["rmse"].iloc[0] == pytest.approx(0.0, abs=1e-12)

    def test_series_feeds_write_smp(self, tmp_path):
        from iwfm_io.pest import read_smp, typical_hydrographs, write_smp

        typ = typical_hydrographs(_two_well_obs(), {"w1": "c1", "w2": "c1"},
                                  periods=_spring())
        f = tmp_path / "typ.smp"
        write_smp(typ.series, f)
        assert read_smp(f)["value"].tolist() == pytest.approx([-5.0, 5.0])


class TestValidation:
    def test_negative_weight_raises(self):
        from iwfm_io.pest import typical_hydrographs

        cl = pd.DataFrame({"site": ["w1"], "cluster": ["c1"],
                           "weight": [-1.0]})
        with pytest.raises(ValueError, match="non-negative"):
            typical_hydrographs(_two_well_obs(), cl, periods=_spring())

    def test_duplicate_membership_raises(self):
        from iwfm_io.pest import typical_hydrographs

        cl = pd.DataFrame({"site": ["w1", "w1"], "cluster": ["c1", "c1"],
                           "weight": [0.5, 0.5]})
        with pytest.raises(ValueError, match="duplicate"):
            typical_hydrographs(_two_well_obs(), cl, periods=_spring())

    def test_bad_clusters_type_raises(self):
        from iwfm_io.pest import typical_hydrographs

        with pytest.raises(TypeError, match="clusters"):
            typical_hydrographs(_two_well_obs(), ["w1", "w2"])

    def test_bad_min_obs_raises(self):
        from iwfm_io.pest import typical_hydrographs

        with pytest.raises(ValueError, match="min_obs"):
            typical_hydrographs(_two_well_obs(), {"w1": "c1"}, min_obs=0)

    def test_bad_period_rep_raises(self):
        from iwfm_io.pest import Period, typical_hydrographs

        with pytest.raises(ValueError, match="rep"):
            typical_hydrographs(_two_well_obs(), {"w1": "c1"},
                                periods=[Period("bad", (2,), "02/30")])

    def test_well_without_data_warns(self, caplog):
        from iwfm_io.pest import typical_hydrographs

        with caplog.at_level("WARNING"):
            typical_hydrographs(_two_well_obs(),
                                {"w1": "c1", "ghost": "c1"},
                                periods=_spring())
        assert "ghost" in caplog.text
