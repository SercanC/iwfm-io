"""Tests for constrained reparameterization + T2P hooks (iwfm_io.pest.reparam)."""

import numpy as np
import pandas as pd
import pytest


def _diamond():
    from iwfm_io.pest import RatioChain

    c = RatioChain()
    c.add_parameter("kxc", bounds=(20.0, 450.0), transform="log")
    c.add_parameter("dt", bounds=(0.7, 4.0))
    c.add_parameter("pa", bounds=(0.05, 0.95))
    c.add_parameter("pb", bounds=(0.05, 0.95))
    c.add_derived("kmax_coarse", "kxc")
    c.add_derived("kmin_coarse", "kxc * 10**(-pa*dt)")
    c.add_derived("kmax_fine", "kxc * 10**(-pb*dt)")
    c.add_derived("kmin_fine", "kxc * 10**(-dt)")
    return c


class TestRatioChain:
    def test_evaluate_diamond(self):
        c = _diamond()
        out = c.evaluate({"kxc": 100.0, "dt": 2.0, "pa": 0.5, "pb": 0.25})
        assert out["kmax_coarse"] == pytest.approx(100.0)
        assert out["kmin_coarse"] == pytest.approx(100.0 * 10**-1.0)
        assert out["kmax_fine"] == pytest.approx(100.0 * 10**-0.5)
        assert out["kmin_fine"] == pytest.approx(100.0 * 10**-2.0)

    def test_diamond_ordering_guaranteed(self):
        c = _diamond()
        c.assert_ordering([
            ("kmax_coarse", ">=", "kmin_coarse"),
            ("kmax_fine", ">=", "kmin_fine"),
            ("kmax_coarse", ">=", "kmax_fine"),
            ("kmin_coarse", ">=", "kmin_fine"),
        ])

    def test_violated_ordering_caught(self):
        from iwfm_io.pest import RatioChain

        c = RatioChain()
        c.add_parameter("a", bounds=(1.0, 10.0))
        c.add_parameter("f", bounds=(0.5, 2.0))     # >1 breaks ordering
        c.add_derived("b", "a * f")
        with pytest.raises(AssertionError, match="ordering violated"):
            c.assert_ordering([("a", ">=", "b")])

    def test_derived_chains_on_derived(self):
        from iwfm_io.pest import RatioChain

        c = RatioChain()
        c.add_parameter("x", bounds=(1.0, 2.0))
        c.add_derived("y", "x * 2")
        c.add_derived("z", "y + 1")
        assert c.evaluate({"x": 1.5})["z"] == pytest.approx(4.0)

    def test_declaration_errors(self):
        from iwfm_io.pest import RatioChain

        c = RatioChain()
        c.add_parameter("a", bounds=(1.0, 2.0))
        with pytest.raises(ValueError, match="duplicate"):
            c.add_parameter("a", bounds=(1.0, 2.0))
        with pytest.raises(ValueError, match="unknown name"):
            c.add_derived("d", "a * nope")
        with pytest.raises(ValueError, match="bad expression"):
            c.add_derived("d", "a *")
        with pytest.raises(ValueError, match="lower < upper"):
            c.add_parameter("b", bounds=(2.0, 1.0))
        with pytest.raises(ValueError, match="log transform"):
            c.add_parameter("b", bounds=(0.0, 1.0), transform="log")

    def test_evaluate_missing_value_raises(self):
        c = _diamond()
        with pytest.raises(KeyError, match="missing"):
            c.evaluate({"kxc": 100.0})

    def test_par_data(self):
        c = _diamond()
        pdata = c.par_data(name_format="{name}_z01")
        assert pdata["parnme"].tolist() == ["kxc_z01", "dt_z01", "pa_z01",
                                            "pb_z01"]
        row = pdata.set_index("parnme").loc["kxc_z01"]
        assert row["partrans"] == "log"
        assert row["parlbnd"] == 20.0 and row["parubnd"] == 450.0
        # log-space midpoint initial
        assert row["parval1"] == pytest.approx(np.sqrt(20.0 * 450.0))


class TestT2pPilotPoints:
    def test_round_trip(self, tmp_path):
        from iwfm_io.pest import (read_t2p_pilot_points,
                                  write_t2p_pilot_points)

        df = pd.DataFrame({
            "pp_id": ["1", "2"], "x": [1846870.0, 1870936.0],
            "y": [14748020.0, 14705800.0], "zone": ["1", "2"]})
        f = tmp_path / "test.ppaq"
        write_t2p_pilot_points(f, df)
        back = read_t2p_pilot_points(f)
        assert back["pp_id"].tolist() == ["1", "2"]
        assert back["x"].tolist() == pytest.approx(df["x"].tolist())
        assert back["zone"].tolist() == ["1", "2"]

    def test_read_real_calsim_file(self):
        import pathlib

        from iwfm_io.pest import read_t2p_pilot_points

        real = pathlib.Path(
            r"C:\Projects\Calsim_PEST28_new\zAgent_template"
            r"\CS3HIST_COMBINED_newGWDLL_Mekong_v1_3_init\Run"
            r"\CVGroundwater\Data\CS3.ppaq")
        if not real.is_file():
            pytest.skip("Calsim workspace not available")
        pps = read_t2p_pilot_points(real)
        assert len(pps) == 80
        assert (pps["x"] > 0).all() and (pps["y"] > 0).all()
        assert pps["pp_id"].is_unique

    def test_missing_column_and_block(self, tmp_path):
        from iwfm_io.pest import (read_t2p_pilot_points,
                                  write_t2p_pilot_points)

        with pytest.raises(ValueError, match="zone"):
            write_t2p_pilot_points(tmp_path / "x.ppaq",
                                   pd.DataFrame({"pp_id": [], "x": [],
                                                 "y": []}))
        bad = tmp_path / "bad.ppaq"
        bad.write_text("no blocks here\n")
        with pytest.raises(ValueError, match="PP_LOCS"):
            read_t2p_pilot_points(bad)
