"""Shared pytest fixtures for iwfm_io tests."""


import pytest

# Root of the sample model — one definition, shared with the root conftest
from tests.conftest import SAMPLE_MODEL  # noqa: E402
PREPROCESSOR_DIR = SAMPLE_MODEL / "Preprocessor"
SIMULATION_DIR = SAMPLE_MODEL / "Simulation"
RESULTS_DIR = SAMPLE_MODEL / "Results"
BUDGET_DIR = SAMPLE_MODEL / "Budget"


@pytest.fixture(scope="session")
def sample_model():
    """Path to the sample_model directory (skips when absent)."""
    if not SAMPLE_MODEL.is_dir():
        pytest.skip("sample model not present (.assets/sample_model)")
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
