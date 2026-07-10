"""
Writers for IWFM stream component input files.

Serialize stream dataclasses back to IWFM text format.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._writer import IWFMFileWriter
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
    for spec in sm.hydrograph_specs:
        w.write_data_line(
            [spec["node_id"], spec["name"]],
            widths=[8, 12],
        )

    # ---- Node budget settings ----
    w.write_keyed_value(cfg.get("n_node_budgets", 0), "NBUDR")
    w.write_keyed_path(cfg.get("node_bud_file"),      "STNDBUDFL", base_dir=base_dir)

    for node_id in sm.node_budget_nodes:
        w.write_data_line([node_id], widths=[8])

    # ---- Stream bed parameters ----
    w.write_keyed_value(cfg.get("factk", 1.0),   "FACTK")
    w.write_keyed_value(cfg.get("tunitk", "1day"), "TUNITSK")
    w.write_keyed_value(cfg.get("factl", 1.0),   "FACTL")

    if sm.reach_params is not None and not sm.reach_params.empty:
        extra_cols = [
            c for c in sm.reach_params.columns
            if c not in ("reach_id", "conductance", "width", "bed_thickness")
        ]
        for _, row in sm.reach_params.iterrows():
            values = [
                int(row["reach_id"]),
                f"{row['conductance']:g}",
                f"{row['width']:g}",
                f"{row['bed_thickness']:g}",
            ]
            values += [f"{row[c]:g}" for c in extra_cols]
            w.write_data_line(values, widths=[6, 12, 12, 12] + [10] * len(extra_cols))

    # ---- Hydraulic disconnection type ----
    w.write_keyed_value(cfg.get("intrctype", 1), "INTRCTYPE")

    # ---- Stream evaporation STARFL ----
    w.write_keyed_path(cfg.get("starfl"), "STARFL", base_dir=base_dir)

    # ---- Stream evaporation node table ----
    if sm.evaporation is not None and len(sm.evaporation) > 0:
        for _, row in sm.evaporation.iterrows():
            w.write_data_line(
                [int(row["stream_node"]), int(row["icetst"]),
                 int(row["icarst"])],
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

    w.write_timeseries_spec(
        sf.spec,
        keywords=["NCOLSTRM", "FACTSTRM", "NSPSTRM", "NFQSTRM", "DSSFL"],
    )

    # Column-to-node assignments
    for col_id, node_id in sf.node_assignments:
        w.write_data_line([col_id, node_id], widths=[6, 8])

    if sf.dss_pathnames:
        w.write_dss_pathnames(sf.dss_pathnames)
    elif sf.data is not None:
        w.write_timeseries_data(sf.data)

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
    from iwfm_io.writers._param_blocks import fmt_num, write_element_groups

    w = IWFMFileWriter(path)
    w.write_header(ds.header)

    w.write_keyed_value(ds.n_diversions, "NRDV")

    if ds.data is None and ds.n_diversions > 0:
        raise ValueError(
            "DiverSpecsFile.data was not parsed — cannot regenerate the "
            "diversion table")

    if ds.data is not None:
        for _, row in ds.data.iterrows():
            tokens = [
                int(row["diversion_id"]), int(row["export_node"]),
                int(row["max_col"]), fmt_num(row["max_frac"]),
                int(row["recov_loss_col"]), fmt_num(row["recov_loss_frac"]),
                int(row["nonrecov_loss_col"]),
                fmt_num(row["nonrecov_loss_frac"]),
            ]
            if row.get("spill_col") is not None and not pd.isna(
                    row.get("spill_col")):
                tokens += [int(row["spill_col"]), fmt_num(row["spill_frac"])]
            tokens += [
                int(row["dest_type"]), int(row["dest_id"]),
                int(row["delivery_col"]), fmt_num(row["delivery_frac"]),
                int(row["irig_frac_col"]), int(row["adjust_col"]),
            ]
            line = "".join(str(t).rjust(wd) for t, wd in zip(
                tokens, [8] + [10] * (len(tokens) - 1)))
            name = row.get("name") or ""
            if name:
                line += f"    /{name}"
            w.write_raw(line)

    w.write_comment("C  Delivery Element Groups")
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

    w.write_keyed_value(bs.n_bypasses, "NBYPS")

    f = bs.factors
    w.write_keyed_value(f.get("factx", 1.0),    "FACTX")
    w.write_keyed_value(f.get("tunitx", "1DAY"), "TUNITX")
    w.write_keyed_value(f.get("facty", 1.0),    "FACTY")
    w.write_keyed_value(f.get("tunity", "1DAY"), "TUNITY")

    # ---- Bypass spec lines ----
    if bs.bypass_data is not None and not bs.bypass_data.empty:
        for _, row in bs.bypass_data.iterrows():
            bid = int(row["bypass_id"])
            w.write_data_line(
                [
                    bid,
                    int(row["stream_node"]),
                    int(row["dest_type"]),
                    int(row["dest"]),
                    int(row["idivc"]),
                    f"{row['divrl']:.1f}",
                    f"{row['divnl']:.1f}",
                    row["name"],
                ],
                widths=[4, 6, 10, 7, 7, 7, 8, 12],
            )

            # Inline rating table when idivc < 0
            if int(row["idivc"]) < 0 and bid in bs.rating_tables:
                rt = bs.rating_tables[bid]
                for _, rt_row in rt.iterrows():
                    w.write_data_line(
                        [f"{rt_row['divx']:.1f}", f"{rt_row['divy']:.1f}"],
                        widths=[28, 8],
                    )

    # ---- Seepage zone sections ----
    for zone in bs.seepage_zones:
        bid = zone["bypass_id"]
        n_elem = zone["n_elements"]
        elements = zone.get("elements", [])

        if n_elem == 0 or not elements:
            w.write_data_line([bid, 0, 0, 0.0], widths=[4, 14, 12, 10])
        else:
            first = elements[0]
            w.write_data_line(
                [bid, n_elem, first["element_id"], f"{first['fraction']:.1f}"],
                widths=[4, 14, 12, 10],
            )
            for elem in elements[1:]:
                w.write_data_line(
                    ["", "", elem["element_id"], f"{elem['fraction']:.1f}"],
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

    w.write_timeseries_spec(
        dv.spec,
        keywords=["NCOLDV", "FACTDV", "NSPDV", "NFQDV", "DSSFL"],
    )

    if dv.dss_pathnames:
        w.write_dss_pathnames(dv.dss_pathnames)
    elif dv.data is not None:
        w.write_timeseries_data(dv.data)

    w.flush()
