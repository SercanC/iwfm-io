"""Tests for phi-budget weight balancing (iwfm_io.pest.weights)."""

import numpy as np
import pandas as pd
import pytest


def _obs_data():
    # gwh01: 2 obs w=1 res=(3,4)  -> phi = 9 + 16 = 25
    # gwh02: 1 obs w=2 res=1      -> phi = 4
    # bud:   1 obs w=1 res=5, plus one zero-weight obs -> phi = 25
    return pd.DataFrame({
        "obsnme": ["h1", "h2", "h3", "b1", "b2"],
        "obsval": [10.0, 10.0, 10.0, 5.0, 5.0],
        "weight": [1.0, 1.0, 2.0, 1.0, 0.0],
        "obgnme": ["gwh01", "gwh01", "gwh02", "bud", "bud"],
    })


def _residuals():
    return pd.Series({"h1": 3.0, "h2": 4.0, "h3": 1.0, "b1": 5.0, "b2": 9.9})


class TestBalanceWeights:
    def test_even_split_hits_targets(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(),
                             {"gwh": 100.0, "bud": 50.0})
        rep = wb.report
        # gwh budget split evenly: 50 per group
        assert rep.loc["gwh01", "target"] == pytest.approx(50.0)
        assert rep.loc["gwh01", "factor"] == pytest.approx(np.sqrt(50 / 25))
        assert rep.loc["gwh02", "factor"] == pytest.approx(np.sqrt(50 / 4))
        assert rep.loc["bud", "factor"] == pytest.approx(np.sqrt(50 / 25))
        # realized phi equals target when unclipped
        assert rep.loc["gwh01", "phi_after"] == pytest.approx(50.0)
        assert rep.loc["gwh02", "phi_after"] == pytest.approx(50.0)
        assert rep.loc["bud", "phi_after"] == pytest.approx(50.0)

    def test_proportional_split_preserves_ratio(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(),
                             {"gwh": 100.0, "bud": 50.0},
                             split="proportional")
        rep = wb.report
        # gwh01:gwh02 phi ratio 25:4 preserved in targets
        assert rep.loc["gwh01", "target"] == pytest.approx(100 * 25 / 29)
        assert rep.loc["gwh02", "target"] == pytest.approx(100 * 4 / 29)

    def test_zero_weight_stays_zero(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(),
                             {"gwh": 100.0, "bud": 50.0}, min_weight=0.5)
        w = wb.obs_data.set_index("obsnme")["weight"]
        assert w["b2"] == 0.0

    def test_weight_clipping_moves_phi_off_target(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(), {"gwh": 10000.0},
                             max_weight=2.0)
        rep = wb.report
        w = wb.obs_data.set_index("obsnme")["weight"]
        assert (w[["h1", "h2", "h3"]] <= 2.0).all()
        assert rep.loc["gwh01", "phi_after"] < rep.loc["gwh01", "target"]

    def test_unmatched_group_unchanged(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(), {"gwh": 100.0})
        assert wb.report.loc["bud", "factor"] == 1.0
        assert pd.isna(wb.report.loc["bud", "pattern"])
        w = wb.obs_data.set_index("obsnme")["weight"]
        assert w["b1"] == 1.0

    def test_pattern_matching_no_group_raises(self):
        from iwfm_io.pest import balance_weights

        with pytest.raises(ValueError, match="matched no observation group"):
            balance_weights(_obs_data(), _residuals(), {"nope": 1.0})

    def test_overlapping_patterns_raise(self):
        from iwfm_io.pest import balance_weights

        with pytest.raises(ValueError, match="two budget patterns"):
            balance_weights(_obs_data(), _residuals(),
                            {"gwh": 100.0, "gwh01": 50.0})

    def test_regex_pattern(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(),
                             {r"gwh\d+": 100.0})
        assert set(wb.report[wb.report["pattern"].notna()].index) == {
            "gwh01", "gwh02"}

    def test_missing_residuals_for_weighted_obs_raise(self):
        from iwfm_io.pest import balance_weights

        res = _residuals().drop("h1")
        with pytest.raises(ValueError, match="residuals missing"):
            balance_weights(_obs_data(), res, {"gwh": 100.0})

    def test_zero_phi_group_left_unchanged(self, caplog):
        from iwfm_io.pest import balance_weights

        res = _residuals()
        res[["h1", "h2"]] = 0.0
        with caplog.at_level("WARNING"):
            wb = balance_weights(_obs_data(), res, {"gwh01": 100.0})
        assert wb.report.loc["gwh01", "factor"] == 1.0
        assert "zero phi" in caplog.text

    def test_budget_split_only_among_scalable_groups(self, caplog):
        from iwfm_io.pest import balance_weights

        # gwh01 has zero phi -> gwh02 absorbs the whole category budget
        res = _residuals()
        res[["h1", "h2"]] = 0.0
        with caplog.at_level("WARNING"):
            wb = balance_weights(_obs_data(), res, {"gwh": 100.0})
        rep = wb.report
        assert rep.loc["gwh02", "target"] == pytest.approx(100.0)
        assert rep.loc["gwh02", "phi_after"] == pytest.approx(100.0)
        assert rep.loc["gwh01", "factor"] == 1.0

    def test_rei_frame_accepted(self, ies_dir):
        from iwfm_io.pest import balance_weights, read_rei
        from tests.pest.conftest import CASE

        rei = read_rei(ies_dir / f"{CASE}.2.base.rei")
        obs = pd.DataFrame({
            "obsnme": rei["name"], "weight": rei["weight"],
            "obgnme": rei["group"],
        })
        wb = balance_weights(obs, rei, {"gwh01": 10.0, "bud": 10.0})
        assert wb.report["phi_after"].sum() == pytest.approx(20.0)

    def test_shares_sum_to_one(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(),
                             {"gwh": 100.0, "bud": 50.0})
        assert wb.report["share_before"].sum() == pytest.approx(1.0)
        assert wb.report["share_after"].sum() == pytest.approx(1.0)

    def test_extra_columns_pass_through(self):
        from iwfm_io.pest import balance_weights

        wb = balance_weights(_obs_data(), _residuals(), {"gwh": 100.0})
        assert "obsval" in wb.obs_data.columns
        pd.testing.assert_series_equal(
            wb.obs_data["obsval"], _obs_data()["obsval"])


class TestBalancePstWeights:
    def test_requires_pyemu(self, tmp_path):
        try:
            import pyemu  # noqa: F401
            pytest.skip("pyemu installed")
        except ImportError:
            pass
        from iwfm_io.pest import balance_pst_weights

        with pytest.raises(RuntimeError, match="pyemu"):
            balance_pst_weights(tmp_path / "x.pst", {"gwh": 1.0})
