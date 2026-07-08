"""
Readers for IWFM groundwater component input files.

All functions return dataclass containers with pandas DataFrames.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm.io._parser import IWFMFileReader
from iwfm.io._tokens import split_keyed_line, tokenize_data_line
from iwfm.io.models.base import FileHeader, TimeSeriesSpec
from iwfm.io.models.groundwater import (
    BCMain,
    BoundaryTSFile,
    ElemPumpFile,
    GWMain,
    PumpMain,
    SpecifiedHeadFile,
    SubsidenceFile,
    TileDrainFile,
    TSPumpingFile,
)


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------

def _read_ts_data_to_eof(
    reader: IWFMFileReader,
    n_columns: int,
    col_names: list[str] | None = None,
) -> pd.DataFrame:
    """Read time-series date+value rows until EOF or non-date line.

    Dates are stored as raw strings to handle IWFM special years (4000,
    2500) that are outside the pandas Timestamp range.

    Parameters
    ----------
    reader : IWFMFileReader
    n_columns : int
    col_names : list[str], optional

    Returns
    -------
    pd.DataFrame
        Columns: date (str), col_1, col_2, ... (or *col_names*).
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

    for _ in range(n_rows):
        line = reader.next_data_line()
        # tokenize_data_line strips any trailing "/ comment" some models
        # append to hydrograph rows (e.g. C2VSimFG subsidence InSAR notes)
        tokens = tokenize_data_line(line)
        row: dict = {col: None for col in col_names}

        if n_cols == 7:
            # Full hydrograph format: ID TYPE LAYER [X Y | NODE] NAME
            id_col, type_col, layer_col, x_col, y_col, node_col, name_col = col_names
            if len(tokens) >= 2:
                row[id_col] = tokens[0]
                loc_type = tokens[1]
                row[type_col] = loc_type
            if len(tokens) >= 3:
                row[layer_col] = tokens[2]
            if loc_type == "0":
                # x-y format: remaining tokens are X Y NAME
                if len(tokens) >= 5:
                    row[x_col] = tokens[3]
                    row[y_col] = tokens[4]
                if len(tokens) >= 6:
                    row[name_col] = tokens[5]
            else:
                # node format: remaining tokens are NODE NAME
                if len(tokens) >= 4:
                    row[node_col] = tokens[3]
                if len(tokens) >= 5:
                    row[name_col] = tokens[4]
        elif n_cols == 4:
            # Simple BC hydrograph format: ID LAYER NODE NAME
            for i, col in enumerate(col_names):
                row[col] = tokens[i] if i < len(tokens) else None
        else:
            # Generic fallback: assign by position
            for i, col in enumerate(col_names):
                row[col] = tokens[i] if i < len(tokens) else None

        rows.append(row)

    return pd.DataFrame(rows, columns=col_names)


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
        rel = value.replace("\\", "/")
        resolved = base_dir / rel
        # IWFM resolves child paths against the simulation working
        # directory (the parent folder when this main file lives in a
        # component subfolder) — prefer whichever candidate exists.
        if not resolved.exists() and (base_dir.parent / rel).exists():
            resolved = base_dir.parent / rel
        return str(resolved)

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
    hydrographs = _read_hydrograph_table(reader, n_hydrographs, hydrograph_cols)

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
    face_flows = _read_hydrograph_table(reader, n_face_flows, face_flow_cols)

    # Aquifer parameter section: capture everything to EOF verbatim
    aquifer_param_raw = reader.skip_to_end()

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
        aquifer_param_raw=aquifer_param_raw,
    )


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
    bc_hydrographs = _read_hydrograph_table(reader, n_bc_hydrographs, bc_hyd_cols)

    return BCMain(
        header=header,
        file_paths=file_paths,
        n_bc_hydrographs=n_bc_hydrographs,
        bc_hyd_out_file=bc_hyd_out_file,
        bc_hydrographs=bc_hydrographs,
    )


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
        DataFrame columns: node_id (int), layer (int), ibctyp (int),
        head (float).
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    factor, _ = reader.read_keyed_float()

    rows = reader.read_data_table(n_nodes, n_cols=4)
    node_ids = [int(r[0]) for r in rows]
    layers = [int(r[1]) for r in rows]
    ibctyps = [int(r[2]) for r in rows]
    heads = [float(r[3]) for r in rows]

    df = pd.DataFrame({
        "node_id": node_ids,
        "layer": layers,
        "ibctyp": ibctyps,
        "head": heads,
    })

    return SpecifiedHeadFile(
        header=header,
        n_nodes=n_nodes,
        factor=factor,
        data=df,
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
        result.data = _read_ts_data_to_eof(reader, n_columns)

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
# Element Pumping
# ------------------------------------------------------------------

def read_elem_pump(path: str | Path) -> ElemPumpFile:
    """Read an element pumping specification file (e.g. ``ElemPump.dat``).

    Each data row has: ID ICOLSK FRACSK IOPTSK FRACSKL(1) FRACSKL(2)
    TYPDSTSK DSTSK ICFIRIGSK ICADJSK ICSKMAX FSKMAX.  Rows with fewer
    columns (the sample model has one row with only 11 tokens) are read
    with missing trailing tokens stored as None.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    ElemPumpFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_sinks, _ = reader.read_keyed_int()

    col_names = [
        "id", "icolsk", "fracsk", "ioptsk",
        "fracskl_1", "fracskl_2",
        "typdstsk", "dstsk", "icfirigsk", "icadjsk", "icskmax", "fskmax",
    ]
    rows: list[dict] = []
    for _ in range(n_sinks):
        line = reader.next_data_line()
        tokens = line.split()
        row: dict = {}
        for i, col in enumerate(col_names):
            row[col] = tokens[i] if i < len(tokens) else None
        rows.append(row)

    df = pd.DataFrame(rows, columns=col_names)
    # Cast known integer/float columns where possible
    for col in ["id", "icolsk", "ioptsk", "typdstsk", "dstsk", "icfirigsk", "icadjsk", "icskmax"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["fracsk", "fracskl_1", "fracskl_2", "fskmax"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    n_groups, _ = reader.read_keyed_int()
    groups_raw = reader.skip_to_end()

    return ElemPumpFile(
        header=header,
        n_sinks=n_sinks,
        data=df,
        n_groups=n_groups,
        groups_raw=groups_raw,
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
        result.data = _read_ts_data_to_eof(reader, spec.n_columns)

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

    td_col_names = ["id", "node", "elev", "conductance", "dest_type", "dest"]
    td_rows = reader.read_data_table(n_tile_drains, n_cols=6)
    td_data = pd.DataFrame(
        [
            {
                "id": int(r[0]),
                "node": int(r[1]),
                "elev": float(r[2]),
                "conductance": float(r[3]),
                "dest_type": int(r[4]),
                "dest": int(r[5]),
            }
            for r in td_rows
        ]
    )

    # Subsurface irrigation section
    n_sub_irrig, _ = reader.read_keyed_int()
    facthsi, _ = reader.read_keyed_float()
    factcdcsi, _ = reader.read_keyed_float()
    tunit_si, _ = reader.read_keyed_value()

    si_col_names = ["id", "node", "elev", "conductance"]
    if n_sub_irrig > 0:
        si_rows = reader.read_data_table(n_sub_irrig, n_cols=4)
        si_data = pd.DataFrame(
            [
                {
                    "id": int(r[0]),
                    "node": int(r[1]),
                    "elev": float(r[2]),
                    "conductance": float(r[3]),
                }
                for r in si_rows
            ]
        )
    else:
        si_data = pd.DataFrame(columns=si_col_names)

    # Hydrograph output section: capture raw for round-trip
    hyd_raw = reader.skip_to_end()

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
        hyd_raw=hyd_raw,
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
        rel = value.replace("\\", "/")
        resolved = base_dir / rel
        # IWFM resolves child paths against the simulation working
        # directory (the parent folder when this main file lives in a
        # component subfolder) — prefer whichever candidate exists.
        if not resolved.exists() and (base_dir.parent / rel).exists():
            resolved = base_dir.parent / rel
        return str(resolved)

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
    hydrographs = _read_hydrograph_table(reader, n_hydrographs, hyd_cols)

    # Subsidence parameter section: capture everything to EOF verbatim
    subsidence_param_raw = reader.skip_to_end()

    return SubsidenceFile(
        header=header,
        file_paths=file_paths,
        config=config,
        n_hydrographs=n_hydrographs,
        hydrograph_factxy=hydrograph_factxy,
        hydrograph_out_file=hydrograph_out_file,
        hydrographs=hydrographs,
        subsidence_param_raw=subsidence_param_raw,
    )
