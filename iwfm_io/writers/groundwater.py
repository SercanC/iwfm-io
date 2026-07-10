"""
Writers for IWFM groundwater component input files.

Serialize groundwater dataclasses back to IWFM text format.  All
sections — including aquifer/subsidence parameters, anomalies, and
initial conditions — are regenerated from the parsed DataFrames.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.groundwater import (
    BCMain,
    BoundaryTSFile,
    ElemPumpFile,
    GWMain,
    PumpMain,
    SpecifiedHeadFile,
    SubsidenceFile,
    TileDrainFile,
    TSPumpingFile,
    WellSpecFile,
)
from iwfm_io.writers._param_blocks import (
    fmt_num,
    write_element_groups,
    write_param_block,
    write_table_rows,
)


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
    w.write_keyed_value(cfg.get("kdeb", 0), "KDEB")

    # Hydrograph output block
    w.write_keyed_value(gw.n_hydrographs, "NOUTH")
    w.write_keyed_value(gw.hydrograph_factxy, "FACTXY")
    w.write_keyed_path(gw.hydrograph_out_file, "GWHYDOUTFL", base_dir=base_dir)

    if gw.hydrographs is not None and len(gw.hydrographs) > 0:
        for _, row in gw.hydrographs.iterrows():
            w.write_data_line(
                [
                    row["id"],
                    row["hydtyp"],
                    row["layer"],
                    row["x"] if row["x"] is not None else "",
                    row["y"] if row["y"] is not None else "",
                    row["node"] if row["node"] is not None else "",
                    row["name"] if row["name"] is not None else "",
                ],
                widths=[6, 8, 10, 14, 14, 14, 12],
            )

    # Face flow output block. FCHYDOUTFL is omitted when there are no
    # face flow hydrographs (matches IWFM 2024.x files with NOUTF=0).
    w.write_keyed_value(gw.n_face_flows, "NOUTF")
    if gw.n_face_flows > 0 or gw.face_flow_out_file is not None:
        w.write_keyed_path(gw.face_flow_out_file, "FCHYDOUTFL", base_dir=base_dir)

    if gw.face_flows is not None and len(gw.face_flows) > 0:
        for _, row in gw.face_flows.iterrows():
            w.write_data_line(
                [
                    row["id"],
                    row["layer"],
                    row["node_a"],
                    row["node_b"],
                    row["name"] if row["name"] is not None else "",
                ],
                widths=[6, 8, 12, 12, 12],
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
    w.write_keyed_value(gw.anomaly_nebk, "NEBK")
    w.write_keyed_value(fmt_num(gw.anomaly_factor), "FACT")
    w.write_keyed_value(gw.anomaly_time_unit or "1day", "TUNITH")
    if gw.kh_anomalies is not None and len(gw.kh_anomalies) > 0:
        cols = ["ic", "element_id"] + [
            c for c in gw.kh_anomalies.columns
            if c.startswith("kh_layer_")]
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
        cols = ["node_id"] + [
            c for c in gw.initial_heads.columns
            if c.startswith("head_layer_")]
        write_table_rows(w, gw.initial_heads, cols,
                         widths=[10] + [14] * (len(cols) - 1))

    w.flush()


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

    w.write_keyed_value(bc.n_bc_hydrographs, "NOUTB")
    w.write_keyed_path(bc.bc_hyd_out_file, "BHYDOUTFL", base_dir=base_dir)

    if bc.bc_hydrographs is not None and len(bc.bc_hydrographs) > 0:
        for _, row in bc.bc_hydrographs.iterrows():
            w.write_data_line(
                [
                    row["id"],
                    row["layer"],
                    row["node"],
                    row["name"] if row["name"] is not None else "",
                ],
                widths=[6, 8, 12, 12],
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

    w.write_keyed_value(sf.n_nodes, "NHB")
    w.write_keyed_value(sf.factor, "FACT")

    if sf.data is not None:
        for _, row in sf.data.iterrows():
            w.write_data_line(
                [
                    int(row["node_id"]),
                    int(row["layer"]),
                    int(row["ibctyp"]),
                    f"{float(row['head']):.1f}",
                ],
                widths=[10, 8, 8, 12],
            )

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
    w.write_keyed_value(spec.n_columns, "NBTSD")
    w.write_keyed_value(spec.factor, "FACTHTS")
    w.write_keyed_value(cfg.get("factqts", 1.0), "FACTQTS")
    w.write_keyed_value(spec.n_steps_update, "NSPHTS")
    w.write_keyed_value(spec.repeat_freq, "NFQHTS")
    w.write_keyed_value(spec.dss_file, "DSSFL")

    if bt.dss_pathnames:
        w.write_dss_pathnames(bt.dss_pathnames)
    elif bt.data is not None:
        w.write_timeseries_data(bt.data)

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

    w.write_keyed_value(ep.n_sinks, "NSINK")

    col_order = [
        "id", "icolsk", "fracsk", "ioptsk",
        "fracskl_1", "fracskl_2",
        "typdstsk", "dstsk", "icfirigsk", "icadjsk", "icskmax", "fskmax",
    ]
    widths = [5, 6, 9, 9, 12, 12, 12, 8, 12, 10, 10, 8]

    if ep.data is not None:
        for _, row in ep.data.iterrows():
            tokens = []
            for col in col_order:
                val = row.get(col)
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    break
                tokens.append(val)
            w.write_data_line(tokens, widths[: len(tokens)])

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

    w.write_keyed_value(ws.n_wells, "NWELL")
    w.write_keyed_value(fmt_num(ws.factors.get("factxy", 1.0)), "FACTXY")
    w.write_keyed_value(fmt_num(ws.factors.get("factrw", 1.0)), "FACTRW")
    w.write_keyed_value(fmt_num(ws.factors.get("factlt", 1.0)), "FACTLT")

    if ws.data is not None:
        for _, row in ws.data.iterrows():
            line_vals = [
                int(row["well_id"]),
                fmt_num(row["x"]), fmt_num(row["y"]),
                fmt_num(row["radius"]),
                fmt_num(row["perf_top"]), fmt_num(row["perf_bot"]),
            ]
            widths = [8, 16, 16, 10, 12, 12]
            name = row.get("name") or ""
            parts = "".join(str(v).rjust(wd)
                            for v, wd in zip(line_vals, widths))
            if name:
                parts += f"    /{name}"
            w.write_raw(parts)

    w.write_comment("C  Well Pumping Configuration")
    if ws.pump_config is not None:
        cols = ["id", "icolwl", "fracwl", "ioptwl", "typdstwl", "dstwl",
                "icfirigwl", "icadjwl", "icwlmax", "fwlmax"]
        write_table_rows(w, ws.pump_config, cols,
                         widths=[8, 8, 8, 8, 8, 10, 10, 8, 8, 8])

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

    w.write_timeseries_spec(
        ts.spec,
        keywords=["NCOLPUMP", "FACTPUMP", "NSPPUMP", "NFQPUMP", "DSSFL"],
    )

    if ts.dss_pathnames:
        w.write_dss_pathnames(ts.dss_pathnames)
    elif ts.data is not None:
        w.write_timeseries_data(ts.data)

    w.flush()


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

    w.write_keyed_value(td.n_tile_drains, "NTD")
    w.write_keyed_value(td.facth, "FACTH")
    w.write_keyed_value(td.factcdc, "FACTCDC")
    w.write_keyed_value(td.tunit_dr, "TUNITDR")

    if td.data is not None:
        for _, row in td.data.iterrows():
            w.write_data_line(
                [
                    int(row["id"]),
                    int(row["node"]),
                    f"{float(row['elev']):.1f}",
                    f"{float(row['conductance']):.1f}",
                    int(row["dest_type"]),
                    int(row["dest"]),
                ],
                widths=[6, 8, 12, 12, 10, 8],
            )

    w.write_keyed_value(td.n_sub_irrig, "NSI")
    w.write_keyed_value(td.facthsi, "FACTHSI")
    w.write_keyed_value(td.factcdcsi, "FACTCDCSI")
    w.write_keyed_value(td.tunit_si, "TUNITSI")

    if td.sub_irrig_data is not None and len(td.sub_irrig_data) > 0:
        for _, row in td.sub_irrig_data.iterrows():
            w.write_data_line(
                [
                    int(row["id"]),
                    int(row["node"]),
                    f"{float(row['elev']):.1f}",
                    f"{float(row['conductance']):.1f}",
                ],
                widths=[6, 8, 12, 12],
            )

    # Hydrograph print control section
    w.write_comment("C  Hydrograph Print Control")
    w.write_keyed_value(td.n_hydrographs, "NOUTTD")
    w.write_keyed_value(fmt_num(td.hyd_factvlou), "FACTVLOU")
    w.write_keyed_value(td.hyd_unitvlou, "UNITVLOU")
    w.write_keyed_value(td.hyd_out_file or "", "TDOUTFL")
    if td.hydrographs is not None and len(td.hydrographs) > 0:
        for _, row in td.hydrographs.iterrows():
            w.write_data_line(
                [int(row["id"]), int(row["idtyp"]), row["name"]],
                widths=[8, 8, 16],
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

    w.write_keyed_value(sub.n_hydrographs, "NOUTS")
    w.write_keyed_value(sub.hydrograph_factxy, "FACTXY")
    w.write_keyed_path(sub.hydrograph_out_file, "SUBHYDOUTFL", base_dir=base_dir)

    if sub.hydrographs is not None and len(sub.hydrographs) > 0:
        for _, row in sub.hydrographs.iterrows():
            w.write_data_line(
                [
                    row["id"],
                    row["subtyp"],
                    row["layer"],
                    row["x"] if row["x"] is not None else "",
                    row["y"] if row["y"] is not None else "",
                    row["node"] if row["node"] is not None else "",
                    row["name"] if row["name"] is not None else "",
                ],
                widths=[6, 8, 10, 14, 14, 14, 12],
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
    )

    w.flush()
