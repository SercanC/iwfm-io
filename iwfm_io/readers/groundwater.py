"""
Readers for IWFM groundwater component input files.

All functions return dataclass containers with pandas DataFrames.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from iwfm_io._parser import IWFMFileReader, IWFMParseError
from iwfm_io._tokens import _KEYED_SEP_RE, split_keyed_line, tokenize_data_line
from iwfm_io.models.base import TimeSeriesSpec
from iwfm_io.readers._param_blocks import parse_param_block
from iwfm_io.models.groundwater import (
    BCMain,
    BoundaryTSFile,
    ConstrainedHeadBCFile,
    ElemPumpFile,
    GeneralHeadBCFile,
    GWMain,
    PumpMain,
    SpecifiedFlowBCFile,
    SpecifiedHeadFile,
    SubsidenceFile,
    TileDrainFile,
    TSPumpingFile,
    WellSpecFile,
)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _split_note(line: str) -> tuple[str, str]:
    """Split a data line into its list-directed body and a trailing
    ``/ note`` annotation (``""`` when absent)."""
    m = _KEYED_SEP_RE.search(line)
    if m is None:
        return line, ""
    return line[:m.start()], line[m.end():].strip().lstrip("/").strip()


def _read_hydrograph_table(
    reader: IWFMFileReader,
    n_rows: int,
    col_names: list[str],
) -> pd.DataFrame:
    """Read *n_rows* of IWFM hydrograph location rows into a DataFrame.

    IWFM hydrograph rows have the format::

        ID  TYPE  LAYER  [X  Y | NODE]  NAME

    where TYPE (column index 1) controls whether the location is given
    as x-y coordinates (TYPE=0: x and y are present, node is blank) or
    as a node number (TYPE=1: x and y are blank, node is present).

    Because the raw tokens differ in count between the two formats, this
    function parses each row based on the type flag rather than purely
    by position.  The expected *col_names* must be exactly
    ``[id_col, type_col, layer_col, x_col, y_col, node_col, name_col]``
    (7 columns) for GW/subsidence hydrographs, or
    ``[id_col, layer_col, node_col, name_col]`` (4 columns) for the
    simpler BC-hydrograph format.

    Parameters
    ----------
    reader : IWFMFileReader
    n_rows : int
    col_names : list[str]
        Column names for the resulting DataFrame.

    Returns
    -------
    pd.DataFrame
    """
    rows: list[dict] = []
    n_cols = len(col_names)

    for i in range(n_rows):
        try:
            line = reader.next_data_line()
        except IWFMParseError:
            raise reader.error(
                f"hydrograph table has only {i} of {n_rows} declared "
                "rows") from None
        # a trailing "/ note" (e.g. C2VSimFG InSAR station details) is
        # transparent to IWFM's list-directed read; keep it separately
        body, note = _split_note(line)
        row: dict = {col: None for col in col_names}
        row["notes"] = note
        # IWFM (Class_BaseHydrograph.f90) consumes the leading numeric
        # fields positionally and takes the REST OF THE LINE as the
        # name -- names may contain blanks
        if n_cols == 7:
            id_col, type_col, layer_col, x_col, y_col, node_col, name_col = col_names
            parts = body.split(None, 3)
            if len(parts) < 3:
                raise reader.error(
                    f"hydrograph row {i + 1}: expected ID TYPE LAYER ..., "
                    f"got {body.strip()!r}")
            row[id_col], row[type_col], row[layer_col] = parts[:3]
            rest = parts[3] if len(parts) > 3 else ""
            if parts[1].strip() == "0":
                xy = rest.split(None, 2)
                if len(xy) < 2:
                    raise reader.error(
                        f"hydrograph row {i + 1}: type 0 needs X Y, got "
                        f"{body.strip()!r}")
                row[x_col], row[y_col] = xy[0], xy[1]
                rest = xy[2] if len(xy) > 2 else ""
                # some decks (C2VSimFG subsidence) write a placeholder
                # node before the name regardless of the type flag:
                # X Y 0 NAME -- an integer token followed by text
                m = re.match(r"\s*(-?\d+)\s+(\S.*)$", rest)
                if m:
                    row[node_col], rest = m.group(1), m.group(2)
            else:
                nd = rest.split(None, 1)
                if not nd:
                    raise reader.error(
                        f"hydrograph row {i + 1}: type {parts[1]} needs a "
                        f"node, got {body.strip()!r}")
                row[node_col] = nd[0]
                rest = nd[1] if len(nd) > 1 else ""
            row[name_col] = rest.strip() or None
        else:
            # positional: the last column is the name (rest of line)
            parts = body.split(None, n_cols - 1)
            for k, col in enumerate(col_names[:-1]):
                row[col] = parts[k] if k < len(parts) else None
            row[col_names[-1]] = (parts[n_cols - 1].strip()
                                  if len(parts) >= n_cols else None)

        rows.append(row)

    df = pd.DataFrame(rows, columns=col_names + ["notes"])
    # Type the columns: ids/layers/nodes as nullable ints, coordinates as
    # floats; the name column stays as strings (None where absent) and
    # notes as plain strings ("" where absent).
    name_col = col_names[-1]
    for col in col_names[:-1]:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if col in ("x", "y"):
            df[col] = numeric
        else:
            df[col] = numeric.astype("Int64")
    df[name_col] = df[name_col].where(df[name_col].notna(), None)
    return df


# ------------------------------------------------------------------
# GW Main
# ------------------------------------------------------------------

def read_gw_main(
    path: str | Path,
    follow_references: bool = False,
) -> GWMain:
    """Read the groundwater component main input file (e.g. ``GW_MAIN.dat``).

    Parses file paths, unit-conversion factors, output flags, hydrograph
    specs, face flow specs, and stores the raw aquifer parameter block for
    round-trip writing.

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        Reserved for future use.

    Returns
    -------
    GWMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    def _resolve(value: str) -> str | None:
        if not value or value == "*":
            return None
        from iwfm_io._parser import resolve_child_path
        return resolve_child_path(value, base_dir)

    # Keyed header block, identified by keyword rather than position:
    # real-world files comment out optional entries (e.g. C2VSimFG has no
    # HTPOUTFL/VTPOUTFL/IHTPFLAG lines at all), so a fixed read order breaks.
    path_keywords = {
        "BCFL": "bc_main",
        "TDFL": "tile_drain",
        "PUMPFL": "pump_main",
        "SUBSFL": "subsidence",
        "OVRWRTFL": "overwrite",
        "VELOUTFL": "vel_out",
        "VFLOWOUTFL": "vflow_out",
        "GWALLOUTFL": "gwhead_all",
        "HTPOUTFL": "htp_out",
        "VTPOUTFL": "vtp_out",
        "GWBUDFL": "gw_budget",
        "ZBUDFL": "zbudget",
        "FNGWFL": "final_heads",
    }
    scalar_keywords = {
        "FACTLTOU", "UNITLTOU", "FACTVLOU", "UNITVLOU", "FACTVROU",
        "UNITVROU", "IHTPFLAG", "KDEB", "NOUTH", "FACTXY",
    }

    file_paths: dict[str, str | None] = {k: None for k in path_keywords.values()}
    scalars: dict[str, str] = {}
    hydrograph_out_file = None
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw == "GWHYDOUTFL":
            reader.next_data_line()
            hydrograph_out_file = _resolve(value)
            break
        if kw in path_keywords:
            reader.next_data_line()
            file_paths[path_keywords[kw]] = _resolve(value)
        elif kw in scalar_keywords:
            reader.next_data_line()
            scalars[kw] = value
        else:
            # Unknown or keyword-less line: table data / aquifer params
            break

    config = {
        "factltou": float(scalars.get("FACTLTOU") or 1.0),
        "unitltou": scalars.get("UNITLTOU", ""),
        "factvlou": float(scalars.get("FACTVLOU") or 1.0),
        "unitvlou": scalars.get("UNITVLOU", ""),
        "factvrou": float(scalars.get("FACTVROU") or 1.0),
        "unitvrou": scalars.get("UNITVROU", ""),
        "ihtpflag": int(scalars["IHTPFLAG"]) if scalars.get("IHTPFLAG") else None,
        "kdeb": int(scalars.get("KDEB") or 0),
    }

    # Hydrograph output block
    n_hydrographs = int(scalars.get("NOUTH") or 0)
    hydrograph_factxy = float(scalars.get("FACTXY") or 1.0)

    hydrograph_cols = ["id", "hydtyp", "layer", "x", "y", "node", "name"]
    with reader.section("hydrograph table"):
        hydrographs = _read_hydrograph_table(reader, n_hydrographs,
                                             hydrograph_cols)

    # Face flow output block. FCHYDOUTFL is omitted entirely when NOUTF=0,
    # so only consume lines whose keyword belongs to this block.
    n_face_flows = 0
    face_flow_out_file = None
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw == "NOUTF":
            reader.next_data_line()
            n_face_flows = int(value)
        elif kw == "FCHYDOUTFL":
            reader.next_data_line()
            face_flow_out_file = _resolve(value)
            break
        else:
            break

    face_flow_cols = ["id", "layer", "node_a", "node_b", "name"]
    with reader.section("face flow table"):
        face_flows = _read_hydrograph_table(reader, n_face_flows,
                                            face_flow_cols)

    # Aquifer parameter section: fully parsed into DataFrames
    tail = _parse_gw_param_tail(reader.tail_cursor())

    return GWMain(
        header=header,
        file_paths=file_paths,
        config=config,
        n_hydrographs=n_hydrographs,
        hydrograph_factxy=hydrograph_factxy,
        hydrograph_out_file=hydrograph_out_file,
        hydrographs=hydrographs,
        n_face_flows=n_face_flows,
        face_flow_out_file=face_flow_out_file,
        face_flows=face_flows,
        **tail,
    )


def _parse_gw_param_tail(cursor) -> dict:
    """Parse the GW main tail: aquifer parameters, Kh anomalies, the
    optional groundwater return-flow section, and initial heads.

    Sections are recognized by their keyed lines (NEBK, IFLAGRF, FACTHP)
    because the return-flow block exists only in some format variants
    (the sample model has it, C2VSimFG does not).  A parse failure is
    an ``IWFMParseError`` in strict mode; in lenient mode what was read
    so far is kept and an ``IWFMReadWarning`` is emitted — the unparsed
    remainder is not retained, so a written file would lack it.

    *cursor* is a :class:`~iwfm_io.readers._param_blocks.LineCursor`
    (see :meth:`IWFMFileReader.tail_cursor`) positioned at NGROUP.
    """
    out: dict = {
        "ngroup": None,
        "param_factors": {},
        "param_time_units": {},
        "aquifer_params": None,
        "parametric_grids": [],
        "anomaly_nebk": 0,
        "anomaly_factor": 1.0,
        "anomaly_time_unit": "",
        "kh_anomalies": None,
        "iflagrf": None,
        "return_flow": None,
        "facthp": None,
        "initial_heads": None,
    }
    section = "aquifer parameters"
    try:
        with cursor.section(section):
            block = parse_param_block(
                cursor,
                param_names=["kh", "ss", "sy", "aquitard_kv", "kv"],
                factor_names=["fx", "fkh", "fs", "fn", "fv", "fl"],
            )
        out["ngroup"] = block["ngroup"]
        out["param_factors"] = block["factors"]
        out["param_time_units"] = block["time_units"]
        out["aquifer_params"] = block["node_params"]
        out["parametric_grids"] = block["parametric_grids"]

        # ---- Anomaly in hydraulic conductivity ----
        if cursor.peek_keyword() == "NEBK":
            section = "Kh anomalies"
            nebk = int(cursor.read_keyed_value()[0])
            out["anomaly_nebk"] = nebk
            if cursor.peek_keyword() == "FACT":
                out["anomaly_factor"] = float(cursor.read_keyed_value()[0])
            if cursor.peek_keyword() == "TUNITH":
                out["anomaly_time_unit"] = cursor.read_keyed_value()[0]
            rows = []
            for _ in range(nebk):
                toks = tokenize_data_line(cursor.next())
                row = {"ic": int(float(toks[0])),
                       "element_id": int(float(toks[1]))}
                for i, v in enumerate(toks[2:], start=1):
                    row[f"kh_layer_{i}"] = float(v)
                rows.append(row)
            if rows:
                out["kh_anomalies"] = pd.DataFrame(rows)

        # ---- Groundwater return flow (only in newer format variants) ----
        if cursor.peek_keyword() == "IFLAGRF":
            section = "groundwater return flow"
            out["iflagrf"] = int(cursor.read_keyed_value()[0])
            rows = []
            while not cursor.eof and cursor.peek_keyword() != "FACTHP":
                toks = tokenize_data_line(cursor.peek())
                if len(toks) != 3:
                    break
                try:
                    rows.append({
                        "node_id": int(float(toks[0])),
                        "dest_type": int(float(toks[1])),
                        "dest": int(float(toks[2])),
                    })
                except ValueError:
                    break
                cursor.next()
            if rows:
                out["return_flow"] = pd.DataFrame(rows)

        # ---- Initial groundwater heads ----
        if cursor.peek_keyword() == "FACTHP":
            section = "initial heads"
            out["facthp"] = float(cursor.read_keyed_value()[0])
            rows = []
            while not cursor.eof:
                if cursor.peek_keyword():
                    # a keyed line after the heads table starts an
                    # unrecognized section — do not absorb it
                    break
                toks = tokenize_data_line(cursor.peek())
                try:
                    node_id = int(float(toks[0]))
                    heads = [float(t) for t in toks[1:]]
                except (ValueError, IndexError):
                    break
                cursor.next()
                row = {"node_id": node_id}
                for i, h in enumerate(heads, start=1):
                    row[f"head_layer_{i}"] = h
                rows.append(row)
            if rows:
                out["initial_heads"] = pd.DataFrame(rows)
        if not cursor.eof:
            cursor.next()
            cursor.degrade(
                "GW main: unrecognized content after the parsed sections "
                "was not understood and will be missing from written "
                "output")
    except (ValueError, IndexError) as exc:
        if isinstance(exc, IWFMParseError) and cursor.strict:
            raise
        with cursor.section(section):
            cursor.degrade(
                f"GW main tail only partially parsed ({exc}); unparsed "
                "sections will be missing from written output")
    return out


# ------------------------------------------------------------------
# BC Main
# ------------------------------------------------------------------

def read_bc_main(
    path: str | Path,
    follow_references: bool = False,
) -> BCMain:
    """Read the boundary conditions main file (e.g. ``BC_MAIN.dat``).

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        Reserved for future use.

    Returns
    -------
    BCMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    sp_flow, _ = reader.read_keyed_path(base_dir)
    sp_head, _ = reader.read_keyed_path(base_dir)
    ghbc, _ = reader.read_keyed_path(base_dir)
    con_ghbc, _ = reader.read_keyed_path(base_dir)
    ts_bc, _ = reader.read_keyed_path(base_dir)

    file_paths = {
        "sp_flow": sp_flow,
        "sp_head": sp_head,
        "ghbc": ghbc,
        "con_ghbc": con_ghbc,
        "ts_bc": ts_bc,
    }

    n_bc_hydrographs, _ = reader.read_keyed_int()
    bc_hyd_out_file, _ = reader.read_keyed_path(base_dir)

    bc_hyd_cols = ["id", "layer", "node", "name"]
    with reader.section("BC hydrograph table"):
        bc_hydrographs = _read_hydrograph_table(reader, n_bc_hydrographs,
                                                bc_hyd_cols)

    return BCMain(
        header=header,
        file_paths=file_paths,
        n_bc_hydrographs=n_bc_hydrographs,
        bc_hyd_out_file=bc_hyd_out_file,
        bc_hydrographs=bc_hydrographs,
    )


def _read_bc_rows(reader: IWFMFileReader, n_rows: int, n_int: int,
                  n_float: int, what: str) -> list[list]:
    """Read *n_rows* boundary-condition rows of ``n_int`` integers
    followed by ``n_float`` numbers, with per-token error context."""
    rows: list[list] = []
    n_cols = n_int + n_float
    with reader.section(what.replace(" row", " table")):
        for i in range(n_rows):
            try:
                toks = reader.read_row(n_cols, what)
            except IWFMParseError as exc:
                if reader.eof and "end of file" in exc.msg:
                    raise reader.error(
                        f"{what}s: only {i} of {n_rows} declared rows "
                        "present") from None
                raise
            ints = reader.to_ints(toks[:n_int], what)
            floats = reader.to_floats(toks[n_int:n_cols], what)
            rows.append(ints + floats)
    return rows


# ------------------------------------------------------------------
# Specified Head BC
# ------------------------------------------------------------------

def read_spec_head_bc(path: str | Path) -> SpecifiedHeadFile:
    """Read a specified head boundary conditions file (e.g. ``SpecHeadBC.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SpecifiedHeadFile
        DataFrame columns: node_id (int), layer (int), itscol (int —
        column number in the time-series BC file, 0 = constant head),
        head (float).
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    factor, _ = reader.read_keyed_float()

    rows = _read_bc_rows(reader, n_nodes, n_int=3, n_float=1,
                         what="specified-head row")
    df = pd.DataFrame(rows, columns=["node_id", "layer", "itscol", "head"])

    return SpecifiedHeadFile(
        header=header,
        n_nodes=n_nodes,
        factor=factor,
        data=df,
    )


# ------------------------------------------------------------------
# Specified Flow BC
# ------------------------------------------------------------------

def read_spec_flow_bc(path: str | Path) -> SpecifiedFlowBCFile:
    """Read a specified flow boundary conditions file.

    Follows the standard IWFM template layout: NQB, FACT, TUNIT, then
    one row per node: NODE LAYER ITSCOL FLOW.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SpecifiedFlowBCFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    factor, _ = reader.read_keyed_float()
    time_unit, _ = reader.read_keyed_value()

    rows = _read_bc_rows(reader, n_nodes, n_int=3, n_float=1,
                         what="specified-flow row")
    df = pd.DataFrame(rows, columns=["node_id", "layer", "itscol", "flow"])

    return SpecifiedFlowBCFile(
        header=header,
        n_nodes=n_nodes,
        factor=factor,
        time_unit=time_unit,
        data=df,
    )


# ------------------------------------------------------------------
# General Head BC
# ------------------------------------------------------------------

def read_general_head_bc(path: str | Path) -> GeneralHeadBCFile:
    """Read a general head boundary conditions file.

    Follows the standard IWFM template layout: NGB, FACTH, FACTC,
    TUNITC, then one row per node: NODE LAYER ITSCOL BH BC.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    GeneralHeadBCFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    facth, _ = reader.read_keyed_float()
    factc, _ = reader.read_keyed_float()
    time_unit, _ = reader.read_keyed_value()

    rows = _read_bc_rows(reader, n_nodes, n_int=3, n_float=2,
                         what="general-head row")
    df = pd.DataFrame(rows, columns=["node_id", "layer", "itscol", "head",
                                     "conductance"])

    return GeneralHeadBCFile(
        header=header,
        n_nodes=n_nodes,
        facth=facth,
        factc=factc,
        time_unit=time_unit,
        data=df,
    )


# ------------------------------------------------------------------
# Constrained General Head BC
# ------------------------------------------------------------------

def read_constrained_head_bc(path: str | Path) -> ConstrainedHeadBCFile:
    """Read a constrained general head boundary conditions file.

    Row layout: NODE LAYER ITSCOL BH BC LBH ITSCOLF CFLOW [/ name].
    ITSCOL/ITSCOLF reference data columns in the time-series boundary
    conditions file.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    ConstrainedHeadBCFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    facth, _ = reader.read_keyed_float()
    factvl, _ = reader.read_keyed_float()
    tunitvl, _ = reader.read_keyed_value()
    factc, _ = reader.read_keyed_float()
    tunitc, _ = reader.read_keyed_value()

    rows = []
    what = "constrained-head row"
    with reader.section("constrained-head table"):
        for _ in range(n_nodes):
            line = reader.next_data_line()
            toks = tokenize_data_line(line)
            if len(toks) < 8:
                raise reader.error(
                    f"{what}: expected 8 values but found {len(toks)}: "
                    f"{line.strip()!r}")
            name = ""
            m = re.search(r"\s/(.+)$", line)
            if m:
                name = m.group(1).strip().lstrip("/").strip()
            ids = reader.to_ints(toks[:3], what)
            vals = reader.to_floats(toks[3:6], what)
            itscolf = reader.to_ints(toks[6:7], what)[0]
            max_flow = reader.to_floats(toks[7:8], what)[0]
            rows.append({
                "node_id": ids[0],
                "layer": ids[1],
                "itscol": ids[2],
                "head": vals[0],
                "conductance": vals[1],
                "limiting_head": vals[2],
                "itscolf": itscolf,
                "max_flow": max_flow,
                "name": name,
            })

    return ConstrainedHeadBCFile(
        header=header,
        n_nodes=n_nodes,
        facth=facth,
        factvl=factvl,
        tunitvl=tunitvl,
        factc=factc,
        tunitc=tunitc,
        data=pd.DataFrame(rows),
    )


# ------------------------------------------------------------------
# Boundary Time Series
# ------------------------------------------------------------------

def read_boundary_ts(path: str | Path) -> BoundaryTSFile:
    """Read a time-series boundary conditions file (e.g. ``BoundTSD.dat``).

    The boundary TS file uses a 6-parameter spec: NBTSD, FACTHTS,
    FACTQTS, NSPHTS, NFQHTS, DSSFL.  Both FACTHTS and FACTQTS are
    read; FACTHTS is stored in ``spec.factor`` while FACTQTS goes
    into ``config['factqts']``.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    BoundaryTSFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    with reader.section("time-series spec"):
        n_columns, _ = reader.read_keyed_int()
        facthts, _ = reader.read_keyed_float()
        factqts, _ = reader.read_keyed_float()
        n_steps_update, _ = reader.read_keyed_int()
        repeat_freq, _ = reader.read_keyed_int()
        dss_file, _ = reader.read_keyed_value()

    spec = TimeSeriesSpec(
        n_columns=n_columns,
        factor=facthts,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
    )
    config = {"factqts": factqts}

    result = BoundaryTSFile(header=header, spec=spec, config=config)

    if dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = reader.read_ts_rows(n_columns)

    return result


# ------------------------------------------------------------------
# Pump Main
# ------------------------------------------------------------------

def read_pump_main(
    path: str | Path,
    follow_references: bool = False,
) -> PumpMain:
    """Read the pumping component main file (e.g. ``Pump_MAIN.dat``).

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        Reserved for future use.

    Returns
    -------
    PumpMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    well, _ = reader.read_keyed_path(base_dir)
    elem_pump, _ = reader.read_keyed_path(base_dir)
    ts_pump, _ = reader.read_keyed_path(base_dir)
    pump_out, _ = reader.read_keyed_path(base_dir)

    file_paths = {
        "well": well,
        "elem_pump": elem_pump,
        "ts_pump": ts_pump,
        "pump_out": pump_out,
    }

    return PumpMain(header=header, file_paths=file_paths)


# ------------------------------------------------------------------
# Well Specifications
# ------------------------------------------------------------------

def read_well_spec(path: str | Path) -> WellSpecFile:
    """Read a well specification file (e.g. ``WellSpec.dat``).

    Parses NWELL, the conversion factors, the well location table
    (ID, XWELL, YWELL, RWELL, PERFT, PERFB, optional ``/name`` comment),
    the per-well pumping-configuration table, and the delivery element
    groups.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    WellSpecFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_wells, _ = reader.read_keyed_int()
    factxy, _ = reader.read_keyed_float()
    factrw, _ = reader.read_keyed_float()
    factlt, _ = reader.read_keyed_float()

    rows = []
    with reader.section("well table"):
        for _ in range(n_wells):
            line = reader.next_data_line()
            toks = tokenize_data_line(line)
            if len(toks) < 6:
                raise reader.error(
                    f"well row: expected 6 values but found {len(toks)}: "
                    f"{line.strip()!r}")
            # Well name rides in the trailing "/..." comment
            name = ""
            m = re.search(r"\s/(.+)$", line)
            if m:
                name = m.group(1).strip().lstrip("/").strip()
            well_id = reader.to_ints(toks[:1], "well row")[0]
            vals = reader.to_floats(toks[1:6], "well row")
            rows.append({
                "well_id": well_id,
                "x": vals[0],
                "y": vals[1],
                "radius": vals[2],
                "perf_top": vals[3],
                "perf_bot": vals[4],
                "name": name,
            })

    # Well pumping-configuration table: one row per well.
    # ID ICOLWL FRACWL IOPTWL TYPDSTWL DSTWL ICFIRIGWL ICADJWL ICWLMAX FWLMAX
    pump_cols = [
        "id", "icolwl", "fracwl", "ioptwl", "typdstwl", "dstwl",
        "icfirigwl", "icadjwl", "icwlmax", "fwlmax",
    ]
    pump_rows: list[dict] = []
    for _ in range(n_wells):
        with reader.section("well pumping configuration"):
            line = reader.next_data_line()
        toks = tokenize_data_line(line)
        row = {col: (toks[i] if i < len(toks) else None)
               for i, col in enumerate(pump_cols)}
        m = re.search(r"\s/(.+)$", line)
        row["notes"] = m.group(1).strip().lstrip("/").strip() if m else ""
        pump_rows.append(row)
    pump_config = pd.DataFrame(pump_rows, columns=pump_cols + ["notes"])
    for col in ["id", "icolwl", "ioptwl", "typdstwl", "dstwl",
                "icfirigwl", "icadjwl", "icwlmax"]:
        pump_config[col] = pd.to_numeric(pump_config[col], errors="coerce")
    for col in ["fracwl", "fwlmax"]:
        pump_config[col] = pd.to_numeric(pump_config[col], errors="coerce")

    # Delivery element groups (NGRP keyed line, then group definitions)
    n_groups = 0
    element_groups: list = []
    while not reader.eof:
        try:
            line = reader.next_data_line()
        except IWFMParseError:
            break
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw == "NGRP":
            try:
                n_groups = int(value)
            except ValueError:
                raise reader.error(
                    f"expected an integer for NGRP but found {value!r}"
                ) from None
            break
    if n_groups > 0:
        from iwfm_io.readers._element_groups import parse_element_groups
        element_groups, _ = parse_element_groups(reader.skip_to_end(), n_groups)

    return WellSpecFile(
        header=header,
        n_wells=n_wells,
        factors={"factxy": factxy, "factrw": factrw, "factlt": factlt},
        data=pd.DataFrame(rows),
        pump_config=pump_config,
        n_groups=n_groups,
        element_groups=element_groups,
    )


# ------------------------------------------------------------------
# Element Pumping
# ------------------------------------------------------------------

def read_elem_pump(path: str | Path,
                   n_layers: int | None = None) -> ElemPumpFile:
    """Read an element pumping specification file (e.g. ``ElemPump.dat``).

    Each data row has: ID ICOLSK FRACSK IOPTSK FRACSKL(1..NL) TYPDSTSK
    DSTSK ICFIRIGSK ICADJSK ICSKMAX FSKMAX [/NAME] — that is ``10 + NL``
    numeric tokens, where NL is the model's aquifer layer count (from
    the stratigraphy file, not declared here).  Pass *n_layers* to size
    the per-layer fraction columns the way the model does; without it
    NL is inferred from the widest data row (individual rows may
    legally omit trailing tokens, which are stored as None).

    Parameters
    ----------
    path : str or Path
    n_layers : int, optional
        The model's aquifer layer count (NL from the stratigraphy
        file).

    Returns
    -------
    ElemPumpFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_sinks, _ = reader.read_keyed_int()

    raw_rows: list[tuple[list[str], str]] = []
    for _ in range(n_sinks):
        with reader.section("element pumping table"):
            line = reader.next_data_line()
        m = re.search(r"\s/(.+)$", line)
        name = m.group(1).strip().lstrip("/").strip() if m else ""
        raw_rows.append((tokenize_data_line(line), name))

    if n_layers is None:
        n_layers = max(
            (len(toks) for toks, _ in raw_rows), default=12) - 10
        n_layers = max(n_layers, 1)
    frac_cols = [f"fracskl_{i}" for i in range(1, n_layers + 1)]
    col_names = (
        ["id", "icolsk", "fracsk", "ioptsk"] + frac_cols
        + ["typdstsk", "dstsk", "icfirigsk", "icadjsk", "icskmax",
           "fskmax"]
    )

    rows: list[dict] = []
    for tokens, name in raw_rows:
        row: dict = {}
        for i, col in enumerate(col_names):
            row[col] = tokens[i] if i < len(tokens) else None
        row["name"] = name
        rows.append(row)

    df = pd.DataFrame(rows, columns=col_names + ["name"])
    for col in col_names:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    # Fraction and max-pumping columns are floats even when a file
    # writes them as whole numbers.
    for col in ["fracsk", "fskmax"] + frac_cols:
        df[col] = df[col].astype(float)

    n_groups, _ = reader.read_keyed_int()

    element_groups = []
    if n_groups > 0:
        from iwfm_io.readers._element_groups import parse_element_groups
        element_groups, _ = parse_element_groups(
            reader.skip_to_end(), n_groups)

    return ElemPumpFile(
        header=header,
        n_sinks=n_sinks,
        data=df,
        n_groups=n_groups,
        element_groups=element_groups,
    )


# ------------------------------------------------------------------
# Time-Series Pumping
# ------------------------------------------------------------------

def read_ts_pumping(path: str | Path) -> TSPumpingFile:
    """Read a time-series pumping data file (e.g. ``TSPumping.dat``).

    Uses the standard 5-parameter time-series spec:
    NCOLPUMP, FACTPUMP, NSPPUMP, NFQPUMP, DSSFL.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    TSPumpingFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    spec = reader.read_timeseries_spec()

    result = TSPumpingFile(header=header, spec=spec)

    if spec.dss_file:
        result.dss_pathnames = reader.read_dss_pathnames(spec)
    else:
        result.data = reader.read_ts_rows(spec.n_columns)

    return result


# ------------------------------------------------------------------
# Tile Drain
# ------------------------------------------------------------------

def read_tile_drain(path: str | Path) -> TileDrainFile:
    """Read a tile drain parameter file (e.g. ``TileDrain.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    TileDrainFile
        Tile drain data columns: id, node, elev, conductance,
        dest_type, dest.  Subsurface irrigation data columns:
        id, node, elev, conductance.
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_tile_drains, _ = reader.read_keyed_int()
    facth, _ = reader.read_keyed_float()
    factcdc, _ = reader.read_keyed_float()
    tunit_dr, _ = reader.read_keyed_value()

    td_records = []
    with reader.section("tile drain table"):
        for _ in range(n_tile_drains):
            r = reader.read_row(6, "tile drain row")
            ids = reader.to_ints(r[:2], "tile drain row")
            vals = reader.to_floats(r[2:4], "tile drain row")
            dest = reader.to_ints(r[4:6], "tile drain row")
            td_records.append({
                "id": ids[0],
                "node": ids[1],
                "elev": vals[0],
                "conductance": vals[1],
                "dest_type": dest[0],
                "dest": dest[1],
            })
    td_data = pd.DataFrame(td_records)

    # Subsurface irrigation section
    n_sub_irrig, _ = reader.read_keyed_int()
    facthsi, _ = reader.read_keyed_float()
    factcdcsi, _ = reader.read_keyed_float()
    tunit_si, _ = reader.read_keyed_value()

    si_col_names = ["id", "node", "elev", "conductance"]
    if n_sub_irrig > 0:
        si_records = []
        with reader.section("subsurface irrigation table"):
            for _ in range(n_sub_irrig):
                r = reader.read_row(4, "subsurface irrigation row")
                ids = reader.to_ints(r[:2], "subsurface irrigation row")
                vals = reader.to_floats(r[2:4], "subsurface irrigation row")
                si_records.append({
                    "id": ids[0],
                    "node": ids[1],
                    "elev": vals[0],
                    "conductance": vals[1],
                })
        si_data = pd.DataFrame(si_records)
    else:
        si_data = pd.DataFrame(columns=si_col_names)

    # Hydrograph print control section
    cursor = reader.tail_cursor()

    n_hydrographs = 0
    hyd_factvlou = 1.0
    hyd_unitvlou = ""
    hyd_out_file = None
    hydrographs = None
    try:
        if cursor.peek_keyword() == "NOUTTD":
            n_hydrographs = int(cursor.read_keyed_value()[0])
            if cursor.peek_keyword() == "FACTVLOU":
                hyd_factvlou = float(cursor.read_keyed_value()[0])
            if cursor.peek_keyword() == "UNITVLOU":
                hyd_unitvlou = cursor.read_keyed_value()[0]
            if cursor.peek_keyword() == "TDOUTFL":
                value = cursor.read_keyed_value()[0]
                hyd_out_file = value if value and value != "*" else None
            rows = []
            for _ in range(n_hydrographs):
                line = cursor.next()
                body = re.split(r"\s+/", line, maxsplit=1)[0]
                parts = body.split(None, 2)
                m = re.search(r"\s/(.+)$", line)
                rows.append({
                    "id": int(float(parts[0])),
                    "idtyp": int(float(parts[1])),
                    "name": (parts[2].rstrip() if len(parts) > 2 else ""),
                    "notes": (m.group(1).strip().lstrip("/").strip()
                              if m else ""),
                })
            if rows:
                hydrographs = pd.DataFrame(rows)
    except (ValueError, IndexError) as exc:
        if isinstance(exc, IWFMParseError) and cursor.strict:
            raise
        with cursor.section("tile drain hydrographs"):
            cursor.degrade(
                f"tile drain hydrograph section only partially parsed "
                f"({exc}); unparsed entries will be missing from written "
                "output")

    return TileDrainFile(
        header=header,
        n_tile_drains=n_tile_drains,
        facth=facth,
        factcdc=factcdc,
        tunit_dr=tunit_dr,
        data=td_data,
        n_sub_irrig=n_sub_irrig,
        facthsi=facthsi,
        factcdcsi=factcdcsi,
        tunit_si=tunit_si,
        sub_irrig_data=si_data,
        n_hydrographs=n_hydrographs,
        hyd_factvlou=hyd_factvlou,
        hyd_unitvlou=hyd_unitvlou,
        hyd_out_file=hyd_out_file,
        hydrographs=hydrographs,
    )


# ------------------------------------------------------------------
# Subsidence
# ------------------------------------------------------------------

def read_subsidence(path: str | Path) -> SubsidenceFile:
    """Read the subsidence component main file (e.g. ``Subsidence.dat``).

    Parses output file paths, unit conversion, hydrograph specs, and
    stores the raw subsidence parameter block for round-trip writing.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SubsidenceFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    def _resolve(value: str) -> str | None:
        if not value or value == "*":
            return None
        from iwfm_io._parser import resolve_child_path
        return resolve_child_path(value, base_dir)

    # Keyed header block, identified by keyword rather than position:
    # optional entries may be commented out entirely (e.g. C2VSimFG has
    # no TPSOUTFL/FNSUBFL data lines).
    path_keywords = {
        "INISUBFL": "ini_sub",
        "TPSOUTFL": "tps_out",
        "FNSUBFL": "fn_sub",
    }
    scalar_keywords = {"FACTLTOU", "UNITLTOU", "NOUTS", "FACTXY"}

    file_paths: dict[str, str | None] = {k: None for k in path_keywords.values()}
    scalars: dict[str, str] = {}
    hydrograph_out_file = None
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw == "SUBHYDOUTFL":
            reader.next_data_line()
            hydrograph_out_file = _resolve(value)
            break
        if kw in path_keywords:
            reader.next_data_line()
            file_paths[path_keywords[kw]] = _resolve(value)
        elif kw in scalar_keywords:
            reader.next_data_line()
            scalars[kw] = value
        else:
            break

    config = {
        "factltou": float(scalars.get("FACTLTOU") or 1.0),
        "unitltou": scalars.get("UNITLTOU", ""),
    }

    n_hydrographs = int(scalars.get("NOUTS") or 0)
    hydrograph_factxy = float(scalars.get("FACTXY") or 1.0)

    hyd_cols = ["id", "subtyp", "layer", "x", "y", "node", "name"]
    with reader.section("subsidence hydrograph table"):
        hydrographs = _read_hydrograph_table(reader, n_hydrographs, hyd_cols)

    # Subsidence parameter section: fully parsed into DataFrames
    _sub_cursor = reader.tail_cursor()

    ngroup = None
    param_factors: dict = {}
    param_time_units: dict = {}
    subsidence_params = None
    parametric_grids: list = []
    try:
        with _sub_cursor.section("subsidence parameters"):
            block = parse_param_block(
                _sub_cursor,
                param_names=["sce", "sci", "dc", "dcmin", "hc"],
                factor_names=["fx", "fsce", "fsci", "fdc", "fdcmin", "fhc"],
            )
        ngroup = block["ngroup"]
        param_factors = block["factors"]
        param_time_units = block["time_units"]
        subsidence_params = block["node_params"]
        parametric_grids = block["parametric_grids"]
        if not _sub_cursor.eof:
            _sub_cursor.next()
            _sub_cursor.degrade(
                "Subsidence: unrecognized content after the parameter "
                "section was not understood and will be missing from "
                "written output")
    except (ValueError, IndexError) as exc:
        if isinstance(exc, IWFMParseError) and _sub_cursor.strict:
            raise
        with _sub_cursor.section("subsidence parameters"):
            _sub_cursor.degrade(
                f"Subsidence parameter tail only partially parsed ({exc}); "
                "unparsed sections will be missing from written output")

    return SubsidenceFile(
        header=header,
        file_paths=file_paths,
        config=config,
        n_hydrographs=n_hydrographs,
        hydrograph_factxy=hydrograph_factxy,
        hydrograph_out_file=hydrograph_out_file,
        hydrographs=hydrographs,
        ngroup=ngroup,
        param_factors=param_factors,
        param_time_units=param_time_units,
        subsidence_params=subsidence_params,
        parametric_grids=parametric_grids,
    )
