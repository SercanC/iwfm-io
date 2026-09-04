"""DLL parity for temporal aggregation (issues #33/#34).

Verifies that ``read_budget_hdf`` / ``read_zbudget_hdf`` with
``interval="1MON"`` / ``"1YEAR"`` reproduce the IWFM DLL's own aggregated
reads — same rows, same window stamps (DLL serials put a 24:00 stamp at
that day's midnight; the library convention is next-day midnight, so
DLL date + 1 day == frame index), and machine-precision values, including
the LWU carry-over columns.

Runs only where the IWFM DLL loads (Windows x64 with an installed build).
"""

from datetime import datetime, timedelta

import numpy as np
import pytest

from tests.io.conftest import RESULTS_DIR, SAMPLE_MODEL

ZBUDGET_DIR = SAMPLE_MODEL / "ZBudget"
_EXCEL0 = datetime(1899, 12, 30)

_dll_ok = False
try:  # pragma: no cover - environment dependent
    from iwfm_io.dll import load_dll

    load_dll()
    _dll_ok = True
except Exception:
    pass

pytestmark = pytest.mark.skipif(not _dll_ok,
                                reason="IWFM DLL not available")


def _assert_frame_matches(vals, df, rtol=1e-9):
    """Compare a DLL (n_times, 1+n_cols) result to a reader DataFrame."""
    dll_dates = [_EXCEL0 + timedelta(days=float(v)) for v in vals[:, 0]]
    assert len(dll_dates) == len(df), \
        f"row count: DLL {len(dll_dates)} vs reader {len(df)}"
    for a, b in zip(dll_dates, df.index):
        assert a + timedelta(days=1) == b, f"stamp: DLL {a} vs reader {b}"
    dll_data = vals[:, 1:]
    diff = np.abs(dll_data - df.to_numpy())
    rel = diff / np.maximum(np.abs(dll_data), 1.0)
    assert float(rel.max()) < rtol, f"worst rel diff {rel.max():.3e}"


@pytest.mark.parametrize("fname", ["LWU.hdf", "GW.hdf"])
@pytest.mark.parametrize("interval", ["1MON", "1YEAR"])
def test_budget_interval_parity(fname, interval):
    from iwfm_io.dll.budget import IWFMBudget
    from iwfm_io.readers.hdf5 import read_budget_hdf

    path = RESULTS_DIR / fname
    if not path.exists():
        pytest.skip(f"{path} not found")

    mine = read_budget_hdf(path, interval=interval)
    with IWFMBudget(str(path)) as bud:
        specs = bud.get_time_specs()
        begin, end = specs["dates"][0], specs["dates"][-1]
        for li, loc_name in enumerate(mine["locations"], start=1):
            df = mine["data"][loc_name]
            vals = bud.get_values(li, list(range(1, len(df.columns) + 1)),
                                  begin, end, interval)
            _assert_frame_matches(vals, df)


def test_zbudget_zone_interval_parity():
    """LWU zone budget at 1YEAR: full column set, per-element LWU
    carry-over, anchored windows — column order is [Time] + FullDataNames
    for files without face flows/storages."""
    from iwfm_io.dll.zbudget import IWFMZBudget
    from iwfm_io.readers.hdf5 import read_zbudget_hdf

    path = RESULTS_DIR / "LWU_ZBud.hdf"
    zdef = ZBUDGET_DIR / "ZoneDef_SRs.dat"
    if not path.exists() or not zdef.exists():
        pytest.skip("LWU_ZBud.hdf / zone definition not found")

    mine = read_zbudget_hdf(path, zone_def=zdef, interval="1YEAR")
    names = mine["metadata"]["data_names_clean"]

    with IWFMZBudget(str(path)) as zb:
        zb.generate_zone_list_from_file(str(zdef))
        specs = zb.get_time_specs()
        begin, end = specs["dates"][0], specs["dates"][-1]
        for zone in zb.get_zone_list():
            zname = mine["zones"]["zone_names"][
                mine["zones"]["zone_ids"].index(int(zone))]
            df = mine["data"][zname][names]
            vals = zb.get_values_for_zone(
                int(zone), list(range(1, len(names) + 2)),
                begin, end, "1YEAR")
            _assert_frame_matches(vals, df)
