"""Tests for model comparison: file diffs and result differences."""

import shutil

import numpy as np
import pytest

from iwfm_io import (
    budget_difference,
    compare_models,
    diff_model_files,
    head_difference,
    open_model,
)

from .conftest import SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")


# ---------------------------------------------------------------------------
# diff_model_files
# ---------------------------------------------------------------------------

@pytest.fixture
def two_dirs(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    (a / "sub").mkdir(parents=True)
    (b / "sub").mkdir(parents=True)
    (a / "same.dat").write_text("identical content\n")
    (b / "same.dat").write_text("identical content\n")
    (a / "sub" / "changed.dat").write_text("value = 1\n")
    (b / "sub" / "changed.dat").write_text("value = 2\n")
    (a / "only_a.dat").write_text("a only\n")
    (b / "only_b.dat").write_text("b only\n")
    # Same size, different bytes — must be caught by hashing, not size
    (a / "samesize.dat").write_text("AAAA")
    (b / "samesize.dat").write_text("AAAB")
    return a, b


def test_diff_model_files(two_dirs):
    a, b = two_dirs
    d = diff_model_files(a, b)
    assert d["only_in_a"] == ["only_a.dat"]
    assert d["only_in_b"] == ["only_b.dat"]
    assert d["changed"] == ["samesize.dat", "sub/changed.dat"]
    assert d["identical"] == ["same.dat"]
    assert d["n_compared"] == 3


def test_diff_model_files_subdirs(two_dirs):
    a, b = two_dirs
    d = diff_model_files(a, b, subdirs=["sub"])
    assert d["changed"] == ["sub/changed.dat"]
    assert d["only_in_a"] == [] and d["only_in_b"] == []


def test_diff_model_files_serial_matches_parallel(two_dirs):
    a, b = two_dirs
    assert diff_model_files(a, b, max_workers=1) == diff_model_files(
        a, b, max_workers=8)


# ---------------------------------------------------------------------------
# Numeric differences (sample model vs itself → all zeros)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def model():
    return open_model(SAMPLE_MODEL)


def test_head_difference_self_is_zero(model):
    diff = head_difference(model, model, layer=1)
    assert diff.shape == (3654, 441)
    assert float(np.abs(diff.values).max()) == 0.0


def test_budget_difference_self_is_zero(model):
    diff = budget_difference(model, model, "GW", location=1, interval="1YEAR")
    assert len(diff) > 0
    assert float(np.abs(diff.values).max()) == 0.0


def test_head_difference_accepts_paths():
    diff = head_difference(SAMPLE_MODEL, SAMPLE_MODEL, layer=2,
                           begin_date="10/01/1999_24:00")
    assert len(diff) < 400  # date-restricted
    assert float(np.abs(diff.values).max()) == 0.0


# ---------------------------------------------------------------------------
# compare_models
# ---------------------------------------------------------------------------

def test_compare_models_self(model):
    import json
    report = compare_models(model, model)
    json.dumps(report)  # must be JSON-serializable
    assert report["grid"]["identical"] is True
    assert report["files"]["changed"] == []
    assert report["files"]["only_in_a"] == []
    assert report["heads"]["layer_1"]["rmse"] == 0.0
    assert report["heads"]["layer_2"]["max_abs_diff"] == 0.0
    assert "GW" in report["budgets"]["common"]


def test_compare_models_detects_changed_input(model, tmp_path):
    # Copy only the input folders (Results not needed for a file diff)
    clone = tmp_path / "clone"
    for sub in ("Preprocessor", "Simulation"):
        shutil.copytree(SAMPLE_MODEL / sub, clone / sub)

    strata = clone / "Preprocessor" / "Strata.dat"
    strata.write_text(strata.read_text().replace("1.0", "2.0", 1))

    d = diff_model_files(SAMPLE_MODEL, clone,
                         subdirs=["Preprocessor", "Simulation"])
    assert "Preprocessor/Strata.dat" in d["changed"]
    assert d["only_in_a"] == [] and d["only_in_b"] == []

    report = compare_models(SAMPLE_MODEL, clone,
                            file_subdirs=["Preprocessor", "Simulation"])
    assert "Preprocessor/Strata.dat" in report["files"]["changed"]
    assert report["heads"] is None  # clone has no Results
