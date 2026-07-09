"""
Writer for the IWFM simulation main file.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.simulation import SimulationMain


def write_simulation_main(
    sim: SimulationMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the IWFM simulation main file.

    Parameters
    ----------
    sim : SimulationMain
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(sim.header)

    for title in sim.titles:
        w.write_raw(f"    {title}")

    path_keys = [
        "preprocessor_bin", "gw_main", "stream_main", "lake_main",
        "rootzone_main", "swshed", "unsatzone", "irigfrac",
        "supply_adjust", "precip", "et", "crop_coeff",
    ]
    labels = [
        "1: BINARY INPUT FROM PRE-PROCESSOR",
        "2: GROUNDWATER COMPONENT MAIN FILE",
        "3: STREAM COMPONENT MAIN FILE",
        "4: LAKE COMPONENT MAIN FILE",
        "5: ROOT ZONE COMPONENT MAIN FILE",
        "6: SMALL WATERSHED COMPONENT MAIN FILE",
        "7: UNSATURATED ZONE COMPONENT MAIN FILE",
        "8: IRRIGATION FRACTIONS DATA FILE",
        "9: SUPPLY ADJUSTMENT SPECIFICATION DATA FILE",
        "10: PRECIPITATION DATA FILE",
        "11: EVAPOTRANSPIRATION DATA FILE",
        "12: CROP COEFFICIENT DATA FILE",
    ]
    for key, label in zip(path_keys, labels):
        # Only write entries the source file had — the file-list length
        # varies by IWFM version (e.g. no crop_coeff entry in 2024.x).
        if key in sim.file_paths:
            w.write_keyed_path(sim.file_paths[key], label, base_dir=base_dir)

    w.write_keyed_value(sim.sim_begin, "BDT")
    w.write_keyed_value(sim.restart, "RESTART")
    w.write_keyed_value(sim.time_unit, "UNITT")
    w.write_keyed_value(sim.sim_end, "EDT")

    out = sim.output
    w.write_keyed_value(out.get("istrt", 0), "ISTRT")
    w.write_keyed_value(out.get("kdeb", 0), "KDEB")
    w.write_keyed_value(out.get("cache", 500000), "CACHE")

    sv = sim.solver
    w.write_keyed_value(sv.get("msolve", 2), "MSOLVE")
    w.write_keyed_value(sv.get("relax", 1.0), "RELAX")
    w.write_keyed_value(sv.get("mxiter", 1500), "MXITER")
    w.write_keyed_value(sv.get("mxitersp", 50), "MXITERSP")
    w.write_keyed_value(sv.get("stopc", 0.0001), "STOPC")
    if "stopcvl" in sv:
        # STOPCVL exists only in older (2015-era) main file layouts
        w.write_keyed_value(sv["stopcvl"], "STOPCVL")
    w.write_keyed_value(sv.get("stopcsp", 0.001), "STOPCSP")

    w.write_keyed_value(sim.supply_adjust_flag, "KOPTDV")

    w.flush()
