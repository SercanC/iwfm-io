"""Tests for lake component readers and writers."""

import pytest
from pathlib import Path

from tests.io.conftest import SIMULATION_DIR

LAKE_DIR = SIMULATION_DIR / "Lake"


class TestLakeMain:
    def test_read_lake_main(self):
        from iwfm_io.readers.lake import read_lake_main

        path = LAKE_DIR / "Lake_MAIN.dat"
        if path.exists():
            lake = read_lake_main(path)
            assert lake.header is not None
            assert lake.n_lakes > 0
            assert lake.lake_params is not None
            assert len(lake.lake_params) == lake.n_lakes

    def test_lake_main_params(self):
        from iwfm_io.readers.lake import read_lake_main

        path = LAKE_DIR / "Lake_MAIN.dat"
        if path.exists():
            lake = read_lake_main(path)
            row = lake.lake_params.iloc[0]
            # sample: 1  2.0  1.0  1  7  2  Lake1
            assert row["lake_id"] == 1
            assert row["conductance"] == 2.0
            assert row["bed_thickness"] == 1.0
            assert row["max_elev_col"] == 1
            assert row["et_col"] == 7
            assert row["precip_col"] == 2
            assert row["name"] == "Lake1"
            # bed factors + initial elevations are captured
            assert lake.factk == 1.0
            assert lake.tunitk.lower() == "1day"
            assert lake.initial_elevations is not None
            assert lake.initial_elevations["elevation"].iloc[0] == 280.0

    def test_lake_main_round_trip(self, tmp_output):
        from iwfm_io.readers.lake import read_lake_main
        from iwfm_io.writers.lake import write_lake_main

        path = LAKE_DIR / "Lake_MAIN.dat"
        if path.exists():
            import pandas as pd
            lake = read_lake_main(path)
            out = tmp_output / "Lake_MAIN.dat"
            write_lake_main(lake, out, base_dir=SIMULATION_DIR)

            lake2 = read_lake_main(out)
            assert lake2.n_lakes == lake.n_lakes
            assert lake2.factk == lake.factk
            assert lake2.tunitk == lake.tunitk
            assert lake2.factl == lake.factl
            pd.testing.assert_frame_equal(lake2.lake_params,
                                          lake.lake_params)
            assert lake2.init_elev_factor == lake.init_elev_factor
            pd.testing.assert_frame_equal(lake2.initial_elevations,
                                          lake.initial_elevations)

    def test_multi_lake_deck(self, tmp_output):
        # 2+ lake decks must parse every row (regression: the old
        # reader consumed exactly one).
        from iwfm_io.readers.lake import read_lake_main
        from iwfm_io.writers.lake import write_lake_main

        deck = (
            "C  test\n"
            "     Lake\\MaxLakeElev.dat   / MXLKELVFL\n"
            "                            / LKBUDFL\n"
            "                            / FNLKELVFL\n"
            "     1.0     / FACTK\n"
            "     1day    / TUNITK\n"
            "     1.0     / FACTL\n"
            "     1   2.0   1.0   1   7   2   North Lake\n"
            "     2   3.5   0.5   2   8   3   South Lake\n"
            "     1.0     / FACT\n"
            "     1   280.0\n"
            "     2   150.5\n"
        )
        path = tmp_output / "multi_lake.dat"
        path.write_text(deck)
        lake = read_lake_main(path)
        assert lake.n_lakes == 2
        assert list(lake.lake_params["name"]) == ["North Lake",
                                                  "South Lake"]
        assert list(lake.initial_elevations["elevation"]) == [280.0, 150.5]

        out = tmp_output / "multi_lake_out.dat"
        write_lake_main(lake, out)
        lake2 = read_lake_main(out)
        assert lake2.n_lakes == 2
        assert list(lake2.lake_params["name"]) == ["North Lake",
                                                   "South Lake"]


class TestMaxLakeElev:
    def test_read_max_lake_elev(self):
        from iwfm_io import read_max_lake_elev

        path = LAKE_DIR / "MaxLakeElev.dat"
        if path.exists():
            ts = read_max_lake_elev(path)
            assert ts.spec.n_columns == 1
            assert ts.data is not None
            assert len(ts.data) >= 1
            assert ts.data["col_1"].iloc[0] == 285.0

    def test_max_lake_elev_round_trip(self, tmp_output):
        import pandas as pd
        from iwfm_io import read_max_lake_elev, write_max_lake_elev

        path = LAKE_DIR / "MaxLakeElev.dat"
        if path.exists():
            ts = read_max_lake_elev(path)
            out = tmp_output / "MaxLakeElev.dat"
            write_max_lake_elev(ts, out)

            ts2 = read_max_lake_elev(out)
            assert ts2.spec.n_columns == ts.spec.n_columns
            pd.testing.assert_frame_equal(ts2.data, ts.data)
