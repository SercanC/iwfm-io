"""Shared pytest fixtures for iwfm.io tests."""

from pathlib import Path

import pytest

# Root of the sample model (relative to repo root)
SAMPLE_MODEL = Path(__file__).resolve().parent.parent.parent / ".assets" / "sample_model"
PREPROCESSOR_DIR = SAMPLE_MODEL / "Preprocessor"
SIMULATION_DIR = SAMPLE_MODEL / "Simulation"
RESULTS_DIR = SAMPLE_MODEL / "Results"
BUDGET_DIR = SAMPLE_MODEL / "Budget"


@pytest.fixture
def sample_model():
    """Path to the sample_model directory."""
    return SAMPLE_MODEL


@pytest.fixture
def preprocessor_dir():
    """Path to sample_model/Preprocessor/."""
    return PREPROCESSOR_DIR


@pytest.fixture
def simulation_dir():
    """Path to sample_model/Simulation/."""
    return SIMULATION_DIR


@pytest.fixture
def results_dir():
    """Path to sample_model/Results/."""
    return RESULTS_DIR


@pytest.fixture
def budget_dir():
    """Path to sample_model/Budget/."""
    return BUDGET_DIR


@pytest.fixture
def tmp_output(tmp_path):
    """Temporary directory for writer output."""
    return tmp_path
