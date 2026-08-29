"""End-of-line annotations are preserved: element-group names and the
``notes`` column on hydrograph / well-config tables round-trip instead
of being discarded (delivery area names, station details, well names)."""

import pandas as pd
import pytest
from pathlib import Path

C2VSIMFG = Path(r"C:\Projects\iwfm-io\.assets\c2vsimfg_v1.5\Simulation")


class TestElementGroupNames:
    def test_slash_and_tail_names(self, tmp_output):
        from iwfm_io import read_diver_specs, write_diver_specs

        deck = (
            "C  test\n"
            "        2   / NRDV\n"
            "  1  0  1  1.0  1  0.03  1  0.54  6  1  1  0.43  2  2"
            "  DIV_001\n"
            "  2  0  2  1.0  2  0.30  2  0.10  4  1  2  0.60  1  0"
            "  DIV_002\n"
            "        2   / NGRP\n"
            "  1   3   10 / Carrier Canal\n"
            "      11\n"
            "      12\n"
            "  2   2   20   21   NKWSD - CLASS 1\n"
            "  1   0   0   0.0\n"
            "  2   0   0   0.0\n"
        )
        path = tmp_output / "divspec_names.dat"
        path.write_text(deck)
        ds = read_diver_specs(path)
        assert ds.n_groups == 2
        # inline "/" comment name
        assert ds.delivery_groups[0]["name"] == "Carrier Canal"
        assert ds.delivery_groups[0]["elements"] == [10, 11, 12]
        # slash-less trailing-text name
        assert ds.delivery_groups[1]["name"] == "NKWSD - CLASS 1"
        assert ds.delivery_groups[1]["elements"] == [20, 21]
        # flattened view carries the name per row
        df = ds.delivery_groups_df
        assert "name" in df.columns
        assert set(df[df["group_id"] == 1]["name"]) == {"Carrier Canal"}

        out = tmp_output / "divspec_names_out.dat"
        write_diver_specs(ds, out)
        ds2 = read_diver_specs(out)
        assert [g["name"] for g in ds2.delivery_groups] == \
            [g["name"] for g in ds.delivery_groups]
        assert [g["elements"] for g in ds2.delivery_groups] == \
            [g["elements"] for g in ds.delivery_groups]

    def test_nameless_groups_have_no_name_column(self, tmp_output):
        from iwfm_io.readers._element_groups import (
            element_groups_to_df, parse_element_groups)

        groups, _ = parse_element_groups(["  1  2  10", "     11"], 1)
        assert groups[0]["name"] == ""
        df = element_groups_to_df(groups)
        assert "name" not in df.columns


class TestHydrographNotes:
    def test_bc_hydrograph_notes_round_trip(self, tmp_output):
        from iwfm_io import read_bc_main, write_bc_main

        deck = (
            "C  test\n"
            "         / SPFLOWFL\n"
            "         / SPHEADFL\n"
            "         / GHBCFL\n"
            "         / CONGHBCFL\n"
            "         / TSBCFL\n"
            "   2     / NOUTB\n"
            "         / BHYDOUTFL\n"
            "   1  1  10  BND1   / USGS station 11447650\n"
            "   2  2  20  BND2\n"
        )
        path = tmp_output / "bc_notes.dat"
        path.write_text(deck)
        bc = read_bc_main(path)
        assert list(bc.bc_hydrographs["notes"]) == \
            ["USGS station 11447650", ""]
        assert bc.bc_hydrographs["name"].iloc[0] == "BND1"

        out = tmp_output / "bc_notes_out.dat"
        write_bc_main(bc, out)
        bc2 = read_bc_main(out)
        pd.testing.assert_frame_equal(bc2.bc_hydrographs,
                                      bc.bc_hydrographs)

    def test_c2vsimfg_subsidence_insar_notes(self):
        from iwfm_io import read_subsidence

        path = C2VSIMFG / "Groundwater" / "C2VSimFG_Subsidence.dat"
        if not path.exists():
            pytest.skip("C2VSimFG not present")
        sub = read_subsidence(path)
        assert "notes" in sub.hydrographs.columns


class TestWellConfigNotes:
    def test_well_config_notes_round_trip(self, tmp_output):
        from iwfm_io import read_well_spec, write_well_spec

        deck = (
            "C  test\n"
            "   1   / NWELL\n"
            "   1.0 / FACTXY\n"
            "   1.0 / FACTRW\n"
            "   1.0 / FACTLT\n"
            "   1  100.0  200.0  1.0  50.0  10.0  /Well One\n"
            "   1  1  1.0  3  -1  0  1  3  0  1.0   / M&T Chico Ranch\n"
            "   0   / NGRP\n"
        )
        path = tmp_output / "wellspec_notes.dat"
        path.write_text(deck)
        ws = read_well_spec(path)
        assert ws.data["name"].iloc[0] == "Well One"
        assert ws.pump_config["notes"].iloc[0] == "M&T Chico Ranch"

        out = tmp_output / "wellspec_notes_out.dat"
        write_well_spec(ws, out)
        ws2 = read_well_spec(out)
        assert ws2.pump_config["notes"].iloc[0] == "M&T Chico Ranch"
        assert ws2.data["name"].iloc[0] == "Well One"

    def test_c2vsimfg_well_group_names(self):
        from iwfm_io import read_well_spec

        path = C2VSIMFG / "Groundwater" / "C2VSimFG_WellSpec.dat"
        if not path.exists():
            pytest.skip("C2VSimFG not present")
        ws = read_well_spec(path)
        assert "notes" in ws.pump_config.columns
        # the delivery groups carry real district names
        names = [g["name"] for g in ws.element_groups if g["name"]]
        assert "Arvin-Edison WSD" in names
