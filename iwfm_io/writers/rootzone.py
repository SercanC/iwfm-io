"""
Writers for IWFM root zone component files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.rootzone import RootZoneMain
from iwfm_io.readers.rootzone import _SOIL_COLS_V411, _SOIL_COLS_V412
from iwfm_io.writers._param_blocks import write_table_rows


def write_rootzone_main(
    rz: RootZoneMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the IWFM root zone component main file.

    Parameters
    ----------
    rz : RootZoneMain
    path : str or Path
    base_dir : str or Path, optional
        Simulation working directory (folder of the simulation main
        file) for relativising the referenced paths — IWFM resolves
        them against that folder.  When omitted, absolute paths are
        written.
    """
    w = IWFMFileWriter(path)
    w.write_header(rz.header)

    w.write_keyed_value(rz.convergence, "RZCONV")
    w.write_keyed_value(rz.max_iterations, "RZITERMX")
    w.write_keyed_value(rz.factor_cn, "FACTCN")
    w.write_keyed_value(rz.gw_uptake, "GWUPTK")

    if rz.path_order:
        # Replay the keyed block (paths + factors) in file order with
        # the original keywords — the keyword set varies by version.
        # IWFM reads the sub-file list as consecutive data lines until
        # a comment line terminates it, so the comment emitted at the
        # transition from file paths to the conversion factors is
        # load-bearing, not decoration.
        prev_kind = None
        for kind, keyword, key in rz.path_order:
            if prev_kind == "path" and kind == "scalar":
                w.write_comment("C  end of file list")
            if kind == "path":
                w.write_keyed_path(rz.file_paths.get(key), keyword,
                                   base_dir=base_dir)
            else:
                w.write_keyed_value(rz.config.get(key), keyword)
            prev_kind = kind
    else:
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

    # Per-element soil parameter table, regenerated from the DataFrame
    # (column order follows the file version the model was read from)
    w.write_comment("C  Soil, Precipitation and Runoff Destination Parameters")
    df = rz.element_params
    if df is not None:
        columns = (_SOIL_COLS_V412 if "icdstag" in df.columns
                   else _SOIL_COLS_V411)
        columns = [c for c in columns if c in df.columns]
        write_table_rows(w, df, columns,
                         widths=[8] + [10] * (len(columns) - 1))

    w.flush()
