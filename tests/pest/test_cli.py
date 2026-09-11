"""Tests for the iwfm-io command line (iwfm_io.cli).

Commands are invoked in-process via ``main(argv)``; the ``pest run``
command (which needs a PEST++ executable) is exercised only for its
argument/error handling.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from iwfm_io.cli import main

SAMPLE = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"

needs_sample = pytest.mark.skipif(
    not SAMPLE.is_dir(), reason="sample model not available")


def test_no_command_prints_help(capsys):
    assert main([]) == 1
    assert "usage" in capsys.readouterr().out.lower()


def test_bare_pest_prints_usage(capsys):
    assert main(["pest"]) == 1
    assert "setup" in capsys.readouterr().out


def test_error_is_clean(capsys):
    rc = main(["describe", "does/not/exist"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "error:" in err and "Traceback" not in err


def test_traceback_flag_reraises():
    with pytest.raises(FileNotFoundError):
        main(["--traceback", "describe", "does/not/exist"])


@needs_sample
def test_describe(capsys):
    assert main(["describe", str(SAMPLE)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["grid"]["n_nodes"] == 441


@needs_sample
def test_pest_setup_and_agents(tmp_path, capsys):
    # observations synthesized from the baseline hydrograph output
    from iwfm_io.pest import write_smp
    from iwfm_io.readers.text_output import read_hydrograph_out
    from iwfm_io.wells import normalize_hydrograph_output

    hyd = normalize_hydrograph_output(
        read_hydrograph_out(SAMPLE / "Results" / "GWHyd.out"))
    s = hyd[2].iloc[5::90]
    obs = pd.DataFrame({"site": "GWHyd2", "datetime": s.index,
                        "value": s.values + 0.5})
    smp = tmp_path / "obs.smp"
    write_smp(obs, smp)

    dest = tmp_path / "tmpl"
    rc = main(["pest", "setup", "--model-dir", str(SAMPLE),
               "--obs", str(smp), "--dest", str(dest),
               "--date-format", "dd/mm/yyyy",
               "--parameters", "kh", "sy", "--zones", "layer"])
    assert rc == 0, capsys.readouterr().err
    out = capsys.readouterr().out
    assert (dest / "iwfm_cal.pst").is_file()
    assert (dest / "model" / "Simulation").is_dir()
    summary = json.loads(out[:out.index("\ntemplate ready")])
    assert summary["n_parameters"] == 4          # kh, sy × 2 layers
    assert summary["n_observations"] == len(obs)

    rc = main(["pest", "agents", "--template", str(dest), "-n", "2",
               "--dest-root", str(tmp_path / "agents")])
    assert rc == 0
    for i in (1, 2):
        agent = tmp_path / "agents" / f"agent_0{i}"
        assert (agent / "iwfm_cal.pst").is_file()
        assert list(agent.glob("start_agent.*"))
    assert list(dest.glob("start_manager.*"))


def test_pest_run_missing_exe(tmp_path, capsys):
    (tmp_path / "case.pst").write_text("pcf\n")
    rc = main(["pest", "run", "--template", str(tmp_path),
               "--exe", "no-such-pestpp-exe"])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_pest_analyze(ies_dir, tmp_path, capsys):
    report = tmp_path / "diag.json"
    rc = main(["pest", "analyze", str(ies_dir),
               "--json", str(report)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "diagnostics" in out
    state = json.loads(report.read_text())
    assert "phi" in state
