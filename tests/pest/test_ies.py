"""Tests for the PESTPP-IES results loader (iwfm_io.pest.ies)."""

import pytest

from tests.pest.conftest import CASE  # noqa: F401


class TestDiscovery:
    def test_load_from_pst_path(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir / f"{CASE}.pst")
        assert r.case == CASE
        assert r.iterations == [0, 1, 2]

    def test_load_from_directory(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        assert r.case == CASE

    def test_load_from_prefix(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir / CASE)
        assert sorted(r.par_files) == [0, 1, 2]
        assert sorted(r.obs_files) == [0, 2]

    def test_empty_directory_raises(self, tmp_path):
        from iwfm_io.pest import load_ies_ensembles

        with pytest.raises(FileNotFoundError):
            load_ies_ensembles(tmp_path)

    def test_multiple_cases_need_disambiguation(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        (ies_dir / "other.phi.composite.csv").write_text(
            "iteration,total_runs,mean,standard_deviation,min,max,0\n"
            "0,1,1,0,1,1,1\n")
        with pytest.raises(ValueError, match="multiple cases"):
            load_ies_ensembles(ies_dir)
        # but explicit prefix still works
        assert load_ies_ensembles(ies_dir / CASE).case == CASE

    def test_describe(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        d = load_ies_ensembles(ies_dir).describe()
        assert d["iterations"] == [0, 1, 2]
        assert d["obs_iterations"] == [0, 2]
        assert d["has_pdc"] and d["has_obs_plus_noise"]
        assert d["phi_mean_by_iteration"][2] == 20


class TestEnsembles:
    def test_par_default_is_last_iteration(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        df = r.par()
        assert list(df.index) == ["0", "base"]
        assert df.loc["base", "par1"] == pytest.approx(4.0)

    def test_par_specific_iteration_and_dropped_real(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        assert "7" in r.par(0).index
        assert "7" not in r.par(1).index

    def test_missing_iteration_raises_keyerror(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        with pytest.raises(KeyError, match="available"):
            r.obs(1)

    def test_par_all_multiindex(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        df = load_ies_ensembles(ies_dir).par_all()
        assert df.index.names == ["iteration", "real_name"]
        assert len(df) == 3 + 2 + 2
        assert df.loc[(0, "7"), "par2"] == pytest.approx(20.0)

    def test_obs_all_only_existing_iterations(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        df = load_ies_ensembles(ies_dir).obs_all()
        assert sorted(df.index.get_level_values("iteration").unique()) == [0, 2]

    def test_caching_returns_same_object(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        assert r.par(2) is r.par(2)

    def test_jcb_without_pyemu_raises(self, ies_dir):
        pytest.importorskip("pytest")  # placeholder guard
        try:
            import pyemu  # noqa: F401
            pytest.skip("pyemu installed; jcb path would succeed")
        except ImportError:
            pass
        from iwfm_io.pest import load_ies_ensembles

        (ies_dir / f"{CASE}.3.par.jcb").write_bytes(b"\x00")
        r = load_ies_ensembles(ies_dir)
        with pytest.raises(RuntimeError, match="pyemu"):
            r.par(3)

    def test_csv_preferred_over_jcb(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        (ies_dir / f"{CASE}.2.par.jcb").write_bytes(b"\x00")
        r = load_ies_ensembles(ies_dir)
        assert r.par_files[2].suffix == ".csv"


class TestPhi:
    def test_tidy_phi_drops_nan(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        phi = load_ies_ensembles(ies_dir).phi()
        assert list(phi.columns) == ["iteration", "real_name", "phi"]
        # real 7 present only in iteration 0
        assert set(phi[phi["real_name"] == "7"]["iteration"]) == {0}
        assert len(phi) == 3 + 2 + 2

    def test_phi_summary(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        s = load_ies_ensembles(ies_dir).phi_summary()
        assert s.loc[0, "total_runs"] == 3
        assert s.loc[2, "mean"] == 20

    def test_phi_other_kind_and_missing_kind(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        assert len(r.phi("actual")) == 3 + 2
        with pytest.raises(FileNotFoundError, match="phi.meas"):
            r.phi("meas")

    def test_phi_groups_tidy(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        g = load_ies_ensembles(ies_dir).phi_groups()
        assert list(g.columns) == ["iteration", "real_name", "group", "phi"]
        assert g.set_index(["iteration", "real_name", "group"]).loc[
            (2, "base", "gwh01"), "phi"] == 10

    def test_best_realization(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        r = load_ies_ensembles(ies_dir)
        assert r.best_realization() == "0"        # iter 2: 0 -> 15, base -> 25
        assert r.best_realization(iteration=0) == "base"


class TestExtras:
    def test_pdc(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        pdc = load_ies_ensembles(ies_dir).pdc()
        assert pdc.loc["gwh_w1_20001031", "distance"] == pytest.approx(20.2)

    def test_pdc_absent_returns_none(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        (ies_dir / f"{CASE}.pdc.csv").unlink()
        assert load_ies_ensembles(ies_dir).pdc() is None

    def test_obs_plus_noise(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        noise = load_ies_ensembles(ies_dir).obs_plus_noise()
        assert noise.loc["base", "bud_sr01"] == pytest.approx(300.0)

    def test_base_rei(self, ies_dir):
        from iwfm_io.pest import load_ies_ensembles

        rei = load_ies_ensembles(ies_dir).base_rei()
        assert list(rei.columns) == [
            "name", "group", "measured", "modelled", "residual", "weight"]
        assert rei.set_index("name").loc["bud_sr01", "residual"] == -1.0

    def test_read_rei_no_header_raises(self, tmp_path):
        from iwfm_io.pest import read_rei

        bad = tmp_path / "bad.rei"
        bad.write_text("nothing here\n")
        with pytest.raises(ValueError, match="no header"):
            read_rei(bad)
