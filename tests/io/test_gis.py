"""Tests for GIS exports (iwfm_io.gis)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"

pytestmark = pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                                reason="sample model not available")


@pytest.fixture(scope="module")
def model():
    from iwfm_io import open_model

    return open_model(SAMPLE_MODEL)


ELEM_AREA = 2000.0 * 2000.0  # sample model: uniform 2000 ft quad elements


class TestLayerBuilders:
    def test_nodes_points_with_stratigraphy(self, model):
        from iwfm_io import nodes_gdf

        g = nodes_gdf(model)
        assert len(g) == 441
        assert (g.geometry.geom_type == "Point").all()
        # stratigraphy joined by default
        assert "elevation" in g.columns and "aquifer_2" in g.columns
        row = g.iloc[0]
        assert row.geometry.x == row["x"] and row.geometry.y == row["y"]

    def test_nodes_data_join_and_collision(self, model):
        from iwfm_io import nodes_gdf

        data = pd.DataFrame({"node_id": [1, 2], "dtw": [10.0, 20.0]})
        g = nodes_gdf(model, data=data)
        by_id = g.set_index("node_id")
        assert by_id.loc[1, "dtw"] == 10.0
        assert np.isnan(by_id.loc[3, "dtw"])          # left join
        with pytest.raises(ValueError, match="collide"):
            nodes_gdf(model, data=pd.DataFrame({"node_id": [1], "x": [0.0]}))
        with pytest.raises(ValueError, match="node_id"):
            nodes_gdf(model, data=pd.DataFrame({"dtw": [1.0]}))

    def test_elements_polygons(self, model):
        from iwfm_io import elements_gdf

        g = elements_gdf(model)
        assert len(g) == 400
        assert (g.geometry.geom_type == "Polygon").all()
        assert g.geometry.area.values == pytest.approx([ELEM_AREA] * 400)
        assert "subregion_name" in g.columns
        assert set(g["subregion_name"]) == {"Region1", "Region2"}

    def test_subregions_dissolved(self, model):
        from iwfm_io import subregions_gdf

        g = subregions_gdf(model)
        assert len(g) == 2
        assert g["n_elements"].tolist() == [200, 200]
        # dissolve preserves total area exactly on this uniform grid
        assert g["area"].values == pytest.approx([200 * ELEM_AREA] * 2)
        assert g.geometry.area.values == pytest.approx(g["area"].values)
        assert g["name"].tolist() == ["Region1", "Region2"]

    def test_streams_lines(self, model):
        from iwfm_io import streams_gdf

        g = streams_gdf(model)
        assert len(g) == 3
        assert (g.geometry.geom_type == "LineString").all()
        # reach 1 has 10 stream nodes -> 10 vertices
        assert len(g.iloc[0].geometry.coords) == 10
        assert g["name"].tolist() == ["Reach1", "Reach2", "Reach3"]

    def test_stream_nodes_points(self, model):
        from iwfm_io import stream_nodes_gdf

        g = stream_nodes_gdf(model)
        assert len(g) == 23
        # positioned at their GW nodes
        nodes = model.nodes_df().set_index("node_id")
        row = g.iloc[0]
        assert row.geometry.x == nodes.loc[int(row["gw_node_id"]), "x"]

    def test_lakes_merged(self, model):
        from iwfm_io import lakes_gdf

        g = lakes_gdf(model)
        assert len(g) == 1
        assert g.iloc[0]["n_elements"] == 10
        assert g.geometry.area.values == pytest.approx([10 * ELEM_AREA])
        assert "elements" not in g.columns    # list column not exportable

    def test_tile_drains_and_wells(self, model):
        from iwfm_io import tile_drains_gdf, wells_gdf

        td = tile_drains_gdf(model)
        assert len(td) == 21
        assert (td.geometry.geom_type == "Point").all()
        assert wells_gdf(model).empty         # sample pumps by element

    def test_crs_applied(self, model):
        from iwfm_io import nodes_gdf

        assert nodes_gdf(model).crs is None
        assert nodes_gdf(model, crs="EPSG:26910").crs.to_epsg() == 26910


class TestExportGis:
    def test_geopackage_round_trip(self, model, tmp_path):
        from iwfm_io import export_gis

        out = tmp_path / "model.gpkg"
        written = export_gis(model, out, crs="EPSG:26910")
        # wells is empty on the sample model and skipped by default
        assert written == {"nodes": 441, "elements": 400, "subregions": 2,
                           "streams": 3, "stream_nodes": 23, "lakes": 1,
                           "tile_drains": 21}
        for layer, n in written.items():
            back = gpd.read_file(out, layer=layer)
            assert len(back) == n, layer
            assert back.crs is not None and back.crs.to_epsg() == 26910

    def test_geopackage_replaced_not_appended(self, model, tmp_path):
        from iwfm_io import export_gis

        out = tmp_path / "model.gpkg"
        export_gis(model, out, layers=["nodes"])
        export_gis(model, out, layers=["nodes"])
        assert len(gpd.read_file(out, layer="nodes")) == 441

    def test_shapefile_directory(self, model, tmp_path):
        from iwfm_io import export_gis

        out = tmp_path / "shp"
        written = export_gis(model, out, layers=["nodes", "streams"])
        assert set(written) == {"nodes", "streams"}
        assert (out / "nodes.shp").is_file()
        assert len(gpd.read_file(out / "streams.shp")) == 3

    def test_data_joins_through_export(self, model, tmp_path):
        from iwfm_io import export_gis

        heads = model.heads_df(layer=1)
        node_data = pd.DataFrame({
            "node_id": model.nodes_df()["node_id"],
            "head_end": heads.iloc[-1].values,
        })
        elem_data = pd.DataFrame({
            "element_id": model.elements_df()["element_id"],
            "zone": "a",
        })
        out = tmp_path / "m.gpkg"
        export_gis(model, out, layers=["nodes", "elements"],
                   node_data=node_data, element_data=elem_data)
        nb = gpd.read_file(out, layer="nodes")
        assert nb["head_end"].notna().all()
        eb = gpd.read_file(out, layer="elements")
        assert (eb["zone"] == "a").all()

    def test_unknown_layer_raises(self, model, tmp_path):
        from iwfm_io import export_gis

        with pytest.raises(ValueError, match="unknown GIS layer"):
            export_gis(model, tmp_path / "m.gpkg", layers=["nodes", "rivers"])

    def test_explicit_missing_layer_raises(self, tmp_path):
        from iwfm_io import export_gis, read_preprocessor

        # a model source with grid only — no streams
        class GridOnly:
            def __init__(self):
                pp = read_preprocessor(
                    SAMPLE_MODEL / "Preprocessor" / "PreProcessor_MAIN.IN")
                self._pp = pp

            def nodes_df(self):
                return self._pp.nodes

            def elements_df(self):
                return self._pp.elements

            def stream_nodes_df(self):
                raise RuntimeError("no stream file")

            def reaches_df(self):
                raise RuntimeError("no stream file")

        src = GridOnly()
        with pytest.raises(RuntimeError, match="no stream file"):
            export_gis(src, tmp_path / "m.gpkg", layers=["streams"])
        # default mode skips it instead
        written = export_gis(src, tmp_path / "m2.gpkg")
        assert "streams" not in written and "nodes" in written

    def test_adapter_to_gis_delegates(self, model, tmp_path):
        out = tmp_path / "adapter.gpkg"
        written = model.to_gis(out, layers=["subregions"])
        assert written == {"subregions": 2}
        assert out.is_file()
