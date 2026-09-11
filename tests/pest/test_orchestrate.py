"""Tests for PEST++ run orchestration (iwfm_io.pest.orchestrate)."""

import os
import subprocess
import sys

import pandas as pd
import pytest

from tests.pest.conftest import CASE  # noqa: F401


@pytest.fixture
def template(tmp_path):
    """Minimal agent template: v2 pst + external par CSV + model bits."""
    t = tmp_path / "template"
    (t / "model" / "Results").mkdir(parents=True)
    (t / "model" / "input.dat").write_text("data\n")
    (t / "model" / "Results" / "old.out").write_text("stale\n")
    (t / "case.pst").write_text(
        "pcf version=2\n"
        "* control data keyword\n"
        "pestmode      estimation\n"
        "noptmax                2\n"
        "ies_num_reals        10\n"
        "* parameter data external\n"
        "case_par_data.csv\n"
        "* model command line\n"
        "python forward_run.py\n")
    pd.DataFrame({
        "parnme": ["p1", "p2", "pfix"],
        "partrans": ["log", "none", "fixed"],
        "parval1": [1.0, 2.0, 3.0],
        "parlbnd": [0.1, 0.5, 3.0],
        "parubnd": [10.0, 5.0, 3.0],
        "pargp": ["g1", "g1", "g2"],
    }).to_csv(t / "case_par_data.csv", index=False)
    return t


class TestSetupAgents:
    def test_creates_agents_with_scripts(self, template, tmp_path):
        from iwfm_io.pest import setup_agents

        agents = setup_agents(template, 3, dest_root=tmp_path / "workers",
                              port=4004)
        assert [a.name for a in agents] == ["agent_01", "agent_02",
                                            "agent_03"]
        for a in agents:
            assert (a / "case.pst").is_file()
            assert (a / "model" / "input.dat").is_file()
            script = a / ("start_agent.bat" if os.name == "nt"
                          else "start_agent.sh")
            body = script.read_text()
            assert "pestpp-ies case.pst /h localhost:4004" in body

    def test_hardlinks_used_and_results_empty(self, template, tmp_path):
        from iwfm_io.pest import setup_agents

        (a,) = setup_agents(template, 1, dest_root=tmp_path / "w")
        # input file hardlinked (same inode -> nlink 2)
        assert os.stat(a / "model" / "input.dat").st_nlink >= 2
        # Results recreated empty, stale outputs not replicated
        assert (a / "model" / "Results").is_dir()
        assert not (a / "model" / "Results" / "old.out").exists()

    def test_existing_agent_requires_overwrite(self, template, tmp_path):
        from iwfm_io.pest import setup_agents

        setup_agents(template, 1, dest_root=tmp_path / "w")
        with pytest.raises(FileExistsError):
            setup_agents(template, 1, dest_root=tmp_path / "w")
        setup_agents(template, 1, dest_root=tmp_path / "w", overwrite=True)

    def test_manager_script(self, template):
        from iwfm_io.pest import write_manager_script

        p = write_manager_script(template, port=4010)
        assert "pestpp-ies case.pst /h :4010" in p.read_text()

    def test_pst_autodetect_requires_single(self, template):
        from iwfm_io.pest import setup_agents

        (template / "other.pst").write_text("pcf\n")
        with pytest.raises(ValueError, match="exactly one"):
            setup_agents(template, 1, dest_root=template.parent / "x")


class TestForwardRun:
    def test_all_steps_pass(self, tmp_path):
        from iwfm_io.pest import write_forward_run

        py = sys.executable
        script = write_forward_run(tmp_path / "forward_run.py", [
            ("ok1", f'"{py}" -c "print(1)"'),
            ("ok2", f'"{py}" -c "open(\'touched.txt\', \'w\').write(\'x\')"'),
        ])
        r = subprocess.run([py, str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert (tmp_path / "touched.txt").exists()
        assert "all steps completed" in r.stdout

    def test_fail_fast_propagates_exit_code(self, tmp_path):
        from iwfm_io.pest import write_forward_run

        py = sys.executable
        script = write_forward_run(tmp_path / "forward_run.py", [
            ("boom", f'"{py}" -c "import sys; sys.exit(7)"'),
            ("never", f'"{py}" -c "open(\'no.txt\', \'w\')"'),
        ])
        r = subprocess.run([py, str(script)], capture_output=True, text=True)
        assert r.returncode == 7
        assert not (tmp_path / "no.txt").exists()

    def test_empty_steps_raise(self, tmp_path):
        from iwfm_io.pest import write_forward_run

        with pytest.raises(ValueError, match="non-empty"):
            write_forward_run(tmp_path / "f.py", [])


class TestParrepV2:
    def test_values_and_noptmax_written(self, template):
        from iwfm_io.pest import parrep_v2

        parrep_v2(template / "case.pst",
                  pd.Series({"p1": 4.2, "p2": 0.9, "extra": 1.0}))
        df = pd.read_csv(template / "case_par_data.csv")
        assert df.set_index("parnme").loc["p1", "parval1"] == pytest.approx(4.2)
        assert df.set_index("parnme").loc["pfix", "parval1"] == 3.0
        text = (template / "case.pst").read_text()
        assert any(l.split() == ["noptmax", "0"]
                   for l in text.splitlines())

    def test_missing_adjustable_parameter_raises(self, template):
        from iwfm_io.pest import parrep_v2

        with pytest.raises(KeyError, match="p2"):
            parrep_v2(template / "case.pst", pd.Series({"p1": 4.2}))

    def test_classic_pst_rejected(self, tmp_path):
        from iwfm_io.pest import parrep_v2

        p = tmp_path / "old.pst"
        p.write_text("pcf\n* control data\n...\n")
        with pytest.raises(ValueError, match="v2"):
            parrep_v2(p, pd.Series({"p1": 1.0}))


class TestRunFinals:
    def test_stages_realization(self, template, ies_dir, tmp_path):
        from iwfm_io.pest import load_ies_ensembles, run_finals

        # give the fixture case's par names to the template's csv
        pd.DataFrame({
            "parnme": ["par1", "par2"],
            "partrans": ["none", "log"],
            "parval1": [0.0, 0.0],
            "parlbnd": [0, 0], "parubnd": [99, 99],
            "pargp": ["g", "g"],
        }).to_csv(template / "case_par_data.csv", index=False)
        r = load_ies_ensembles(ies_dir)
        dest = run_finals(r, template, tmp_path / "final",
                          realization="base")
        df = pd.read_csv(dest / "case_par_data.csv")
        # iteration 2 base row: par1=4.0, par2=20.0 (from shared fixture)
        assert df.set_index("parnme").loc["par1",
                                          "parval1"] == pytest.approx(4.0)
        assert "noptmax                0" not in ""  # sanity placeholder
        assert any(l.split() == ["noptmax", "0"]
                   for l in (dest / "case.pst").read_text().splitlines())

    def test_unknown_realization_raises(self, template, ies_dir, tmp_path):
        from iwfm_io.pest import load_ies_ensembles, run_finals

        r = load_ies_ensembles(ies_dir)
        with pytest.raises(KeyError, match="realization"):
            run_finals(r, template, tmp_path / "f2", realization="nope")
