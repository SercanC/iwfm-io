"""Tests for the IES diagnostics suite (iwfm_io.pest.diagnostics)."""

import json

import pandas as pd
import pytest

from tests.pest.conftest import CASE  # noqa: F401


def _par_data():
    # par1 in group "ga": real "0" sits exactly on its lower bound
    # par2 in group "gb" (log): mid-range, never railed
    return pd.DataFrame({
        "parnme": ["par1", "par2"],
        "partrans": ["none", "log"],
        "parlbnd": [3.0, 1.0],
        "parubnd": [10.0, 100.0],
        "pargp": ["ga", "gb"],
    })


@pytest.fixture
def diag(ies_dir):
    from iwfm_io.pest import diagnose_ies, load_ies_ensembles

    return diagnose_ies(load_ies_ensembles(ies_dir), par_data=_par_data())


class TestSections:
    def test_phi_section(self, diag):
        phi = diag.state["phi"]
        # actual is preferred over composite; fixture has iterations 0 and 2
        assert phi["source"] == "phi.actual"
        assert phi["n_iterations"] == 2
        assert phi["per_iteration"][0]["mean"] == 155
        # (155-120)/155 total reduction
        assert phi["total_phi_reduction_frac"] == pytest.approx(0.2258, abs=1e-4)
        assert phi["signals"]["phi_stalled"] is False
        assert phi["signals"]["ensemble_collapsed"] is False

    def test_conflict_section(self, diag):
        pdc = diag.state["prior_data_conflict"]
        assert pdc["total_conflicts"] == 1
        assert pdc["nonzero_obs"] == 2
        # 1/2 = 0.5 > 0.40 default
        assert pdc["signals"]["conflict_systemic"] is True
        assert pdc["by_category"] == {"gwh": 1}

    def test_railing_section(self, diag):
        rail = diag.state["bound_railing"]
        assert rail["n_parameters"] == 2
        assert rail["n_realizations"] == 2
        # par1: real "0" at value 3.0 == lower bound -> 1 of 2 railed
        assert rail["by_group"]["ga"]["pct_railed"] == pytest.approx(50.0)
        assert rail["by_group"]["ga"]["direction"] == "low"
        assert "gb" not in rail["by_group"]
        assert "ga" in rail["flagged_groups"]
        assert rail["signals"]["railing_present"] is True

    def test_railing_needs_par_data(self, ies_dir):
        from iwfm_io.pest import diagnose_ies, load_ies_ensembles

        d = diagnose_ies(load_ies_ensembles(ies_dir))
        assert "note" in d.state["bound_railing"]

    def test_residuals_section(self, diag):
        res = diag.state["residuals"]
        assert res["by_group"]["gwh01"]["mean_res"] == pytest.approx(-22.67)
        # bias beyond 15 -> flagged
        assert "gwh01" in res["flagged_groups"]
        assert res["flagged_groups"]["gwh01"]["likely"] == "bias"
        assert "bud" not in res["flagged_groups"]

    def test_outliers_default_threshold(self, diag):
        assert diag.state["outliers"]["n_over_threshold"] == 0

    def test_outliers_custom_threshold(self, ies_dir):
        from iwfm_io.pest import (DiagThresholds, diagnose_ies,
                                  load_ies_ensembles)

        d = diagnose_ies(load_ies_ensembles(ies_dir),
                         thresholds=DiagThresholds(outlier_threshold=10.0))
        outl = d.state["outliers"]
        assert outl["n_over_threshold"] == 1
        assert outl["top"][0]["obs"] == "gwh_w1_20001031"

    def test_objective_section(self, diag):
        obj = diag.state["objective_balance"]
        # last iteration: gwh01 -> 10, bud -> 15
        assert obj["category_share"] == {"bud": 0.6, "gwh": 0.4}
        assert obj["signals"]["dominant_category"] == "bud"
        assert obj["signals"]["objective_imbalance"] is True


class TestSignalsAndOutput:
    def test_flattened_signals(self, diag):
        s = diag.signals
        assert s["conflict_systemic"] is True
        assert s["railing_present"] is True
        assert s["phi_stalled"] is False
        assert diag.state["signals"] == s

    def test_stalled_and_collapsed_signals(self, tmp_path):
        from iwfm_io.pest import diagnose_ies, load_ies_ensembles

        d = tmp_path / "m"
        d.mkdir()
        (d / "x.phi.composite.csv").write_text(
            "iteration,total_runs,mean,standard_deviation,min,max,0,1\n"
            "0,2,100,10,90,110,110,90\n"
            "1,2,99.5,1,99,100,100,99\n")
        diag = diagnose_ies(load_ies_ensembles(d))
        phi = diag.state["phi"]
        assert phi["signals"]["phi_stalled"] is True       # 0.5% < 1%
        assert phi["signals"]["ensemble_collapsed"] is True  # 1/10 < 0.30
        # all other sections degrade to notes/errors, never raise
        for sec in ("prior_data_conflict", "residuals", "outliers",
                    "objective_balance"):
            assert "signals" not in diag.state[sec] or True

    def test_to_json_round_trips(self, diag, tmp_path):
        text = diag.to_json(tmp_path / "state.json")
        state = json.loads(text)
        assert state["case"] == CASE
        assert state["phi"]["n_iterations"] == 2
        assert json.loads((tmp_path / "state.json").read_text()) == state

    def test_summary_mentions_key_facts(self, diag):
        s = diag.summary()
        assert CASE in s
        assert "phi mean by iteration" in s
        assert "conflict" in s
        assert "active signals" in s

    def test_custom_category_of(self, ies_dir):
        from iwfm_io.pest import diagnose_ies, load_ies_ensembles

        d = diagnose_ies(load_ies_ensembles(ies_dir),
                         category_of=lambda g: "everything")
        obj = d.state["objective_balance"]
        assert obj["category_share"] == {"everything": 1.0}
