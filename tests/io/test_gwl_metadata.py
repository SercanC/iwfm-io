"""Tests for the gwl_metadata suite (iwfm_io.wells)."""

import numpy as np
import pandas as pd
import pytest


def _metadata(**kw):
    base = {
        "well_id": ["w1", "w2", "w3"],
        "group": [10, 10, 20],
        "site_code": ["350092N001", "350425N001", "351111N001"],
        "perf_top": [np.nan, 100.0, np.nan],
        "perf_bottom": [np.nan, 300.0, np.nan],
        "layer": pd.array([1, pd.NA, pd.NA], dtype="Int64"),
    }
    base.update(kw)
    return pd.DataFrame(base)


def _hyd_frame():
    """Hydrograph section: w1/w2 with 2 layers each, one orphan stem."""
    rows = []
    hid = 0
    for stem, (x, y) in [("350092N001", (0.0, 100.0)),
                         ("350425N001", (50.0, 50.0)),
                         ("orphan01", (99.0, 99.0))]:
        for layer in (1, 2):
            hid += 1
            rows.append((hid, 0, layer, x, y, None, f"{stem}%{layer}"))
    return pd.DataFrame(rows, columns=["id", "hydtyp", "layer", "x", "y",
                                       "node", "name"])


class TestValidate:
    def test_clean_frame_passes(self):
        from iwfm_io import validate_gwl_metadata

        assert validate_gwl_metadata(_metadata()) == []

    def test_problems_reported(self):
        from iwfm_io import validate_gwl_metadata

        df = _metadata()
        df.loc[1, "well_id"] = "w1"                      # duplicate
        df.loc[1, "perf_top"] = 400.0                    # top >= bottom
        df["layer"] = [1, -1, 0]                         # legacy codes
        probs = "; ".join(validate_gwl_metadata(df))
        assert "duplicate well_id" in probs
        assert "perf_top >= perf_bottom" in probs
        assert "legacy 0/-1" in probs

    def test_seq_needs_group_and_uniqueness(self):
        from iwfm_io import validate_gwl_metadata

        df = _metadata(seq=pd.array([1, 1, 2], dtype="Int64"))
        assert any("duplicate (group, seq)" in p
                   for p in validate_gwl_metadata(df))
        df2 = _metadata().drop(columns="group")
        df2["seq"] = pd.array([1, 2, 3], dtype="Int64")
        assert any("no group column" in p
                   for p in validate_gwl_metadata(df2))


class TestLinkHydrographs:
    def test_links_by_site_code(self):
        from iwfm_io import link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        s = link.summary()
        assert s["n_wells_linked"] == 2
        assert s["n_hydrographs_linked"] == 4
        assert link.unmatched_wells == ["w3"]
        assert link.orphan_stems == ["orphan01"]
        w1 = link.links[link.links["well_id"] == "w1"]
        assert w1["layer"].tolist() == [1, 2]
        assert (w1["x"] == 0.0).all() and (w1["y"] == 100.0).all()

    def test_layer_suffix_cross_check(self, caplog):
        from iwfm_io import link_hydrographs

        hyd = _hyd_frame()
        hyd.loc[0, "name"] = "350092N001%2"       # says 2, LAYER field is 1
        with caplog.at_level("WARNING"):
            link = link_hydrographs(_metadata(), hyd)
        assert len(link.layer_mismatches) == 1
        assert link.layer_mismatches.iloc[0]["declared_layer"] == 1
        # the LAYER field is trusted
        w1 = link.links[link.links["well_id"] == "w1"]
        assert w1["layer"].tolist() == [1, 2]

    def test_name_without_separator_is_single_stem(self):
        from iwfm_io import link_hydrographs

        hyd = pd.DataFrame({
            "id": [1], "hydtyp": [0], "layer": [1], "x": [0.0],
            "y": [0.0], "node": [None], "name": ["350092N001"]})
        link = link_hydrographs(_metadata(), hyd)
        assert link.links["well_id"].tolist() == ["w1"]

    def test_custom_on_column_and_sep(self):
        from iwfm_io import link_hydrographs

        md = _metadata(hydrograph_name=["A|x", "B|x", "C|x"])
        md["hydrograph_name"] = ["A", "B", "C"]
        hyd = pd.DataFrame({
            "id": [1, 2], "hydtyp": [0, 0], "layer": [1, 1],
            "x": [0.0, 1.0], "y": [0.0, 1.0], "node": [None, None],
            "name": ["A|1", "B|1"]})
        link = link_hydrographs(md, hyd, on="hydrograph_name",
                                name_sep="|")
        assert sorted(link.links["well_id"]) == ["w1", "w2"]

    def test_duplicate_link_values_raise(self):
        from iwfm_io import link_hydrographs

        md = _metadata(site_code=["same", "same", "other"])
        with pytest.raises(ValueError, match="duplicate value"):
            link_hydrographs(md, _hyd_frame())

    def test_invalid_metadata_rejected(self):
        from iwfm_io import link_hydrographs

        md = _metadata()
        md.loc[1, "well_id"] = "w1"
        with pytest.raises(ValueError, match="invalid gwl_metadata"):
            link_hydrographs(md, _hyd_frame())
        with pytest.raises(ValueError, match="no column"):
            link_hydrographs(_metadata().drop(columns="site_code"),
                             _hyd_frame())


class TestAssignSequences:
    def test_north_to_south_from_link(self):
        from iwfm_io import assign_sequences, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        md = _metadata(group=[10, 10, 10])
        out = assign_sequences(md, link)
        s = out.set_index("well_id")["seq"]
        # w1 at y=100 (north) before w2 at y=50; w3 has no coords -> last
        assert s["w1"] == 1 and s["w2"] == 2 and s["w3"] == 3

    def test_existing_seq_never_renumbered(self):
        from iwfm_io import assign_sequences, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        md = _metadata(group=[10, 10, 10],
                       seq=pd.array([pd.NA, 5, pd.NA], dtype="Int64"))
        out = assign_sequences(md, link)
        s = out.set_index("well_id")["seq"]
        assert s["w2"] == 5                       # untouched
        assert s["w1"] == 6 and s["w3"] == 7      # appended after max

    def test_metadata_xy_preferred(self):
        from iwfm_io import assign_sequences

        md = _metadata(group=[1, 1, 1], x=[0.0, 0.0, 0.0],
                       y=[10.0, 30.0, 20.0])
        out = assign_sequences(md, order="north_to_south")
        assert out.set_index("well_id")["seq"].tolist() == [3, 1, 2]

    def test_needs_group_and_coords(self):
        from iwfm_io import assign_sequences

        with pytest.raises(ValueError, match="group"):
            assign_sequences(_metadata().drop(columns="group"))
        with pytest.raises(ValueError, match="available"):
            assign_sequences(_metadata())
        with pytest.raises(ValueError, match="order"):
            assign_sequences(_metadata(), order="spiral")


class TestComposite:
    def test_composites_with_fraction_frame(self):
        from iwfm_io import composite_well_hydrographs, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        idx = pd.date_range("2000-01-31", periods=3, freq="ME")
        # hyd ids 1..4: w1-L1, w1-L2, w2-L1, w2-L2
        hyd_out = pd.DataFrame(
            {1: 100.0, 2: 80.0, 3: 60.0, 4: 40.0}, index=idx)
        frac = pd.DataFrame({
            "well_id": ["w1", "w1", "w2"],
            "layer": [1, 2, 1],
            "fraction": [0.25, 0.75, 1.0]})
        out = composite_well_hydrographs(link, hyd_out, frac)
        assert out["w1"].values == pytest.approx([85.0] * 3)
        assert out["w2"].values == pytest.approx([60.0] * 3)

    def test_col_n_labels_resolve(self):
        from iwfm_io import composite_well_hydrographs, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        idx = pd.date_range("2000-01-31", periods=2, freq="ME")
        hyd_out = pd.DataFrame(
            {f"col_{i}": float(i) for i in (1, 2, 3, 4)}, index=idx)
        frac = pd.DataFrame({"well_id": ["w1"], "layer": [2],
                             "fraction": [1.0]})
        out = composite_well_hydrographs(link, hyd_out, frac)
        assert out["w1"].values == pytest.approx([2.0, 2.0])

    def test_missing_layer_raises(self):
        from iwfm_io import composite_well_hydrographs, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        idx = pd.date_range("2000-01-31", periods=2, freq="ME")
        hyd_out = pd.DataFrame({1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}, index=idx)
        frac = pd.DataFrame({"well_id": ["w1"], "layer": [3],
                             "fraction": [1.0]})
        with pytest.raises(KeyError, match="no linked hydrograph"):
            composite_well_hydrographs(link, hyd_out, frac)

    def test_wellmapping_fractions_accepted(self):
        from iwfm_io import (WellMapping, composite_well_hydrographs,
                             link_hydrographs)

        link = link_hydrographs(_metadata(), _hyd_frame())
        mapping = WellMapping(
            wells=pd.DataFrame({"well_id": ["w1"], "x": [0.0], "y": [100.0],
                                "node": [1], "method": ["perforation"]}),
            weights=pd.DataFrame({
                "well_id": ["w1", "w1"], "node": [1, 1],
                "layer": [1, 2], "weight": [0.5, 0.5]}),
            n_layers=2)
        idx = pd.date_range("2000-01-31", periods=2, freq="ME")
        hyd_out = pd.DataFrame({1: 10.0, 2: 20.0, 3: 0.0, 4: 0.0},
                               index=idx)
        out = composite_well_hydrographs(link, hyd_out, mapping)
        assert out["w1"].values == pytest.approx([15.0, 15.0])


class TestEnrichAndLegacy:
    class Model:
        def nodes_df(self):
            return pd.DataFrame({"node_id": [1, 2],
                                 "x": [0.0, 50.0], "y": [100.0, 50.0]})

        def stratigraphy_df(self):
            return pd.DataFrame({"node_id": [1, 2],
                                 "elevation": [500.0, 400.0],
                                 "aquitard_1": [0.0, 0.0],
                                 "aquifer_1": [100.0, 100.0]})

        def elements_df(self):
            return pd.DataFrame({"element_id": [1], "node1": [1],
                                 "node2": [2], "node3": [0], "node4": [0],
                                 "subregion": [21]})

    def test_enrich_from_link_and_obs(self):
        from iwfm_io import enrich_gwl_metadata, link_hydrographs

        link = link_hydrographs(_metadata(), _hyd_frame())
        obs = pd.DataFrame({
            "site": ["w1", "w1", "w2"],
            "datetime": pd.to_datetime(
                ["2000-01-15", "2001-06-15", "2000-03-01"]),
            "value": [1.0, 2.0, 3.0]})
        out = enrich_gwl_metadata(self.Model(), _metadata(), link=link,
                                  obs=obs)
        row = out.set_index("well_id")
        assert row.loc["w1", "gse"] == 500.0        # nearest node 1
        assert row.loc["w1", "subregion"] == 21
        assert row.loc["w1", "n_obs"] == 2
        assert row.loc["w3", "n_obs"] == 0
        assert row.loc["w1", "first_date"] == pd.Timestamp("2000-01-15")

    def test_legacy_conversion(self):
        from iwfm_io import gwl_metadata_from_legacy, validate_gwl_metadata

        legacy = pd.DataFrame({
            "SITE": ["350092N001", "350425N001", "351111N001"],
            "HYDID": [670001, 670002, 670003],
            "GRP": [67, 67, 67],
            "X": [0.0, 1.0, 2.0], "Y": [0.0, 1.0, 2.0],
            "gse": [100.0, 200.0, 300.0],
            "perft": [0, 396, 0], "perfb": [0, 1000, 0],
            "layer": [2, -1, 0],
        })
        out = gwl_metadata_from_legacy(legacy)
        assert validate_gwl_metadata(out) == []
        r = out.set_index("well_id")
        assert r.loc[670001, "layer"] == 2          # fixed layer kept
        assert pd.isna(r.loc[670001, "perf_top"])   # layer overrides perf
        assert r.loc[670002, "perf_top"] == 396.0   # -1 -> perforations
        assert pd.isna(r.loc[670002, "layer"])
        assert pd.isna(r.loc[670003, "layer"])      # 0 -> unknown
        assert pd.isna(r.loc[670003, "perf_top"])
        assert r.loc[670001, "hydrograph_name"] == "350092N001"
        assert r.loc[670001, "group"] == 67
