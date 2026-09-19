"""Terminating comments for IWFM's "count the lines of this block" gates.

Several IWFM readers decide how many entries a block holds by reading
*all* consecutive data lines and looking at the count -- the backward
compatibility trick for optional trailing entries:

* ``Class_AppGW::New``    -- 19 lines means "no IHTPFLAG", 20 means it is
  there (issue #38);
* ``RootZone_v4xx::New``  -- one line more means the land-use area
  scaling output file is defined.

A regenerated file must therefore keep the comment that ends the block.
Without it the count runs on into the next section and every entry of
the block is read one position out of step -- in the GW main's case
``KDEB`` is taken for IHTPFLAG, ``NOUTH`` for KDEB and ``FACTXY``
(a real) for NOUTH, which is where IWFM 2024.2 gives up.
"""

import pytest

from iwfm_io import read_gw_main, read_rootzone_main, write_gw_main, write_rootzone_main
from iwfm_io._tokens import is_comment
from tests.io.conftest import SIMULATION_DIR

pytestmark = pytest.mark.sample_model


def data_line_runs(path):
    """Lengths of the file's runs of consecutive data lines."""
    runs, n = [], 0
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if is_comment(line) or not line.strip():
                if n:
                    runs.append(n)
                    n = 0
            else:
                n += 1
    if n:
        runs.append(n)
    return runs


def test_gw_main_output_file_list_is_terminated(tmp_path):
    src = SIMULATION_DIR / "GW" / "GW_MAIN.dat"
    gw = read_gw_main(src)
    dst = tmp_path / "GW_MAIN.dat"
    write_gw_main(gw, dst, base_dir=SIMULATION_DIR)

    # first run = the version line, second = the output file list
    original, regenerated = data_line_runs(src), data_line_runs(dst)
    assert regenerated[1] == original[1]
    # the sample model carries IHTPFLAG, so the list is 20 entries long
    assert gw.config.get("ihtpflag") is not None
    assert regenerated[1] == 20


def test_gw_main_file_list_is_19_without_ihtpflag(tmp_path):
    """A deck with no IHTPFLAG (2024.x style) must write exactly 19."""
    gw = read_gw_main(SIMULATION_DIR / "GW" / "GW_MAIN.dat")
    gw.config["ihtpflag"] = None
    dst = tmp_path / "GW_MAIN.dat"
    write_gw_main(gw, dst, base_dir=SIMULATION_DIR)
    assert data_line_runs(dst)[1] == 19


def test_rootzone_main_file_list_is_terminated(tmp_path):
    src = SIMULATION_DIR / "RootZone" / "RootZone_MAIN.dat"
    rz = read_rootzone_main(src)
    dst = tmp_path / "RootZone_MAIN.dat"
    write_rootzone_main(rz, dst, base_dir=SIMULATION_DIR)
    assert data_line_runs(dst)[1] == data_line_runs(src)[1]
