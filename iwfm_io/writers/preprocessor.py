"""
Writers for IWFM preprocessor input files.

Serialize preprocessor dataclasses back to IWFM text format.
"""

from __future__ import annotations

from pathlib import Path


from iwfm_io._writer import IWFMFileWriter, format_cell, numbered_columns
from iwfm_io.writers._param_blocks import (
    check_count,
    fmt_int,
    fmt_name,
    fmt_num,
    write_titles,
)
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
    w.write_keyed_value(fmt_int(node_file.n_nodes, "NodeXY: ND"), "ND")
    w.write_keyed_value(format_cell(node_file.factor.value, what="NodeXY: FACT"),
                        node_file.factor.keyword or "FACT")

    # Write node table
    for _, row in df.iterrows():
        w.write_data_line(
            [fmt_int(row["node_id"], "node_id"),
             fmt_num(row["x"], what="node x"),
             fmt_num(row["y"], what="node y")],
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
        sid = fmt_int(row["subregion_id"], "subregion_id")
        w.write_keyed_value(fmt_name(row["name"], f"subregion {sid} name"),
                            f"RNAME{sid}")

    # Element table
    for _, row in df.iterrows():
        w.write_data_line(
            [fmt_int(row[c], f"element {c}")
             for c in ("element_id", "node1", "node2", "node3", "node4",
                       "subregion")],
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

    n_layers = int(fmt_int(strata_file.n_layers, "Stratigraphy: NL"))
    w.write_keyed_value(n_layers, "NL")
    w.write_keyed_value(format_cell(strata_file.factor.value,
                                    what="Stratigraphy: FACT"),
                        strata_file.factor.keyword or "FACT")

    df = strata_file.data
    if strata_file.n_nodes:
        check_count(strata_file.n_nodes, len(df),
                    "Stratigraphy: node rows")
    # Layer columns are selected by their numeric suffix and must be
    # exactly 1..NL: a missing layer would write short rows, an extra
    # one would be silently dropped
    try:
        aquitard_cols = numbered_columns(df, "aquitard_", n=n_layers)
        aquifer_cols = numbered_columns(df, "aquifer_", n=n_layers)
    except ValueError as exc:
        raise ValueError(
            f"Stratigraphy: NL={n_layers} but the table's layer columns "
            f"disagree ({exc}) -- update NL or the table") from None
    widths = [8, 12] + [12] * (2 * n_layers)
    for idx, row in df.iterrows():
        tokens = [fmt_int(row["node_id"], f"node_id at row {idx}"),
                  fmt_num(row["elevation"], what=f"elevation at row {idx}")]
        for at, aq in zip(aquitard_cols, aquifer_cols):
            tokens.append(fmt_num(row[at], what=f"{at} at row {idx}"))
            tokens.append(fmt_num(row[aq], what=f"{aq} at row {idx}"))
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
        reach_id = int(fmt_int(reach["reach_id"], "reach_id"))
        reach_nodes = nodes[nodes["reach_id"] == reach_id]
        check_count(reach["n_nodes"], len(reach_nodes),
                    f"Stream geometry: reach {reach_id} NRD")
        w.write_data_line(
            [reach_id,
             fmt_int(reach["n_nodes"], f"reach {reach_id} n_nodes"),
             fmt_int(reach["outflow_dest"], f"reach {reach_id} outflow_dest"),
             fmt_name(reach["name"], f"reach {reach_id} name")],
            widths=[6, 10, 10, 12],
        )
        for _, sn in reach_nodes.iterrows():
            w.write_data_line(
                [fmt_int(sn["stream_node_id"], "stream_node_id"),
                 fmt_int(sn["gw_node_id"], "gw_node_id")],
                widths=[6, 12],
            )

    # Rating table factors
    rf = stream_file.rating_factors
    w.write_keyed_value(rf.get("factlt", 1.0), "FACTLT")
    w.write_keyed_value(rf.get("factq", 1.0), "FACTQ")
    w.write_keyed_value(rf.get("tunit", "1min"), "TUNIT")

    # Rating tables: NRTB rows per stream node, one table per stream
    # node of the reaches (IWFM reads them in that order)
    rt = stream_file.rating_tables
    missing = sorted(set(nodes["stream_node_id"].astype(int))
                     - set(rt["stream_node_id"].astype(int)))
    if missing:
        raise ValueError(
            "Stream geometry: no rating table for stream node(s) "
            f"{missing[:10]} -- IWFM reads NRTB rows for every stream node")
    for sn_id in rt["stream_node_id"].unique():
        sn_rows = rt[rt["stream_node_id"] == sn_id]
        check_count(stream_file.n_rating_points, len(sn_rows),
                    f"Stream geometry: rating table rows for node {sn_id}"
                    " (NRTB)")
        first = True
        for _, row in sn_rows.iterrows():
            what = f"rating table for stream node {sn_id}"
            if first:
                w.write_data_line(
                    [
                        fmt_int(row["stream_node_id"], "stream_node_id"),
                        fmt_num(row["bottom_elev"], what=f"{what} bottom_elev"),
                        fmt_num(row["stage"], what=f"{what} stage"),
                        fmt_num(row["flow"], what=f"{what} flow"),
                    ],
                    widths=[6, 12, 12, 14],
                )
                first = False
            else:
                w.write_data_line(
                    ["", "",
                     fmt_num(row["stage"], what=f"{what} stage"),
                     fmt_num(row["flow"], what=f"{what} flow")],
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
                [fmt_int(row["stream_node_id"], "stream_node_id"),
                 fmt_num(row["fraction"], what="partial interaction fraction")],
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
        lake_id = fmt_int(row["lake_id"], "lake_id")
        check_count(row["n_elements"], len(elements),
                    f"Lake geometry: lake {lake_id} NELAKE")
        # First line: lake_id, dest_type, dest_id, n_elements, first_element
        w.write_data_line(
            [
                lake_id,
                fmt_int(row["dest_type"], f"lake {lake_id} dest_type"),
                fmt_int(row["dest_id"], f"lake {lake_id} dest_id"),
                fmt_int(row["n_elements"], f"lake {lake_id} n_elements"),
                fmt_int(elements[0], f"lake {lake_id} element"),
            ],
            widths=[8, 8, 10, 10, 10],
        )
        # Continuation lines for remaining elements
        for elem in elements[1:]:
            w.write_data_line(
                ["", "", "", "", fmt_int(elem, f"lake {lake_id} element")],
                widths=[8, 8, 10, 10, 10])

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

    # IWFM reads exactly 3 title lines positionally -- pad to 3 so the
    # file list is never shifted (a "." line is a valid title).
    write_titles(w, pp.titles, "Preprocessor main titles")
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
    w.write_keyed_value(fmt_int(cfg.get("kout", 1), "KOUT"), "KOUT")
    w.write_keyed_value(fmt_int(cfg.get("kdeb", 0), "KDEB"), "KDEB")
    w.write_keyed_value(cfg.get("factltou", 1.0), "FACTLTOU")
    w.write_keyed_value(cfg.get("unitltou", "FEET"), "UNITLTOU")
    w.write_keyed_value(cfg.get("factarou", 1.0), "FACTAROU")
    w.write_keyed_value(cfg.get("unitarou", "ACRES"), "UNITAROU")

    w.flush()
