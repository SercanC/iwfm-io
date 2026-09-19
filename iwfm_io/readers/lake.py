"""
Readers for IWFM lake component files.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._parser import IWFMFileReader
import re

from iwfm_io._tokens import split_name_notes, tokenize_data_line
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
    what = "lake parameter row"
    with reader.section("lake parameter table"):
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
            lake_id = reader.to_ints(tokens[:1], what)[0]
            cond, thick = reader.to_floats(tokens[1:3], what)
            cols = reader.to_ints(tokens[3:6], what)
            lake_name, lake_note = split_name_notes(
                " ".join(tokens[6:]),
                m.group(1).strip().lstrip("/").strip() if m else "")
            lake_rows.append({
                "lake_id": lake_id,
                "conductance": cond,
                "bed_thickness": thick,
                "max_elev_col": cols[0],
                "et_col": cols[1],
                "precip_col": cols[2],
                "name": lake_name,
                "notes": lake_note,
            })
    lake_params = pd.DataFrame(lake_rows) if lake_rows else None

    # Initial lake elevations: FACT, then one ILAKE HLAKE row per lake
    init_elev_factor = 1.0
    init_rows: list[dict] = []
    with reader.section("initial lake elevations"):
        if reader.peek_data_line() is not None:
            init_elev_factor, _ = reader.read_keyed_float()
            while True:
                line = reader.peek_data_line()
                if line is None:
                    break
                tokens = tokenize_data_line(line)
                if len(tokens) < 2:
                    reader.next_data_line()
                    reader.degrade(
                        "initial lake elevation row: expected 2 values "
                        f"(ILAKE HLAKE) but found {len(tokens)}: "
                        f"{line.strip()!r}; the rest of the file was not "
                        "read")
                    break
                reader.next_data_line()
                lake_id = reader.to_ints(tokens[:1],
                                         "initial lake elevation row")[0]
                elev = reader.to_floats(tokens[1:2],
                                        "initial lake elevation row")[0]
                init_rows.append({"lake_id": lake_id, "elevation": elev})
        if lake_rows and len(init_rows) != len(lake_rows):
            reader.degrade(
                f"{len(init_rows)} initial lake elevation rows for "
                f"{len(lake_rows)} lakes")
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
    reader = IWFMFileReader(path)
    header = reader.read_header()
    spec = reader.read_timeseries_spec()

    result = TimeSeriesFile(header=header, spec=spec)
    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = reader.read_ts_rows(spec.n_columns,
                                          what="maximum lake elevations")
    return result
