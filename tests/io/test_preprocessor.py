"""Tests for iwfm.io preprocessor readers and writers."""

from pathlib import Path

import pandas as pd
import pytest

from tests.io.conftest import PREPROCESSOR_DIR, SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")

from iwfm.io.readers.preprocessor import (
    read_elements,
    read_lake_geom,
    read_nodes,
    read_preprocessor_main,
    read_strata,
    read_stream_geom,
)
from iwfm.io.writers.preprocessor import (
    write_elements,
    write_lake_geom,
    write_nodes,
    write_strata,
    write_stream_geom,
)


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------

class TestNodes:
    def test_read_nodes_shape(self):
        nf = read_nodes(PREPROCESSOR_DIR / "NodeXY.dat")
        assert len(nf.data) == 441
        assert list(nf.data.columns[:3]) == ["node_id", "x", "y"]
        assert nf.factor.value == pytest.approx(3.2808)

    def test_read_nodes_first_row(self):
        nf = read_nodes(PREPROCESSOR_DIR / "NodeXY.dat")
        row = nf.data.iloc[0]
        assert int(row["node_id"]) == 1
        assert row["x"] == pytest.approx(550000.0)
        assert row["y"] == pytest.approx(4400000.0)

    def test_nodes_round_trip(self, tmp_output):
        nf = read_nodes(PREPROCESSOR_DIR / "NodeXY.dat")
        out = tmp_output / "NodeXY_rt.dat"
        write_nodes(nf, out)
        nf2 = read_nodes(out)
        pd.testing.assert_frame_equal(
            nf.data[["node_id", "x", "y"]].reset_index(drop=True),
            nf2.data[["node_id", "x", "y"]].reset_index(drop=True),
        )


# ------------------------------------------------------------------
# Elements
# ------------------------------------------------------------------

class TestElements:
    def test_read_elements_shape(self):
        ef = read_elements(PREPROCESSOR_DIR / "Element.dat")
        assert len(ef.data) == 400
        assert len(ef.subregions) == 2

    def test_read_elements_subregions(self):
        ef = read_elements(PREPROCESSOR_DIR / "Element.dat")
        assert ef.subregions["name"].tolist() == ["Region1", "Region2"]

    def test_read_elements_first_row(self):
        ef = read_elements(PREPROCESSOR_DIR / "Element.dat")
        row = ef.data.iloc[0]
        assert int(row["element_id"]) == 1
        assert int(row["node1"]) == 1
        assert int(row["node2"]) == 2
        assert int(row["node3"]) == 23
        assert int(row["node4"]) == 22
        assert int(row["subregion"]) == 1

    def test_elements_with_geometry(self):
        nf = read_nodes(PREPROCESSOR_DIR / "NodeXY.dat")
        ef = read_elements(PREPROCESSOR_DIR / "Element.dat", node_file=nf)
        assert "geometry" in ef.data.columns
        assert ef.data.iloc[0].geometry is not None

    def test_elements_round_trip(self, tmp_output):
        ef = read_elements(PREPROCESSOR_DIR / "Element.dat")
        out = tmp_output / "Element_rt.dat"
        write_elements(ef, out)
        ef2 = read_elements(out)
        cols = ["element_id", "node1", "node2", "node3", "node4", "subregion"]
        pd.testing.assert_frame_equal(
            ef.data[cols].reset_index(drop=True),
            ef2.data[cols].reset_index(drop=True),
        )


# ------------------------------------------------------------------
# Stratigraphy
# ------------------------------------------------------------------

class TestStratigraphy:
    def test_read_strata_shape(self):
        sf = read_strata(PREPROCESSOR_DIR / "Strata.dat")
        assert sf.n_layers == 2
        assert len(sf.data) == 441
        assert "aquitard_1" in sf.data.columns
        assert "aquifer_2" in sf.data.columns

    def test_read_strata_values(self):
        sf = read_strata(PREPROCESSOR_DIR / "Strata.dat")
        row = sf.data.iloc[0]
        assert int(row["node_id"]) == 1
        assert row["elevation"] == pytest.approx(500.0)
        assert row["aquitard_1"] == pytest.approx(0.0)
        assert row["aquifer_1"] == pytest.approx(500.0)

    def test_strata_round_trip(self, tmp_output):
        sf = read_strata(PREPROCESSOR_DIR / "Strata.dat")
        out = tmp_output / "Strata_rt.dat"
        write_strata(sf, out)
        sf2 = read_strata(out)
        pd.testing.assert_frame_equal(
            sf.data.reset_index(drop=True),
            sf2.data.reset_index(drop=True),
        )


# ------------------------------------------------------------------
# Stream Geometry
# ------------------------------------------------------------------

class TestStreamGeom:
    def test_read_stream_geom_reaches(self):
        sg = read_stream_geom(PREPROCESSOR_DIR / "Stream.dat")
        assert len(sg.reaches) == 3
        assert sg.reaches["name"].tolist() == ["Reach1", "Reach2", "Reach3"]

    def test_read_stream_geom_nodes(self):
        sg = read_stream_geom(PREPROCESSOR_DIR / "Stream.dat")
        assert len(sg.nodes) == 23

    def test_read_stream_geom_rating_tables(self):
        sg = read_stream_geom(PREPROCESSOR_DIR / "Stream.dat")
        assert sg.n_rating_points == 5
        # 23 nodes × 5 points each = 115 rating table rows
        assert len(sg.rating_tables) == 115

    def test_stream_geom_with_node_geometry(self):
        nf = read_nodes(PREPROCESSOR_DIR / "NodeXY.dat")
        sg = read_stream_geom(PREPROCESSOR_DIR / "Stream.dat", node_file=nf)
        assert "geometry" in sg.nodes.columns

    def test_stream_round_trip(self, tmp_output):
        sg = read_stream_geom(PREPROCESSOR_DIR / "Stream.dat")
        out = tmp_output / "Stream_rt.dat"
        write_stream_geom(sg, out)
        sg2 = read_stream_geom(out)
        assert len(sg2.reaches) == len(sg.reaches)
        assert len(sg2.nodes) == len(sg.nodes)
        pd.testing.assert_frame_equal(
            sg.nodes[["stream_node_id", "reach_id", "gw_node_id"]].reset_index(drop=True),
            sg2.nodes[["stream_node_id", "reach_id", "gw_node_id"]].reset_index(drop=True),
        )


# ------------------------------------------------------------------
# Lake Geometry
# ------------------------------------------------------------------

class TestLakeGeom:
    def test_read_lake_geom(self):
        lg = read_lake_geom(PREPROCESSOR_DIR / "Lake.dat")
        assert len(lg.data) == 1
        lake = lg.data.iloc[0]
        assert int(lake["lake_id"]) == 1
        assert int(lake["dest_type"]) == 1
        assert int(lake["dest_id"]) == 11
        assert int(lake["n_elements"]) == 10
        assert len(lake["elements"]) == 10

    def test_lake_round_trip(self, tmp_output):
        lg = read_lake_geom(PREPROCESSOR_DIR / "Lake.dat")
        out = tmp_output / "Lake_rt.dat"
        write_lake_geom(lg, out)
        lg2 = read_lake_geom(out)
        assert len(lg2.data) == len(lg.data)
        assert lg2.data.iloc[0]["elements"] == lg.data.iloc[0]["elements"]


# ------------------------------------------------------------------
# Preprocessor Main
# ------------------------------------------------------------------

class TestPreprocessorMain:
    def test_read_preprocessor_main_no_follow(self):
        pp = read_preprocessor_main(
            PREPROCESSOR_DIR / "PreProcessor_MAIN.IN",
            follow_references=False,
        )
        assert len(pp.titles) == 3
        assert pp.config["kout"] == 1
        assert pp.config["kdeb"] == 2
        assert pp.config["factltou"] == pytest.approx(1.0)
        assert pp.config["unitltou"] == "FEET"

    def test_read_preprocessor_main_with_children(self):
        pp = read_preprocessor_main(
            PREPROCESSOR_DIR / "PreProcessor_MAIN.IN",
            follow_references=True,
        )
        assert "node" in pp.children
        assert "element" in pp.children
        assert "strata" in pp.children
        assert "stream" in pp.children
        assert "lake" in pp.children
        assert len(pp.children["node"].data) == 441
        assert len(pp.children["element"].data) == 400
