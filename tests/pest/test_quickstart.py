"""Tests for the PEST quickstart (iwfm_io.pest.quickstart) and the
nested-table apply path it relies on.

Template assembly, observation pairing, the generated apply/extract
steps, and the CLI wrapper are exercised against the sample model
(skipped when ``.assets/sample_model`` is absent). The IWFM executables
are NOT run here — the forward-run *scripts* are validated against the
baseline Results instead (the full exe pass lives in the opt-in
``tests/io/test_exe_roundtrip.py`` tier).
"""

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"

pytestmark = pytest.mark.skipif(
    not SAMPLE.is_dir(), reason="sample model not available")


@pytest.fixture(scope="module")
def baseline_hyd():
    """Baseline GW hydrograph output, normalized (datetime × id)."""
    from iwfm_io.readers.text_output import read_hydrograph_out
    from iwfm_io.wells import normalize_hydrograph_output
    return normalize_hydrograph_output(
        read_hydrograph_out(SAMPLE / "Results" / "GWHyd.out"))


@pytest.fixture(scope="module")
def obs(baseline_hyd):
    """Sparse noisy observations at three hydrograph sites plus one
    unmatched site."""
    rng = np.random.default_rng(7)
    recs = []
    for site, hid in [("GWHyd2", 2), ("GWHyd5", 5), ("GWHyd23", 23)]:
        s = baseline_hyd[hid].iloc[10::60]
        recs.append(pd.DataFrame({
            "site": site, "datetime": s.index,
            "value": s.values + rng.normal(0, 1.0, len(s))}))
    recs.append(pd.DataFrame({
        "site": ["NOSUCHWELL"],
        "datetime": [recs[0]["datetime"].iloc[0]], "value": [1.0]}))
    return pd.concat(recs, ignore_index=True)


@pytest.fixture(scope="module")
def template(obs, tmp_path_factory):
    from iwfm_io.pest import pest_setup_from_model
    dest = tmp_path_factory.mktemp("qs") / "template"
    qs = pest_setup_from_model(
        SAMPLE, obs, dest, parameters=("kh", "ss", "sy", "strk"),
        ies_num_reals=10)
    return qs


class TestSetup:
    def test_template_structure(self, template):
        d = template.template
        for f in ["iwfm_cal.pst", "iwfm_cal_par_data.csv",
                  "iwfm_cal_obs_data.csv", "iwfm_cal_heads.pout.ins",
                  "forward_run.py", "_apply_step.py", "_run_step.py",
                  "_extract_step.py", "_quickstart.json",
                  "_obs_index.csv", "mult_kh.csv", "mult_kh.csv.tpl",
                  "mult_strk.csv", "mult_strk.csv.tpl"]:
            assert (d / f).is_file(), f
        assert (d / "model" / "Simulation").is_dir()
        assert (d / "model" / "Results").is_dir()
        pst = (d / "iwfm_cal.pst").read_text()
        assert "pcf version=2" in pst
        assert "ies_num_reals" in pst

    def test_parameters_zoned(self, template):
        par = template.par_data
        # sample model: 1 parametric node × 2 layers → 2 zones per GW
        # property (kh, ss, sy) + one global stream multiplier
        assert len(par) == 7
        assert set(par["pargp"]) == {"kh", "ss", "sy", "strk"}
        assert (par["parval1"] == 1.0).all()
        assert par["parnme"].str.match(r"^(kh|ss|sy)_sr\d+_l\d+$|^strk$") \
            .all()

    def test_observations_paired(self, template, obs):
        paired = template.paired
        assert set(paired["site"].unique()) == {"GWHyd2", "GWHyd5",
                                                "GWHyd23"}
        assert paired["obsnme"].is_unique
        assert paired["obsnme"].str.startswith("gwh_gwhyd").all()
        # noise was ~N(0, 1): the baseline pairing must be tight
        resid = paired["observed"] - paired["simulated"]
        assert abs(resid.mean()) < 0.5
        assert resid.abs().max() < 5.0
        # the fabricated site was dropped with a reason
        assert set(template.dropped["reason"]) == {"no_hydrograph"}
        assert (template.dropped["site"] == "NOSUCHWELL").all()

    def test_obs_data_matches_ins(self, template):
        d = template.template
        obs_data = pd.read_csv(d / "iwfm_cal_obs_data.csv")
        ins = (d / "iwfm_cal_heads.pout.ins").read_text().splitlines()
        assert len(ins) == len(obs_data) + 1        # 'pif #' header
        assert obs_data["obsnme"].tolist() == \
            template.paired["obsnme"].tolist()

    def test_summary_serializable(self, template):
        text = json.dumps(template.summary(), default=str)
        assert "n_parameters" in text


class TestForwardRunSteps:
    def test_apply_step_nested_parametric_table(self, template):
        """The generated apply actions modify the parametric-grid kh
        (nested table path) and the stream conductance in place."""
        from iwfm_io.pest.apply import ApplyAction, apply_parameters
        from iwfm_io.readers.groundwater import read_gw_main
        from iwfm_io.readers.stream import read_stream_main

        d = template.template
        actions = [ApplyAction(**a)
                   for a in json.loads((d / "_apply_actions.json")
                                       .read_text())]
        gw_path = d / "model" / "Simulation" / "GW" / "GW_MAIN.dat"
        st_path = d / "model" / "Simulation" / "Stream" / \
            "Stream_MAIN.dat"
        kh0 = read_gw_main(gw_path).parametric_grids[0]["params"]["kh"]
        cond0 = read_stream_main(st_path).reach_params["conductance"]

        mult = pd.read_csv(d / "mult_kh.csv")
        mult["value"] = 2.0
        mult.to_csv(d / "mult_kh.csv", index=False)
        try:
            log = apply_parameters(d, actions)
            assert set(log["column"]) == {"kh", "ss", "sy",
                                          "conductance"}
            gw = read_gw_main(gw_path)
            kh1 = gw.parametric_grids[0]["params"]["kh"]
            assert np.allclose(kh1.values, kh0.values * 2.0)
            # ×1 multipliers leave the other tables unchanged
            cond1 = read_stream_main(st_path).reach_params["conductance"]
            assert np.allclose(cond1.values, cond0.values)
            # referenced paths survive the rewrite: re-apply parses fine
            apply_parameters(d, actions)
        finally:
            mult["value"] = 0.5
            mult.to_csv(d / "mult_kh.csv", index=False)
            apply_parameters(d, actions)
            mult["value"] = 1.0
            mult.to_csv(d / "mult_kh.csv", index=False)

    def test_rewritten_mains_keep_working_dir_paths(self, template):
        """After repeated applies, referenced paths stay relative to the
        simulation working directory (no path accumulation)."""
        import re

        from iwfm_io.pest.apply import ApplyAction, apply_parameters

        d = template.template
        actions = [ApplyAction(**a)
                   for a in json.loads((d / "_apply_actions.json")
                                       .read_text())]
        apply_parameters(d, actions)
        apply_parameters(d, actions)
        text = (d / "model" / "Simulation" / "Stream" /
                "Stream_MAIN.dat").read_text()
        line = next(l for l in text.splitlines() if "INFLOWFL" in l
                    and not l.lstrip().startswith(("C", "c", "*")))
        assert re.search(r"(?i)^\s*Stream[/\\]StreamInflow\.dat\s*/",
                         line), line

    def test_extract_step_reproduces_baseline(self, template,
                                              monkeypatch):
        """run_extract on the baseline hydrograph output reproduces the
        setup-time simulated values exactly."""
        from iwfm_io.pest import ObsFileSpec
        from iwfm_io.pest.quickstart import run_extract

        d = template.template
        results = d / "model" / "Results"
        shutil.copy(SAMPLE / "Results" / "GWHyd.out",
                    results / "GWHyd.out")
        monkeypatch.chdir(d)
        run_extract()
        idx = pd.read_csv(d / "_obs_index.csv")
        out = ObsFileSpec(list(idx["obsnme"])).read_output(
            d / "iwfm_cal_heads.pout")
        expected = template.paired.set_index("obsnme")["simulated"]
        assert np.allclose(out.reindex(expected.index).values,
                           expected.values, rtol=1e-6)


class TestValidation:
    def test_no_matching_sites_raises(self, tmp_path):
        from iwfm_io.pest import pest_setup_from_model
        bad = pd.DataFrame({"site": ["XX"],
                            "datetime": ["2000-01-15"], "value": [1.0]})
        with pytest.raises(ValueError, match="no observation site"):
            pest_setup_from_model(SAMPLE, bad, tmp_path / "t")

    def test_unknown_property_raises(self, tmp_path, obs):
        from iwfm_io.pest import pest_setup_from_model
        with pytest.raises(ValueError, match="no column"):
            pest_setup_from_model(SAMPLE, obs, tmp_path / "t",
                                  parameters=("porosity",))

    def test_smp_observations(self, tmp_path, obs, baseline_hyd):
        from iwfm_io.pest import pest_setup_from_model, write_smp
        smp = tmp_path / "obs.smp"
        write_smp(obs[obs["site"] != "NOSUCHWELL"], smp)
        qs = pest_setup_from_model(SAMPLE, smp, tmp_path / "t",
                                   date_format="dd/mm/yyyy",
                                   parameters=("kh",), zones="global")
        assert len(qs.par_data) == 1
        assert qs.par_data["parnme"].iloc[0] == "kh"
