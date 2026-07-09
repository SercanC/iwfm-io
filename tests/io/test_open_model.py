"""Tests for iwfm_io.open_model() discovery and describe() summaries."""

import json

import pytest

from iwfm_io import open_model, read_preprocessor

from .conftest import SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")


@pytest.fixture(scope="module")
def model(sample_model_root):
    return open_model(sample_model_root)


@pytest.fixture(scope="module")
def sample_model_root():
    from .conftest import SAMPLE_MODEL
    return SAMPLE_MODEL


def test_open_model_from_root(model):
    assert model.n_nodes == 441
    assert model.n_elements == 400
    assert model.n_layers == 2


def test_open_model_from_main_file(sample_model_root):
    m = open_model(sample_model_root / "Preprocessor" / "PreProcessor_MAIN.IN")
    assert m.n_nodes == 441


def test_open_model_missing_path():
    with pytest.raises(FileNotFoundError):
        open_model("does/not/exist")


def test_open_model_discovers_results(model):
    assert model._heads_hdf is not None
    assert "GW" in model._budget_hdfs
    assert model._budget_hdfs  # several budgets found
    assert model._hydrograph_hdfs


def test_describe_is_json_serializable(model):
    d = model.describe()
    text = json.dumps(d)
    assert "grid" in d and "results" in d
    assert d["grid"]["n_nodes"] == 441
    assert d["grid"]["n_layers"] == 2
    assert d["simulation"]["timestep"] == "1DAY"
    assert "GW" in d["results"]["budgets"]
    assert isinstance(text, str)


def test_describe_budget_locations(model):
    d = model.describe()
    gw_locs = d["results"]["budgets"]["GW"]["locations"]
    assert "ENTIRE MODEL AREA" in gw_locs


def test_heads_and_budget_load(model):
    heads = model.heads_df(layer=1)
    assert heads.shape[1] == 441
    bud = model.budget_df("GW", location=1)
    assert len(bud) > 0


def test_repr(model):
    text = repr(model)
    assert "441 nodes" in text


def test_preprocessor_properties(preprocessor_dir):
    pp = read_preprocessor(preprocessor_dir / "PreProcessor_MAIN.IN")
    assert len(pp.nodes) == 441
    assert len(pp.elements) == 400
    assert pp.n_layers == 2
    assert len(pp.subregions) == 2
    assert len(pp.stream_reaches) == 3
    assert len(pp.stream_nodes) == 23
    assert len(pp.lakes) == 1
    assert "elevation" in pp.stratigraphy.columns


def test_preprocessor_property_error_message(preprocessor_dir):
    pp = read_preprocessor(
        preprocessor_dir / "PreProcessor_MAIN.IN", follow_references=False)
    with pytest.raises(KeyError, match="follow_references"):
        pp.nodes
