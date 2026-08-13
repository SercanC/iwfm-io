"""Tests for pilot-point kriging (iwfm_io.pest.pilot_points)."""

import numpy as np
import pandas as pd
import pytest


def _pps():
    return pd.DataFrame({
        "pp_id": ["pp0001", "pp0002", "pp0003", "pp0004"],
        "x": [0.0, 100.0, 0.0, 100.0],
        "y": [0.0, 0.0, 100.0, 100.0],
        "zone": ["a", "a", "b", "b"],
    })


def _targets():
    return pd.DataFrame({
        "node_id": [1, 2, 3],
        "x": [0.0, 50.0, 90.0],
        "y": [0.0, 50.0, 10.0],
        "zone": ["a", "a", "a"],
    })


class TestKrigingProperties:
    def test_weights_sum_to_one(self):
        from iwfm_io.pest import ExpVariogram, compute_kriging_factors

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0))
        sums = fac.groupby("node_id")["weight"].sum()
        assert sums.values == pytest.approx([1.0] * 3, abs=1e-9)

    def test_exact_at_pilot_point(self):
        from iwfm_io.pest import (ExpVariogram, apply_kriging_factors,
                                  compute_kriging_factors)

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0))
        vals = pd.Series({"pp0001": 10.0, "pp0002": 20.0,
                          "pp0003": 30.0, "pp0004": 40.0})
        out = apply_kriging_factors(fac, vals)
        # node 1 coincides with pp0001
        assert out[1] == pytest.approx(10.0, abs=1e-8)

    def test_constant_field_reproduced(self):
        from iwfm_io.pest import (SphVariogram, apply_kriging_factors,
                                  compute_kriging_factors)

        fac = compute_kriging_factors(_pps(), _targets(),
                                      SphVariogram(a=150.0))
        out = apply_kriging_factors(
            fac, {p: 7.5 for p in _pps()["pp_id"]})
        assert out.values == pytest.approx([7.5] * 3)

    def test_log_kriging(self):
        from iwfm_io.pest import (GauVariogram, apply_kriging_factors,
                                  compute_kriging_factors)

        fac = compute_kriging_factors(_pps(), _targets(),
                                      GauVariogram(a=200.0))
        vals = {"pp0001": 1.0, "pp0002": 100.0, "pp0003": 10.0,
                "pp0004": 10.0}
        out = apply_kriging_factors(fac, vals, log=True)
        # exact at the pilot point even in log space
        assert out[1] == pytest.approx(1.0, abs=1e-6)
        assert (out > 0).all()
        with pytest.raises(ValueError, match="positive"):
            apply_kriging_factors(fac, {**vals, "pp0001": -1.0}, log=True)

    def test_anisotropy_pulls_along_bearing(self):
        from iwfm_io.pest import ExpVariogram, compute_kriging_factors

        # bearing 0 (north), anisotropy 5: the north-south neighbor
        # should carry more weight than the equally distant east one
        pps = pd.DataFrame({
            "pp_id": ["east", "north"],
            "x": [60.0, 0.0], "y": [0.0, 60.0]})
        tg = pd.DataFrame({"node_id": [1], "x": [0.0], "y": [0.0]})
        fac = compute_kriging_factors(
            pps, tg, ExpVariogram(a=100.0, anisotropy=5.0, bearing=0.0))
        w = fac.set_index("pp_id")["weight"]
        assert w["north"] > w["east"]


class TestSelectionOptions:
    def test_max_points_limits_neighbors(self):
        from iwfm_io.pest import ExpVariogram, compute_kriging_factors

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0), max_points=2)
        assert (fac.groupby("node_id").size() == 2).all()

    def test_search_radius(self):
        from iwfm_io.pest import ExpVariogram, compute_kriging_factors

        fac = compute_kriging_factors(_pps(), _targets().iloc[[0]],
                                      ExpVariogram(a=200.0),
                                      search_radius=10.0)
        assert fac["pp_id"].tolist() == ["pp0001"]
        with pytest.raises(ValueError, match="no pilot point"):
            compute_kriging_factors(_pps(), _targets().iloc[[1]],
                                    ExpVariogram(a=200.0),
                                    search_radius=1.0)

    def test_same_zone_only(self):
        from iwfm_io.pest import ExpVariogram, compute_kriging_factors

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0),
                                      same_zone_only=True)
        used = set(fac["pp_id"])
        assert used <= {"pp0001", "pp0002"}      # zone 'a' only
        with pytest.raises(ValueError, match="zone"):
            compute_kriging_factors(_pps().drop(columns="zone"),
                                    _targets(), ExpVariogram(a=200.0),
                                    same_zone_only=True)

    def test_factors_csv_round_trip(self, tmp_path):
        from iwfm_io.pest import (ExpVariogram, apply_kriging_factors,
                                  compute_kriging_factors)

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0))
        f = tmp_path / "factors.csv"
        fac.to_csv(f, index=False)
        back = pd.read_csv(f)
        vals = {p: float(i + 1) for i, p in enumerate(_pps()["pp_id"])}
        pd.testing.assert_series_equal(
            apply_kriging_factors(fac, vals),
            apply_kriging_factors(back, vals))

    def test_missing_pp_value_raises(self):
        from iwfm_io.pest import (ExpVariogram, apply_kriging_factors,
                                  compute_kriging_factors)

        fac = compute_kriging_factors(_pps(), _targets(),
                                      ExpVariogram(a=200.0))
        with pytest.raises(KeyError, match="pp_values missing"):
            apply_kriging_factors(fac, {"pp0001": 1.0})


class TestPlacement:
    def test_grid_clipped_to_footprint(self):
        from iwfm_io.pest import place_pilot_points_grid

        rng = np.random.default_rng(3)
        nodes = pd.DataFrame({
            "x": rng.uniform(0, 1000, 300),
            "y": rng.uniform(0, 500, 300)})
        pps = place_pilot_points_grid(nodes, spacing=200.0)
        assert len(pps) > 0
        assert pps["pp_id"].is_unique
        # every pilot point is within `spacing` of some node
        for _, p in pps.iterrows():
            d = np.hypot(nodes["x"] - p["x"], nodes["y"] - p["y"]).min()
            assert d <= 200.0

    def test_zones_inherited_from_nearest_node(self):
        from iwfm_io.pest import place_pilot_points_grid

        nodes = pd.DataFrame({"x": [0.0, 1000.0], "y": [0.0, 0.0]})
        zones = pd.Series(["west", "east"])
        pps = place_pilot_points_grid(nodes, spacing=500.0, zones=zones,
                                      buffer=100.0)
        z = pps.set_index("x")["zone"]
        assert z[0.0] == "west" and z[1000.0] == "east"

    def test_too_tight_raises(self):
        from iwfm_io.pest import place_pilot_points_grid

        # grid corners land 10 units from every node; buffer 1 rejects all
        nodes = pd.DataFrame({"x": [0.0, 10.0], "y": [10.0, 0.0]})
        with pytest.raises(ValueError, match="no pilot points"):
            place_pilot_points_grid(nodes, spacing=20.0, buffer=1.0)
