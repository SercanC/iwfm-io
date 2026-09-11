"""
Writers for IWFM stream component input files.

Serialize stream dataclasses back to IWFM text format.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._writer import IWFMFileWriter, format_cell
from iwfm_io.writers._param_blocks import (
    check_count,
    fmt_int,
    fmt_name,
    fmt_num,
    write_element_groups,
)
from iwfm_io.writers._timeseries import write_ts_body
from iwfm_io.models.stream import (
    BypassSpecsFile,
    DiverSpecsFile,
    DiversionsFile,
    StreamInflowFile,
    StreamMain,
)


def write_stream_main(
    sm: StreamMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write an IWFM stream main file.

    Parameters
    ----------
    sm : StreamMain
    path : str or Path
    base_dir : str or Path, optional
        Base directory for relativising file paths.  IWFM resolves the
        referenced paths against the simulation working directory (the
        folder of the simulation main file), so pass that folder here.
        When omitted, absolute paths are written — always valid.
    """
    w = IWFMFileWriter(path)
    w.write_header(sm.header)

    # ---- File paths ----
    path_key_labels = [
        ("inflow",           "INFLOWFL"),
        ("diver_specs",      "DIVSPECFL"),
        ("bypass_specs",     "BYPSPECFL"),
        ("diversions",       "DIVFL"),
        ("strm_bud_hdf",     "STRMRCHBUDFL"),
        ("diver_detail_hdf", "DIVDTLBUDFL"),
    ]
    for key, label in path_key_labels:
        w.write_keyed_path(sm.file_paths.get(key), label, base_dir=base_dir)

    # ---- Hydrograph output settings ----
    cfg = sm.config
    w.write_keyed_value(cfg.get("n_hydrographs", 0),       "NOUTR")
    w.write_keyed_value(cfg.get("ihsqr", 0),               "IHSQR")
    w.write_keyed_value(cfg.get("factvrou", 1.0),          "FACTVROU")
    w.write_keyed_value(cfg.get("unitvrou", "cfs"),        "UNITVROU")
    w.write_keyed_value(cfg.get("factltou", 1.0),          "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "ft"),         "UNITLTOU")
    w.write_keyed_path(cfg.get("hydro_out_file"),          "STHYDOUTFL", base_dir=base_dir)

    # ---- Hydrograph spec lines ----
    check_count(cfg.get("n_hydrographs", 0), len(sm.hydrograph_specs),
                "Stream main: NOUTR")
    for spec in sm.hydrograph_specs:
        w.write_data_line(
            [fmt_int(spec["node_id"], "stream hydrograph node_id"),
             fmt_name(spec["name"], "stream hydrograph name")],
            widths=[8, 12],
        )

    # ---- Node budget settings ----
    check_count(cfg.get("n_node_budgets", 0), len(sm.node_budget_nodes),
                "Stream main: NBUDR")
    w.write_keyed_value(cfg.get("n_node_budgets", 0), "NBUDR")
    w.write_keyed_path(cfg.get("node_bud_file"),      "STNDBUDFL", base_dir=base_dir)

    for node_id in sm.node_budget_nodes:
        w.write_data_line([fmt_int(node_id, "stream budget node")],
                          widths=[8])

    # ---- Stream bed parameters ----
    w.write_keyed_value(cfg.get("factk", 1.0),   "FACTK")
    w.write_keyed_value(cfg.get("tunitk", "1day"), "TUNITSK")
    w.write_keyed_value(cfg.get("factl", 1.0),   "FACTL")

    if sm.reach_params is not None and not sm.reach_params.empty:
        rp = sm.reach_params
        try:
            _ver = float(sm.header.version) if sm.header.version else 4.0
        except (TypeError, ValueError):
            _ver = 4.0
        if _ver >= 4.2:
            base_cols = ["wetted_perimeter", "gw_node_id",
                         "conductance", "bed_thickness"]
        else:
            base_cols = ["conductance", "bed_thickness",
                         "wetted_perimeter"]
        extra_cols = [c for c in rp.columns
                      if c not in ("stream_node_id", "notes")
                      and c not in base_cols]
        prev_node = None
        for _, row in rp.iterrows():
            node_cell = fmt_int(row["stream_node_id"], "stream_node_id")
            node = int(node_cell)
            cells: list = []
            widths: list = []
            if not (_ver >= 4.2 and node == prev_node):
                cells.append(node_cell)
                widths.append(6)
            for c in base_cols + extra_cols:
                cells.append(format_cell(
                    row[c], what=f"stream bed table column {c!r} for "
                                 f"stream node {node}",
                    integer=(c == "gw_node_id")))
                widths.append(12)
            note = row.get("notes")
            w.write_data_line(cells, widths,
                              note=note if isinstance(note, str) else "")
            prev_node = node

    # ---- Hydraulic disconnection type (None = the source file ended
    # at the stream-bed table; keep that layout) ----
    if cfg.get("intrctype", 1) is None:
        w.flush()
        return
    w.write_keyed_value(cfg.get("intrctype", 1), "INTRCTYPE")

    # ---- Stream evaporation STARFL ----
    w.write_keyed_path(cfg.get("starfl"), "STARFL", base_dir=base_dir)

    # ---- Stream evaporation node table ----
    if sm.evaporation is not None and len(sm.evaporation) > 0:
        for _, row in sm.evaporation.iterrows():
            w.write_data_line(
                [fmt_int(row["stream_node"], "evaporation stream_node"),
                 fmt_int(row["icetst"], "evaporation icetst"),
                 fmt_int(row["icarst"], "evaporation icarst")],
                widths=[10, 8, 8])

    w.flush()


def write_stream_inflow(sf: StreamInflowFile, path: str | Path) -> None:
    """Write an IWFM stream inflow file.

    Parameters
    ----------
    sf : StreamInflowFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sf.header)

    def _node_assignments(w: IWFMFileWriter) -> None:
        # Column-to-node assignments
        for col_id, node_id in sf.node_assignments:
            w.write_data_line(
                [fmt_int(col_id, "inflow column"),
                 fmt_int(node_id, "inflow stream node")],
                widths=[6, 8])
        # Load-bearing comment terminating the node list -- like the
        # spec block, IWFM otherwise consumes the first data line
        # (verified against the executables)
        w.write_comment("C  end of inflow node list")

    spec = sf.spec
    fields = list(zip(
        [spec.n_columns, spec.factor, spec.n_steps_update,
         spec.repeat_freq, spec.dss_file],
        ["NCOLSTRM", "FACTSTRM", "NSPSTRM", "NFQSTRM", "DSSFL"]))
    write_ts_body(w, fields, sf.data, sf.dss_pathnames,
                  n_columns=spec.n_columns, between=_node_assignments)

    w.flush()


def write_diver_specs(ds: DiverSpecsFile, path: str | Path) -> None:
    """Write an IWFM diversion specification file.

    The per-diversion table, delivery element groups, and recharge
    zones are regenerated from the parsed data.

    Parameters
    ----------
    ds : DiverSpecsFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(ds.header)

    check_count(ds.n_diversions,
                0 if ds.data is None else len(ds.data),
                "Diversion specs: NRDV")
    w.write_keyed_value(ds.n_diversions, "NRDV")

    if ds.data is None and ds.n_diversions > 0:
        raise ValueError(
            "DiverSpecsFile.data was not parsed — cannot regenerate the "
            "diversion table")

    if ds.data is not None:
        for _, row in ds.data.iterrows():
            what = "diversion spec"

            def _i(col):
                return fmt_int(row[col], f"{what} {col}")

            def _f(col):
                return fmt_num(row[col], what=f"{what} {col}")

            tokens = [
                _i("diversion_id"), _i("export_node"),
                _i("max_col"), _f("max_frac"),
                _i("recov_loss_col"), _f("recov_loss_frac"),
                _i("nonrecov_loss_col"), _f("nonrecov_loss_frac"),
            ]
            if row.get("spill_col") is not None and not pd.isna(
                    row.get("spill_col")):
                tokens += [_i("spill_col"), _f("spill_frac")]
            tokens += [
                _i("dest_type"), _i("dest_id"),
                _i("delivery_col"), _f("delivery_frac"),
                _i("irig_frac_col"), _i("adjust_col"),
            ]
            widths = [8] + [10] * (len(tokens) - 1)
            # NAME is a positional field the model reads; a "/" would
            # blank it for IWFM -- it is the trailing token, separated
            # by four spaces
            name = fmt_name(row.get("name"), f"{what} name")
            if name:
                tokens.append(name)
                widths.append(len(name) + 4)
            w.write_data_line(tokens, widths,
                              note=fmt_name(row.get("notes"),
                                            f"{what} notes"))

    w.write_comment("C  Delivery Element Groups")
    check_count(ds.n_groups, len(ds.delivery_groups),
                "Diversion specs: NGRP")
    w.write_keyed_value(ds.n_groups, "NGRP")
    write_element_groups(w, ds.delivery_groups)

    w.write_comment("C  Recharge Zone for Each Diversion")
    write_element_groups(w, ds.recharge_zones, with_fractions=True)

    # Spill locations exist only in older stream-package formats
    if ds.spill_locations:
        w.write_comment("C  Diversion Spill Locations")
        write_element_groups(w, ds.spill_locations, with_fractions=True)

    w.flush()


def write_bypass_specs(bs: BypassSpecsFile, path: str | Path) -> None:
    """Write an IWFM bypass specification file.

    Parameters
    ----------
    bs : BypassSpecsFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(bs.header)

    check_count(bs.n_bypasses,
                0 if bs.bypass_data is None else len(bs.bypass_data),
                "Bypass specs: NBYPS")
    w.write_keyed_value(bs.n_bypasses, "NBYPS")

    f = bs.factors
    w.write_keyed_value(f.get("factx", 1.0),    "FACTX")
    w.write_keyed_value(f.get("tunitx", "1DAY"), "TUNITX")
    w.write_keyed_value(f.get("facty", 1.0),    "FACTY")
    w.write_keyed_value(f.get("tunity", "1DAY"), "TUNITY")

    # ---- Bypass spec lines ----
    if bs.bypass_data is not None and not bs.bypass_data.empty:
        for _, row in bs.bypass_data.iterrows():
            bid = int(fmt_int(row["bypass_id"], "bypass_id"))
            note = row.get("notes")
            w.write_data_line(
                [
                    bid,
                    fmt_int(row["stream_node"], "bypass stream_node"),
                    fmt_int(row["dest_type"], "bypass dest_type"),
                    fmt_int(row["dest"], "bypass dest"),
                    fmt_int(row["idivc"], "bypass idivc"),
                    fmt_num(row["divrl"], what="bypass divrl"),
                    fmt_num(row["divnl"], what="bypass divnl"),
                    fmt_name(row["name"], "bypass name"),
                ],
                widths=[4, 6, 10, 7, 7, 7, 8, 12],
                note=note if isinstance(note, str) else "",
            )

            # Inline rating table when idivc < 0
            if int(row["idivc"]) < 0 and bid in bs.rating_tables:
                rt = bs.rating_tables[bid]
                for _, rt_row in rt.iterrows():
                    w.write_data_line(
                        [fmt_num(rt_row["divx"], what="bypass rating divx"),
                         fmt_num(rt_row["divy"], what="bypass rating divy")],
                        widths=[28, 12],
                    )

    # ---- Seepage zone sections ----
    for zone in bs.seepage_zones:
        bid = zone["bypass_id"]
        n_elem = zone["n_elements"]
        elements = zone.get("elements", [])
        name = zone.get("name") or ""

        if n_elem == 0 or not elements:
            w.write_data_line([fmt_int(bid, "seepage zone bypass_id"),
                               "0", "0", "0.0"],
                              widths=[4, 14, 12, 10], note=name)
        else:
            check_count(n_elem, len(elements),
                        f"Bypass specs: seepage zone {bid} NERELS")
            first = elements[0]
            w.write_data_line(
                [fmt_int(bid, "seepage zone bypass_id"),
                 fmt_int(n_elem, "seepage zone NERELS"),
                 fmt_int(first["element_id"], "seepage zone element_id"),
                 fmt_num(first["fraction"], what="seepage zone fraction")],
                widths=[4, 14, 12, 10],
                note=name,
            )
            for elem in elements[1:]:
                w.write_data_line(
                    ["", "",
                     fmt_int(elem["element_id"], "seepage zone element_id"),
                     fmt_num(elem["fraction"], what="seepage zone fraction")],
                    widths=[4, 14, 12, 10],
                )

    w.flush()


def write_diversions(dv: DiversionsFile, path: str | Path) -> None:
    """Write an IWFM surface water diversion data file.

    Parameters
    ----------
    dv : DiversionsFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(dv.header)

    spec = dv.spec
    fields = list(zip(
        [spec.n_columns, spec.factor, spec.n_steps_update,
         spec.repeat_freq, spec.dss_file],
        ["NCOLDV", "FACTDV", "NSPDV", "NFQDV", "DSSFL"]))
    write_ts_body(w, fields, dv.data, dv.dss_pathnames,
                  n_columns=spec.n_columns)

    w.flush()
