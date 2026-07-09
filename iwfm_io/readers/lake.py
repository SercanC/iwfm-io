"""
Readers for IWFM lake component files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import tokenize_data_line
from iwfm_io.models.lake import LakeMain


def read_lake_main(path: str | Path) -> LakeMain:
    """Read the IWFM lake component main file (e.g. ``Lake_MAIN.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    LakeMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # File paths
    max_elev_file, _ = reader.read_keyed_path(base_dir)
    budget_file, _ = reader.read_keyed_path(base_dir)
    final_elev_file, _ = reader.read_keyed_path(base_dir)

    # Conductance parameters
    factk, _ = reader.read_keyed_float()
    tunitk, _ = reader.read_keyed_value()
    factl, _ = reader.read_keyed_float()

    # Lake definitions - read remaining data lines
    # Format: lake_id  conductance  bed_thickness  precip_col  et_col  n_stream_nodes  name
    line = reader.next_data_line()
    tokens = tokenize_data_line(line)
    lake_params = []

    # Parse lake parameter line
    # Based on sample: 1  2.0  1.0  1  7  2  Lake1
    lake_id = int(tokens[0])
    conductance = float(tokens[1])
    bed_thickness = float(tokens[2])
    precip_col = int(tokens[3])
    et_col = int(tokens[4])
    n_stream_nodes = int(tokens[5])
    name = tokens[6] if len(tokens) > 6 else f"Lake{lake_id}"
    lake_params.append({
        "lake_id": lake_id,
        "conductance": conductance,
        "bed_thickness": bed_thickness,
        "precip_col": precip_col,
        "et_col": et_col,
        "n_stream_nodes": n_stream_nodes,
        "name": name,
    })

    params_df = pd.DataFrame(lake_params)

    # Initial lake elevation
    fact_init, _ = reader.read_keyed_float()
    init_line = reader.next_data_line()
    init_tokens = tokenize_data_line(init_line)
    # lake_id  initial_elev
    init_elev = float(init_tokens[1]) if len(init_tokens) > 1 else 0.0

    return LakeMain(
        header=header,
        budget_file=budget_file,
        final_elev_file=final_elev_file,
        n_lakes=len(lake_params),
        lake_params=params_df,
        max_elev_file=max_elev_file,
    )
