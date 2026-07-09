"""
Writers for IWFM lake component files.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.lake import LakeMain


def write_lake_main(lake: LakeMain, path: str | Path) -> None:
    """Write the IWFM lake component main file.

    Parameters
    ----------
    lake : LakeMain
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(lake.header)

    w.write_keyed_path(lake.max_elev_file, "MXLKELVFL")
    w.write_keyed_path(lake.budget_file, "LKBUDFL")
    w.write_keyed_path(lake.final_elev_file, "FNLKELVFL")

    if lake.lake_params is not None:
        for _, row in lake.lake_params.iterrows():
            tokens = [
                int(row["lake_id"]),
                row["conductance"],
                row["bed_thickness"],
                int(row["precip_col"]),
                int(row["et_col"]),
                int(row["n_stream_nodes"]),
                row["name"],
            ]
            w.write_data_line(tokens, widths=[6, 8, 8, 6, 6, 6, 12])

    w.flush()
