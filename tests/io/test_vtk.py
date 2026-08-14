"""Tests for VTK exports (iwfm_io.vtk).

Validates the written XML directly (ElementTree + numpy) so no VTK
library is needed. Cell orientation (positive volumes for both wedges
and hexahedra) was additionally verified against pyvista's
``compute_cell_sizes`` on the sample model and C2VSimFG v1.5.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"


class TriQuadModel:
    """Two triangles + aquitard gap between two aquifer layers."""

    def nodes_df(self):
        return pd.DataFrame({"node_id": [1, 2, 3, 4],
                             "x": [0.0, 100.0, 0.0, 100.0],
                             "y": [0.0, 0.0, 100.0, 100.0]})

    def elements_df(self):
        return pd.DataFrame({"element_id": [1, 2],
                             "node1": [1, 2], "node2": [2, 4],
                             "node3": [3, 3], "node4": [0, 0],
                             "subregion": [1, 2]})

    def stratigraphy_df(self):
        return pd.DataFrame({"node_id": [1, 2, 3, 4],
                             "elevation": [100.0] * 4,
                             "aquitard_1": [0.0] * 4,
                             "aquifer_1": [50.0] * 4,
                             "aquitard_2": [10.0] * 4,
                             "aquifer_2": [40.0] * 4})


def _read_vtu(path):
    """Parse a .vtu into {'points': (n,3), 'connectivity', 'offsets',
    'types', point/cell arrays by name}."""
    root = ET.parse(path).getroot()
    piece = root.find("./UnstructuredGrid/Piece")
    out = {"n_points": int(piece.get("NumberOfPoints")),
           "n_cells": int(piece.get("NumberOfCells"))}

    def arr(el):
        return np.array(el.text.split(), dtype=float)

    out["points"] = arr(piece.find("./Points/DataArray")).reshape(-1, 3)
    for el in piece.findall("./Cells/DataArray"):
        out[el.get("Name")] = arr(el)
    for section, prefix in (("PointData", "p:"), ("CellData", "c:")):
        sec = piece.find(section)
        if sec is not None:
            for el in sec.findall("DataArray"):
                out[prefix + el.get("Name")] = arr(el)
    return out


class TestSyntheticMesh:
    def test_counts_and_types(self, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(TriQuadModel(), tmp_path / "tri")
        assert info["path"].endswith(".vtu")          # suffix appended
        v = _read_vtu(info["path"])
        assert v["n_points"] == 4 * 2 * 2             # nodes x sheets x layers
        assert v["n_cells"] == 2 * 2
        assert set(v["types"]) == {13.0}              # all wedges
        assert v["offsets"].tolist() == [6, 12, 18, 24]
        assert len(v["connectivity"]) == 24

    def test_layer_elevations_and_aquitard_gap(self, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(TriQuadModel(), tmp_path / "tri.vtu")
        z = np.unique(_read_vtu(info["path"])["points"][:, 2])
        # layer 1: 100 -> 50; aquitard 10; layer 2: 40 -> 0
        assert z.tolist() == [0.0, 40.0, 50.0, 100.0]

    def test_z_scale(self, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(TriQuadModel(), tmp_path / "s.vtu", z_scale=3.0)
        z = np.unique(_read_vtu(info["path"])["points"][:, 2])
        assert z.tolist() == [0.0, 120.0, 150.0, 300.0]

    def test_wedge_orientation_first_face_is_top(self, tmp_path):
        from iwfm_io import export_vtk

        # VTK_WEDGE wants its first triangle on the opposite side from
        # a hexahedron's first quad; regressing this flips cell volumes
        # negative in ParaView.
        info = export_vtk(TriQuadModel(), tmp_path / "o.vtu")
        v = _read_vtu(info["path"])
        conn = v["connectivity"].astype(int)
        z = v["points"][:, 2]
        first_tri, second_tri = conn[:3], conn[3:6]
        assert (z[first_tri] > z[second_tri]).all()

    def test_default_arrays(self, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(TriQuadModel(), tmp_path / "d.vtu")
        v = _read_vtu(info["path"])
        assert v["c:layer"].tolist() == [1.0, 1.0, 2.0, 2.0]
        assert v["c:element_id"].tolist() == [1.0, 2.0, 1.0, 2.0]
        assert v["c:subregion"].tolist() == [1.0, 2.0, 1.0, 2.0]
        assert v["c:thickness"].tolist() == [50.0, 50.0, 40.0, 40.0]
        assert set(v["p:node_id"]) == {1.0, 2.0, 3.0, 4.0}

    def test_point_and_cell_data_shapes(self, tmp_path):
        from iwfm_io import export_vtk

        per_node = np.array([10.0, 20.0, 30.0, 40.0])
        per_node_layer = np.column_stack([per_node, per_node + 1])
        per_elem_layer = np.array([[1.0, 2.0], [3.0, 4.0]])

        info = export_vtk(
            TriQuadModel(), tmp_path / "data.vtu",
            point_data={"gse": per_node, "head": per_node_layer},
            cell_data={"kh": per_elem_layer})
        v = _read_vtu(info["path"])
        # (n,) tiles to every sheet
        assert v["p:gse"].reshape(4, 4).tolist() == [per_node.tolist()] * 4
        # (n, n_layers): layer 1 sheets then layer 2 sheets
        assert v["p:head"][:8].tolist() == per_node.tolist() * 2
        assert v["p:head"][8:].tolist() == (per_node + 1).tolist() * 2
        assert v["c:kh"].tolist() == [1.0, 3.0, 2.0, 4.0]

    def test_bad_shapes_raise(self, tmp_path):
        from iwfm_io import export_vtk

        with pytest.raises(ValueError, match="point array 'bad'"):
            export_vtk(TriQuadModel(), tmp_path / "x.vtu",
                       point_data={"bad": np.zeros(3)})
        with pytest.raises(ValueError, match="cell array 'bad'"):
            export_vtk(TriQuadModel(), tmp_path / "y.vtu",
                       cell_data={"bad": np.zeros(5)})

    def test_layer_subset(self, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(TriQuadModel(), tmp_path / "l2.vtu", layers=[2])
        v = _read_vtu(info["path"])
        assert info["layers"] == [2]
        assert v["n_cells"] == 2
        assert np.unique(v["points"][:, 2]).tolist() == [0.0, 40.0]
        with pytest.raises(ValueError, match="out of range"):
            export_vtk(TriQuadModel(), tmp_path / "l9.vtu", layers=[9])


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestSampleModel:
    @pytest.fixture(scope="class")
    def model(self):
        from iwfm_io import open_model

        return open_model(SAMPLE_MODEL)

    def test_static_export(self, model, tmp_path):
        from iwfm_io import export_vtk

        info = export_vtk(model, tmp_path / "m.vtu", z_scale=5.0)
        assert info["n_points"] == 441 * 2 * 2
        assert info["n_cells"] == 400 * 2
        v = _read_vtu(info["path"])
        assert set(v["types"]) == {12.0}              # all quads
        # hexahedron orientation: first face is the bottom sheet
        conn = v["connectivity"].astype(int)
        z = v["points"][:, 2]
        assert (z[conn[:4]] < z[conn[4:8]]).all()

    def test_adapter_to_vtk_delegates(self, model, tmp_path):
        out = tmp_path / "adapter.vtu"
        info = model.to_vtk(out, layers=[1])
        assert Path(info["path"]) == out
        assert info["n_cells"] == 400

    def test_timeseries(self, model, tmp_path):
        from iwfm_io import export_vtk_timeseries

        ts = export_vtk_timeseries(
            model, tmp_path / "anim",
            begin_date="10/01/1990_24:00", end_date="12/31/1990_24:00",
            stride=30, z_scale=5.0)
        pvd = Path(ts["pvd"])
        assert pvd.is_file() and ts["n_steps"] >= 3

        text = pvd.read_text()
        frames = sorted(pvd.parent.glob("heads_*.vtu"))
        assert len(frames) == ts["n_steps"]
        for f in frames:
            assert f.name in text
        # timestep attributes are ascending day offsets starting at 0
        import re

        steps = [float(s) for s in re.findall(r'timestep="([\d.]+)"', text)]
        assert steps[0] == 0.0 and steps == sorted(steps)

        v = _read_vtu(frames[0])
        heads = v["p:head"]
        assert np.isfinite(heads).all()
        assert 100 < heads.mean() < 500                # plausible ft range
        # dtw = GSE - layer-1 head everywhere on every sheet
        strat = model.stratigraphy_df()
        gse = np.tile(strat["elevation"].to_numpy(float), 4)
        l1_head = np.tile(heads[:441], 4)
        assert v["p:dtw"] == pytest.approx(gse - l1_head)
