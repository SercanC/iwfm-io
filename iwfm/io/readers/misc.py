"""
Readers for miscellaneous IWFM files (SWShed, UnsatZone).
"""

from __future__ import annotations

from pathlib import Path

from iwfm.io._parser import IWFMFileReader
from iwfm.io.models.misc import SWShedFile, UnsatZoneFile


def read_swshed(path: str | Path) -> SWShedFile:
    """Read the IWFM small watershed file (e.g. ``SWShed.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SWShedFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Output file paths
    budget_file, _ = reader.read_keyed_path(base_dir)
    final_file, _ = reader.read_keyed_path(base_dir)
    file_paths = {"budget": budget_file, "final": final_file}

    # Number of watersheds and conversion factors
    n_watersheds, _ = reader.read_keyed_int()
    facta, _ = reader.read_keyed_float()
    factq, _ = reader.read_keyed_float()
    tunitq, _ = reader.read_keyed_value()

    config = {"facta": facta, "factq": factq, "tunitq": tunitq}

    # Remaining lines (watershed definitions, soil params, GW params, etc.)
    raw_lines = reader.skip_to_end()

    return SWShedFile(
        header=header,
        file_paths=file_paths,
        n_watersheds=n_watersheds,
        config=config,
        raw_lines=raw_lines,
    )


def read_unsatzone(path: str | Path) -> UnsatZoneFile:
    """Read the IWFM unsaturated zone file (e.g. ``UnsatZone.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    UnsatZoneFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Main parameters
    n_unsat_layers, _ = reader.read_keyed_int()
    convergence, _ = reader.read_keyed_float()
    max_iterations, _ = reader.read_keyed_int()

    # Output file paths
    budget_file, _ = reader.read_keyed_path(base_dir)
    zbudget_file, _ = reader.read_keyed_path(base_dir)
    final_file, _ = reader.read_keyed_path(base_dir)
    file_paths = {
        "budget": budget_file,
        "zbudget": zbudget_file,
        "final": final_file,
    }

    # Remaining lines (groups, parameters, element data)
    raw_lines = reader.skip_to_end()

    return UnsatZoneFile(
        header=header,
        n_unsat_layers=n_unsat_layers,
        convergence=convergence,
        max_iterations=max_iterations,
        file_paths=file_paths,
        raw_lines=raw_lines,
    )
