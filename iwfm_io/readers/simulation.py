"""
Reader for the IWFM simulation main file.
"""

from __future__ import annotations

import re
from pathlib import Path

from iwfm_io._parser import IWFMFileReader
from iwfm_io._strict import strict_mode
from iwfm_io._tokens import keyword_name, split_keyed_line
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


#: Keyed scalars a simulation main may carry (all known layouts).
_KNOWN_SCALARS = frozenset({
    "BDT", "RESTART", "UNITT", "EDT", "DELTAT", "ISTRT", "KDEB", "CACHE",
    "MSOLVE", "RELAX", "MXITER", "MXITERSP", "STOPC", "STOPCVL", "STOPCSP",
    "KOPTDV",
})


def read_simulation_main(
    path: str | Path,
    follow_references: bool = False,
    strict: bool | None = None,
) -> SimulationMain:
    """Read the IWFM simulation main file (e.g. ``Simulation_MAIN.IN``).

    The file must carry at least one ``/ N:`` file-list entry and the
    ``BDT``/``EDT`` simulation-period keywords; anything else is not a
    simulation main and raises :class:`~iwfm_io.IWFMParseError`.  An
    unrecognized keyed scalar in the control block is an error in strict
    mode (it would be dropped from written output) and a warning in
    lenient mode.

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        If True, also read referenced child files.
    strict : bool, optional
        Reader mode: ``True`` raises on malformed input, ``False`` warns
        and keeps what parsed.  ``None`` (default) uses the mode in
        effect (see :func:`iwfm_io.strict_mode`; strict by default).

    Returns
    -------
    SimulationMain
    """
    if strict is not None:
        with strict_mode(strict):
            return read_simulation_main(path, follow_references)
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Title lines: up to 3 non-comment data lines before the file list.
    # A file-list entry is keyed "/ N: DESCRIPTION", so stop early when
    # one appears (decks may carry fewer than 3 titles).
    titles = []
    with reader.section("titles"):
        for _ in range(3):
            line = reader.peek_data_line()
            if line is None:
                break
            _, kw = split_keyed_line(line)
            if kw and _FILE_NUM_RE.match(kw):
                break
            reader.next_data_line()
            titles.append(line.strip())

    # File list: the entry count varies by IWFM version (12 in 2015-era
    # mains, 11 in 2024.x), so read entries for as long as the keyword
    # matches "N: DESCRIPTION" instead of assuming a fixed count.
    file_paths: dict[str, str | None] = {}
    with reader.section("file list"):
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
        if not file_paths:
            raise reader.error(
                "no file-list entries (lines keyed '/ N: DESCRIPTION') "
                "found — this is not an IWFM simulation main file")

    # Scalar settings, identified by keyword rather than position because
    # the set differs across versions (e.g. STOPCVL exists only in older
    # mains). KOPTDV is the last entry in all known layouts; the block
    # ends there, at EOF, or at a keyword-less line.
    scalars: dict[str, str] = {}
    with reader.section("simulation control"):
        while True:
            line = reader.peek_data_line()
            if line is None:
                break
            value_str, keyword = split_keyed_line(line)
            if not keyword:
                reader.next_data_line()
                reader.degrade(
                    "keyword-less line in the simulation control block: "
                    f"{line.strip()[:60]!r}; it and anything after it are "
                    "not modeled and will be missing from written output")
                break
            reader.next_data_line()
            key = keyword_name(keyword)
            if key not in _KNOWN_SCALARS:
                reader.degrade(
                    f"unrecognized keyed value {key!r} in the simulation "
                    "control block; it is not modeled and will be missing "
                    "from written output")
            scalars.setdefault(key, value_str)
            if key == "KOPTDV":
                break
        missing = [k for k in ("BDT", "EDT") if k not in scalars]
        if missing:
            raise reader.error(
                f"required simulation-period keyword(s) {missing} not "
                "found — this is not an IWFM simulation main file")

    def _int(key: str, default: int = 0) -> int:
        v = scalars.get(key)
        if not v:
            return default
        try:
            return int(v)
        except ValueError:
            raise reader.error(
                f"expected an integer for {key} but found {v!r}") from None

    def _float(key: str, default: float = 0.0) -> float:
        v = scalars.get(key)
        if not v:
            return default
        try:
            return float(v)
        except ValueError:
            raise reader.error(
                f"expected a number for {key} but found {v!r}") from None

    sim_begin = scalars.get("BDT", "")
    restart = _int("RESTART")
    time_unit = scalars.get("UNITT", "")
    sim_end = scalars.get("EDT", "")
    # DELTAT exists only in the "date and time NOT tracked" layout
    # (BDT/EDT given as plain numbers instead of dates).
    time_step = _float("DELTAT") if "DELTAT" in scalars else None

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
        time_step=time_step,
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
