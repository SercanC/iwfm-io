"""Smoke tests for the calibration figure set (iwfm_io.plots.calibration).

These verify each function builds a valid figure from real data
structures without exceptions — visual quality is reviewed via the
gallery, not asserted here.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from tests.pest.conftest import CASE  # noqa: F401


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def results(ies_dir):
    from iwfm_io.pest import load_ies_ensembles

    return load_ies_ensembles(ies_dir)


def _par_data():
    return pd.DataFrame({
        "parnme": ["par1", "par2"],
        "partrans": ["none", "log"],
        "parlbnd": [3.0, 1.0],
        "parubnd": [10.0, 100.0],
        "pargp": ["ga", "gb"],
    })


class TestPhiPlots:
    def test_phi_convergence_from_results(self, results):
        from iwfm_io.plots.calibration import plot_phi_convergence

        fig, ax = plot_phi_convergence(results)
        assert len(ax.lines) >= 1          # mean line present
        assert ax.get_yscale() == "log"

    def test_phi_convergence_from_frame_linear(self, results):
        from iwfm_io.plots.calibration import plot_phi_convergence

        fig, ax = plot_phi_convergence(results.phi(), log=False)
        assert ax.get_yscale() == "linear"

    def test_phi_by_group(self, results):
        from iwfm_io.plots.calibration import plot_phi_by_group

        fig, ax = plot_phi_by_group(results)
        labels = [t.get_text() for t in ax.get_yticklabels()]
        assert "gwh01" in labels and "bud" in labels

    def test_save_path(self, results, tmp_path):
        from iwfm_io.plots.calibration import plot_phi_convergence

        out = tmp_path / "phi.png"
        plot_phi_convergence(results, save_path=out)
        assert out.exists()


class TestResidualPlots:
    def test_butterfly(self, ies_dir):
        from iwfm_io.pest import rei_stats
        from iwfm_io.plots.calibration import plot_residual_butterfly

        stats = rei_stats(ies_dir / f"{CASE}.2.base.rei")
        fig, ax = plot_residual_butterfly(stats)
        assert len(ax.patches) == 2        # two groups

    def test_obs_vs_sim_scatter(self, results):
        from iwfm_io.plots.calibration import plot_obs_vs_sim

        rei = results.base_rei()
        fig, ax = plot_obs_vs_sim(rei, observed="measured",
                                  simulated="modelled")
        assert ax.get_xlabel() == "Observed"

    def test_obs_vs_sim_hexbin_path(self):
        from iwfm_io.plots.calibration import plot_obs_vs_sim

        rng = np.random.default_rng(0)
        o = rng.normal(100, 10, 6000)
        df = pd.DataFrame({"observed": o,
                           "simulated": o + rng.normal(0, 2, 6000)})
        fig, ax = plot_obs_vs_sim(df, hexbin_threshold=5000)
        assert len(ax.collections) >= 1    # hexbin collection

    def test_residual_map(self):
        from iwfm_io.plots.calibration import plot_residual_map

        stats = pd.DataFrame({
            "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 0.5],
            "mean_res": [-5.0, 2.0, 8.0],
        })
        fig, ax = plot_residual_map(stats)
        assert len(ax.collections) == 1


class TestParameterPlots:
    def test_histograms_default(self, results):
        from iwfm_io.plots.calibration import plot_parameter_histograms

        fig, axes = plot_parameter_histograms(results)
        assert axes.shape == (1, 2)        # par1, par2

    def test_histograms_with_bounds_and_log(self, results):
        from iwfm_io.plots.calibration import plot_parameter_histograms

        fig, axes = plot_parameter_histograms(results, par_data=_par_data())
        assert axes[0][1].get_xscale() == "log"     # par2 is log
        assert len(axes[0][0].lines) == 2           # bound lines

    def test_histograms_group_filter(self, results):
        from iwfm_io.plots.calibration import plot_parameter_histograms

        fig, axes = plot_parameter_histograms(results, group="ga",
                                              par_data=_par_data())
        assert axes.shape == (1, 1)

    def test_histograms_group_needs_par_data(self, results):
        from iwfm_io.plots.calibration import plot_parameter_histograms

        with pytest.raises(ValueError, match="par_data"):
            plot_parameter_histograms(results, group="ga")

    def test_railing_from_diagnostics(self, results):
        from iwfm_io.pest import diagnose_ies
        from iwfm_io.plots.calibration import plot_parameter_railing

        diag = diagnose_ies(results, par_data=_par_data())
        fig, ax = plot_parameter_railing(diag)
        labels = [t.get_text() for t in ax.get_yticklabels()]
        assert "ga" in labels

    def test_railing_without_data_raises(self, results):
        from iwfm_io.pest import diagnose_ies
        from iwfm_io.plots.calibration import plot_parameter_railing

        diag = diagnose_ies(results)  # no par_data -> note, no by_group
        with pytest.raises(ValueError, match="railing"):
            plot_parameter_railing(diag)


class TestEnsembleHydrograph:
    def test_full_featured(self):
        from iwfm_io.plots.calibration import plot_ensemble_hydrograph

        idx = pd.date_range("2000-01-31", periods=24, freq="ME")
        rng = np.random.default_rng(1)
        ens = pd.DataFrame(
            rng.normal(0, 1, (24, 10)).cumsum(axis=0) + 100.0,
            index=idx, columns=[str(i) for i in range(9)] + ["base"])
        obs = pd.Series(100 + np.arange(24) * 0.1, index=idx)
        orig = obs + 5
        fig, ax = plot_ensemble_hydrograph(
            ens, observed=obs, original=orig, ylabel="Head (ft)",
            title="Well X")
        legend_texts = [t.get_text() for t in ax.get_legend().get_texts()]
        assert "base realization" in legend_texts
        assert "observed" in legend_texts
        assert "original model" in legend_texts

    def test_minimal(self):
        from iwfm_io.plots.calibration import plot_ensemble_hydrograph

        idx = pd.date_range("2000-01-31", periods=5, freq="ME")
        ens = pd.DataFrame(np.ones((5, 3)), index=idx,
                           columns=["0", "1", "2"])
        fig, ax = plot_ensemble_hydrograph(ens, base=None)
        assert ax.get_ylabel() == "Value"
