"""
Readers for IWFM preprocessor input files.

All functions return dataclass containers with pandas/geopandas DataFrames.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon

    HAS_GEO = True
except ImportError:
    HAS_GEO = False

from iwfm_io._parser import IWFMFileReader, IWFMParseError
from iwfm_io._strict import strict_mode
from iwfm_io._tokens import tokenize_data_line
from iwfm_io.models.base import ConversionFactor
from iwfm_io.models.preprocessor import (
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

    node_ids, xs, ys = [], [], []
    with reader.section("node table"):
        for i in range(n_nodes):
            try:
                r = reader.read_row(3, "node row")
            except IWFMParseError as exc:
                if reader.eof and "end of file" in exc.msg:
                    raise reader.error(
                        f"node table has only {i} of {n_nodes} declared "
                        "(ND) rows") from None
                raise
            node_ids.append(reader.to_ints(r[:1], "node row")[0])
            x, y = reader.to_floats(r[1:3], "node row")
            xs.append(x)
            ys.append(y)

    df = pd.DataFrame({"node_id": node_ids, "x": xs, "y": ys})

    if HAS_GEO:
        geometry = [Point(x, y) for x, y in zip(xs, ys)]
        df = gpd.GeoDataFrame(df, geometry=geometry)

    return NodeFile(header=header, n_nodes=n_nodes, factor=factor,
                    data=df)


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

    # Read subregion names.  The subregion id is the numeric suffix of
    # the RNAMEn keyword; position is the fallback when absent.
    sub_ids = []
    sub_names = []
    for i in range(n_regions):
        name_str, kw = reader.read_keyed_value()
        m = re.search(r"(\d+)", kw.split()[0]) if kw else None
        sub_ids.append(int(m.group(1)) if m else i + 1)
        sub_names.append(name_str)
    subregions = pd.DataFrame({"subregion_id": sub_ids, "name": sub_names})

    # Read element table: IE  IDE(1) IDE(2) IDE(3) IDE(4) IRGE
    rows = []
    with reader.section("element table"):
        for i in range(n_elements):
            try:
                r = reader.read_row(6, "element row")
            except IWFMParseError as exc:
                if reader.eof and "end of file" in exc.msg:
                    raise reader.error(
                        f"element table has only {i} of {n_elements} "
                        "declared (NE) rows") from None
                raise
            rows.append(reader.to_ints(r[:6], "element row"))
    elem_ids = [r[0] for r in rows]
    n1 = [r[1] for r in rows]
    n2 = [r[2] for r in rows]
    n3 = [r[3] for r in rows]
    n4 = [r[4] for r in rows]
    subs = [r[5] for r in rows]

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

        df = gpd.GeoDataFrame(df, geometry=polygons)

    return ElementFile(header=header, n_elements=n_elements,
                       n_subregions=n_regions, subregions=subregions,
                       data=df)


# ------------------------------------------------------------------
# Stratigraphy
# ------------------------------------------------------------------

def read_strata(path: str | Path,
                n_nodes: int | None = None) -> StratigraphyFile:
    """Read an IWFM stratigraphy file (e.g. ``Strata.dat``).

    The file has no node-count variable of its own — IWFM sizes it by
    ND from the node file.  Pass *n_nodes* to read exactly that many
    rows the way the model does (a shortfall raises); without it the
    table is read to EOF / the first non-numeric line.

    Parameters
    ----------
    path : str or Path
    n_nodes : int, optional
        Expected row count (ND from the node file).

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

    # Read n_nodes rows when the caller supplies the count (matching
    # how the model reads); otherwise read until EOF/non-numeric line.
    data_rows = []
    with reader.section("stratigraphy table"):
        while not reader.eof:
            if n_nodes is not None and len(data_rows) >= n_nodes:
                break
            line = reader.peek_data_line()
            if line is None:
                break
            tokens = tokenize_data_line(line)
            if not tokens or not tokens[0].lstrip("-").isdigit():
                reader.next_data_line()
                reader.degrade(
                    "stratigraphy row: expected a node id but found "
                    f"{line.strip()[:60]!r}; the rest of the file was not "
                    "read")
                break
            reader.next_data_line()
            if len(tokens) < n_cols:
                raise reader.error(
                    f"Stratigraphy row for node {tokens[0]} has "
                    f"{len(tokens)} of {n_cols} expected values")
            row = [int(tokens[0])] + reader.to_floats(
                tokens[1:n_cols], f"stratigraphy row for node {tokens[0]}")
            data_rows.append(row)
        if n_nodes is not None and len(data_rows) != n_nodes:
            raise reader.error(
                f"Stratigraphy table has {len(data_rows)} rows but "
                f"n_nodes={n_nodes} was expected")

    df = pd.DataFrame(data_rows, columns=col_names)
    df["node_id"] = df["node_id"].astype(int)

    return StratigraphyFile(
        header=header,
        n_layers=n_layers,
        n_nodes=len(df),
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
        # Reach header line: IRHID  NRD  IDWN  NAME (name may be
        # multiple words; a trailing "/ comment" is stripped)
        with reader.section("reach table"):
            line = reader.next_data_line()
            # keep the raw name substring — re-joining tokens would
            # collapse internal double spaces, which changes the name
            # IWFM stores in the binary (observed in C2VSimFG reach names)
            body = re.split(r"\s+/", line, maxsplit=1)[0]
            parts = body.split(None, 3)
            if len(parts) < 3:
                raise reader.error(
                    "reach row: expected IRHID NRD IDWN [NAME] but found "
                    f"{line.strip()!r}")
            reach_id, n_nodes_in_reach, outflow_dest = reader.to_ints(
                parts[:3], "reach row")
            name = parts[3].rstrip() if len(parts) > 3 else ""
        reach_data.append({
            "reach_id": reach_id,
            "n_nodes": n_nodes_in_reach,
            "outflow_dest": outflow_dest,
            "name": name,
        })

        # Stream node lines: ISTRMND  IGWND
        with reader.section(f"reach {reach_id} stream nodes"):
            for _ in range(n_nodes_in_reach):
                stream_node_id, gw_node_id = reader.read_ints(
                    2, "stream node row")
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
    with reader.section("rating tables"):
        for _ in range(total_stream_nodes):
            # First line has stream_node_id, bottom_elev, first
            # stage/flow pair
            tokens = reader.read_row(4, "rating table row")
            sn_id = reader.to_ints(tokens[:1], "rating table row")[0]
            bottom_elev, stage, flow = reader.to_floats(
                tokens[1:4], "rating table row")
            rating_rows.append({
                "stream_node_id": sn_id,
                "bottom_elev": bottom_elev,
                "stage": stage,
                "flow": flow,
            })
            # Remaining rating table points
            for _ in range(n_rating_points - 1):
                stage, flow = reader.read_floats(
                    2, f"rating table row for stream node {sn_id}")
                rating_rows.append({
                    "stream_node_id": sn_id,
                    "bottom_elev": bottom_elev,
                    "stage": stage,
                    "flow": flow,
                })

    rating_df = pd.DataFrame(rating_rows)

    # Partial stream-aquifer interaction: NSTRPINT count, then one
    # IDSTR FPINT row per node (fraction of the wetted perimeter that
    # interacts with the aquifer).
    n_partial, _ = reader.read_keyed_int()
    partial_rows = []
    with reader.section("partial interaction table"):
        for _ in range(n_partial):
            tokens = reader.read_row(2, "partial interaction row")
            partial_rows.append({
                "stream_node_id": reader.to_ints(
                    tokens[:1], "partial interaction row")[0],
                "fraction": reader.to_floats(
                    tokens[1:2], "partial interaction row")[0],
            })
    partial_df = pd.DataFrame(partial_rows) if partial_rows else None

    return StreamGeomFile(
        header=header,
        n_reaches=n_reaches,
        n_rating_points=n_rating_points,
        reaches=reaches_df,
        nodes=nodes_df,
        rating_tables=rating_df,
        rating_factors=rating_factors,
        n_partial_interaction=n_partial,
        partial_interaction=partial_df,
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
    with reader.section("lake table"):
        for _ in range(n_lakes):
            # First line: LAKE_ID  TYPDST  DST  NELAKE  IELAKE(1)
            tokens = reader.read_row(4, "lake row")
            lake_id, dest_type, dest_id, n_elements = reader.to_ints(
                tokens[:4], "lake row")
            elements = reader.to_ints(tokens[4:], f"lake {lake_id} elements")

            # Remaining element IDs on continuation lines (one or more
            # element ids per line)
            while len(elements) < n_elements:
                cont_tokens = reader.read_row(1, f"lake {lake_id} elements")
                elements.extend(reader.to_ints(
                    cont_tokens, f"lake {lake_id} elements"))
            if len(elements) > n_elements:
                raise reader.error(
                    f"lake {lake_id} lists {len(elements)} elements but "
                    f"declares NELAKE={n_elements}")

            lake_data.append({
                "lake_id": lake_id,
                "dest_type": dest_type,
                "dest_id": dest_id,
                "n_elements": n_elements,
                "elements": elements,
            })

    df = pd.DataFrame(lake_data)
    return LakeGeomFile(header=header, n_lakes=n_lakes, data=df)


# ------------------------------------------------------------------
# Preprocessor Main
# ------------------------------------------------------------------

def read_preprocessor_main(
    path: str | Path,
    follow_references: bool = True,
    strict: bool | None = None,
) -> PreprocessorMain:
    """Read the preprocessor main input file.

    Parameters
    ----------
    path : str or Path
    follow_references : bool
        If True, also read referenced child files (Element, Node, etc.).
    strict : bool, optional
        Reader mode for this file and its children: ``True`` raises
        :class:`~iwfm_io.IWFMParseError` on malformed input, ``False``
        warns and keeps what parsed.  ``None`` (default) uses the mode
        in effect (see :func:`iwfm_io.strict_mode`; strict by default).

    Returns
    -------
    PreprocessorMain
    """
    if strict is not None:
        with strict_mode(strict):
            return read_preprocessor_main(path, follow_references)
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Title lines: up to 3 non-comment data lines before the file list.
    # A file-list entry is keyed "/ N: DESCRIPTION", so stop early when
    # one appears (decks may carry fewer than 3 titles).
    from iwfm_io._tokens import split_keyed_line
    titles = []
    file_num_re = re.compile(r"^\d+\s*:")
    for _ in range(3):
        line = reader.peek_data_line()
        if line is None:
            break
        _, kw = split_keyed_line(line)
        if kw and file_num_re.match(kw):
            break
        reader.next_data_line()
        titles.append(line.strip())

    # File paths (6 entries)
    path_keys = ["binary_output", "element", "node", "strata", "stream", "lake"]
    file_paths: dict[str, str | None] = {}
    with reader.section("file list"):
        for key in path_keys:
            fp, kw = reader.read_keyed_path(base_dir)
            file_paths[key] = fp

    # Config values
    config: dict = {}
    with reader.section("output control"):
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
            node_child = children.get("node")
            children["strata"] = read_strata(
                file_paths["strata"],
                n_nodes=node_child.n_nodes if node_child else None)
        if file_paths.get("stream"):
            node_child = children.get("node")
            children["stream"] = read_stream_geom(file_paths["stream"], node_file=node_child)
        if file_paths.get("lake"):
            children["lake"] = read_lake_geom(file_paths["lake"])
        result.children = children

    return result
