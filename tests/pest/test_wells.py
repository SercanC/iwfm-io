"""Tests for multi-layer well observations (iwfm_io.pest.wells)."""

import numpy as np
import pandas as pd
import pytest


class FakeModel:
    """Duck-typed model: 4 nodes, 2 layers.

    GSE 100. Layer 1: depths 0–50. Aquitard: 50–60. Layer 2: 60–100.
    """

    def nodes_df(self):
        return pd.DataFrame({
            "node_id": [1, 2, 3, 4],
            "x": [0.0, 10.0, 0.0, 10.0],
            "y": [0.0, 0.0, 10.0, 10.0],
        })

    def stratigraphy_df(self):
        return pd.DataFrame({
            "node_id": [1, 2, 3, 4],
            "elevation": [100.0] * 4,
            "aquitard_1": [0.0] * 4,
            "aquifer_1": [50.0] * 4,
            "aquitard_2": [10.0] * 4,
            "aquifer_2": [40.0] * 4,
        })


def _kh():
    # node 1: L1 twice as conductive as L2; other nodes uniform
    rows = []
    for n in [1, 2, 3, 4]:
        rows.append((n, 1, 2.0 if n == 1 else 1.0))
        rows.append((n, 2, 1.0))
    return pd.DataFrame(rows, columns=["node_id", "layer", "kh"])


def _heads(l1=90.0, l2=70.0):
    idx = pd.date_range("2000-01-31", periods=3, freq="ME")
    mk = lambda v: pd.DataFrame(
        {f"node_{n}": v if np.isscalar(v) else v[n - 1] for n in [1, 2, 3, 4]},
        index=idx)
    return {1: mk(l1), 2: mk(l2)}


def _wells(**cols):
    base = {"well_id": ["w1"], "x": [1.0], "y": [1.0]}
    base.update(cols)
    return pd.DataFrame(base)


class TestBuildFractions:
    def test_explicit_layer_wins(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(FakeModel(), _wells(layer=[2],
                                                   perf_top=[0.0],
                                                   perf_bottom=[100.0]))
        w = m.weights
        assert len(w) == 1
        assert w.iloc[0]["layer"] == 2 and w.iloc[0]["weight"] == 1.0
        assert m.wells.iloc[0]["method"] == "layer"

    def test_perforation_transmissivity_weighted(self):
        from iwfm_io.pest import build_well_mapping

        # perf 40–80 at node 1: L1 intersect 10, L2 intersect 20
        # kh (2, 1) -> trans (20, 20) -> 0.5 / 0.5
        m = build_well_mapping(
            FakeModel(), _wells(perf_top=[40.0], perf_bottom=[80.0]),
            kh=_kh())
        w = m.weights.set_index("layer")["weight"]
        assert w[1] == pytest.approx(0.5)
        assert w[2] == pytest.approx(0.5)
        assert m.wells.iloc[0]["method"] == "perforation"

    def test_thickness_only_without_kh(self):
        from iwfm_io.pest import build_well_mapping

        # same interval, kh=1: trans (10, 20) -> 1/3, 2/3
        m = build_well_mapping(
            FakeModel(), _wells(perf_top=[40.0], perf_bottom=[80.0]))
        w = m.weights.set_index("layer")["weight"]
        assert w[1] == pytest.approx(1 / 3)
        assert w[2] == pytest.approx(2 / 3)

    def test_aquitard_interval_falls_back_to_layer1(self, caplog):
        from iwfm_io.pest import build_well_mapping

        with caplog.at_level("WARNING"):
            m = build_well_mapping(
                FakeModel(), _wells(perf_top=[52.0], perf_bottom=[58.0]))
        w = m.weights
        assert w.iloc[0]["layer"] == 1 and w.iloc[0]["weight"] == 1.0
        assert m.wells.iloc[0]["method"] == "no_intersect"
        assert "no aquifer layer" in caplog.text

    def test_below_model_bottom_gets_deepest(self, caplog):
        from iwfm_io.pest import build_well_mapping

        with caplog.at_level("WARNING"):
            m = build_well_mapping(
                FakeModel(), _wells(perf_top=[120.0], perf_bottom=[150.0]))
        assert m.weights.iloc[0]["layer"] == 2
        assert m.wells.iloc[0]["method"] == "below_model"

    def test_unknown_gets_default_layer(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(FakeModel(), _wells(), default_layer=2)
        assert m.weights.iloc[0]["layer"] == 2
        assert m.wells.iloc[0]["method"] == "default"

    def test_nearest_node_assignment(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(FakeModel(), _wells(x=[9.0], y=[8.0]))
        assert m.wells.iloc[0]["node"] == 4

    def test_idw_spreads_over_neighbors(self):
        from iwfm_io.pest import build_well_mapping

        # center point equidistant from all 4 nodes -> 0.25 each
        m = build_well_mapping(FakeModel(), _wells(x=[5.0], y=[5.0]),
                               spatial="idw", k=4, default_layer=1)
        w = m.weights
        assert len(w) == 4
        assert w["weight"].values == pytest.approx([0.25] * 4)
        assert w["weight"].sum() == pytest.approx(1.0)

    def test_idw_exact_hit_collapses_to_node(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(FakeModel(), _wells(x=[10.0], y=[0.0]),
                               spatial="idw", k=4)
        assert len(m.weights) == 1
        assert m.weights.iloc[0]["node"] == 2

    def test_input_validation(self):
        from iwfm_io.pest import build_well_mapping

        with pytest.raises(ValueError, match="spatial"):
            build_well_mapping(FakeModel(), _wells(), spatial="kriging")
        with pytest.raises(ValueError, match="well_id"):
            build_well_mapping(FakeModel(), pd.DataFrame({"x": [1]}))


class TestComposite:
    def test_composite_mixed_layers(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(
            FakeModel(), _wells(perf_top=[40.0], perf_bottom=[80.0]),
            kh=_kh())
        out = m.composite(_heads(l1=90.0, l2=70.0))
        # 0.5 * 90 + 0.5 * 70 = 80
        assert out["w1"].values == pytest.approx([80.0] * 3)

    def test_composite_from_multiindex_frame(self):
        from iwfm_io.pest import build_well_mapping
        from iwfm_io.wells import _canonical_heads

        m = build_well_mapping(FakeModel(), _wells(layer=[1]))
        canon = _canonical_heads(_heads(), 2)
        out = m.composite(canon)
        assert out["w1"].values == pytest.approx([90.0] * 3)

    def test_composite_from_node_layer_columns(self):
        from iwfm_io.pest import build_well_mapping

        idx = pd.date_range("2000-01-31", periods=2, freq="ME")
        flat = pd.DataFrame(
            {f"node_{n}_layer_{l}": [50.0 * l] * 2
             for n in [1, 2, 3, 4] for l in [1, 2]}, index=idx)
        m = build_well_mapping(FakeModel(), _wells(layer=[2]))
        out = m.composite(flat)
        assert out["w1"].values == pytest.approx([100.0, 100.0])

    def test_composite_missing_columns_raise(self):
        from iwfm_io.pest import build_well_mapping

        m = build_well_mapping(FakeModel(), _wells(layer=[2]))
        only_l1 = {1: _heads()[1]}
        with pytest.raises(KeyError, match="missing"):
            m.composite(only_l1)

    def test_composite_model_duck_path(self):
        from iwfm_io.pest import build_well_mapping

        class ModelWithHeads(FakeModel):
            def heads_df(self, layer):
                return _heads()[layer]

        m = build_well_mapping(ModelWithHeads(), _wells(layer=[2]))
        out = m.composite(ModelWithHeads())
        assert out["w1"].values == pytest.approx([70.0] * 3)


class TestPersistence:
    def test_csv_round_trip(self, tmp_path):
        from iwfm_io.pest import WellMapping, build_well_mapping

        m = build_well_mapping(
            FakeModel(),
            pd.DataFrame({
                "well_id": ["w1", "w2"], "x": [1.0, 9.0], "y": [1.0, 9.0],
                "perf_top": [40.0, np.nan], "perf_bottom": [80.0, np.nan],
                "layer": [np.nan, 2],
            }), kh=_kh())
        f = tmp_path / "mapping.csv"
        m.to_csv(f)
        back = WellMapping.from_csv(f)
        assert back.n_layers == 2
        pd.testing.assert_frame_equal(
            back.weights.sort_values(["well_id", "layer"]).reset_index(drop=True),
            m.weights.sort_values(["well_id", "layer"]).reset_index(drop=True),
            check_dtype=False)
        a = m.composite(_heads())
        b = back.composite(_heads())
        pd.testing.assert_frame_equal(a, b, check_names=False)


class TestBestLayers:
    def test_picks_matching_layer(self):
        from iwfm_io.pest import build_well_mapping, select_best_layers

        m = build_well_mapping(FakeModel(), _wells())
        idx = pd.date_range("2000-01-31", periods=8, freq="ME")
        heads = {
            1: pd.DataFrame({f"node_{n}": 90.0 for n in [1, 2, 3, 4]},
                            index=idx),
            2: pd.DataFrame({f"node_{n}": 70.0 for n in [1, 2, 3, 4]},
                            index=idx),
        }
        obs = pd.DataFrame({
            "site": "w1", "datetime": idx,
            "value": 71.0 + np.linspace(0, 1, 8)})
        picked = select_best_layers(m, heads, obs)
        assert picked["w1"] == 2

    def test_too_few_obs_gets_default(self, caplog):
        from iwfm_io.pest import build_well_mapping, select_best_layers

        m = build_well_mapping(FakeModel(), _wells())
        idx = pd.date_range("2000-01-31", periods=3, freq="ME")
        heads = {l: pd.DataFrame(
            {f"node_{n}": 80.0 for n in [1, 2, 3, 4]}, index=idx)
            for l in [1, 2]}
        obs = pd.DataFrame({"site": "w1", "datetime": idx[:2],
                            "value": [80.0, 80.0]})
        with caplog.at_level("WARNING"):
            picked = select_best_layers(m, heads, obs, min_n=6,
                                        default_layer=2)
        assert picked["w1"] == 2
        assert "aligned observation" in caplog.text

    def test_rebuild_with_selected_layers(self):
        from iwfm_io.pest import build_well_mapping, select_best_layers

        wells = _wells()
        m = build_well_mapping(FakeModel(), wells)
        idx = pd.date_range("2000-01-31", periods=8, freq="ME")
        heads = {
            1: pd.DataFrame({f"node_{n}": 90.0 for n in [1, 2, 3, 4]},
                            index=idx),
            2: pd.DataFrame({f"node_{n}": 70.0 for n in [1, 2, 3, 4]},
                            index=idx),
        }
        obs = pd.DataFrame({"site": "w1", "datetime": idx, "value": 69.5})
        wells["layer"] = select_best_layers(m, heads, obs).reindex(
            wells["well_id"].astype(str)).values
        m2 = build_well_mapping(FakeModel(), wells)
        assert m2.wells.iloc[0]["method"] == "layer"
        assert m2.composite(heads)["w1"].iloc[0] == pytest.approx(70.0)
