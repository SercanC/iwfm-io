"""
Readers for IWFM lake component files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._parser import IWFMFileReader
import re

from iwfm_io._tokens import split_keyed_line, tokenize_data_line
from iwfm_io.models.lake import LakeMain
from iwfm_io.models.timeseries import TimeSeriesFile


def read_lake_main(path: str | Path) -> LakeMain:
    """Read the IWFM lake component main file (e.g. ``Lake_MAIN.dat``).

    Parses the file references, the lake bed conversion factors, the
    per-lake parameter table (any number of lakes), and the initial
    lake elevations.  The referenced maximum-elevation time series is
    read separately with :func:`read_max_lake_elev`.

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

    # File references
    max_elev_file, _ = reader.read_keyed_path(base_dir)
    budget_file, _ = reader.read_keyed_path(base_dir)
    final_elev_file, _ = reader.read_keyed_path(base_dir)

    # Lake bed conversion factors
    factk, _ = reader.read_keyed_float()
    tunitk, _ = reader.read_keyed_value()
    factl, _ = reader.read_keyed_float()

    # Lake parameter table: IL CLAKE DLAKE ICHLMAX ICETLK ICPCPLK NAMELK
    # — one row per lake; the table ends at the initial-elevation FACT
    # keyed line.
    lake_rows: list[dict] = []
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if len(tokens) < 6:
            # the "1.0 / FACT" line opening the next section has a
            # single value token
            break
        reader.next_data_line()
        m = re.search(r"\s/(.+)$", line)
        lake_rows.append({
            "lake_id": int(tokens[0]),
            "conductance": float(tokens[1]),
            "bed_thickness": float(tokens[2]),
            "max_elev_col": int(tokens[3]),
            "et_col": int(tokens[4]),
            "precip_col": int(tokens[5]),
            "name": " ".join(tokens[6:]),
            "notes": (m.group(1).strip().lstrip("/").strip()
                      if m else ""),
        })
    lake_params = pd.DataFrame(lake_rows) if lake_rows else None

    # Initial lake elevations: FACT, then one ILAKE HLAKE row per lake
    init_elev_factor = 1.0
    init_rows: list[dict] = []
    if not reader.eof:
        init_elev_factor, _ = reader.read_keyed_float()
        while True:
            line = reader.peek_data_line()
            if line is None:
                break
            tokens = tokenize_data_line(line)
            if len(tokens) < 2:
                break
            try:
                row = {"lake_id": int(tokens[0]),
                       "elevation": float(tokens[1])}
            except ValueError:
                break
            reader.next_data_line()
            init_rows.append(row)
    initial_elevations = pd.DataFrame(init_rows) if init_rows else None

    return LakeMain(
        header=header,
        max_elev_file=max_elev_file,
        budget_file=budget_file,
        final_elev_file=final_elev_file,
        factk=factk,
        tunitk=tunitk,
        factl=factl,
        n_lakes=len(lake_rows),
        lake_params=lake_params,
        init_elev_factor=init_elev_factor,
        initial_elevations=initial_elevations,
    )


def read_max_lake_elev(path: str | Path) -> TimeSeriesFile:
    """Read an IWFM maximum lake elevation file (e.g. ``MaxLakeElev.dat``).

    Standard 5-param time-series file: NCOLHLMX, FACTHLMX, NSPHLMX,
    NFQHLMX, DSSFL, then rows of ``DATE  elev1 .. elevNCOL`` (or DSS
    pathnames when DSSFL is set).  The lake parameter table's
    ``max_elev_col`` points at these 1-based columns.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    TimeSeriesFile
    """
    from iwfm_io.readers.timeseries import _read_ts_data_to_eof

    reader = IWFMFileReader(path)
    header = reader.read_header()
    spec = reader.read_timeseries_spec()

    result = TimeSeriesFile(header=header, spec=spec)
    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = _read_ts_data_to_eof(reader, spec.n_columns)
    return result
