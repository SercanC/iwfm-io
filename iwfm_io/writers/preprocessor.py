"""
Writers for IWFM preprocessor input files.

Serialize preprocessor dataclasses back to IWFM text format.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.writers._param_blocks import check_count, fmt_num
from iwfm_io.models.preprocessor import (
    ElementFile,
    LakeGeomFile,
    NodeFile,
    PreprocessorMain,
    StratigraphyFile,
    StreamGeomFile,
)


def write_nodes(node_file: NodeFile, path: str | Path) -> None:
    """Write an IWFM node coordinate file.

    Parameters
    ----------
    node_file : NodeFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(node_file.header)

    df = node_file.data
    check_count(node_file.n_nodes, len(df), "NodeXY: ND")
    w.write_keyed_value(node_file.n_nodes, "ND")
    w.write_keyed_value(node_file.factor.value, node_file.factor.keyword or "FACT")

    # Write node table
    for _, row in df.iterrows():
        w.write_data_line(
            [int(row["node_id"]), fmt_num(row["x"]), fmt_num(row["y"])],
            widths=[7, 16, 16],
        )

    w.flush()


def write_elements(elem_file: ElementFile, path: str | Path) -> None:
    """Write an IWFM element configuration file.

    Parameters
    ----------
    elem_file : ElementFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(elem_file.header)

    df = elem_file.data
    check_count(elem_file.n_elements, len(df), "Element: NE")
    check_count(elem_file.n_subregions, len(elem_file.subregions),
                "Element: NREGN")
    w.write_keyed_value(elem_file.n_elements, "NE")
    w.write_keyed_value(elem_file.n_subregions, "NREGN")

    # Subregion names
    for _, row in elem_file.subregions.iterrows():
        w.write_keyed_value(row["name"], f"RNAME{int(row['subregion_id'])}")

    # Element table
    for _, row in df.iterrows():
        w.write_data_line(
            [
                int(row["element_id"]),
                int(row["node1"]),
                int(row["node2"]),
                int(row["node3"]),
                int(row["node4"]),
                int(row["subregion"]),
            ],
            widths=[6, 12, 12, 12, 12, 12],
        )

    w.flush()


def write_strata(strata_file: StratigraphyFile, path: str | Path) -> None:
    """Write an IWFM stratigraphy file.

    Parameters
    ----------
    strata_file : StratigraphyFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(strata_file.header)

    w.write_keyed_value(strata_file.n_layers, "NL")
    w.write_keyed_value(strata_file.factor.value, strata_file.factor.keyword or "FACT")

    df = strata_file.data
    if strata_file.n_nodes:
        check_count(strata_file.n_nodes, len(df),
                    "Stratigraphy: node rows")
    for i in range(1, strata_file.n_layers + 1):
        if f"aquitard_{i}" not in df.columns or f"aquifer_{i}" not in df.columns:
            raise ValueError(
                f"Stratigraphy: NL={strata_file.n_layers} but layer {i} "
                "columns are missing from the table")
    for _, row in df.iterrows():
        tokens = [int(row["node_id"]), fmt_num(row["elevation"])]
        for i in range(1, strata_file.n_layers + 1):
            tokens.append(fmt_num(row[f"aquitard_{i}"]))
            tokens.append(fmt_num(row[f"aquifer_{i}"]))
        widths = [8, 12] + [12] * (2 * strata_file.n_layers)
        w.write_data_line(tokens, widths)

    w.flush()


def write_stream_geom(stream_file: StreamGeomFile, path: str | Path) -> None:
    """Write an IWFM stream geometry file.

    Parameters
    ----------
    stream_file : StreamGeomFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(stream_file.header)

    reaches = stream_file.reaches
    nodes = stream_file.nodes
    check_count(stream_file.n_reaches, len(reaches), "Stream geometry: NRH")
    w.write_keyed_value(stream_file.n_reaches, "NRH")
    w.write_keyed_value(stream_file.n_rating_points, "NRTB")

    # Reaches and their nodes
    for _, reach in reaches.iterrows():
        reach_id = int(reach["reach_id"])
        reach_nodes = nodes[nodes["reach_id"] == reach_id]
        check_count(reach["n_nodes"], len(reach_nodes),
                    f"Stream geometry: reach {reach_id} NRD")
        w.write_data_line(
            [reach_id, int(reach["n_nodes"]), int(reach["outflow_dest"]), reach["name"]],
            widths=[6, 10, 10, 12],
        )
        for _, sn in reach_nodes.iterrows():
            w.write_data_line(
                [int(sn["stream_node_id"]), int(sn["gw_node_id"])],
                widths=[6, 12],
            )

    # Rating table factors
    rf = stream_file.rating_factors
    w.write_keyed_value(rf.get("factlt", 1.0), "FACTLT")
    w.write_keyed_value(rf.get("factq", 1.0), "FACTQ")
    w.write_keyed_value(rf.get("tunit", "1min"), "TUNIT")

    # Rating tables: NRTB rows per stream node, validated
    rt = stream_file.rating_tables
    for sn_id in rt["stream_node_id"].unique():
        sn_rows = rt[rt["stream_node_id"] == sn_id]
        check_count(stream_file.n_rating_points, len(sn_rows),
                    f"Stream geometry: rating table rows for node {sn_id}"
                    " (NRTB)")
        first = True
        for _, row in sn_rows.iterrows():
            if first:
                w.write_data_line(
                    [
                        int(row["stream_node_id"]),
                        fmt_num(row["bottom_elev"]),
                        fmt_num(row["stage"]),
                        fmt_num(row["flow"]),
                    ],
                    widths=[6, 12, 12, 14],
                )
                first = False
            else:
                w.write_data_line(
                    ["", "", fmt_num(row["stage"]), fmt_num(row["flow"])],
                    widths=[6, 12, 12, 14],
                )

    # Partial stream-aquifer interaction (IDSTR FPINT rows)
    n_pint = (0 if stream_file.partial_interaction is None
              else len(stream_file.partial_interaction))
    check_count(stream_file.n_partial_interaction, n_pint,
                "Stream geometry: NSTRPINT")
    w.write_keyed_value(stream_file.n_partial_interaction, "NSTRPINT")
    if stream_file.partial_interaction is not None:
        for _, row in stream_file.partial_interaction.iterrows():
            w.write_data_line(
                [int(row["stream_node_id"]), fmt_num(row["fraction"])],
                widths=[8, 12])

    w.flush()


def write_lake_geom(lake_file: LakeGeomFile, path: str | Path) -> None:
    """Write an IWFM lake geometry file.

    Parameters
    ----------
    lake_file : LakeGeomFile
    path : str or Path
    """
    w = IWFMFileWriter(path)
    w.write_header(lake_file.header)

    df = lake_file.data
    check_count(lake_file.n_lakes, len(df), "Lake geometry: NLAKE")
    w.write_keyed_value(lake_file.n_lakes, "NLAKE")

    for _, row in df.iterrows():
        elements = row["elements"]
        check_count(row["n_elements"], len(elements),
                    f"Lake geometry: lake {int(row['lake_id'])} NELAKE")
        # First line: lake_id, dest_type, dest_id, n_elements, first_element
        w.write_data_line(
            [
                int(row["lake_id"]),
                int(row["dest_type"]),
                int(row["dest_id"]),
                int(row["n_elements"]),
                int(elements[0]),
            ],
            widths=[8, 8, 10, 10, 10],
        )
        # Continuation lines for remaining elements
        for elem in elements[1:]:
            w.write_data_line(["", "", "", "", int(elem)], widths=[8, 8, 10, 10, 10])

    w.flush()


def write_preprocessor_main(
    pp: PreprocessorMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the preprocessor main input file.

    Parameters
    ----------
    pp : PreprocessorMain
    path : str or Path
    base_dir : str or Path, optional
        Base directory for relativising file paths.
    """
    w = IWFMFileWriter(path)
    w.write_header(pp.header)

    # IWFM reads exactly 3 title lines positionally — pad to 3 so the
    # file list is never shifted (a "." line is a valid title).
    titles = (list(pp.titles) + [".", ".", "."])[:3]
    for title in titles:
        w.write_raw(f"    {title}")
    w.write_comment("C  end of titles")

    path_keys = ["binary_output", "element", "node", "strata", "stream", "lake"]
    labels = [
        "1: BINARY OUTPUT FOR SIMULATION",
        "2: ELEMENT CONFIGURATION FILE",
        "3: NODE X-Y COORDINATE FILE",
        "4: STRATIGRAPHIC DATA FILE",
        "5: STREAM GEOMETRIC DATA FILE",
        "6: LAKE DATA FILE",
    ]
    for key, label in zip(path_keys, labels):
        w.write_keyed_path(pp.file_paths.get(key), label, base_dir=base_dir)
    w.write_comment("C  end of file list")

    cfg = pp.config
    w.write_keyed_value(cfg.get("kout", 1), "KOUT")
    w.write_keyed_value(cfg.get("kdeb", 0), "KDEB")
    w.write_keyed_value(cfg.get("factltou", 1.0), "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "FEET"), "UNITLTOU")
    w.write_keyed_value(cfg.get("factarou", 1.0), "FACTAROU")
    w.write_keyed_value(cfg.get("unitarou", "ACRES"), "UNITAROU")

    w.flush()
