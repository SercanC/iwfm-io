"""Tests for the land use area file reader/writer.

All four root-zone land use area files (non-ponded crops, ponded
crops, urban, native/riparian vegetation) share one format; the sample
model provides one of each (recurring-year, 400 elements).
"""

from pathlib import Path

import pandas as pd
import pytest

from iwfm_io import read_land_use_area, write_land_use_area
from iwfm_io.models.rootzone import LandUseAreaFile

ROOTZONE = (Path(__file__).resolve().parent.parent.parent
            / ".assets" / "sample_model" / "Simulation" / "RootZone")

# (relative path, expected number of area columns)
AREA_FILES = [
    ("NonPondedAg/CropAreas.dat", 2),
    ("PondedAg/RiceAreas.dat", 5),
    ("Urban/UrbanAreas.dat", 1),
    ("NativeVeg/NativeVegArea.dat", 2),
]

pytestmark = pytest.mark.skipif(
    not ROOTZONE.exists(), reason="sample model not available")


@pytest.mark.parametrize("rel,n_areas", AREA_FILES)
def test_read_land_use_area(rel, n_areas):
    lu = read_land_use_area(ROOTZONE / rel)
    assert lu.factor == 0.0
    assert lu.n_steps_update == 1
    assert lu.repeat_freq == 0
    assert lu.dss_file == ""
    assert len(lu.keywords) == 4
    assert lu.keywords[3] == "DSSFL"
    assert lu.n_land_uses == n_areas

    df = lu.data
    assert list(df.columns[:2]) == ["date", "element_id"]
    # sample model: one recurring-year timestep x 400 elements
    assert len(df) == 400
    assert df["date"].nunique() == 1
    assert df["date"].iloc[0] == "09/30/2500_24:00"
    assert df["element_id"].tolist() == list(range(1, 401))
    assert df.iloc[:, 2:].notna().all().all()


def test_read_land_use_area_values():
    lu = read_land_use_area(ROOTZONE / "NonPondedAg/CropAreas.dat")
    df = lu.data
    # element 1 is fully crop 1 in the sample model
    assert df.loc[df["element_id"] == 1, "area_1"].iloc[0] == 1.0
    assert df.loc[df["element_id"] == 1, "area_2"].iloc[0] == 0.0


def test_read_land_use_area_column_names():
    lu = read_land_use_area(ROOTZONE / "NonPondedAg/CropAreas.dat",
                            columns=["TO", "AL"])
    assert list(lu.data.columns) == ["date", "element_id", "TO", "AL"]
    with pytest.raises(ValueError):
        read_land_use_area(ROOTZONE / "NonPondedAg/CropAreas.dat",
                           columns=["only_one"])


@pytest.mark.parametrize("rel,n_areas", AREA_FILES)
def test_land_use_area_roundtrip(rel, n_areas, tmp_path):
    lu = read_land_use_area(ROOTZONE / rel)
    out = tmp_path / Path(rel).name
    write_land_use_area(lu, out)
    back = read_land_use_area(out)

    assert back.factor == lu.factor
    assert back.n_steps_update == lu.n_steps_update
    assert back.repeat_freq == lu.repeat_freq
    assert back.dss_file == lu.dss_file
    assert back.keywords == lu.keywords
    pd.testing.assert_frame_equal(back.data, lu.data)


def test_land_use_area_multi_timestep_roundtrip(tmp_path):
    """Synthetic multi-timestep data survives write -> re-read."""
    rows = []
    for date in ["09/30/1990_24:00", "09/30/1991_24:00"]:
        for elem in range(1, 4):
            rows.append({"date": date, "element_id": elem,
                         "area_1": 0.25 * elem, "area_2": 12.375})
    data = pd.DataFrame(rows)
    lu = LandUseAreaFile(factor=43560.0, data=data)

    out = tmp_path / "areas.dat"
    write_land_use_area(lu, out)

    text = out.read_text()
    # only the first row of each timestep block carries the date
    assert text.count("09/30/1990_24:00") == 1
    assert text.count("09/30/1991_24:00") == 1

    back = read_land_use_area(out)
    assert back.factor == 43560.0
    pd.testing.assert_frame_equal(back.data, data)


def test_land_use_area_dss_roundtrip(tmp_path):
    """DSSFL variant: pathname rows instead of inline data."""
    paths = pd.DataFrame({
        "element_id": [1, 1, 2, 2],
        "lu_type": [1, 2, 1, 2],
        "pathname": [f"/IWFM/E{e}T{t}/AREA//1MON/LU/" for e, t in
                     [(1, 1), (1, 2), (2, 1), (2, 2)]],
    })
    lu = LandUseAreaFile(dss_file="landuse.dss", dss_pathnames=paths)

    out = tmp_path / "areas_dss.dat"
    write_land_use_area(lu, out)
    back = read_land_use_area(out)

    assert back.dss_file == "landuse.dss"
    assert back.data is None
    pd.testing.assert_frame_equal(back.dss_pathnames, paths)


class TestReadAllLandUseAreas:
    """Combined reader; the sample model is fraction-based (FACT=0.0),
    so element areas (2000 x 2000 m grid) resolve the fractions."""

    RZ_MAIN = ROOTZONE / "RootZone_MAIN.dat"
    PP_MAIN = (ROOTZONE.parent.parent / "Preprocessor"
               / "PreProcessor_MAIN.IN")

    def test_fractions_kept_without_element_areas(self):
        # FACT=0.0 files keep their fractions when element_areas is
        # omitted (all sample files are fraction-based, so no
        # mixed-units warning either)
        import warnings

        from iwfm_io import read_all_land_use_areas
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            df = read_all_land_use_areas(self.RZ_MAIN)
        row1 = df[df["element_id"] == 1].iloc[0]
        assert row1["TO"] == 1.0  # still a fraction
        assert df.iloc[:, 2:].sum(axis=1).max() == pytest.approx(1.0)

    def test_combined_areas_from_preprocessor(self):
        from iwfm_io import read_all_land_use_areas, read_preprocessor
        pp = read_preprocessor(self.PP_MAIN)
        df = read_all_land_use_areas(self.RZ_MAIN, element_areas=pp)

        # 2 non-ponded crops + 5 ponded types + urban + native/riparian
        assert list(df.columns) == [
            "date", "element_id", "TO", "AL",
            "rice_fl", "rice_nfl", "rice_ndc", "refuge_sl", "refuge_pr",
            "urban", "native", "riparian"]
        assert len(df) == 400
        # element 1 is fully crop TO: fraction 1.0 x (2000 m)^2
        row1 = df[df["element_id"] == 1].iloc[0]
        assert row1["TO"] == pytest.approx(4_000_000.0)
        assert row1["AL"] == 0.0
        # land use fractions sum to 1 -> areas sum to the element area
        totals = df.iloc[:, 2:].sum(axis=1)
        assert totals.max() == pytest.approx(4_000_000.0, rel=1e-6)

    def test_element_areas_dict(self):
        from iwfm_io import read_all_land_use_areas
        areas = {e: 4_000_000.0 for e in range(1, 401)}
        df = read_all_land_use_areas(self.RZ_MAIN, element_areas=areas)
        assert df[df["element_id"] == 1]["TO"].iloc[0] == pytest.approx(
            4_000_000.0)

    def test_accepts_parsed_rootzone_main(self):
        from iwfm_io import read_all_land_use_areas, read_rootzone_main
        rz = read_rootzone_main(self.RZ_MAIN)
        areas = {e: 1.0 for e in range(1, 401)}  # keep fractions
        df = read_all_land_use_areas(rz, element_areas=areas)
        assert df[df["element_id"] == 1]["TO"].iloc[0] == 1.0
