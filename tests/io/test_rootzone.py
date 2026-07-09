"""Tests for root zone component readers and writers."""

import pytest
from pathlib import Path

from tests.io.conftest import SIMULATION_DIR

RZ_DIR = SIMULATION_DIR / "RootZone"


class TestRootZoneMain:
    def test_read_rootzone_main(self):
        from iwfm_io.readers.rootzone import read_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            assert rz.header is not None
            assert rz.convergence > 0
            assert rz.max_iterations > 0
            assert len(rz.file_paths) == 14

    def test_rootzone_file_paths(self):
        from iwfm_io.readers.rootzone import read_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            assert "nonponded_ag" in rz.file_paths
            assert "urban" in rz.file_paths
            assert "native_veg" in rz.file_paths

    def test_rootzone_round_trip(self, tmp_output):
        from iwfm_io.readers.rootzone import read_rootzone_main
        from iwfm_io.writers.rootzone import write_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            out = tmp_output / "RootZone_MAIN.dat"
            write_rootzone_main(rz, out)
            assert out.exists()

            rz2 = read_rootzone_main(out)
            assert rz2.convergence == rz.convergence
            assert rz2.max_iterations == rz.max_iterations
            assert rz2.gw_uptake == rz.gw_uptake
