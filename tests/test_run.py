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
# failure detection (no executables needed)
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


# ---------------------------------------------------------------------------
# streaming / hang warning / timeout, driven by a fake executable: the
# Python interpreter stands in for the IWFM tool (``_find_exe`` is pointed
# at it; ``IWFM_BIN_DIR`` still has to resolve) and the step's "main input
# file" is a tiny Python script that prints slowly, hangs, or never ends.
# ---------------------------------------------------------------------------

windows_only = pytest.mark.skipif(os.name != "nt",
                                  reason="runner is Windows-only")


@pytest.fixture
def fake_exe(tmp_path, monkeypatch):
    """Return ``make(step, script) -> model_dir`` wiring a fake tool."""
    import sys

    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir()
    for name in ("PreProcessor_x64.exe", "Simulation_x64.exe",
                 "Budget_x64.exe", "ZBudget_x64.exe"):
        (bin_dir / name).write_bytes(b"")          # discovered by name ...
    monkeypatch.setenv("IWFM_BIN_DIR", str(bin_dir))
    # ... but the interpreter is what actually runs the "input file"
    monkeypatch.setattr("iwfm_io.run._find_exe",
                        lambda bin_dir, key: Path(sys.executable))
    subdir = {"preprocessor": ("Preprocessor", "PreProcessor_MAIN.IN"),
              "simulation": ("Simulation", "Simulation_MAIN.IN"),
              "zbudget": ("ZBudget", "ZBudget_MAIN.IN")}

    def make(step, script):
        model = tmp_path / "model"
        folder, name = subdir[step]
        (model / folder).mkdir(parents=True, exist_ok=True)
        (model / folder / name).write_text(script)
        return model
    return make


@windows_only
def test_streams_lines_to_logger_and_keeps_tail(fake_exe, caplog):
    import logging
    from iwfm_io.run import run_step
    model = fake_exe("simulation", (
        "import time\n"
        "for i in range(3):\n"
        "    print('step', i, flush=True); time.sleep(0.2)\n"
        "print('done', flush=True)\n"))
    with caplog.at_level(logging.INFO, logger="iwfm_io.run"):
        r = run_step("simulation", model, quiet=False, timeout=60)
    assert r.success and r.returncode == 0 and not r.timed_out
    assert r.stdout_tail.splitlines() == ["step 0", "step 1", "step 2", "done"]
    streamed = [rec.getMessage() for rec in caplog.records
                if rec.levelno == logging.INFO]
    assert streamed == ["simulation | step 0", "simulation | step 1",
                        "simulation | step 2", "simulation | done"]


@windows_only
def test_quiet_run_does_not_stream(fake_exe, caplog):
    import logging
    from iwfm_io.run import run_step
    model = fake_exe("simulation", "print('hello')\n")
    with caplog.at_level(logging.INFO, logger="iwfm_io.run"):
        r = run_step("simulation", model, quiet=True, timeout=60)
    assert r.success and r.stdout_tail == "hello"
    assert not [rec for rec in caplog.records if rec.levelno == logging.INFO]


@windows_only
def test_hang_warning_after_silence(fake_exe, caplog):
    """No output for ``hang_warning_seconds`` -> one warning naming the
    step, the ZBudget busy-loop and ``timeout=``; output resuming
    re-arms it; the run itself still completes normally."""
    import logging
    from iwfm_io.run import run_step
    model = fake_exe("zbudget", (
        "import time\n"
        "print('start', flush=True)\n"
        "time.sleep(1.6)\n"
        "print('resumed', flush=True)\n"
        "time.sleep(1.6)\n"
        "print('finished', flush=True)\n"))
    with caplog.at_level(logging.WARNING, logger="iwfm_io.run"):
        r = run_step("zbudget", model, quiet=True, hang_warning_seconds=0.5)
    assert r.success and not r.timed_out
    assert r.stdout_tail.splitlines() == ["start", "resumed", "finished"]
    warnings = [rec.getMessage() for rec in caplog.records
                if rec.levelno == logging.WARNING]
    assert len(warnings) == 2                    # once per silent stretch
    for msg in warnings:
        assert msg.startswith("zbudget: no console output for")
        assert "may be hung" in msg and "ZBudget" in msg
        assert "timeout=" in msg and "no timeout is set" in msg


@windows_only
def test_hang_warning_disabled(fake_exe, caplog):
    import logging
    from iwfm_io.run import run_step
    model = fake_exe("simulation", "import time; time.sleep(1.2)\n")
    with caplog.at_level(logging.WARNING, logger="iwfm_io.run"):
        r = run_step("simulation", model, quiet=True, hang_warning_seconds=0.3,
                     timeout=30)
        assert any("may be hung" in rec.getMessage() for rec in caplog.records)
        caplog.clear()
        r = run_step("simulation", model, quiet=True, hang_warning_seconds=None)
    assert r.success
    assert not [rec for rec in caplog.records if rec.levelno == logging.WARNING]


@windows_only
def test_timeout_is_a_failed_result(fake_exe, caplog):
    """A run that exceeds ``timeout`` is killed and reported, never
    raised; what it printed before is kept."""
    import logging
    import time as _time
    from iwfm_io.run import run_step
    model = fake_exe("simulation", (
        "import time\n"
        "print('tick', flush=True)\n"
        "time.sleep(120)\n"
        "print('never', flush=True)\n"))
    t0 = _time.perf_counter()
    with caplog.at_level(logging.WARNING, logger="iwfm_io.run"):
        r = run_step("simulation", model, timeout=1.5, quiet=True,
                     hang_warning_seconds=0.5)
    assert _time.perf_counter() - t0 < 30       # the child was killed
    assert r.success is False and r.timed_out is True and r.returncode == -1
    assert any("timed out after 1.5 s" in e for e in r.errors)
    assert r.stdout_tail == "tick"
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("killed after timeout=1.5 s" in m for m in msgs)


@windows_only
def test_fatal_banner_in_streamed_output_fails_the_step(fake_exe):
    from iwfm_io.run import run_step
    model = fake_exe("simulation", (
        "print('*   Reading data')\n"
        "print('* FATAL:')\n"
        "print('*   Error in opening file PreProcessor.bin!')\n"))
    r = run_step("simulation", model, quiet=True, timeout=60)
    assert r.success is False and r.returncode == 0 and not r.timed_out
    assert len(r.errors) == 1 and "PreProcessor.bin" in r.errors[0]


@windows_only
def test_nonzero_exit_fails_the_step(fake_exe):
    from iwfm_io.run import run_step
    model = fake_exe("simulation", "import sys; print('bye'); sys.exit(3)\n")
    r = run_step("simulation", model, quiet=True, timeout=60)
    assert r.success is False and r.returncode == 3
    assert r.stdout_tail == "bye"


@windows_only
def test_relative_input_file_is_relative_to_model_dir(fake_exe, monkeypatch):
    """The tool runs in its input file's folder (like the DWR batch
    files) even when the input path is given relative to the model."""
    from iwfm_io.run import run_step
    model = fake_exe("preprocessor", "import os; print(os.getcwd())\n")
    monkeypatch.chdir(model.parent)
    r = run_step("preprocessor", model,
                 input_file="Preprocessor/PreProcessor_MAIN.IN", quiet=True,
                 timeout=60)
    assert r.success
    assert Path(r.stdout_tail.strip()).resolve() == (
        model / "Preprocessor").resolve()


@windows_only
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
