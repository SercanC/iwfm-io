"""
Writers for miscellaneous IWFM files (SWShed, UnsatZone).

All sections are regenerated from the parsed DataFrames.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.misc import SWShedFile, UnsatZoneFile
from iwfm_io.writers._param_blocks import fmt_num, write_table_rows


def write_swshed(sw: SWShedFile, path: str | Path) -> None:
    """Write the IWFM small watershed file (e.g. ``SWShed.dat``).

    Parameters
    ----------
    sw : SWShedFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(sw.header)

    base_dir = Path(path).parent

    # Output file paths
    w.write_keyed_path(sw.file_paths.get("budget"), "SWBUDFL", base_dir=base_dir)
    w.write_keyed_path(sw.file_paths.get("final"), "FNSWFL", base_dir=base_dir)

    # Number of watersheds and conversion factors
    w.write_keyed_value(sw.n_watersheds, "NSW")
    cfg = sw.config
    w.write_keyed_value(fmt_num(cfg.get("facta", 1.0)), "FACTA")
    w.write_keyed_value(fmt_num(cfg.get("factq", 1.0)), "FACTQ")
    w.write_keyed_value(cfg.get("tunitq", "1DAY"), "TUNITQ")

    # Watershed definitions: ID AREAS IWBTS NWB + first receiving node
    # on the same line, remaining nodes on continuation lines.
    w.write_comment("C  Watershed Definitions")
    if sw.watershed_data is not None:
        nodes = sw.watershed_nodes
        for _, ws in sw.watershed_data.iterrows():
            ws_id = int(ws["id"])
            ws_nodes = (nodes[nodes["watershed_id"] == ws_id]
                        if nodes is not None else None)
            head = [ws_id, fmt_num(ws["area"]), int(ws["stream_node"]),
                    int(ws["n_gw_nodes"])]
            widths = [8, 14, 8, 8]
            if ws_nodes is not None and len(ws_nodes) > 0:
                head += [int(ws_nodes["gw_node"].iloc[0]),
                         fmt_num(ws_nodes["qmax"].iloc[0])]
                widths += [10, 12]
            w.write_data_line(head, widths)
            if ws_nodes is not None:
                for _, nrow in ws_nodes.iloc[1:].iterrows():
                    w.write_data_line(
                        [int(nrow["gw_node"]), fmt_num(nrow["qmax"])],
                        widths=[48, 12])

    # Root zone parameters
    w.write_comment("C  Small Watershed Root Zone Parameters")
    w.write_keyed_value(fmt_num(cfg.get("toler", 0.001)), "TOLER")
    w.write_keyed_value(cfg.get("itermax", 150), "ITERMAX")
    w.write_keyed_value(fmt_num(cfg.get("factl", 1.0)), "FACTL")
    w.write_keyed_value(fmt_num(cfg.get("factcn", 1.0)), "FACTCN")
    w.write_keyed_value(fmt_num(cfg.get("factk", 1.0)), "FACTK")
    w.write_keyed_value(cfg.get("tunitk", "1DAY"), "TUNITK")
    if sw.rootzone_params is not None:
        write_table_rows(
            w, sw.rootzone_params,
            ["id", "irns", "frns", "icets", "wp", "fc", "porosity",
             "lambda", "root_depth", "soil_k", "rhc", "cn"],
            widths=[8, 8, 8, 8, 8, 8, 8, 10, 10, 10, 6, 6])

    # Aquifer parameters
    w.write_comment("C  Small Watershed Aquifer Parameters")
    w.write_keyed_value(fmt_num(cfg.get("factgw", 1.0)), "FACTGW")
    w.write_keyed_value(fmt_num(cfg.get("factt", 1.0)), "FACTT")
    w.write_keyed_value(cfg.get("tunitt", "1DAY"), "TUNITT")
    if sw.aquifer_params is not None:
        write_table_rows(
            w, sw.aquifer_params,
            ["id", "gw_threshold_depth", "gw_max_depth",
             "surface_flow_recession", "baseflow_recession"],
            widths=[8, 12, 12, 12, 12])

    # Initial conditions
    w.write_comment("C  Initial Root Zone Moisture and GW Storage")
    w.write_keyed_value(fmt_num(cfg.get("fact_ic", 1.0)), "FACT")
    if sw.initial_conditions is not None:
        write_table_rows(
            w, sw.initial_conditions,
            ["id", "soil_moisture", "gw_storage"],
            widths=[8, 10, 10])

    w.flush()


def write_unsatzone(uz: UnsatZoneFile, path: str | Path) -> None:
    """Write the IWFM unsaturated zone file (e.g. ``UnsatZone.dat``).

    Parameters
    ----------
    uz : UnsatZoneFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(uz.header)

    base_dir = Path(path).parent

    # Main parameters
    w.write_keyed_value(uz.n_unsat_layers, "NUNSAT")
    w.write_keyed_value(fmt_num(uz.convergence), "UZCONV")
    w.write_keyed_value(uz.max_iterations, "UZITERMX")

    # Output file paths
    w.write_keyed_path(uz.file_paths.get("budget"), "UZBUDFL", base_dir=base_dir)
    w.write_keyed_path(uz.file_paths.get("zbudget"), "UZZBUDFL", base_dir=base_dir)
    w.write_keyed_path(uz.file_paths.get("final"), "UZFNFL", base_dir=base_dir)

    cfg = uz.config
    w.write_comment("C  Unsaturated Zone Parameters")
    w.write_keyed_value(uz.ngroup if uz.ngroup is not None else 0, "NGROUP")
    w.write_data_line(
        [fmt_num(cfg.get("fx", 1.0)), fmt_num(cfg.get("fd", 1.0)),
         fmt_num(cfg.get("fk", 1.0))],
        widths=[12, 12, 12])
    w.write_keyed_value(cfg.get("tunitz", "1DAY"), "TUNITZ")

    # Per-element parameter rows: IE + (PD PN PI PK PRHC) per layer,
    # all layers on one line (long-format DataFrame is pivoted back).
    if uz.element_params is not None:
        param_cols = ["thickness", "porosity", "pore_size_index", "k", "rhc"]
        for elem_id, group in uz.element_params.groupby("element_id",
                                                        sort=True):
            group = group.sort_values("layer")
            tokens: list = [int(elem_id)]
            for _, row in group.iterrows():
                tokens.extend(fmt_num(row[c]) for c in param_cols)
            w.write_data_line(
                tokens, widths=[8] + [12] * (len(tokens) - 1))

    # Initial moisture: IE + one value per layer (IE 0 = all elements)
    w.write_comment("C  Initial Moisture Condition")
    if uz.initial_moisture is not None:
        cols = ["element_id"] + [
            c for c in uz.initial_moisture.columns
            if c.startswith("moisture_layer_")]
        write_table_rows(w, uz.initial_moisture, cols,
                         widths=[8] + [12] * (len(cols) - 1))

    w.flush()
