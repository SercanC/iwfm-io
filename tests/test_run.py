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
    from iwfm.run import run_step
    with pytest.raises((ValueError, OSError)):
        run_step("nosuchstep", SAMPLE_MODEL)


@needs_exes
def test_missing_bin_dir_raises(tmp_path):
    from iwfm import run_preprocessor
    with pytest.raises(FileNotFoundError):
        run_preprocessor(SAMPLE_MODEL, bin_dir=tmp_path / "nope")


@needs_exes
def test_run_preprocessor_on_scenario(tmp_path):
    """Full preprocessor run on a scenario copy of the sample model."""
    from iwfm import run_preprocessor
    from iwfm.io import create_scenario

    scen = create_scenario(SAMPLE_MODEL, tmp_path / "scen",
                           subdirs=("Preprocessor", "Simulation", "Bin"))
    result = run_preprocessor(scen, quiet=True, timeout=300)
    assert result.success, result.errors
    assert result.returncode == 0
    assert result.elapsed > 0
    # The preprocessor writes its binary output for the simulation step
    assert (scen / "Simulation" / "PreProcessor.bin").is_file()
