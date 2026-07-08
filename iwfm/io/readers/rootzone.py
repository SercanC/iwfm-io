"""
Readers for IWFM root zone component files.

The root zone is the most complex IWFM component with many sub-files.
This reader parses the main file structure and key parameters, storing
complex subsections as raw data for round-trip fidelity.
"""

from __future__ import annotations

from pathlib import Path

from iwfm.io._parser import IWFMFileReader
from iwfm.io.models.rootzone import RootZoneMain


def read_rootzone_main(path: str | Path) -> RootZoneMain:
    """Read the IWFM root zone component main file.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    RootZoneMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Convergence and iteration parameters
    convergence, _ = reader.read_keyed_float()
    max_iterations, _ = reader.read_keyed_int()
    factor_cn, _ = reader.read_keyed_float()
    gw_uptake, _ = reader.read_keyed_int()

    # Sub-component file paths
    file_path_keys = [
        "nonponded_ag",    # AGNPFL
        "ponded_ag",       # PFL
        "urban",           # URBFL
        "native_veg",      # NVRVFL
        "return_flow",     # RFFL
        "reuse_frac",      # RUFL
        "irig_period",     # IPFL
        "moisture_src",    # MSRCFL
        "ag_water_demand", # AGWDFL
        "lwu_budget",      # LWUBUDFL
        "rz_budget",       # RZBUDFL
        "lwu_zbudget",     # ZLWUBUDFL
        "rz_zbudget",      # ZRZBUDFL
        "area_scale",      # ARSCLFL
    ]

    file_paths: dict[str, str | None] = {}
    for key in file_path_keys:
        fp, kw = reader.read_keyed_path(base_dir)
        file_paths[key] = fp

    # Store remaining lines as raw data (soil params, element tables, etc.)
    raw_lines = reader.skip_to_end()

    return RootZoneMain(
        header=header,
        convergence=convergence,
        max_iterations=max_iterations,
        factor_cn=factor_cn,
        gw_uptake=gw_uptake,
        file_paths=file_paths,
        raw_lines=raw_lines,
    )
