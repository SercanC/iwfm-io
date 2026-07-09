"""Tests for miscellaneous IWFM file readers and writers."""

import pytest
from pathlib import Path

from tests.io.conftest import SIMULATION_DIR


class TestSWShed:
    def test_read_swshed(self):
        from iwfm_io.readers.misc import read_swshed

        path = SIMULATION_DIR / "SWShed.dat"
        if path.exists():
            sw = read_swshed(path)
            assert sw.header is not None
            assert sw.n_watersheds > 0
            assert "facta" in sw.config
            assert "factq" in sw.config

    def test_swshed_round_trip(self, tmp_output):
        from iwfm_io.readers.misc import read_swshed
        from iwfm_io.writers.misc import write_swshed

        path = SIMULATION_DIR / "SWShed.dat"
        if path.exists():
            sw = read_swshed(path)
            out = tmp_output / "SWShed.dat"
            write_swshed(sw, out)
            assert out.exists()

            sw2 = read_swshed(out)
            assert sw2.n_watersheds == sw.n_watersheds


class TestUnsatZone:
    def test_read_unsatzone(self):
        from iwfm_io.readers.misc import read_unsatzone

        path = SIMULATION_DIR / "UnsatZone.dat"
        if path.exists():
            uz = read_unsatzone(path)
            assert uz.header is not None
            assert uz.n_unsat_layers > 0
            assert uz.convergence > 0

    def test_unsatzone_round_trip(self, tmp_output):
        from iwfm_io.readers.misc import read_unsatzone
        from iwfm_io.writers.misc import write_unsatzone

        path = SIMULATION_DIR / "UnsatZone.dat"
        if path.exists():
            uz = read_unsatzone(path)
            out = tmp_output / "UnsatZone.dat"
            write_unsatzone(uz, out)
            assert out.exists()

            uz2 = read_unsatzone(out)
            assert uz2.n_unsat_layers == uz.n_unsat_layers
            assert uz2.convergence == uz.convergence
