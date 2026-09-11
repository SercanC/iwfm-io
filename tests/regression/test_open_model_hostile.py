"""Hostile-QA regressions: open_model / IOModelAdapter / _links / wells / gis / vtk / cli.

Imported from the 2026-09-09 hostile-QA pass. Every test asserts the
EXPECTED behaviour; ``xfail(strict=True)`` marks the ones that still
reproduce a defect on the current code. Never touches the read-only
sample model (edits go to ``tmp_path`` copies).
"""
import json
import warnings

import h5py
import numpy as np
import pandas as pd
import pytest

from tests.regression._helpers import copy_model, edit_line

pytestmark = [pytest.mark.regression, pytest.mark.sample_model]

_HDF_RESULTS = ("GWHeadAll.hdf", "GW.hdf", "GWHyd.hdf", "StrmHyd.hdf", "StrmNodeBud.hdf")


# 1. read_diver_specs silently scrambles a row whose TYPDSTDL is not in {0,2,4,6}
def test_diver_specs_invalid_dest_type_is_not_silently_reparsed(tmp_path):
    from iwfm_io.readers.stream import read_diver_specs
    d = copy_model(tmp_path / "model")
    p = d / "Simulation/Stream/DiverSpecs.dat"
    edit_line(p, 85, "    4        22     0        0.0     4       0.00        4         0.01       4"
                     "        0.0     7           0       4        0.99      2        3      DiverToOutside")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        row = read_diver_specs(p).data.set_index("diversion_id").loc[4]
    # expected: dest_type 7 surfaced (or a warning); observed: dest_type=4, spill NaN, name='2 3 DiverToOutside'
    assert row["dest_type"] == 7 or any("TYPDSTDL" in str(x.message) or "dest" in str(x.message)
                                        for x in w), row.to_dict()
    assert row["name"] == "DiverToOutside", row.to_dict()


# 2. a non-numeric pointer drops three NonPondedAg tables silently; validate_references finds nothing
def test_nonnumeric_pointer_is_reported(sample_model_copy):
    """A non-numeric pointer is a parse error under the strict default
    (decided 2.13.0); lenient mode keeps the table and validate_references
    reports the value."""
    import iwfm_io
    from iwfm_io import open_model
    d = sample_model_copy
    edit_line(d / "Simulation/RootZone/NonPondedAg/NonPondedAg_MAIN.dat", 521,
              "    0     abc        2")
    with pytest.raises(iwfm_io.IWFMParseError):
        open_model(d).component("nonponded_ag")
    with iwfm_io.strict_mode(False), pytest.warns(iwfm_io.IWFMReadWarning):
        m = open_model(d, strict=False)
        assert m.component("nonponded_ag") is not None
        assert len(m.validate_references()) > 0


# 3. text-heads fallback: layer=-1 silently returns layer 1 data (negative iloc wrap)
def test_text_heads_negative_layer_raises(tmp_path):
    from iwfm_io import open_model
    d = copy_model(tmp_path / "model", results=("GWHeadAll.out",))
    m = open_model(d)
    assert str(m._heads_hdf).endswith(".out")
    with pytest.raises((ValueError, IndexError)):
        m.heads_df(-1)          # observed: returns layer-1 heads


def test_hdf_heads_out_of_range_layer_raises(open_sample):
    with pytest.raises((ValueError, IndexError)):
        open_sample.heads_df(3)  # observed: (3654, 0) empty frame; text path -> pandas 'Length mismatch'


# 4. budget_df columns=[0] wraps to the LAST column
def test_budget_columns_zero_does_not_wrap(open_sample):
    with pytest.raises((ValueError, IndexError)):
        open_sample.budget_df("GW", 1, columns=[0])   # observed: ['Cumulative Subsidence'] (last column)


# 5. relative root path -> stale relative file paths after os.chdir; false validation findings
def test_relative_root_survives_chdir(tmp_path, monkeypatch):
    from iwfm_io import open_model
    copy_model(tmp_path / "model", results=_HDF_RESULTS)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(tmp_path)
    m = open_model("model")
    monkeypatch.chdir(elsewhere)
    findings = m.validate_references()
    assert findings.empty, findings.to_string()       # observed: 6 'references no such file' errors
    m.heads_df(1)                                       # observed: FileNotFoundError


# 6. cache staleness is inconsistent across accessors (no reload API)
def test_series_and_stream_flows_follow_disk_changes(tmp_path):
    from iwfm_io import open_model
    d = copy_model(tmp_path / "model", results=_HDF_RESULTS)
    m = open_model(d)
    et1 = m.series("et", 1).value.copy()
    sf1 = m.stream_flows_df().flow.copy()
    h1 = m.heads_df(1).iloc[0, 0]
    # simulate an edit + re-run
    etp = d / "Simulation/ET.dat"
    lines = etp.read_text().splitlines()
    i = next(k for k, ln in enumerate(lines) if "4000_24:00" in ln and not ln.startswith(("C", "c", "*")))
    parts = lines[i].split()
    parts[1] = "9.9999"
    lines[i] = "  ".join(parts)
    etp.write_text("\n".join(lines) + "\n")
    with h5py.File(d / "Results/StrmNodeBud.hdf", "r+") as f:
        k = [k for k in f if k != "Attributes"][0]
        f[k][...] = 0.0
    with h5py.File(d / "Results/GWHeadAll.hdf", "r+") as f:
        f["GWHeadAtAllNode"][0, 0] = 12345.0
    assert m.heads_df(1).iloc[0, 0] == 12345.0 and h1 != 12345.0          # heads re-read: OK
    fresh = m.series("et", 1)
    et2 = fresh.value
    assert (et2 != et1).any()                                               # was: stale
    # the edited 10/31/4000_24:00 row is November of every recurring year
    import pandas as pd
    assert set(pd.DatetimeIndex(fresh.date[et2 != et1]).month) == {11}
    assert not m.stream_flows_df().flow.equals(sf1)                        # was: stale
    # reload() is the explicit escape hatch
    assert m.reload() is m and m.series("et", 1).value.equals(et2)


# 7. corrupt result HDFs vanish from describe() without a trace
def test_describe_reports_unreadable_result_files(tmp_path, sample_model):
    from iwfm_io import open_model
    d = copy_model(tmp_path / "model")
    for n in ("GWHeadAll.hdf", "GW.hdf"):
        b = (sample_model / "Results" / n).read_bytes()
        (d / "Results" / n).write_bytes(b[: len(b) // 2])
    info = open_model(d).describe()
    txt = json.dumps(info)
    assert "GWHeadAll" in txt or "unreadable" in txt or "error" in txt.lower()   # observed: heads None, budgets {}


# 8. non-integer pointer passes validation and is silently truncated
def test_non_integer_pointer_flagged(tmp_path):
    from iwfm_io import open_model
    d = copy_model(tmp_path / "model")
    edit_line(d / "Simulation/RootZone/NativeVeg/NativeVeg_MAIN.dat", 61,
              "   1       65      65       1.5        5        0")
    m = open_model(d)
    assert not m.validate_references().empty          # observed: empty; crop_series('et','native',element=1) uses col 1


# 9. stream_hydrograph_series(quantity='stage') on the HDF output: confusing KeyError
def test_stream_stage_from_hdf_has_clear_error(open_sample):
    from iwfm_io.gauges import link_stream_hydrographs, stream_hydrograph_series
    m = open_sample
    sm = m.component("stream_main")
    specs = pd.DataFrame(sm.hydrograph_specs)
    gl = link_stream_hydrographs(pd.DataFrame({"gauge_id": specs.name, "site_code": specs.name}), sm)
    with pytest.raises(ValueError):  # observed: KeyError 'hydrograph output is missing 23 column(s), e.g. [24, 25, 26]'
        stream_hydrograph_series(gl, m.hydrograph_df("StrmHyd"), quantity="stage")


# 10. export_vtk writes malformed XML for array names with XML specials
def test_vtk_array_name_is_xml_escaped(tmp_path, open_sample):
    from iwfm_io.vtk import export_vtk
    import xml.etree.ElementTree as ET
    out = export_vtk(open_sample, tmp_path / "x.vtu", point_data={'a<b "c"': np.zeros(441)}, layers=[1])
    ET.parse(out["path"])   # observed: ParseError (not well-formed)


# 11. export_gis: duplicate node_id in node_data duplicates features; .geojson path becomes a directory
def test_export_gis_dup_node_data_rejected(tmp_path, open_sample):
    pytest.importorskip("geopandas")
    from iwfm_io.gis import export_gis
    with pytest.raises(ValueError):
        export_gis(open_sample, tmp_path / "a.gpkg", layers=["nodes"],
                   node_data=pd.DataFrame({"node_id": [1, 1], "v": [1, 2]}))  # observed: {'nodes': 442}


def test_export_gis_geojson_suffix_not_a_shapefile_dir(tmp_path, open_sample):
    pytest.importorskip("geopandas")
    from iwfm_io.gis import export_gis
    p = tmp_path / "out.geojson"
    try:
        export_gis(open_sample, p, layers=["nodes"])
    except ValueError:
        return
    assert p.is_file(), "observed: a directory named out.geojson containing nodes.shp"


# 12. build_well_mapping silently snaps NaN / far-away coordinates to a node
def test_well_mapping_rejects_nan_coordinates(open_sample):
    from iwfm_io.wells import build_well_mapping
    with pytest.raises(ValueError):
        build_well_mapping(open_sample, pd.DataFrame({"well_id": ["w"], "x": [np.nan], "y": [np.nan]}))
        # observed: node 1, method 'default'


# 13. hydrograph_df(column=-1) silently serves the last column
def test_hydrograph_negative_column_rejected(open_sample):
    with pytest.raises((ValueError, IndexError)):
        open_sample.hydrograph_df("GWHyd", column=-1)


# 14. parse_iwfm_date accepts garbage around the date
def test_date_parser_rejects_garbage():
    from iwfm_io._tokens import parse_iwfm_date
    with pytest.raises(ValueError):
        parse_iwfm_date("xx10/01/1990_24:00zz")


# 15. CLI: --traceback after the subcommand is rejected although the error hint suggests re-running with it
def test_cli_traceback_flag_accepted_after_subcommand(capsys, sample_model):
    from iwfm_io.cli import main
    # was: argparse exit 2 'unrecognized arguments: --traceback'
    assert main(["describe", str(sample_model), "--traceback"]) == 0
    assert main(["--traceback", "describe", str(sample_model)]) == 0
    assert '"n_nodes"' in capsys.readouterr().out


# 16. open_model(simulation=<preprocessor main>) accepted silently
def test_open_model_rejects_wrong_simulation_file(tmp_path):
    from iwfm_io import open_model
    d = copy_model(tmp_path / "model")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        m = open_model(d, simulation=d / "Preprocessor/PreProcessor_MAIN.IN")
    assert m.describe()["simulation"] is None or w, m.describe()["simulation"]
    # observed: {'begins': '', 'ends': '', 'timestep': ''}
