"""
Writers for IWFM preprocessor input files.

Serialize preprocessor dataclasses back to IWFM text format.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm.io._writer import IWFMFileWriter
from iwfm.io.models.preprocessor import (
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
    n_nodes = len(df)
    w.write_keyed_value(n_nodes, f"{node_file.factor.keyword or 'ND'}")
    w.write_keyed_value(node_file.factor.value, node_file.factor.keyword or "FACT")

    # Write node table
    for _, row in df.iterrows():
        w.write_data_line(
            [int(row["node_id"]), f"{row['x']:.1f}", f"{row['y']:.1f}"],
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
    n_elements = len(df)
    n_regions = len(elem_file.subregions)
    w.write_keyed_value(n_elements, "NE")
    w.write_keyed_value(n_regions, "NREGN")

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
    for _, row in df.iterrows():
        tokens = [int(row["node_id"]), f"{row['elevation']:.1f}"]
        for i in range(1, strata_file.n_layers + 1):
            tokens.append(f"{row[f'aquitard_{i}']:.1f}")
            tokens.append(f"{row[f'aquifer_{i}']:.1f}")
        widths = [8, 10] + [10] * (2 * strata_file.n_layers)
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
    n_reaches = len(reaches)
    w.write_keyed_value(n_reaches, "NRH")
    w.write_keyed_value(stream_file.n_rating_points, "NRTB")

    # Reaches and their nodes
    for _, reach in reaches.iterrows():
        reach_id = int(reach["reach_id"])
        w.write_data_line(
            [reach_id, int(reach["n_nodes"]), int(reach["outflow_dest"]), reach["name"]],
            widths=[6, 10, 10, 12],
        )
        reach_nodes = nodes[nodes["reach_id"] == reach_id]
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

    # Rating tables
    rt = stream_file.rating_tables
    for sn_id in rt["stream_node_id"].unique():
        sn_rows = rt[rt["stream_node_id"] == sn_id]
        first = True
        for _, row in sn_rows.iterrows():
            if first:
                w.write_data_line(
                    [
                        int(row["stream_node_id"]),
                        f"{row['bottom_elev']:.1f}",
                        f"{row['stage']:.1f}",
                        f"{row['flow']:.2f}",
                    ],
                    widths=[6, 12, 12, 12],
                )
                first = False
            else:
                w.write_data_line(
                    ["", "", f"{row['stage']:.1f}", f"{row['flow']:.2f}"],
                    widths=[6, 12, 12, 12],
                )

    # Partial interaction
    w.write_keyed_value(stream_file.n_partial_interaction, "NSTRPINT")

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
    w.write_keyed_value(len(df), "NLAKE")

    for _, row in df.iterrows():
        elements = row["elements"]
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

    for title in pp.titles:
        w.write_raw(f"    {title}")

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

    cfg = pp.config
    w.write_keyed_value(cfg.get("kout", 1), "KOUT")
    w.write_keyed_value(cfg.get("kdeb", 0), "KDEB")
    w.write_keyed_value(cfg.get("factltou", 1.0), "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "FEET"), "UNITLTOU")
    w.write_keyed_value(cfg.get("factarou", 1.0), "FACTAROU")
    w.write_keyed_value(cfg.get("unitarou", "ACRES"), "UNITAROU")

    w.flush()
