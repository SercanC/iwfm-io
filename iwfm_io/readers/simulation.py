"""
Reader for the IWFM simulation main file.
"""

from __future__ import annotations

import re
from pathlib import Path

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import split_keyed_line
from iwfm_io.models.simulation import SimulationMain

# File-list entries are keyed "/ N: DESCRIPTION"
_FILE_NUM_RE = re.compile(r"^(\d+)\s*:")

# Canonical role names by file-list position (1-based)
_PATH_KEYS = [
    "preprocessor_bin",  # 1
    "gw_main",           # 2
    "stream_main",       # 3
    "lake_main",         # 4
    "rootzone_main",     # 5
    "swshed",            # 6
    "unsatzone",         # 7
    "irigfrac",          # 8
    "supply_adjust",     # 9
    "precip",            # 10
    "et",                # 11
    "crop_coeff",        # 12 (absent in IWFM 2024.x mains)
]


def read_simulation_main(
    path: str | Path,
    follow_references: bool = False,
) -> SimulationMain:
    """Read the IWFM simulation main file (e.g. ``Simulation_MAIN.IN``).

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        If True, also read referenced child files.

    Returns
    -------
    SimulationMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # 3 title lines
    titles = []
    for _ in range(3):
        line = reader.next_data_line()
        titles.append(line.strip())

    # File list: the entry count varies by IWFM version (12 in 2015-era
    # mains, 11 in 2024.x), so read entries for as long as the keyword
    # matches "N: DESCRIPTION" instead of assuming a fixed count.
    file_paths: dict[str, str | None] = {}
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value_str, keyword = split_keyed_line(line)
        m = _FILE_NUM_RE.match(keyword)
        if m is None:
            break
        reader.next_data_line()
        idx = int(m.group(1))
        key = _PATH_KEYS[idx - 1] if 1 <= idx <= len(_PATH_KEYS) else f"file_{idx}"
        if not value_str or value_str == "*":
            file_paths[key] = None
        else:
            file_paths[key] = str(Path(base_dir) / value_str.replace("\\", "/"))

    # Scalar settings, identified by keyword rather than position because
    # the set differs across versions (e.g. STOPCVL exists only in older
    # mains). KOPTDV is the last entry in all known layouts.
    scalars: dict[str, str] = {}
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value_str, keyword = split_keyed_line(line)
        if not keyword:
            break
        reader.next_data_line()
        key = keyword.split()[0].upper()
        scalars.setdefault(key, value_str)
        if key == "KOPTDV":
            break

    def _int(key: str, default: int = 0) -> int:
        v = scalars.get(key)
        return int(v) if v else default

    def _float(key: str, default: float = 0.0) -> float:
        v = scalars.get(key)
        return float(v) if v else default

    sim_begin = scalars.get("BDT", "")
    restart = _int("RESTART")
    time_unit = scalars.get("UNITT", "")
    sim_end = scalars.get("EDT", "")

    output = {
        "istrt": _int("ISTRT"),
        "kdeb": _int("KDEB"),
        "cache": _int("CACHE", 500000),
    }

    solver = {
        "msolve": _int("MSOLVE", 2),
        "relax": _float("RELAX", 1.0),
        "mxiter": _int("MXITER", 1500),
        "mxitersp": _int("MXITERSP", 50),
        "stopc": _float("STOPC", 0.0001),
    }
    if "STOPCVL" in scalars:
        solver["stopcvl"] = _float("STOPCVL")
    solver["stopcsp"] = _float("STOPCSP", 0.001)

    supply_adjust_flag = _int("KOPTDV")

    result = SimulationMain(
        header=header,
        titles=titles,
        file_paths=file_paths,
        sim_begin=sim_begin,
        sim_end=sim_end,
        time_unit=time_unit,
        restart=restart,
        solver=solver,
        output=output,
        supply_adjust_flag=supply_adjust_flag,
    )

    if follow_references:
        from iwfm_io.readers.timeseries import read_et, read_precip, read_irigfrac, read_supply_adjust
        children: dict = {}
        if file_paths.get("precip"):
            children["precip"] = read_precip(file_paths["precip"])
        if file_paths.get("et"):
            children["et"] = read_et(file_paths["et"])
        if file_paths.get("irigfrac"):
            children["irigfrac"] = read_irigfrac(file_paths["irigfrac"])
        if file_paths.get("supply_adjust"):
            children["supply_adjust"] = read_supply_adjust(file_paths["supply_adjust"])
        result.children = children

    return result
