"""
Writers for IWFM root zone component files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.rootzone import RootZoneMain


def write_rootzone_main(rz: RootZoneMain, path: str | Path) -> None:
    """Write the IWFM root zone component main file.

    Parameters
    ----------
    rz : RootZoneMain
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(rz.header)

    w.write_keyed_value(rz.convergence, "RZCONV")
    w.write_keyed_value(rz.max_iterations, "RZITERMX")
    w.write_keyed_value(rz.factor_cn, "FACTCN")
    w.write_keyed_value(rz.gw_uptake, "GWUPTK")

    path_keys = [
        "nonponded_ag", "ponded_ag", "urban", "native_veg",
        "return_flow", "reuse_frac", "irig_period", "moisture_src",
        "ag_water_demand", "lwu_budget", "rz_budget", "lwu_zbudget",
        "rz_zbudget", "area_scale",
    ]
    labels = [
        "AGNPFL", "PFL", "URBFL", "NVRVFL", "RFFL", "RUFL", "IPFL",
        "MSRCFL", "AGWDFL", "LWUBUDFL", "RZBUDFL", "ZLWUBUDFL",
        "ZRZBUDFL", "ARSCLFL",
    ]
    for key, label in zip(path_keys, labels):
        w.write_keyed_path(rz.file_paths.get(key), label)

    # Write remaining raw lines
    for line in rz.raw_lines:
        w.write_raw(line)

    w.flush()
