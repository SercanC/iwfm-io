"""
Readers for IWFM stream component input files.

All functions return dataclass containers with pandas DataFrames.
"""

from __future__ import annotations

import re

from pathlib import Path
from typing import Any

import pandas as pd

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import tokenize_data_line
from iwfm_io.models.base import TimeSeriesSpec
from iwfm_io.models.stream import (
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

    # ---- Hydrograph spec lines: IOUTR  NAME (may be multi-word;
    # internal spacing preserved) ----
    hydrograph_specs: list[dict] = []
    for _ in range(n_hydrographs):
        line = reader.next_data_line()
        body = re.split(r"\s+/", line, maxsplit=1)[0]
        parts = body.split(None, 1)
        node_id = int(parts[0])
        name = parts[1].rstrip() if len(parts) > 1 else ""
        hydrograph_specs.append({"node_id": node_id, "name": name})

    # ---- Node budget settings ----
    n_node_budgets, _ = reader.read_keyed_int()
    config["n_node_budgets"] = n_node_budgets

    node_bud_file, _ = reader.read_keyed_path(base_dir)
    config["node_bud_file"] = node_bud_file

    node_budget_nodes: list[int] = []
    for _ in range(n_node_budgets):
        line = reader.next_data_line()
        node_budget_nodes.append(int(tokenize_data_line(line)[0]))

    # ---- Stream bed parameters ----
    factk, _ = reader.read_keyed_float()
    config["factk"] = factk

    tunitk, _ = reader.read_keyed_value()
    config["tunitk"] = tunitk

    factl, _ = reader.read_keyed_float()
    config["factl"] = factl

    # Stream-node bed parameter rows — one row per stream NODE (plus,
    # in v4.2+, optional 4-token continuation rows for additional GW
    # nodes of wide stream nodes).  The column ORDER changed across
    # stream-package versions (confirmed against the IWFM source,
    # Class_StrmGWConnector_v4*.f90):
    #   v4.0/4.1:  IR  CSTRM  DSTRM  WETPR
    #   v4.2+:     IR  WETPR  IGW  CSTRM  DSTRM
    # Rows may carry a trailing "/ annotation" (kept in "notes").
    try:
        _stream_ver = float(header.version) if header.version else 4.0
    except (TypeError, ValueError):
        _stream_ver = 4.0
    reach_rows: list[dict] = []
    _cur_node = None
    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        m = re.search(r"\s/(.+)$", line)
        note = m.group(1).strip().lstrip("/").strip() if m else ""
        if _stream_ver >= 4.2:
            if len(tokens) >= 5:
                _cur_node = int(tokens[0])
                row = {
                    "stream_node_id": _cur_node,
                    "wetted_perimeter": float(tokens[1]),
                    "gw_node_id": int(float(tokens[2])),
                    "conductance": float(tokens[3]),
                    "bed_thickness": float(tokens[4]),
                }
                extra_start = 5
            elif len(tokens) == 4 and _cur_node is not None:
                # continuation row: extra GW node of a wide stream node
                row = {
                    "stream_node_id": _cur_node,
                    "wetted_perimeter": float(tokens[0]),
                    "gw_node_id": int(float(tokens[1])),
                    "conductance": float(tokens[2]),
                    "bed_thickness": float(tokens[3]),
                }
                extra_start = 4
            else:
                break
        else:
            if len(tokens) < 4:
                break
            row = {
                "stream_node_id": int(tokens[0]),
                "conductance": float(tokens[1]),
                "bed_thickness": float(tokens[2]),
                "wetted_perimeter": float(tokens[3]),
            }
            extra_start = 4
        reader.next_data_line()
        for i, extra in enumerate(tokens[extra_start:],
                                  start=len(row) + 1):
            row[f"col_{i}"] = float(extra)
        row["notes"] = note
        reach_rows.append(row)

    reach_params = pd.DataFrame(reach_rows)

    # ---- Hydraulic disconnection type (optional: some v4.x files,
    # e.g. C2VSimCG, end right after the stream-bed table; IWFM then
    # uses its default. Recorded as None so the writer omits it too.) ----
    if reader.peek_data_line() is None:
        config["intrctype"] = None
        config["starfl"] = None
        return StreamMain(
            header=header,
            file_paths=file_paths,
            config=config,
            hydrograph_specs=hydrograph_specs,
            node_budget_nodes=node_budget_nodes,
            reach_params=reach_params if reach_rows else None,
            evaporation=None,
        )
    intrctype, _ = reader.read_keyed_int()
    config["intrctype"] = intrctype

    # ---- Stream evaporation STARFL (optional; older layouts end at
    # INTRCTYPE with no evaporation section at all) ----
    if reader.eof:
        config["starfl"] = None
    else:
        starfl, _ = reader.read_keyed_path(base_dir)
        config["starfl"] = starfl

    # ---- Stream evaporation node table (blank when not simulated) ----
    # IR (stream node), ICETST (column in the ET file; 0 = no
    # evaporation), ICARST (column in STARFL; 0 = computed from wetted
    # perimeter x stream length).
    evap_rows: list[dict] = []
    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if len(tokens) < 3:
            break
        try:
            row = {
                "stream_node": int(float(tokens[0])),
                "icetst": int(float(tokens[1])),
                "icarst": int(float(tokens[2])),
            }
        except ValueError:
            break
        reader.next_data_line()
        evap_rows.append(row)
    evaporation = pd.DataFrame(evap_rows) if evap_rows else None

    return StreamMain(
        header=header,
        file_paths=file_paths,
        config=config,
        hydrograph_specs=hydrograph_specs,
        node_budget_nodes=node_budget_nodes,
        reach_params=reach_params if reach_rows else None,
        evaporation=evaporation,
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

    Parses the per-diversion table, the delivery element groups, and
    the per-diversion recharge zones.

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

    # Parse the per-diversion table from the first NRDV data rows.
    # Row layout: ID IRDV ICDVMAX FDVMAX ICOLRL FRACRL ICOLNL FRACNL
    # [ICOLSL FRACSL] TYPDSTDL DSTDL ICOLDL FRACDL ICFSIRIG ICADJ [NAME]
    # — the ICOLSL/FRACSL diversion-spills pair exists only in older
    # stream-package formats (16 numeric columns vs 14). All numeric
    # fields precede NAME, so rows are parsed positionally from the
    # left; everything after the last numeric slot is the name (real
    # decks carry free text after the 20-char NAME field, e.g.
    # C2VSimFG v2.0). The layout is disambiguated by the count of
    # leading numeric tokens plus which candidate slot holds a valid
    # TYPDSTDL (0=outside, 2=element, 4=subregion, 6=element group).
    import re
    import warnings
    from iwfm_io._tokens import is_comment
    rows = []
    for line in raw_data:
        if is_comment(line):
            continue
        toks = tokenize_data_line(line)
        if len(toks) < 3:
            continue
        # A name may also ride in a trailing "/ name" comment (already
        # stripped from toks by tokenize_data_line).
        m = re.search(r"\s/(.+)$", line)
        comment_name = m.group(1).strip().lstrip("/").strip() if m else ""

        n_numeric = 0
        for t in toks:
            if not _is_number(t):
                break
            n_numeric += 1
        if n_numeric >= 16 and _is_dest_type(toks[10]):
            n_slots = 16  # spill layout
        elif n_numeric >= 14 and _is_dest_type(toks[8]):
            n_slots = 14  # no-spill layout
        elif n_numeric >= 16:
            n_slots = 16
        else:
            break  # not a spec row — end of the table
        nums = toks[:n_slots]
        # NAME is a real positional field (IWFM reads it); a trailing
        # "/" annotation is kept separately as "notes"
        name = " ".join(toks[n_slots:])
        tail = nums[n_slots - 6:]
        try:
            row = {
                "diversion_id": int(float(nums[0])),
                "export_node": int(float(nums[1])),
                "max_col": int(float(nums[2])),
                "max_frac": float(nums[3]),
                "recov_loss_col": int(float(nums[4])),
                "recov_loss_frac": float(nums[5]),
                "nonrecov_loss_col": int(float(nums[6])),
                "nonrecov_loss_frac": float(nums[7]),
                "spill_col": None,
                "spill_frac": None,
                "dest_type": int(float(tail[0])),
                "dest_id": int(float(tail[1])),
                "delivery_col": int(float(tail[2])),
                "delivery_frac": float(tail[3]),
                "irig_frac_col": int(float(tail[4])),
                "adjust_col": int(float(tail[5])),
                "name": name,
                "notes": comment_name,
            }
            if n_slots == 16:  # older format with the spills pair
                row["spill_col"] = int(float(nums[8]))
                row["spill_frac"] = float(nums[9])
            rows.append(row)
        except (ValueError, IndexError):
            break
        if len(rows) == n_diversions:
            break

    if len(rows) == n_diversions:
        data = pd.DataFrame(rows)
    else:
        data = None
        if n_diversions > 0:
            warnings.warn(
                f"read_diver_specs: parsed {len(rows)} of {n_diversions} "
                f"diversion spec rows; spec table set to None",
                stacklevel=2)

    # Delivery element groups: locate the "/ NGRP" keyed line, then read
    # NGRP groups (ID NELEM IELEM..., wrapping over continuation lines).
    n_groups = 0
    delivery_groups: list = []
    recharge_zones: list = []
    from iwfm_io._tokens import split_keyed_line
    from iwfm_io.readers._element_groups import parse_element_groups
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
    spill_locations: list = []
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
        rz_used = 0
        try:
            recharge_zones, rz_used = parse_element_groups(
                rest[used:], n_diversions, with_fractions=True)
        except ValueError:
            recharge_zones = []
        # Older stream-package formats (the ones whose diversion rows
        # carry the ICOLSL/FRACSL spill pair) end with a spill-location
        # section: ID NSPILL ISPILL FSPILL per diversion.
        try:
            spill_locations, _ = parse_element_groups(
                rest[used + rz_used:], n_diversions, with_fractions=True)
        except ValueError:
            spill_locations = []

    return DiverSpecsFile(
        header=header,
        n_diversions=n_diversions,
        data=data,
        n_groups=n_groups,
        delivery_groups=delivery_groups,
        recharge_zones=recharge_zones,
        spill_locations=spill_locations,
    )


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _is_dest_type(token: str) -> bool:
    """True if *token* is a valid TYPDSTDL value (0, 2, 4, or 6)."""
    try:
        v = float(token)
    except ValueError:
        return False
    return v == int(v) and int(v) in (0, 2, 4, 6)


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
        body = re.split(r"\s+/", line, maxsplit=1)[0]
        parts = body.split(None, 7)
        name = parts[7].rstrip() if len(parts) > 7 else ""
        m = re.search(r"\s/(.+)$", line)
        note = m.group(1).strip().lstrip("/").strip() if m else ""

        bypass_rows.append({
            "bypass_id": bypass_id,
            "stream_node": stream_node,
            "dest_type": dest_type,
            "dest": dest,
            "idivc": idivc,
            "divrl": divrl,
            "divnl": divnl,
            "name": name,
            "notes": note,
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
    # One group per bypass: ID NERELS IERELS FERELS ... — parsed with
    # the shared element-group parser (tolerates elements starting on
    # the next line, packed continuation lines, and header annotations).
    from iwfm_io.readers._element_groups import parse_element_groups
    seepage_zones: list[dict] = []
    rest = reader.skip_to_end()
    try:
        groups, _ = parse_element_groups(rest, n_bypasses,
                                         with_fractions=True)
    except ValueError:
        import warnings
        warnings.warn(
            "Bypass seepage-zone table only partially parsed; the "
            "section will be missing from written output")
        groups = []
    for g in groups:
        seepage_zones.append({
            "bypass_id": g["group_id"],
            "n_elements": len(g["elements"]),
            "elements": [
                {"element_id": e, "fraction": f}
                for e, f in zip(g["elements"], g.get("fractions") or [])
            ],
            "name": g.get("name", ""),
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
