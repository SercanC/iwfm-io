"""
Readers for IWFM stream component input files.

All functions return dataclass containers with pandas DataFrames.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from iwfm.io._parser import IWFMFileReader
from iwfm.io._tokens import tokenize_data_line
from iwfm.io.models.base import TimeSeriesSpec
from iwfm.io.models.stream import (
    BypassSpecsFile,
    DiverSpecsFile,
    DiversionsFile,
    StreamInflowFile,
    StreamMain,
)


# ------------------------------------------------------------------
# Internal helper: read timeseries rows storing dates as strings
# ------------------------------------------------------------------

def _read_ts_data_to_eof(
    reader: IWFMFileReader,
    n_columns: int,
    col_names: list[str] | None = None,
) -> pd.DataFrame:
    """Read time-series data rows until EOF, storing dates as strings.

    IWFM files use special years such as 4000 or 2500 for cyclic data
    that fall outside the pandas Timestamp range.  Dates are therefore
    kept as raw IWFM date strings in a ``date`` column.

    Parameters
    ----------
    reader : IWFMFileReader
    n_columns : int
    col_names : list[str], optional

    Returns
    -------
    pd.DataFrame
        Columns: ``date`` (str), then one per data column.
    """
    if col_names is None:
        col_names = [f"col_{i + 1}" for i in range(n_columns)]

    date_strs: list[str] = []
    values: list[list[float]] = []

    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if not tokens:
            break
        # First token must look like an IWFM date MM/DD/YYYY_HH:MM
        if "/" not in tokens[0] or "_" not in tokens[0]:
            break
        reader.next_data_line()
        row_vals = [float(v) for v in tokens[1 : n_columns + 1]]
        date_strs.append(tokens[0])
        values.append(row_vals)

    if not date_strs:
        return pd.DataFrame(columns=["date"] + col_names)

    df = pd.DataFrame(values, columns=col_names)
    df.insert(0, "date", date_strs)
    return df


# ------------------------------------------------------------------
# Stream Main
# ------------------------------------------------------------------

def read_stream_main(path: str | Path) -> StreamMain:
    """Read an IWFM stream main file (e.g. ``Stream_MAIN.dat``).

    Parameters
    ----------
    path : str or Path
        Path to the stream main file.

    Returns
    -------
    StreamMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # ---- File paths (6 keyed path lines) ----
    path_keys = [
        "inflow",
        "diver_specs",
        "bypass_specs",
        "diversions",
        "strm_bud_hdf",
        "diver_detail_hdf",
    ]
    file_paths: dict[str, str | None] = {}
    for key in path_keys:
        fp, _ = reader.read_keyed_path(base_dir)
        file_paths[key] = fp

    # ---- Hydrograph output settings ----
    config: dict = {}

    n_hydrographs, _ = reader.read_keyed_int()
    config["n_hydrographs"] = n_hydrographs

    ihsqr, _ = reader.read_keyed_int()
    config["ihsqr"] = ihsqr

    factvrou, _ = reader.read_keyed_float()
    config["factvrou"] = factvrou

    unitvrou, _ = reader.read_keyed_value()
    config["unitvrou"] = unitvrou

    factltou, _ = reader.read_keyed_float()
    config["factltou"] = factltou

    unitltou, _ = reader.read_keyed_value()
    config["unitltou"] = unitltou

    hydro_out_file, _ = reader.read_keyed_path(base_dir)
    config["hydro_out_file"] = hydro_out_file

    # ---- Hydrograph spec lines: IOUTR  NAME ----
    hydrograph_specs: list[dict] = []
    for _ in range(n_hydrographs):
        line = reader.next_data_line()
        tokens = line.split()
        node_id = int(tokens[0])
        name = tokens[1] if len(tokens) > 1 else ""
        hydrograph_specs.append({"node_id": node_id, "name": name})

    # ---- Node budget settings ----
    n_node_budgets, _ = reader.read_keyed_int()
    config["n_node_budgets"] = n_node_budgets

    node_bud_file, _ = reader.read_keyed_path(base_dir)
    config["node_bud_file"] = node_bud_file

    node_budget_nodes: list[int] = []
    for _ in range(n_node_budgets):
        line = reader.next_data_line()
        node_budget_nodes.append(int(line.strip()))

    # ---- Stream bed parameters ----
    factk, _ = reader.read_keyed_float()
    config["factk"] = factk

    tunitk, _ = reader.read_keyed_value()
    config["tunitk"] = tunitk

    factl, _ = reader.read_keyed_float()
    config["factl"] = factl

    # Reach parameter rows: IR  CSTRM  DSTRM  WETPR  [extra cols...]
    # Rows may carry a trailing "/ comment" (e.g. C2VSimFG reach names)
    # and newer formats add columns, so a row is distinguished from the
    # next keyed line by its token count after the comment is stripped —
    # keyed scalar lines have a single value token, rows have >= 4.
    reach_rows: list[dict] = []
    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if len(tokens) < 4:
            break
        reader.next_data_line()
        row = {
            "reach_id": int(tokens[0]),
            "conductance": float(tokens[1]),
            "width": float(tokens[2]),
            "bed_thickness": float(tokens[3]),
        }
        for i, extra in enumerate(tokens[4:], start=5):
            row[f"col_{i}"] = float(extra)
        reach_rows.append(row)

    reach_params = pd.DataFrame(reach_rows)

    # ---- Hydraulic disconnection type ----
    intrctype, _ = reader.read_keyed_int()
    config["intrctype"] = intrctype

    # ---- Stream evaporation STARFL (optional, may be blank) ----
    starfl, _ = reader.read_keyed_path(base_dir)
    config["starfl"] = starfl

    # Remaining lines (stream evaporation node table) are not parsed;
    # they follow after STARFL and only matter when STARFL is non-blank.

    return StreamMain(
        header=header,
        file_paths=file_paths,
        config=config,
        hydrograph_specs=hydrograph_specs,
        node_budget_nodes=node_budget_nodes,
        reach_params=reach_params if reach_rows else None,
    )


# ------------------------------------------------------------------
# Stream Inflow
# ------------------------------------------------------------------

def read_stream_inflow(path: str | Path) -> StreamInflowFile:
    """Read an IWFM stream inflow file (e.g. ``StreamInflow.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    StreamInflowFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    # 5-param time-series spec
    spec = reader.read_timeseries_spec()

    # Column-to-node assignment lines. Two layouts exist:
    #   ID  IRST   (explicit column id + stream node)
    #   IRST       (stream node only, column id implicit — e.g. C2VSimFG)
    node_assignments: list[tuple[int, int]] = []
    for i in range(spec.n_columns):
        line = reader.next_data_line()
        tokens = tokenize_data_line(line)
        if len(tokens) >= 2:
            node_assignments.append((int(tokens[0]), int(tokens[1])))
        else:
            node_assignments.append((i + 1, int(tokens[0])))

    result = StreamInflowFile(
        header=header,
        spec=spec,
        node_assignments=node_assignments,
    )

    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        col_names = [f"col_{i + 1}" for i in range(spec.n_columns)]
        result.data = _read_ts_data_to_eof(reader, spec.n_columns, col_names)

    return result


# ------------------------------------------------------------------
# Diversion Specs
# ------------------------------------------------------------------

def read_diver_specs(path: str | Path) -> DiverSpecsFile:
    """Read an IWFM diversion specification file (e.g. ``DiverSpecs.dat``).

    The diversion spec format is complex (nested element groups, recharge
    zones, spill locations) and varies non-trivially with model
    configuration.  Only the ``NRDV`` header line is parsed; all remaining
    data lines are stored verbatim for lossless round-trip writing.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    DiverSpecsFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_diversions, _ = reader.read_keyed_int()

    # Collect all remaining raw lines (data + comments)
    raw_data = reader.skip_to_end()

    # Parse the basic per-diversion table from the first NRDV data rows.
    # Column layouts vary across IWFM versions, but the first two columns
    # (ID, export stream node — 0 means import from outside the model)
    # and the trailing NAME token are stable.
    from iwfm.io._tokens import is_comment
    rows = []
    for line in raw_data:
        if is_comment(line):
            continue
        toks = tokenize_data_line(line)
        if len(toks) < 3:
            continue
        try:
            rows.append({
                "diversion_id": int(float(toks[0])),
                "export_node": int(float(toks[1])),
                "name": toks[-1] if not _is_number(toks[-1]) else "",
            })
        except ValueError:
            break
        if len(rows) == n_diversions:
            break

    data = pd.DataFrame(rows) if len(rows) == n_diversions else None

    # Delivery element groups: locate the "/ NGRP" keyed line, then read
    # NGRP groups (ID NELEM IELEM..., wrapping over continuation lines).
    n_groups = 0
    delivery_groups: list = []
    recharge_zones: list = []
    from iwfm.io._tokens import split_keyed_line
    from iwfm.io.readers._element_groups import parse_element_groups
    ngrp_idx = None
    for i, line in enumerate(raw_data):
        if is_comment(line):
            continue
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw == "NGRP":
            n_groups = int(value)
            ngrp_idx = i
            break
    if ngrp_idx is not None:
        rest = raw_data[ngrp_idx + 1:]
        used = 0
        if n_groups > 0:
            try:
                delivery_groups, used = parse_element_groups(rest, n_groups)
            except ValueError:
                delivery_groups, used = [], 0
        # Recharge zones follow, one per diversion, with an element
        # fraction after each element id.
        try:
            recharge_zones, _ = parse_element_groups(
                rest[used:], n_diversions, with_fractions=True)
        except ValueError:
            recharge_zones = []

    return DiverSpecsFile(
        header=header,
        n_diversions=n_diversions,
        raw_data=raw_data,
        data=data,
        n_groups=n_groups,
        delivery_groups=delivery_groups,
        recharge_zones=recharge_zones,
    )


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


# ------------------------------------------------------------------
# Bypass Specs
# ------------------------------------------------------------------

def read_bypass_specs(path: str | Path) -> BypassSpecsFile:
    """Read an IWFM bypass specification file (e.g. ``BypassSpecs.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    BypassSpecsFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    # ---- Global counts and conversion factors ----
    n_bypasses, _ = reader.read_keyed_int()

    factx, _ = reader.read_keyed_float()
    tunitx, _ = reader.read_keyed_value()
    facty, _ = reader.read_keyed_float()
    tunity, _ = reader.read_keyed_value()
    factors = {
        "factx": factx,
        "tunitx": tunitx,
        "facty": facty,
        "tunity": tunity,
    }

    # ---- Bypass spec lines ----
    # Each bypass occupies one spec line:
    #   ID  IA  TYPEDEST  DEST  IDIVC  DIVRL  DIVNL  NAME
    # When IDIVC < 0, abs(IDIVC) rating table rows follow immediately:
    #   DIVX  DIVY
    bypass_rows: list[dict] = []
    rating_tables: dict[int, pd.DataFrame] = {}

    for _ in range(n_bypasses):
        line = reader.next_data_line()
        tokens = tokenize_data_line(line)
        bypass_id = int(tokens[0])
        stream_node = int(tokens[1])
        dest_type = int(tokens[2])
        dest = int(tokens[3])
        idivc = int(tokens[4])
        divrl = float(tokens[5])
        divnl = float(tokens[6])
        name = tokens[7] if len(tokens) > 7 else ""

        bypass_rows.append({
            "bypass_id": bypass_id,
            "stream_node": stream_node,
            "dest_type": dest_type,
            "dest": dest,
            "idivc": idivc,
            "divrl": divrl,
            "divnl": divnl,
            "name": name,
        })

        # Inline rating table when idivc is negative
        if idivc < 0:
            n_rating_pts = abs(idivc)
            rt_rows: list[dict] = []
            for _ in range(n_rating_pts):
                rt_line = reader.next_data_line()
                rt_tokens = tokenize_data_line(rt_line)
                rt_rows.append({
                    "divx": float(rt_tokens[0]),
                    "divy": float(rt_tokens[1]),
                })
            rating_tables[bypass_id] = pd.DataFrame(rt_rows)

    bypass_data = pd.DataFrame(bypass_rows) if bypass_rows else None

    # ---- Seepage zone sections ----
    # One entry per bypass:
    #   ID  NERELS  IERELS  FERELS   (first element on same line)
    #              IERELS  FERELS   (continuation lines)
    seepage_zones: list[dict] = []
    for _ in range(n_bypasses):
        line = reader.next_data_line()
        tokens = tokenize_data_line(line)
        zone_id = int(tokens[0])
        n_elements = int(tokens[1])
        elements: list[dict] = []

        if n_elements > 0:
            # First element is on the same line
            elements.append({
                "element_id": int(tokens[2]),
                "fraction": float(tokens[3]),
            })
            # Remaining elements on continuation lines
            for _ in range(n_elements - 1):
                cont_line = reader.next_data_line()
                cont_tokens = tokenize_data_line(cont_line)
                elements.append({
                    "element_id": int(cont_tokens[0]),
                    "fraction": float(cont_tokens[1]),
                })

        seepage_zones.append({
            "bypass_id": zone_id,
            "n_elements": n_elements,
            "elements": elements,
        })

    return BypassSpecsFile(
        header=header,
        n_bypasses=n_bypasses,
        factors=factors,
        bypass_data=bypass_data,
        rating_tables=rating_tables,
        seepage_zones=seepage_zones,
    )


# ------------------------------------------------------------------
# Diversions (timeseries)
# ------------------------------------------------------------------

def read_diversions(path: str | Path) -> DiversionsFile:
    """Read an IWFM surface water diversion data file (e.g. ``Diversions.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    DiversionsFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    # 5-param time-series spec
    spec = reader.read_timeseries_spec()

    result = DiversionsFile(header=header, spec=spec)

    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        col_names = [f"col_{i + 1}" for i in range(spec.n_columns)]
        result.data = _read_ts_data_to_eof(reader, spec.n_columns, col_names)

    return result
