"""Tests for the IWFM executable runner (Windows + sample-model Bin only)."""

import os
from pathlib import Path

import pytest

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"

needs_exes = pytest.mark.skipif(
    os.name != "nt" or not (SAMPLE_MODEL / "Bin" / "PreProcessor_x64.exe").is_file(),
    reason="requires Windows and the sample-model executables",
)


def test_unknown_step_raises():
    from iwfm_io.run import run_step
    with pytest.raises((ValueError, OSError)):
        run_step("nosuchstep", SAMPLE_MODEL)


@needs_exes
def test_missing_bin_dir_raises(tmp_path):
    from iwfm_io import run_preprocessor
    with pytest.raises(FileNotFoundError):
        run_preprocessor(SAMPLE_MODEL, bin_dir=tmp_path / "nope")


@needs_exes
def test_run_preprocessor_on_scenario(tmp_path):
    """Full preprocessor run on a scenario copy of the sample model."""
    from iwfm_io import run_preprocessor
    from iwfm_io import create_scenario

    scen = create_scenario(SAMPLE_MODEL, tmp_path / "scen",
                           subdirs=("Preprocessor", "Simulation", "Bin"))
    result = run_preprocessor(scen, quiet=True, timeout=300)
    assert result.success, result.errors
    assert result.returncode == 0
    assert result.elapsed > 0
    # The preprocessor writes its binary output for the simulation step
    assert (scen / "Simulation" / "PreProcessor.bin").is_file()


# ---------------------------------------------------------------------------
# failure detection and timeouts (no executables needed)
# ---------------------------------------------------------------------------

def test_scan_for_errors_keeps_detail_lines():
    from iwfm_io.run import _scan_for_errors
    text = ("*   Reading data\n"
            "* FATAL:\n"
            "*   Error in opening file PreProcessor.bin!\n"
            "*   File not found, unit 10\n"
            "\n"
            "STANDARD ERROR: none\n"
            "FATAL_FLAG=0\n")
    errors = _scan_for_errors(text)
    assert len(errors) == 1
    assert "PreProcessor.bin" in errors[0]
    assert "unit 10" in errors[0]


def test_scan_for_errors_ignores_benign_words():
    from iwfm_io.run import _scan_for_errors
    assert _scan_for_errors("nonfatal warning\nERROR: none\n") == []


@pytest.mark.skipif(os.name != "nt", reason="runner is Windows-only")
def test_timeout_is_a_failed_result(tmp_path, monkeypatch):
    import subprocess
    from iwfm_io.run import run_step
    binp = tmp_path / "Bin"; binp.mkdir()
    (binp / "Simulation_x64.exe").write_bytes(b"")
    sim = tmp_path / "Simulation"; sim.mkdir()
    (sim / "Simulation_MAIN.IN").write_text("C\n")

    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"), output=b"tick\n")
    monkeypatch.setattr("iwfm_io.run.subprocess.run", fake_run)
    r = run_step("simulation", tmp_path, timeout=1, quiet=True)
    assert r.success is False and r.timed_out is True
    assert any("timed out" in e for e in r.errors)


@pytest.mark.skipif(os.name != "nt", reason="runner is Windows-only")
def test_relative_input_file_is_relative_to_model_dir(tmp_path, monkeypatch):
    from iwfm_io.run import run_step
    binp = tmp_path / "Bin"; binp.mkdir()
    (binp / "PreProcessor_x64.exe").write_bytes(b"")
    pp = tmp_path / "Preprocessor"; pp.mkdir()
    (pp / "PreProcessor_MAIN.IN").write_text("C\n")
    seen = {}

    class P:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cwd"] = kw["cwd"]
        return P()
    monkeypatch.setattr("iwfm_io.run.subprocess.run", fake_run)
    monkeypatch.chdir(tmp_path.parent)
    r = run_step("preprocessor", tmp_path,
                 input_file="Preprocessor/PreProcessor_MAIN.IN", quiet=True)
    assert r.success
    assert Path(seen["cwd"]) == pp


@pytest.mark.skipif(os.name != "nt", reason="runner is Windows-only")
def test_run_model_error_carries_partial_results(tmp_path, monkeypatch):
    from iwfm_io.run import RunError, RunResult, run_model
    calls = []

    def fake_step(step, model_dir, **kw):
        calls.append(step)
        ok = step == "preprocessor"
        return RunResult(step, "x", "y", 0 if ok else 0, 0.1, ok,
                         [] if ok else ["* FATAL:\n*   boom"])
    monkeypatch.setattr("iwfm_io.run.run_step", fake_step)
    with pytest.raises(RunError) as exc:
        run_model(tmp_path, steps=("preprocessor", "simulation", "budget"))
    assert list(exc.value.results) == ["preprocessor", "simulation"]
    assert calls == ["preprocessor", "simulation"]
