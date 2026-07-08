"""
Writers for miscellaneous IWFM files (SWShed, UnsatZone).
"""

from __future__ import annotations

from pathlib import Path

from iwfm.io._writer import IWFMFileWriter
from iwfm.io.models.misc import SWShedFile, UnsatZoneFile


def write_swshed(sw: SWShedFile, path: str | Path) -> None:
    """Write the IWFM small watershed file (e.g. ``SWShed.dat``).

    Parameters
    ----------
    sw : SWShedFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sw.header)

    base_dir = Path(path).parent

    # Output file paths
    w.write_keyed_path(sw.file_paths.get("budget"), "SWBUDFL", base_dir=base_dir)
    w.write_keyed_path(sw.file_paths.get("final"), "FNSWFL", base_dir=base_dir)

    # Number of watersheds and conversion factors
    w.write_keyed_value(sw.n_watersheds, "NSWSHED")
    cfg = sw.config
    w.write_keyed_value(cfg.get("facta", 1.0), "FACTA")
    w.write_keyed_value(cfg.get("factq", 1.0), "FACTQ")
    w.write_keyed_value(cfg.get("tunitq", "1DAY"), "TUNITQ")

    # Remaining raw lines
    for line in sw.raw_lines:
        w.write_raw(line)

    w.flush()


def write_unsatzone(uz: UnsatZoneFile, path: str | Path) -> None:
    """Write the IWFM unsaturated zone file (e.g. ``UnsatZone.dat``).

    Parameters
    ----------
    uz : UnsatZoneFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(uz.header)

    base_dir = Path(path).parent

    # Main parameters
    w.write_keyed_value(uz.n_unsat_layers, "NUZL")
    w.write_keyed_value(uz.convergence, "UZCONV")
    w.write_keyed_value(uz.max_iterations, "UZITERMX")

    # Output file paths
    w.write_keyed_path(uz.file_paths.get("budget"), "UZBUDFL", base_dir=base_dir)
    w.write_keyed_path(uz.file_paths.get("zbudget"), "UZZBUDFL", base_dir=base_dir)
    w.write_keyed_path(uz.file_paths.get("final"), "UZFNFL", base_dir=base_dir)

    # Remaining raw lines
    for line in uz.raw_lines:
        w.write_raw(line)

    w.flush()
