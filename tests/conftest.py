"""Root pytest configuration shared by every test package.

Environment markers (registered in ``pyproject.toml``) replace the ad-hoc
``skipif`` blocks: mark a module with ``pytestmark = pytest.mark.sample_model``
(or ``exe`` / ``dll`` / ``c2vsimfg``) and it skips when that resource is
absent. Probes run once per session.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_MODEL = REPO_ROOT / ".assets" / "sample_model"
C2VSIMFG_DIR = Path(os.environ.get(
    "IWFM_C2VSIMFG_DIR", str(REPO_ROOT / ".assets" / "c2vsimfg_v1.5")))

# Results files larger than this are not copied by ``sample_model_copy``
# (the zone-budget HDFs run to hundreds of MB and are optional, regenerable).
_COPY_SIZE_LIMIT = 50 * 1024 * 1024


def _dll_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        from iwfm_io.dll import load_dll
        load_dll()
        return True
    except Exception:
        return False


def _exe_available() -> bool:
    return (bool(os.environ.get("IWFM_RUN_EXE_TESTS"))
            and sys.platform == "win32"
            and (SAMPLE_MODEL / "Bin" / "Simulation_x64.exe").exists())


_PROBES = {
    "sample_model": (lambda: SAMPLE_MODEL.is_dir(),
                     "sample model not present (.assets/sample_model)"),
    "exe": (_exe_available,
            "exe tests run only with IWFM_RUN_EXE_TESTS=1 on Windows with "
            "the sample model executables"),
    "dll": (_dll_available, "IWFM DLL not available (Windows x64 only)"),
    "c2vsimfg": (lambda: C2VSIMFG_DIR.is_dir(),
                 "C2VSimFG v1.5 not present (set IWFM_C2VSIMFG_DIR)"),
}


def pytest_configure(config):
    import matplotlib
    matplotlib.use("Agg")


def pytest_collection_modifyitems(config, items):
    cache: dict[str, bool] = {}
    for item in items:
        for name, (probe, reason) in _PROBES.items():
            if name in item.keywords:
                if name not in cache:
                    cache[name] = bool(probe())
                if not cache[name]:
                    item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def sample_model() -> Path:
    """Path to the read-only sample model (skips when absent)."""
    if not SAMPLE_MODEL.is_dir():
        pytest.skip("sample model not present (.assets/sample_model)")
    return SAMPLE_MODEL


def copy_sample_model(dest: Path, *, results: bool = True) -> Path:
    """Copy the sample model into ``dest`` (inputs, control files, and
    Results files under the size limit). Never touches the original."""
    dest = Path(dest)
    for sub in ("Preprocessor", "Simulation", "Budget", "ZBudget", "Bin"):
        src = SAMPLE_MODEL / sub
        if src.is_dir():
            shutil.copytree(src, dest / sub)
    res = dest / "Results"
    res.mkdir(parents=True, exist_ok=True)
    if results and (SAMPLE_MODEL / "Results").is_dir():
        for f in (SAMPLE_MODEL / "Results").iterdir():
            if f.is_file() and f.stat().st_size <= _COPY_SIZE_LIMIT:
                shutil.copy2(f, res / f.name)
    return dest


@pytest.fixture
def sample_model_copy(sample_model, tmp_path) -> Path:
    """A disposable full copy of the sample model under ``tmp_path/model``.

    Use this for anything that edits, corrupts, or runs the model.
    """
    return copy_sample_model(tmp_path / "model")


@pytest.fixture(scope="module")
def open_sample(sample_model):
    """A module-scoped ``IOModelAdapter`` on the read-only sample model."""
    from iwfm_io import open_model
    return open_model(sample_model)
