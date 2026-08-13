"""Tests for the residual/calibration statistics engine (iwfm_io.pest.stats)."""

import numpy as np
import pandas as pd
import pytest

from tests.pest.conftest import CASE  # noqa: F401


def _frame(obs, sim, **cols):
    df = pd.DataFrame({"observed": obs, "simulated": sim})
    for k, v in cols.items():
        df[k] = v
    return df


class TestResidualStats:
    def test_perfect_fit(self):
        from iwfm_io.pest import residual_stats

        out = residual_stats(_frame([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]))
        row = out.iloc[0]
        assert row["rmse"] == 0
        assert row["mean_res"] == 0
        assert row["r2"] == pytest.approx(1.0)
        assert row["nse"] == pytest.approx(1.0)
        assert row["kge"] == pytest.approx(1.0)
        assert row["n"] == 3

    def test_known_values_constant_simulation(self):
        from iwfm_io.pest import residual_stats

        # obs 1,2,3 vs constant sim 2: residuals 1-2,2-2,3-2 = -1,0,1
        out = residual_stats(_frame([1.0, 2.0, 3.0], [2.0, 2.0, 2.0]))
        row = out.iloc[0]
        assert row["mean_res"] == pytest.approx(0.0)
        assert row["med_res"] == pytest.approx(0.0)
        assert row["mean_abs_res"] == pytest.approx(2 / 3)
        assert row["max_abs_res"] == pytest.approx(1.0)
        assert row["rmse"] == pytest.approx(np.sqrt(2 / 3))
        assert row["nse"] == pytest.approx(0.0)  # as bad as predicting the mean
        # constant simulation has zero variance -> correlation undefined
        assert np.isnan(row["r2"])
        assert np.isnan(row["kge"])

    def test_residual_sign_convention(self):
        from iwfm_io.pest import residual_stats

        # PEST convention: residual = observed - simulated
        out = residual_stats(_frame([1.0, 1.0], [3.0, 3.0]))
        assert out.iloc[0]["mean_res"] == pytest.approx(-2.0)

    def test_grouped_by_two_columns(self):
        from iwfm_io.pest import residual_stats

        df = _frame(
            [1.0, 2.0, 10.0, 20.0], [1.0, 2.0, 12.0, 18.0],
            obs_type=["gwh", "gwh", "stf", "stf"],
            location=["w1", "w1", "g1", "g1"],
        )
        out = residual_stats(df, by=["obs_type", "location"])
        assert out.loc[("gwh", "w1"), "rmse"] == 0
        assert out.loc[("stf", "g1"), "rmse"] == pytest.approx(2.0)
        assert out.loc[("stf", "g1"), "mean_res"] == pytest.approx(0.0)

    def test_nan_rows_dropped(self):
        from iwfm_io.pest import residual_stats

        out = residual_stats(_frame([1.0, np.nan, 3.0], [1.0, 2.0, np.nan]))
        assert out.iloc[0]["n"] == 1

    def test_weight_adds_phi(self):
        from iwfm_io.pest import residual_stats

        df = _frame([1.0, 2.0, 3.0], [2.0, 2.0, 2.0], w=[2.0, 2.0, 2.0])
        out = residual_stats(df, weight="w")
        # phi = sum((w*res)^2) = 4 + 0 + 4
        assert out.iloc[0]["phi"] == pytest.approx(8.0)

    def test_single_sample_group(self):
        from iwfm_io.pest import residual_stats

        df = _frame([5.0], [4.0], g=["a"])
        out = residual_stats(df, by="g")
        assert out.loc["a", "rmse"] == pytest.approx(1.0)
        assert np.isnan(out.loc["a", "r2"])
        assert np.isnan(out.loc["a", "nse"])


class TestReiStats:
    def test_from_rei_path(self, ies_dir):
        from iwfm_io.pest import rei_stats

        out = rei_stats(ies_dir / f"{CASE}.2.base.rei")
        assert "phi" in out.columns
        assert out.loc["bud", "rmse"] == pytest.approx(1.0)
        assert out.loc["gwh01", "mean_res"] == pytest.approx(-22.67)

    def test_weighted_only_filters(self, ies_dir):
        from iwfm_io.pest import read_rei, rei_stats

        rei = read_rei(ies_dir / f"{CASE}.2.base.rei")
        rei.loc[rei["group"] == "gwh01", "weight"] = 0.0
        out = rei_stats(rei, weighted_only=True)
        assert "gwh01" not in out.index
        assert "bud" in out.index

    def test_summary_row(self, ies_dir):
        from iwfm_io.pest import rei_stats

        out = rei_stats(ies_dir / f"{CASE}.2.base.rei", by=None)
        assert list(out.index) == ["all"]
        assert out.iloc[0]["n"] == 2


class TestIesStats:
    BY = {"gwh_w1_20001031": "gwh", "gwh_w2_20001031": "gwh",
          "bud_sr01": "bud"}

    def test_default_observed_from_obs_plus_noise(self, ies_dir):
        from iwfm_io.pest import ies_stats, load_ies_ensembles

        out = ies_stats(load_ies_ensembles(ies_dir), by=self.BY)
        assert out.index.names == ["iteration", "real_name", "group"]
        assert sorted(out.index.get_level_values("iteration").unique()) == [0, 2]
        # iter 2, real "0": obs (100,200,300) sim (102,200,300)
        assert out.loc[(2, "0", "gwh"), "rmse"] == pytest.approx(np.sqrt(2.0))
        assert out.loc[(2, "0", "gwh"), "mean_res"] == pytest.approx(-1.0)
        assert out.loc[(2, "base", "bud"), "rmse"] == pytest.approx(1.0)

    def test_single_iteration_and_callable_by(self, ies_dir):
        from iwfm_io.pest import ies_stats, load_ies_ensembles

        out = ies_stats(load_ies_ensembles(ies_dir), iterations=2,
                        by=lambda n: n.split("_")[0])
        assert set(out.index.get_level_values("group")) == {"gwh", "bud"}
        assert set(out.index.get_level_values("iteration")) == {2}

    def test_explicit_observed_series(self, ies_dir):
        from iwfm_io.pest import ies_stats, load_ies_ensembles

        observed = pd.Series(
            {"gwh_w1_20001031": 102.0, "gwh_w2_20001031": 200.0,
             "bud_sr01": 300.0})
        out = ies_stats(load_ies_ensembles(ies_dir), observed=observed,
                        iterations=2)
        # real "0" simulates exactly these values -> perfect fit
        assert out.loc[(2, "0", "all"), "rmse"] == 0

    def test_missing_observed_raises(self, ies_dir):
        from iwfm_io.pest import ies_stats, load_ies_ensembles

        (ies_dir / f"{CASE}.obs+noise.csv").unlink()
        with pytest.raises(ValueError, match="observed"):
            ies_stats(load_ies_ensembles(ies_dir))

    def test_consistent_with_long_form(self, ies_dir):
        from iwfm_io.pest import ies_stats, load_ies_ensembles, residual_stats

        r = load_ies_ensembles(ies_dir)
        ens = ies_stats(r, by=self.BY, iterations=2)
        observed = r.obs_plus_noise().loc["base"]
        # rebuild the same comparison in long form for one realization
        sim = r.obs(2).loc["base"]
        long = pd.DataFrame({
            "observed": observed, "simulated": sim,
            "group": pd.Series(self.BY),
        }).dropna()
        ref = residual_stats(long, by="group")
        for g in ("gwh", "bud"):
            for m in ("rmse", "mean_res", "nse", "n"):
                a, b = ens.loc[(2, "base", g), m], ref.loc[g, m]
                assert (np.isnan(a) and np.isnan(b)) or a == pytest.approx(b)
