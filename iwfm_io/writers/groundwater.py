"""
Writers for IWFM groundwater component input files.

Serialize groundwater dataclasses back to IWFM text format.  All
sections — including aquifer/subsidence parameters, anomalies, and
initial conditions — are regenerated from the parsed DataFrames.
"""

from __future__ import annotations

import pandas as pd

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter, format_cell, numbered_columns
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
from iwfm_io.writers._param_blocks import (
    check_count,
    fmt_int,
    fmt_name,
    fmt_note,
    fmt_num,
    write_element_groups,
    write_param_block,
    write_table_rows,
)
from iwfm_io.writers._timeseries import write_ts_body


def _nrows(df) -> int:
    return 0 if df is None else len(df)


def _note(row) -> str:
    """The row's notes annotation, or "" when absent."""
    v = row.get("notes")
    return v if isinstance(v, str) else ""


def _hydrograph_row(row, id_col: str, type_col: str, what: str) -> list[str]:
    """``ID TYPE LAYER X Y NODE NAME`` cells of a GW/subsidence
    hydrograph row: ids/type/layer must be integral, x/y/node/name may
    be blank (a hydrograph is located by either coordinates or node)."""
    return [
        fmt_int(row[id_col], f"{what} id"),
        fmt_int(row[type_col], f"{what} type"),
        fmt_int(row["layer"], f"{what} layer"),
        format_cell(row["x"], what=f"{what} x", allow_blank=True),
        format_cell(row["y"], what=f"{what} y", allow_blank=True),
        format_cell(row["node"], what=f"{what} node", allow_blank=True,
                    integer=True),
        fmt_name(row["name"], f"{what} name"),
    ]


# ------------------------------------------------------------------
# GW Main
# ------------------------------------------------------------------

def write_gw_main(
    gw: GWMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the groundwater component main file.

    Parameters
    ----------
    gw : GWMain
    path : str or Path
    base_dir : str or Path, optional
        Base directory for relativising file paths.
    """
    w = IWFMFileWriter(path)
    w.write_header(gw.header)

    fp = gw.file_paths
    w.write_keyed_path(fp.get("bc_main"), "BCFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("tile_drain"), "TDFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("pump_main"), "PUMPFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("subsidence"), "SUBSFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("overwrite"), "OVRWRTFL", base_dir=base_dir)

    cfg = gw.config
    w.write_keyed_value(cfg.get("factltou", 1.0), "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "ft."), "UNITLTOU")
    w.write_keyed_value(cfg.get("factvlou", 1.0), "FACTVLOU")
    w.write_keyed_value(cfg.get("unitvlou", "ac.ft."), "UNITVLOU")
    w.write_keyed_value(cfg.get("factvrou", 1.0), "FACTVROU")
    w.write_keyed_value(cfg.get("unitvrou", "fpd"), "UNITVROU")

    w.write_keyed_path(fp.get("vel_out"), "VELOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("vflow_out"), "VFLOWOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("gwhead_all"), "GWALLOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("htp_out"), "HTPOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("vtp_out"), "VTPOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("gw_budget"), "GWBUDFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("zbudget"), "ZBUDFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("final_heads"), "FNGWFL", base_dir=base_dir)

    if cfg.get("ihtpflag") is not None:
        # IHTPFLAG is absent from newer (2024.x) GW main files
        w.write_keyed_value(cfg["ihtpflag"], "IHTPFLAG")

    # Terminating comment for the output-file list. IWFM decides whether
    # IHTPFLAG is present by counting the data lines of this block
    # (Class_AppGW::New -- 19 entries means "no IHTPFLAG", anything else
    # means it is there), so without a comment here KDEB and everything
    # after it are swallowed by the count and the file is read one entry
    # out of step.
    w.write_comment("C  end of output file list")

    w.write_keyed_value(cfg.get("kdeb", 0), "KDEB")

    # Hydrograph output block
    check_count(gw.n_hydrographs, _nrows(gw.hydrographs), "GW main: NOUTH")
    w.write_keyed_value(gw.n_hydrographs, "NOUTH")
    w.write_keyed_value(gw.hydrograph_factxy, "FACTXY")
    w.write_keyed_path(gw.hydrograph_out_file, "GWHYDOUTFL", base_dir=base_dir)

    if gw.hydrographs is not None and len(gw.hydrographs) > 0:
        for _, row in gw.hydrographs.iterrows():
            w.write_data_line(
                _hydrograph_row(row, "id", "hydtyp", "GW hydrograph"),
                widths=[6, 8, 10, 14, 14, 14, 12],
                note=_note(row),
            )

    # Face flow output block. FCHYDOUTFL is omitted when there are no
    # face flow hydrographs (matches IWFM 2024.x files with NOUTF=0).
    check_count(gw.n_face_flows, _nrows(gw.face_flows), "GW main: NOUTF")
    w.write_keyed_value(gw.n_face_flows, "NOUTF")
    # IWFM reads FCHYDOUTFL unconditionally (C2VSimFG carries a blank
    # line even with NOUTF=0), so always emit it
    w.write_keyed_path(gw.face_flow_out_file, "FCHYDOUTFL", base_dir=base_dir)

    if gw.face_flows is not None and len(gw.face_flows) > 0:
        for _, row in gw.face_flows.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["id"], "face flow id"),
                    fmt_int(row["layer"], "face flow layer"),
                    fmt_int(row["node_a"], "face flow node_a"),
                    fmt_int(row["node_b"], "face flow node_b"),
                    fmt_name(row["name"], "face flow name"),
                ],
                widths=[6, 8, 12, 12, 12],
                note=_note(row),
            )

    # Aquifer parameter section, regenerated from the parsed data
    w.write_comment("C  Aquifer Parameters")
    write_param_block(
        w,
        ngroup=gw.ngroup if gw.ngroup is not None else 0,
        factors=gw.param_factors,
        factor_names=["fx", "fkh", "fs", "fn", "fv", "fl"],
        param_names=["kh", "ss", "sy", "aquitard_kv", "kv"],
        node_params=gw.aquifer_params,
        parametric_grids=gw.parametric_grids,
        time_units={
            "TUNITKH": gw.param_time_units.get("TUNITKH", "1day"),
            "TUNITV": gw.param_time_units.get("TUNITV", "1day"),
            "TUNITL": gw.param_time_units.get("TUNITL", "1day"),
        },
    )

    # Anomaly in hydraulic conductivity
    w.write_comment("C  Anomaly in Hydraulic Conductivity")
    check_count(gw.anomaly_nebk, _nrows(gw.kh_anomalies), "GW main: NEBK")
    w.write_keyed_value(gw.anomaly_nebk, "NEBK")
    w.write_keyed_value(fmt_num(gw.anomaly_factor), "FACT")
    w.write_keyed_value(gw.anomaly_time_unit or "1day", "TUNITH")
    if gw.kh_anomalies is not None and len(gw.kh_anomalies) > 0:
        cols = ["ic", "element_id"] + numbered_columns(
            gw.kh_anomalies, "kh_layer_")
        write_table_rows(w, gw.kh_anomalies, cols,
                         widths=[8, 10] + [14] * (len(cols) - 2))

    # Groundwater return flow (only in format variants that have it)
    if gw.iflagrf is not None:
        w.write_comment("C  Simulation of Groundwater Return Flow")
        w.write_keyed_value(gw.iflagrf, "IFLAGRF")
        if gw.return_flow is not None and len(gw.return_flow) > 0:
            write_table_rows(w, gw.return_flow,
                             ["node_id", "dest_type", "dest"],
                             widths=[10, 8, 8])

    # Initial groundwater heads
    w.write_comment("C  Initial Groundwater Head Values")
    w.write_keyed_value(fmt_num(gw.facthp if gw.facthp is not None else 1.0),
                        "FACTHP")
    if gw.initial_heads is not None and len(gw.initial_heads) > 0:
        cols = ["node_id"] + numbered_columns(gw.initial_heads,
                                             "head_layer_")
        write_table_rows(w, gw.initial_heads, cols,
                         widths=[10] + [14] * (len(cols) - 1))

    w.flush()


# ------------------------------------------------------------------
# GW initial-conditions (restart) file
# ------------------------------------------------------------------

_DASH = "C" + "-" * 79


def _normalize_heads_frame(heads) -> "tuple[list[int], pd.DataFrame]":
    """Coerce a heads table to ``node_id`` + ``head_layer_1..NL``.

    Accepts the ``initial_heads`` shape from :func:`read_gw_main`
    (``node_id, head_layer_*``) and the shape
    :func:`~iwfm_io.readers.text_output.read_final_state_out` returns
    for ``FinalGWHeads.out`` (``ID, HP[1], HP[2], …``): the first
    column is the node id, every remaining column is one layer, in
    order.
    """
    import pandas as pd

    if heads is None or len(heads) == 0:
        raise ValueError("initial heads table is empty")
    df = pd.DataFrame(heads)
    cols = list(df.columns)
    if "node_id" in cols:
        id_col = "node_id"
        layer_cols = numbered_columns(df, "head_layer_")
        # HP[k] is positional in the file: the layers must be 1..NL
        # with no gap, or layer 3 would silently be written as HP[2]
        numbered_columns(df, "head_layer_", n=len(layer_cols))
    else:
        id_col = cols[0]
        layer_cols = cols[1:]
    if not layer_cols:
        raise ValueError(
            "initial heads table needs at least one layer column "
            "(head_layer_1 …) besides the node id")

    out = pd.DataFrame({"node_id": df[id_col].astype(float)})
    if not (out["node_id"] % 1 == 0).all():
        raise ValueError("node ids must be integers")
    out["node_id"] = out["node_id"].astype(int)
    if out["node_id"].duplicated().any():
        dup = out.loc[out["node_id"].duplicated(), "node_id"].iloc[0]
        raise ValueError(f"duplicate node id {dup} in initial heads table")
    for i, c in enumerate(layer_cols, start=1):
        out[f"head_layer_{i}"] = pd.to_numeric(df[c], errors="coerce")
    if out.isna().any().any():
        bad = out.columns[out.isna().any()][0]
        raise ValueError(
            f"NaN in initial heads column {bad!r} — a missing head would "
            "write a short data row that IWFM mis-reads")
    return list(out["node_id"]), out


def write_gw_initial_conditions(
    path: str | Path,
    heads,
    facthp: float = 1.0,
    header: "list[str] | None" = None,
) -> None:
    """Write an IWFM groundwater initial-conditions (restart) file.

    The optional file the GW main file points to with its INITIAL
    CONDITIONS FILE entry; it overrides the ``FACTHP`` / initial-head
    block inside the GW main file. Layout matches IWFM's own
    ``FinalGWHeads.out`` so :func:`~iwfm_io.readers.text_output.read_final_state_out`
    reads the written file back::

        C*** banner ***
        C---
             1.0                           / FACTHP
        C---
        C      ID           HP[1]             HP[2]
        C---
               1        290.000000        291.172170

    Parameters
    ----------
    path : str or Path
    heads : pandas.DataFrame
        ``node_id`` + ``head_layer_1 … head_layer_NL`` (the
        ``initial_heads`` shape from :func:`read_gw_main`, or the
        frame :func:`initial_heads_from_head_all` builds), or the
        ``ID, HP[1], …`` frame :func:`read_final_state_out` returns.
        Layer count comes from the columns; node count from the rows.
    facthp : float, default 1.0
        Conversion factor written on the ``FACTHP`` line. Head values
        are written as given, never rescaled.
    header : list of str, optional
        Comment lines for the banner (a leading ``C`` is added when
        missing). Default: a one-line generic banner.

    Raises
    ------
    ValueError
        Empty table, no layer columns, non-integer or duplicate node
        ids, or any NaN head.
    """
    node_ids, df = _normalize_heads_frame(heads)
    layer_cols = numbered_columns(df, "head_layer_")

    w = IWFMFileWriter(path)
    w.write_comment("C" + "*" * 79)
    if header:
        for line in header:
            # free text: every physical line becomes its own comment line
            for part in str(line).splitlines() or [""]:
                w.write_comment(part.strip())
    else:
        w.write_comment("C ***** GROUNDWATER INITIAL CONDITIONS "
                        f"({len(node_ids)} nodes, {len(layer_cols)} layers)")
    w.write_comment("C" + "*" * 79)
    w.write_comment("C")
    w.write_comment(_DASH)
    w.write_keyed_value(fmt_num(facthp), "FACTHP", width=8,
                        comment="Conversion factor for initial heads")
    w.write_comment(_DASH)
    hdr = "C      ID" + "".join(f"{f'HP[{i}]':>18}"
                                for i in range(1, len(layer_cols) + 1))
    w.write_comment(hdr)
    w.write_comment(_DASH)
    write_table_rows(w, df, ["node_id"] + layer_cols,
                     widths=[8] + [18] * len(layer_cols))
    w.flush()


def initial_heads_from_head_all(head_all, date=None):
    """Build an initial-heads table from one ``GWHeadAll.out`` timestep.

    Parameters
    ----------
    head_all : pandas.DataFrame
        The frame :func:`~iwfm_io.readers.text_output.read_head_all_out`
        returns: a ``date`` column plus ``node_<id>_layer_<L>`` columns.
    date : str, datetime, or pandas.Timestamp, optional
        Timestep to take. ``None`` (default) takes the last record — the
        usual spin-up-to-restart case. A string is matched verbatim
        against the file's ``MM/DD/YYYY_HH:MM`` stamps; a datetime is
        matched after parsing them (IWFM's ``24:00`` = next-day
        midnight convention applies).

    Returns
    -------
    pandas.DataFrame
        ``node_id, head_layer_1 … head_layer_NL`` in the file's node
        order — what :func:`write_gw_initial_conditions` takes.

    Raises
    ------
    ValueError
        Empty input, generic ``col_N`` columns (node ids unknown), a
        *date* that matches no record or more than one, or a record
        with missing values (a truncated last timestep).
    """
    import re

    import pandas as pd

    from iwfm_io._tokens import parse_iwfm_date

    if head_all is None or len(head_all) == 0:
        raise ValueError("HeadAll table is empty")
    if "date" not in head_all.columns:
        raise ValueError("HeadAll table has no 'date' column")

    pat = re.compile(r"^node_(.+)_layer_(\d+)$")
    parsed = [(c, pat.match(str(c))) for c in head_all.columns if c != "date"]
    if not parsed or any(m is None for _, m in parsed):
        raise ValueError(
            "HeadAll columns are not named node_<id>_layer_<L> — the file "
            "header node ids could not be matched, so the heads cannot be "
            "assigned to nodes")

    if date is None:
        row = head_all.iloc[-1]
    else:
        stamps = head_all["date"].astype(str)
        if isinstance(date, str):
            mask = stamps.str.strip() == date.strip()
        else:
            target = pd.Timestamp(date).to_pydatetime()
            mask = stamps.map(lambda s: parse_iwfm_date(s.strip()) == target)
        n = int(mask.sum())
        if n == 0:
            raise ValueError(f"no HeadAll record at {date!r}")
        if n > 1:
            raise ValueError(f"{n} HeadAll records match {date!r}")
        row = head_all.loc[mask].iloc[0]

    node_order: list = []
    seen = set()
    layers = set()
    for c, m in parsed:
        nid, lay = m.group(1), int(m.group(2))
        layers.add(lay)
        if nid not in seen:
            seen.add(nid)
            node_order.append(nid)
    n_layers = max(layers)
    if layers != set(range(1, n_layers + 1)):
        raise ValueError(f"HeadAll layer columns are not 1..{n_layers}")

    data = {"node_id": [int(float(n)) for n in node_order]}
    for lay in range(1, n_layers + 1):
        vals = []
        for nid in node_order:
            col = f"node_{nid}_layer_{lay}"
            if col not in head_all.columns:
                raise ValueError(f"HeadAll table is missing column {col!r}")
            vals.append(row[col])
        data[f"head_layer_{lay}"] = vals
    out = pd.DataFrame(data)
    if out.isna().any().any():
        raise ValueError(
            f"HeadAll record {row['date']!r} has missing values — likely a "
            "truncated last timestep; refusing to write a partial restart")
    return out


# ------------------------------------------------------------------
# BC Main
# ------------------------------------------------------------------

def write_bc_main(
    bc: BCMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the boundary conditions main file.

    Parameters
    ----------
    bc : BCMain
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(bc.header)

    fp = bc.file_paths
    w.write_keyed_path(fp.get("sp_flow"), "SPFLOWFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("sp_head"), "SPHEADFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("ghbc"), "GHBCFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("con_ghbc"), "CONGHBCFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("ts_bc"), "TSBCFL", base_dir=base_dir)

    check_count(bc.n_bc_hydrographs, _nrows(bc.bc_hydrographs),
                "BC main: NOUTB")
    w.write_keyed_value(bc.n_bc_hydrographs, "NOUTB")
    w.write_keyed_path(bc.bc_hyd_out_file, "BHYDOUTFL", base_dir=base_dir)

    if bc.bc_hydrographs is not None and len(bc.bc_hydrographs) > 0:
        for _, row in bc.bc_hydrographs.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["id"], "BC hydrograph id"),
                    fmt_int(row["layer"], "BC hydrograph layer"),
                    fmt_int(row["node"], "BC hydrograph node"),
                    fmt_name(row["name"], "BC hydrograph name"),
                ],
                widths=[6, 8, 12, 12],
                note=_note(row),
            )

    w.flush()


# ------------------------------------------------------------------
# Specified Head BC
# ------------------------------------------------------------------

def write_spec_head_bc(sf: SpecifiedHeadFile, path: str | Path) -> None:
    """Write a specified head boundary conditions file.

    Parameters
    ----------
    sf : SpecifiedHeadFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sf.header)

    check_count(sf.n_nodes, _nrows(sf.data), "Specified head BC: NHB")
    w.write_keyed_value(sf.n_nodes, "NHB")
    w.write_keyed_value(sf.factor, "FACT")

    if sf.data is not None:
        for _, row in sf.data.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["node_id"], "specified head node_id"),
                    fmt_int(row["layer"], "specified head layer"),
                    fmt_int(row["itscol"], "specified head itscol"),
                    fmt_num(row["head"], what="specified head"),
                ],
                widths=[10, 8, 8, 12],
            )

    w.flush()


# ------------------------------------------------------------------
# Specified Flow BC
# ------------------------------------------------------------------

def write_spec_flow_bc(sf: SpecifiedFlowBCFile, path: str | Path) -> None:
    """Write a specified flow boundary conditions file.

    Mirrors :func:`iwfm_io.readers.groundwater.read_spec_flow_bc`:
    NQB, FACT, TUNIT, then one ``NODE LAYER ITSCOL FLOW`` row per node.

    Parameters
    ----------
    sf : SpecifiedFlowBCFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sf.header)

    check_count(sf.n_nodes, _nrows(sf.data), "Specified flow BC: NQB")
    w.write_keyed_value(sf.n_nodes, "NQB")
    w.write_keyed_value(sf.factor, "FACT")
    w.write_keyed_value(sf.time_unit, "TUNIT")

    if sf.data is not None:
        for _, row in sf.data.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["node_id"], "specified flow node_id"),
                    fmt_int(row["layer"], "specified flow layer"),
                    fmt_int(row["itscol"], "specified flow itscol"),
                    fmt_num(row["flow"], what="specified flow"),
                ],
                widths=[10, 8, 8, 14],
            )

    w.flush()


# ------------------------------------------------------------------
# General Head BC
# ------------------------------------------------------------------

def write_general_head_bc(gh: GeneralHeadBCFile, path: str | Path) -> None:
    """Write a general head boundary conditions file.

    Mirrors :func:`iwfm_io.readers.groundwater.read_general_head_bc`:
    NGB, FACTH, FACTC, TUNITC, then one ``NODE LAYER ITSCOL BH BC``
    row per node.

    Parameters
    ----------
    gh : GeneralHeadBCFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(gh.header)

    check_count(gh.n_nodes, _nrows(gh.data), "General head BC: NGB")
    w.write_keyed_value(gh.n_nodes, "NGB")
    w.write_keyed_value(gh.facth, "FACTH")
    w.write_keyed_value(gh.factc, "FACTC")
    w.write_keyed_value(gh.time_unit, "TUNITC")

    if gh.data is not None:
        for _, row in gh.data.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["node_id"], "general head BC node_id"),
                    fmt_int(row["layer"], "general head BC layer"),
                    fmt_int(row["itscol"], "general head BC itscol"),
                    fmt_num(row["head"], what="general head BC head"),
                    fmt_num(row["conductance"],
                            what="general head BC conductance"),
                ],
                widths=[10, 8, 8, 14, 14],
            )

    w.flush()


# ------------------------------------------------------------------
# Constrained General Head BC
# ------------------------------------------------------------------

def write_constrained_head_bc(
    ch: ConstrainedHeadBCFile,
    path: str | Path,
) -> None:
    """Write a constrained general head boundary conditions file.

    Mirrors :func:`iwfm_io.readers.groundwater.read_constrained_head_bc`
    (keywords as in the C2VSimFG release files): NGB, FACTH, FACTVL,
    TUNITVL, FACTC, TUNITC, then one row per node —
    ``NODE LAYER ITSCOL BH BC LBH ITSCOLF CFLOW [/ name]``.

    Parameters
    ----------
    ch : ConstrainedHeadBCFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ch.header)

    check_count(ch.n_nodes, _nrows(ch.data),
                "Constrained head BC: NGB")
    w.write_keyed_value(ch.n_nodes, "NGB")
    w.write_keyed_value(ch.facth, "FACTH")
    w.write_keyed_value(ch.factvl, "FACTVL")
    w.write_keyed_value(ch.tunitvl, "TUNITVL")
    w.write_keyed_value(ch.factc, "FACTC")
    w.write_keyed_value(ch.tunitc, "TUNITC")

    if ch.data is not None:
        for _, row in ch.data.iterrows():
            what = "constrained head BC"
            values = [
                fmt_int(row["node_id"], f"{what} node_id"),
                fmt_int(row["layer"], f"{what} layer"),
                fmt_int(row["itscol"], f"{what} itscol"),
                fmt_num(row["head"], what=f"{what} head"),
                fmt_num(row["conductance"], what=f"{what} conductance"),
                fmt_num(row["limiting_head"], what=f"{what} limiting_head"),
                fmt_int(row["itscolf"], f"{what} itscolf"),
                fmt_num(row["max_flow"], what=f"{what} max_flow"),
            ]
            widths = [10, 8, 8, 14, 14, 14, 10, 14]
            w.write_data_line(values, widths,
                              note=fmt_note(row.get("name"), f"{what} name"))

    w.flush()


# ------------------------------------------------------------------
# Boundary Time Series
# ------------------------------------------------------------------

def write_boundary_ts(
    bt: BoundaryTSFile,
    path: str | Path,
) -> None:
    """Write a time-series boundary conditions file.

    Parameters
    ----------
    bt : BoundaryTSFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(bt.header)

    spec = bt.spec
    cfg = bt.config
    write_ts_body(
        w,
        [(spec.n_columns, "NBTSD"),
         (spec.factor, "FACTHTS"),
         (cfg.get("factqts", 1.0), "FACTQTS"),
         (spec.n_steps_update, "NSPHTS"),
         (spec.repeat_freq, "NFQHTS"),
         (spec.dss_file, "DSSFL")],
        bt.data, bt.dss_pathnames, n_columns=spec.n_columns)

    w.flush()


# ------------------------------------------------------------------
# Pump Main
# ------------------------------------------------------------------

def write_pump_main(
    pm: PumpMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the pumping component main file.

    Parameters
    ----------
    pm : PumpMain
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(pm.header)

    fp = pm.file_paths
    w.write_keyed_path(fp.get("well"), "WELLFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("elem_pump"), "ELEMPUMPFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("ts_pump"), "PUMPFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("pump_out"), "PUMPOUTFL", base_dir=base_dir)

    w.flush()


# ------------------------------------------------------------------
# Element Pumping
# ------------------------------------------------------------------

def write_elem_pump(ep: ElemPumpFile, path: str | Path) -> None:
    """Write an element pumping specification file.

    Parameters
    ----------
    ep : ElemPumpFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ep.header)

    check_count(ep.n_sinks, _nrows(ep.data), "Element pumping: NSINK")
    w.write_keyed_value(ep.n_sinks, "NSINK")

    if ep.data is not None:
        # Per-layer fraction columns are dynamic (one per aquifer layer)
        frac_cols = numbered_columns(ep.data, "fracskl_")
        col_order = (
            ["id", "icolsk", "fracsk", "ioptsk"] + frac_cols
            + ["typdstsk", "dstsk", "icfirigsk", "icadjsk", "icskmax",
               "fskmax"]
        )
        int_cols = {"id", "icolsk", "ioptsk", "typdstsk", "dstsk",
                    "icfirigsk", "icadjsk", "icskmax"}
        widths = ([5, 6, 9, 9] + [12] * len(frac_cols)
                  + [12, 8, 12, 10, 10, 8])

        def _isna(v):
            return v is None or (not isinstance(v, str) and pd.isna(v))

        for _, row in ep.data.iterrows():
            vals = [row.get(col) for col in col_order]
            n_valid = len(vals)
            while n_valid and _isna(vals[n_valid - 1]):
                n_valid -= 1
            tokens = []
            for col, val in zip(col_order[:n_valid], vals[:n_valid]):
                if _isna(val):
                    raise ValueError(
                        f"NaN in elem-pump column {col!r} -- only "
                        "TRAILING values may be omitted; a gap in the "
                        "middle would shift IWFM's read")
                tokens.append(format_cell(
                    val, what=f"elem-pump column {col!r}",
                    integer=col in int_cols))
            w.write_data_line(tokens, widths[:n_valid],
                              note=fmt_note(row.get("name"),
                                            "elem-pump name"))

    check_count(ep.n_groups, len(ep.element_groups),
                "Element pumping: NGRP")
    w.write_keyed_value(ep.n_groups, "NGRP")
    write_element_groups(w, ep.element_groups)

    w.flush()


# ------------------------------------------------------------------
# Well Specifications
# ------------------------------------------------------------------

def write_well_spec(ws: WellSpecFile, path: str | Path) -> None:
    """Write a well specification file.

    Parameters
    ----------
    ws : WellSpecFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ws.header)

    check_count(ws.n_wells, _nrows(ws.data), "Well specs: NWELL")
    w.write_keyed_value(ws.n_wells, "NWELL")
    w.write_keyed_value(fmt_num(ws.factors.get("factxy", 1.0)), "FACTXY")
    w.write_keyed_value(fmt_num(ws.factors.get("factrw", 1.0)), "FACTRW")
    w.write_keyed_value(fmt_num(ws.factors.get("factlt", 1.0)), "FACTLT")

    if ws.data is not None:
        for _, row in ws.data.iterrows():
            line_vals = [
                fmt_int(row["well_id"], "well_id"),
                fmt_num(row["x"], what="well x"),
                fmt_num(row["y"], what="well y"),
                fmt_num(row["radius"], what="well radius"),
                fmt_num(row["perf_top"], what="well perf_top"),
                fmt_num(row["perf_bot"], what="well perf_bot"),
            ]
            w.write_data_line(line_vals, [8, 16, 16, 10, 12, 12],
                              note=fmt_note(row.get("name"), "well name"))

    w.write_comment("C  Well Pumping Configuration")
    if ws.pump_config is not None:
        cols = ["id", "icolwl", "fracwl", "ioptwl", "typdstwl", "dstwl",
                "icfirigwl", "icadjwl", "icwlmax", "fwlmax"]
        int_cols = {"id", "icolwl", "ioptwl", "typdstwl", "dstwl",
                    "icfirigwl", "icadjwl", "icwlmax"}
        widths = [8, 8, 8, 8, 8, 10, 10, 8, 8, 8]
        for _, row in ws.pump_config.iterrows():
            cells = [format_cell(
                row[c], what=f"well pump-config column {c!r} for well "
                             f"{row.get('id')}",
                integer=c in int_cols) for c in cols]
            w.write_data_line(cells, widths, note=_note(row))

    check_count(ws.n_groups, len(ws.element_groups), "Well specs: NGRP")
    w.write_keyed_value(ws.n_groups, "NGRP")
    write_element_groups(w, ws.element_groups)

    w.flush()


# ------------------------------------------------------------------
# Time-Series Pumping
# ------------------------------------------------------------------

def write_ts_pumping(ts: TSPumpingFile, path: str | Path) -> None:
    """Write a time-series pumping data file.

    Parameters
    ----------
    ts : TSPumpingFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ts.header)

    _write_ts_file(w, ts, ["NCOLPUMP", "FACTPUMP", "NSPPUMP", "NFQPUMP",
                           "DSSFL"])
    w.flush()


def _write_ts_file(w: IWFMFileWriter, ts, keywords: list[str]) -> None:
    """Body of a 5-parameter time-series file (spec + data)."""
    spec = ts.spec
    fields = list(zip(
        [spec.n_columns, spec.factor, spec.n_steps_update,
         spec.repeat_freq, spec.dss_file], keywords))
    write_ts_body(w, fields, ts.data, ts.dss_pathnames,
                  n_columns=spec.n_columns)


# ------------------------------------------------------------------
# Tile Drain
# ------------------------------------------------------------------

def write_tile_drain(td: TileDrainFile, path: str | Path) -> None:
    """Write a tile drain parameter file.

    Parameters
    ----------
    td : TileDrainFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(td.header)

    check_count(td.n_tile_drains, _nrows(td.data), "Tile drains: NTD")
    w.write_keyed_value(td.n_tile_drains, "NTD")
    w.write_keyed_value(td.facth, "FACTH")
    w.write_keyed_value(td.factcdc, "FACTCDC")
    w.write_keyed_value(td.tunit_dr, "TUNITDR")

    if td.data is not None:
        for _, row in td.data.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["id"], "tile drain id"),
                    fmt_int(row["node"], "tile drain node"),
                    fmt_num(row["elev"], what="tile drain elev"),
                    fmt_num(row["conductance"], what="tile drain conductance"),
                    fmt_int(row["dest_type"], "tile drain dest_type"),
                    fmt_int(row["dest"], "tile drain dest"),
                ],
                widths=[6, 8, 12, 12, 10, 8],
            )

    check_count(td.n_sub_irrig, _nrows(td.sub_irrig_data),
                "Tile drains: NSI")
    w.write_keyed_value(td.n_sub_irrig, "NSI")
    w.write_keyed_value(td.facthsi, "FACTHSI")
    w.write_keyed_value(td.factcdcsi, "FACTCDCSI")
    w.write_keyed_value(td.tunit_si, "TUNITSI")

    if td.sub_irrig_data is not None and len(td.sub_irrig_data) > 0:
        for _, row in td.sub_irrig_data.iterrows():
            w.write_data_line(
                [
                    fmt_int(row["id"], "sub-irrigation id"),
                    fmt_int(row["node"], "sub-irrigation node"),
                    fmt_num(row["elev"], what="sub-irrigation elev"),
                    fmt_num(row["conductance"],
                            what="sub-irrigation conductance"),
                ],
                widths=[6, 8, 12, 12],
            )

    # Hydrograph print control section
    w.write_comment("C  Hydrograph Print Control")
    check_count(td.n_hydrographs, _nrows(td.hydrographs),
                "Tile drains: NOUTTD")
    w.write_keyed_value(td.n_hydrographs, "NOUTTD")
    w.write_keyed_value(fmt_num(td.hyd_factvlou), "FACTVLOU")
    w.write_keyed_value(td.hyd_unitvlou, "UNITVLOU")
    w.write_keyed_value(td.hyd_out_file or "", "TDOUTFL")
    if td.hydrographs is not None and len(td.hydrographs) > 0:
        for _, row in td.hydrographs.iterrows():
            w.write_data_line(
                [fmt_int(row["id"], "tile drain hydrograph id"),
                 fmt_int(row["idtyp"], "tile drain hydrograph idtyp"),
                 fmt_name(row["name"], "tile drain hydrograph name")],
                widths=[8, 8, 16],
                note=_note(row),
            )

    w.flush()


# ------------------------------------------------------------------
# Subsidence
# ------------------------------------------------------------------

def write_subsidence(
    sub: SubsidenceFile,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the subsidence component main file.

    Parameters
    ----------
    sub : SubsidenceFile
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(sub.header)

    fp = sub.file_paths
    w.write_keyed_path(fp.get("ini_sub"), "INISUBFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("tps_out"), "TPSOUTFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("fn_sub"), "FNSUBFL", base_dir=base_dir)

    cfg = sub.config
    w.write_keyed_value(cfg.get("factltou", 1.0), "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "ft."), "UNITLTOU")

    check_count(sub.n_hydrographs, _nrows(sub.hydrographs),
                "Subsidence: NOUTS")
    w.write_keyed_value(sub.n_hydrographs, "NOUTS")
    w.write_keyed_value(sub.hydrograph_factxy, "FACTXY")
    w.write_keyed_path(sub.hydrograph_out_file, "SUBHYDOUTFL", base_dir=base_dir)

    if sub.hydrographs is not None and len(sub.hydrographs) > 0:
        for _, row in sub.hydrographs.iterrows():
            w.write_data_line(
                _hydrograph_row(row, "id", "subtyp",
                                "subsidence hydrograph"),
                widths=[6, 8, 10, 14, 14, 14, 12],
                note=_note(row),
            )

    # Subsidence parameter section, regenerated from the parsed data
    w.write_comment("C  Subsidence Parameters")
    write_param_block(
        w,
        ngroup=sub.ngroup if sub.ngroup is not None else 0,
        factors=sub.param_factors,
        factor_names=["fx", "fsce", "fsci", "fdc", "fdcmin", "fhc"],
        param_names=["sce", "sci", "dc", "dcmin", "hc"],
        node_params=sub.subsidence_params,
        parametric_grids=sub.parametric_grids,
        time_units=sub.param_time_units or None,
    )

    w.flush()
