"""
Readers for IWFM preprocessor input files.

All functions return dataclass containers with pandas/geopandas DataFrames.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon

    HAS_GEO = True
except ImportError:
    HAS_GEO = False

from iwfm.io._parser import IWFMFileReader
from iwfm.io._tokens import tokenize_data_line
from iwfm.io.models.base import ConversionFactor, FileHeader
from iwfm.io.models.preprocessor import (
    ElementFile,
    LakeGeomFile,
    NodeFile,
    PreprocessorMain,
    StratigraphyFile,
    StreamGeomFile,
)


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------

def read_nodes(path: str | Path) -> NodeFile:
    """Read an IWFM node coordinate file (e.g. ``NodeXY.dat``).

    Parameters
    ----------
    path : str or Path
        Path to the node file.

    Returns
    -------
    NodeFile
        Contains a GeoDataFrame with columns ``node_id``, ``x``, ``y``
        and ``Point`` geometry (if geopandas is available).
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_nodes, _ = reader.read_keyed_int()
    factor_val, kw = reader.read_keyed_float()
    factor = ConversionFactor(value=factor_val, keyword=kw)

    rows = reader.read_data_table(n_nodes, n_cols=3)
    node_ids = [int(r[0]) for r in rows]
    xs = [float(r[1]) for r in rows]
    ys = [float(r[2]) for r in rows]

    df = pd.DataFrame({"node_id": node_ids, "x": xs, "y": ys})

    if HAS_GEO:
        geometry = [Point(x, y) for x, y in zip(xs, ys)]
        gdf = gpd.GeoDataFrame(df, geometry=geometry)
        return NodeFile(header=header, factor=factor, data=gdf)

    return NodeFile(header=header, factor=factor, data=df)


# ------------------------------------------------------------------
# Elements
# ------------------------------------------------------------------

def read_elements(path: str | Path, node_file: NodeFile | None = None) -> ElementFile:
    """Read an IWFM element configuration file (e.g. ``Element.dat``).

    Parameters
    ----------
    path : str or Path
    node_file : NodeFile, optional
        If provided and geopandas is available, polygon geometries
        are built from node coordinates.

    Returns
    -------
    ElementFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_elements, _ = reader.read_keyed_int()
    n_regions, _ = reader.read_keyed_int()

    # Read subregion names
    sub_ids = []
    sub_names = []
    for i in range(n_regions):
        name_str, kw = reader.read_keyed_value()
        sub_ids.append(i + 1)
        sub_names.append(name_str)
    subregions = pd.DataFrame({"subregion_id": sub_ids, "name": sub_names})

    # Read element table: IE  IDE(1) IDE(2) IDE(3) IDE(4) IRGE
    rows = reader.read_data_table(n_elements, n_cols=6)
    elem_ids = [int(r[0]) for r in rows]
    n1 = [int(r[1]) for r in rows]
    n2 = [int(r[2]) for r in rows]
    n3 = [int(r[3]) for r in rows]
    n4 = [int(r[4]) for r in rows]
    subs = [int(r[5]) for r in rows]

    df = pd.DataFrame({
        "element_id": elem_ids,
        "node1": n1,
        "node2": n2,
        "node3": n3,
        "node4": n4,
        "subregion": subs,
    })

    # Build polygon geometry if node coordinates available
    if HAS_GEO and node_file is not None and node_file.data is not None:
        node_df = node_file.data
        coord_lookup = {}
        for _, row in node_df.iterrows():
            coord_lookup[int(row["node_id"])] = (float(row["x"]), float(row["y"]))

        polygons = []
        for _, row in df.iterrows():
            nodes = [row["node1"], row["node2"], row["node3"]]
            if row["node4"] != 0:
                nodes.append(row["node4"])
            coords = [coord_lookup[n] for n in nodes]
            coords.append(coords[0])  # close the polygon
            polygons.append(Polygon(coords))

        gdf = gpd.GeoDataFrame(df, geometry=polygons)
        return ElementFile(header=header, subregions=subregions, data=gdf)

    return ElementFile(header=header, subregions=subregions, data=df)


# ------------------------------------------------------------------
# Stratigraphy
# ------------------------------------------------------------------

def read_strata(path: str | Path) -> StratigraphyFile:
    """Read an IWFM stratigraphy file (e.g. ``Strata.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    StratigraphyFile
        DataFrame columns: ``node_id``, ``elevation``,
        ``aquitard_1``, ``aquifer_1``, ..., ``aquitard_N``, ``aquifer_N``.
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_layers, _ = reader.read_keyed_int()
    factor_val, kw = reader.read_keyed_float()
    factor = ConversionFactor(value=factor_val, keyword=kw)

    # Columns: node_id, elevation, then 2 per layer (aquitard, aquifer)
    n_cols = 2 + 2 * n_layers

    # Build column names
    col_names = ["node_id", "elevation"]
    for i in range(1, n_layers + 1):
        col_names.append(f"aquitard_{i}")
        col_names.append(f"aquifer_{i}")

    # Read until we run out of data lines (node count = n_nodes from node file)
    # We don't know n_nodes here, so read until EOF or non-numeric line
    data_rows = []
    while not reader.eof:
        line = reader.peek_data_line()
        if line is None:
            break
        tokens = tokenize_data_line(line)
        if not tokens or not tokens[0].lstrip("-").isdigit():
            break
        reader.next_data_line()
        row = [int(tokens[0])] + [float(t) for t in tokens[1:n_cols]]
        data_rows.append(row)

    df = pd.DataFrame(data_rows, columns=col_names)
    df["node_id"] = df["node_id"].astype(int)

    return StratigraphyFile(
        header=header,
        n_layers=n_layers,
        factor=factor,
        data=df,
    )


# ------------------------------------------------------------------
# Stream Geometry
# ------------------------------------------------------------------

def read_stream_geom(path: str | Path, node_file: NodeFile | None = None) -> StreamGeomFile:
    """Read an IWFM stream geometry file (e.g. ``Stream.dat``).

    Parameters
    ----------
    path : str or Path
    node_file : NodeFile, optional
        If provided, stream nodes get Point geometry from GW node coords.

    Returns
    -------
    StreamGeomFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_reaches, _ = reader.read_keyed_int()
    n_rating_points, _ = reader.read_keyed_int()

    # Parse reaches and their stream nodes
    reach_data = []  # (reach_id, n_nodes, outflow_dest, name)
    stream_nodes = []  # (stream_node_id, reach_id, gw_node_id)

    for _ in range(n_reaches):
        # Reach header line: IRHID  NRD  IDWN  NAME
        line = reader.next_data_line()
        tokens = line.split()
        reach_id = int(tokens[0])
        n_nodes_in_reach = int(tokens[1])
        outflow_dest = int(tokens[2])
        name = tokens[3] if len(tokens) > 3 else ""
        reach_data.append({
            "reach_id": reach_id,
            "n_nodes": n_nodes_in_reach,
            "outflow_dest": outflow_dest,
            "name": name,
        })

        # Stream node lines: ISTRMND  IGWND
        for _ in range(n_nodes_in_reach):
            node_line = reader.next_data_line()
            node_tokens = node_line.split()
            stream_node_id = int(node_tokens[0])
            gw_node_id = int(node_tokens[1])
            stream_nodes.append({
                "stream_node_id": stream_node_id,
                "reach_id": reach_id,
                "gw_node_id": gw_node_id,
            })

    reaches_df = pd.DataFrame(reach_data)
    nodes_df = pd.DataFrame(stream_nodes)

    # Add geometry from GW node coordinates if available
    if HAS_GEO and node_file is not None and node_file.data is not None:
        ndf = node_file.data
        coord_lookup = {}
        for _, row in ndf.iterrows():
            coord_lookup[int(row["node_id"])] = (float(row["x"]), float(row["y"]))

        geometry = []
        for _, row in nodes_df.iterrows():
            gw_id = int(row["gw_node_id"])
            if gw_id in coord_lookup:
                geometry.append(Point(*coord_lookup[gw_id]))
            else:
                geometry.append(None)
        nodes_df = gpd.GeoDataFrame(nodes_df, geometry=geometry)

    # Rating table factors
    factlt, _ = reader.read_keyed_float()
    factq, _ = reader.read_keyed_float()
    tunit, _ = reader.read_keyed_value()
    rating_factors = {"factlt": factlt, "factq": factq, "tunit": tunit}

    # Rating tables: for each stream node
    # First line: ISTRMND  BOTR  HRTB(1) QRTB(1)
    # Then (NRTB-1) continuation lines: HRTB QRTB
    total_stream_nodes = len(stream_nodes)
    rating_rows = []
    for _ in range(total_stream_nodes):
        # First line has stream_node_id, bottom_elev, first stage/flow pair
        line = reader.next_data_line()
        tokens = line.split()
        sn_id = int(tokens[0])
        bottom_elev = float(tokens[1])
        stage = float(tokens[2])
        flow = float(tokens[3])
        rating_rows.append({
            "stream_node_id": sn_id,
            "bottom_elev": bottom_elev,
            "stage": stage,
            "flow": flow,
        })
        # Remaining rating table points
        for _ in range(n_rating_points - 1):
            cont_line = reader.next_data_line()
            cont_tokens = cont_line.split()
            rating_rows.append({
                "stream_node_id": sn_id,
                "bottom_elev": bottom_elev,
                "stage": float(cont_tokens[0]),
                "flow": float(cont_tokens[1]),
            })

    rating_df = pd.DataFrame(rating_rows)

    # Partial interaction nodes
    n_partial, _ = reader.read_keyed_int()

    return StreamGeomFile(
        header=header,
        n_rating_points=n_rating_points,
        reaches=reaches_df,
        nodes=nodes_df,
        rating_tables=rating_df,
        rating_factors=rating_factors,
        n_partial_interaction=n_partial,
    )


# ------------------------------------------------------------------
# Lake Geometry
# ------------------------------------------------------------------

def read_lake_geom(path: str | Path) -> LakeGeomFile:
    """Read an IWFM lake geometry file (e.g. ``Lake.dat``).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    LakeGeomFile
        Data contains one row per lake with columns: lake_id, dest_type,
        dest_id, n_elements, elements (list of int).
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    n_lakes, _ = reader.read_keyed_int()

    lake_data = []
    for _ in range(n_lakes):
        # First line: LAKE_ID  TYPDST  DST  NELAKE  IELAKE(1)
        line = reader.next_data_line()
        tokens = line.split()
        lake_id = int(tokens[0])
        dest_type = int(tokens[1])
        dest_id = int(tokens[2])
        n_elements = int(tokens[3])
        elements = [int(tokens[4])]

        # Remaining element IDs on continuation lines
        for _ in range(n_elements - 1):
            cont_line = reader.next_data_line()
            elements.append(int(cont_line.strip()))

        lake_data.append({
            "lake_id": lake_id,
            "dest_type": dest_type,
            "dest_id": dest_id,
            "n_elements": n_elements,
            "elements": elements,
        })

    df = pd.DataFrame(lake_data)
    return LakeGeomFile(header=header, data=df)


# ------------------------------------------------------------------
# Preprocessor Main
# ------------------------------------------------------------------

def read_preprocessor_main(
    path: str | Path,
    follow_references: bool = True,
) -> PreprocessorMain:
    """Read the preprocessor main input file.

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        If True, also read referenced child files (Element, Node, etc.).

    Returns
    -------
    PreprocessorMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Read 3 title lines (non-comment data lines before file paths)
    titles = []
    for _ in range(3):
        line = reader.next_data_line()
        titles.append(line.strip())

    # File paths (6 entries)
    path_keys = ["binary_output", "element", "node", "strata", "stream", "lake"]
    file_paths: dict[str, str | None] = {}
    for key in path_keys:
        fp, kw = reader.read_keyed_path(base_dir)
        file_paths[key] = fp

    # Config values
    config: dict = {}
    kout, _ = reader.read_keyed_int()
    config["kout"] = kout
    kdeb, _ = reader.read_keyed_int()
    config["kdeb"] = kdeb
    factltou, _ = reader.read_keyed_float()
    config["factltou"] = factltou
    unitltou, _ = reader.read_keyed_value()
    config["unitltou"] = unitltou
    factarou, _ = reader.read_keyed_float()
    config["factarou"] = factarou
    unitarou, _ = reader.read_keyed_value()
    config["unitarou"] = unitarou

    result = PreprocessorMain(
        header=header,
        titles=titles,
        file_paths=file_paths,
        config=config,
    )

    # Follow references
    if follow_references:
        children: dict = {}
        if file_paths.get("node"):
            children["node"] = read_nodes(file_paths["node"])
        if file_paths.get("element"):
            node_child = children.get("node")
            children["element"] = read_elements(file_paths["element"], node_file=node_child)
        if file_paths.get("strata"):
            children["strata"] = read_strata(file_paths["strata"])
        if file_paths.get("stream"):
            node_child = children.get("node")
            children["stream"] = read_stream_geom(file_paths["stream"], node_file=node_child)
        if file_paths.get("lake"):
            children["lake"] = read_lake_geom(file_paths["lake"])
        result.children = children

    return result
