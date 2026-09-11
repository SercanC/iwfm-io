"""
Writers for IWFM lake component files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.lake import LakeMain
from iwfm_io.models.timeseries import TimeSeriesFile
from iwfm_io.writers._param_blocks import (
    check_count,
    fmt_int,
    fmt_name,
    fmt_num,
)
from iwfm_io.writers._timeseries import write_ts_body


def write_lake_main(
    lake: LakeMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the IWFM lake component main file.

    Regenerates every section: file references, bed conversion factors,
    the per-lake parameter table, and the initial lake elevations.

    Parameters
    ----------
    lake : LakeMain
    path : str or Path
    base_dir : str or Path, optional
        Simulation working directory for relativising the referenced
        paths (IWFM resolves them against that folder).
    """
    w = IWFMFileWriter(path)
    w.write_header(lake.header)

    w.write_keyed_path(lake.max_elev_file, "MXLKELVFL", base_dir=base_dir)
    w.write_keyed_path(lake.budget_file, "LKBUDFL", base_dir=base_dir)
    w.write_keyed_path(lake.final_elev_file, "FNLKELVFL", base_dir=base_dir)

    n_params = 0 if lake.lake_params is None else len(lake.lake_params)
    check_count(lake.n_lakes, n_params, "Lake main: lake parameter rows")
    if lake.initial_elevations is not None:
        check_count(lake.n_lakes, len(lake.initial_elevations),
                    "Lake main: initial elevation rows")

    w.write_comment("C  Lake Parameters")
    w.write_keyed_value(fmt_num(lake.factk), "FACTK")
    w.write_keyed_value(lake.tunitk, "TUNITK")
    w.write_keyed_value(fmt_num(lake.factl), "FACTL")

    if lake.lake_params is not None:
        for _, row in lake.lake_params.iterrows():
            tokens = [
                fmt_int(row["lake_id"], "lake_id"),
                fmt_num(row["conductance"], what="lake conductance"),
                fmt_num(row["bed_thickness"], what="lake bed_thickness"),
                fmt_int(row["max_elev_col"], "lake max_elev_col"),
                fmt_int(row["et_col"], "lake et_col"),
                fmt_int(row["precip_col"], "lake precip_col"),
                fmt_name(row.get("name"), "lake name"),
            ]
            note = row.get("notes")
            w.write_data_line(tokens, widths=[6, 10, 10, 8, 8, 8, 12],
                              note=note if isinstance(note, str) else "")

    w.write_comment("C  Initial Lake Elevations")
    w.write_keyed_value(fmt_num(lake.init_elev_factor), "FACT")
    if lake.initial_elevations is not None:
        for _, row in lake.initial_elevations.iterrows():
            w.write_data_line(
                [fmt_int(row["lake_id"], "lake_id"),
                 fmt_num(row["elevation"], what="lake initial elevation")],
                widths=[8, 12])

    w.flush()


def write_max_lake_elev(ts: TimeSeriesFile, path: str | Path) -> None:
    """Write an IWFM maximum lake elevation file.

    Parameters
    ----------
    ts : TimeSeriesFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ts.header)
    spec = ts.spec
    fields = list(zip(
        [spec.n_columns, spec.factor, spec.n_steps_update,
         spec.repeat_freq, spec.dss_file],
        ["NCOLHLMX", "FACTHLMX", "NSPHLMX", "NFQHLMX", "DSSFL"]))
    write_ts_body(w, fields, ts.data, ts.dss_pathnames,
                  n_columns=spec.n_columns)

    w.flush()
