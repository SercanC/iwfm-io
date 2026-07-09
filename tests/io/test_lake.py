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
            assert "lake_id" in lake.lake_params.columns
            assert "conductance" in lake.lake_params.columns

    def test_lake_main_round_trip(self, tmp_output):
        from iwfm_io.readers.lake import read_lake_main
        from iwfm_io.writers.lake import write_lake_main

        path = LAKE_DIR / "Lake_MAIN.dat"
        if path.exists():
            lake = read_lake_main(path)
            out = tmp_output / "Lake_MAIN.dat"
            write_lake_main(lake, out)
            assert out.exists()
