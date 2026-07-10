"""End-to-end proof that DataFrame-regenerated inputs are IWFM-valid.

Copies the sample model, round-trips every rewritten input file through
its reader/writer pair, runs the real PreProcessor and Simulation
executables, and compares the simulated heads with the baseline.

Slow (~3 min) and Windows-only, so it runs only when opted in:

    set IWFM_RUN_EXE_TESTS=1
    pytest tests/io/test_exe_roundtrip.py
"""

import os
import sys

import numpy as np
import pytest

from tests.io.conftest import SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not os.environ.get("IWFM_RUN_EXE_TESTS")
    or sys.platform != "win32"
    or not (SAMPLE_MODEL / "Bin" / "Simulation_x64.exe").exists(),
    reason="exe round-trip test runs only with IWFM_RUN_EXE_TESTS=1 "
           "on Windows with the sample model executables",
)


def test_regenerated_inputs_reproduce_baseline_heads(tmp_path):
    from iwfm_io import (
        create_scenario, run_model,
        read_gw_main, write_gw_main,
        read_subsidence, write_subsidence_file,
        read_tile_drain, write_tile_drain,
        read_elem_pump, write_elem_pump,
        read_diver_specs, write_diver_specs,
        read_swshed, write_swshed,
        read_unsatzone, write_unsatzone,
        read_rootzone_main, write_rootzone_main,
        read_stream_main, write_stream_main,
    )
    from iwfm_io.readers.text_output import read_head_all_out

    scen = create_scenario(SAMPLE_MODEL, tmp_path / "scenario")
    sim = scen / "Simulation"

    pairs = [
        (sim / "GW" / "GW_MAIN.dat", read_gw_main, write_gw_main, True),
        (sim / "GW" / "Subsidence.dat", read_subsidence,
         write_subsidence_file, True),
        (sim / "GW" / "TileDrain.dat", read_tile_drain,
         write_tile_drain, False),
        (sim / "GW" / "ElemPump.dat", read_elem_pump,
         write_elem_pump, False),
        (sim / "Stream" / "DiverSpecs.dat", read_diver_specs,
         write_diver_specs, False),
        (sim / "SWShed.dat", read_swshed, write_swshed, False),
        (sim / "UnsatZone.dat", read_unsatzone, write_unsatzone, False),
        (sim / "RootZone" / "RootZone_MAIN.dat", read_rootzone_main,
         write_rootzone_main, True),
        (sim / "Stream" / "Stream_MAIN.dat", read_stream_main,
         write_stream_main, True),
    ]
    for path, rd, wr, takes_base in pairs:
        obj = rd(path)
        if takes_base:
            wr(obj, path, base_dir=sim)
        else:
            wr(obj, path)

    results = run_model(scen, steps=("preprocessor", "simulation"))
    assert all(r.success for r in results.values())

    new = read_head_all_out(scen / "Results" / "GWHeadAll.out")
    old = read_head_all_out(SAMPLE_MODEL / "Results" / "GWHeadAll.out")
    a = new.drop(columns="date").to_numpy(float)
    b = old.drop(columns="date").to_numpy(float)
    assert a.shape == b.shape
    assert np.abs(a - b).max() == 0.0
