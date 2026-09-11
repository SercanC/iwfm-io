"""Shared serializers for IWFM writer modules.

Counterparts to ``iwfm_io.readers._param_blocks`` and
``iwfm_io.readers._element_groups``: they regenerate NGROUP-style
parameter sections and element-group tables from the parsed
DataFrames, so writers never depend on stored raw text.
"""

from __future__ import annotations

import pandas as pd

from iwfm_io._writer import IWFMFileWriter, format_cell


def check_count(declared: int, actual: int, what: str) -> None:
    """Raise if a declared dimension disagrees with the table it sizes.

    IWFM reads tables BY their declared count, so writers emit the
    stored count and refuse to write an inconsistent file -- a mismatch
    means either the count or the table was edited without the other.
    """
    if int(declared) != int(actual):
        raise ValueError(
            f"{what}: the file declares {declared} but the parsed data "
            f"has {actual} rows/entries -- update the count field or the "
            "table so they agree")


#: ``fmt_num`` is the historical name of the cell formatter; it is
#: :func:`iwfm_io._writer.format_cell` (NaN raises -- it no longer
#: returns ``""``).
fmt_num = format_cell


def fmt_int(value, what: str = "") -> str:
    """Format an ID / count / flag cell (non-integral values raise)."""
    return format_cell(value, what=what, integer=True)


def fmt_name(value, what: str = "name") -> str:
    """Format an optional name cell: missing values become ``""``.

    A ``/`` inside the name raises: IWFM (and the readers) treat the
    first ``/`` as the start of the trailing comment, so
    ``"North / South"`` would be read back as ``"North"``.
    """
    text = format_cell(value, what=what, allow_blank=True)
    if "/" in text:
        raise ValueError(
            f"{what}: {text!r} contains '/', which IWFM reads as the start "
            "of a comment -- the name would be truncated on read")
    return text


def write_titles(w: IWFMFileWriter, titles, what: str = "titles") -> None:
    """Write the three positional title lines of a main file.

    IWFM reads exactly 3 title lines positionally (fewer shifts the
    file list that follows), so the block is padded to 3 with ``"."``.
    More than 3 titles, ``None``, or a line break inside a title raise.
    An empty title is written as ``"."`` too -- a blank line would be
    skipped by IWFM and shift the file list.
    """
    if titles is None:
        raise ValueError(f"{what}: titles is None (pass a list of up to "
                         "3 strings)")
    titles = list(titles)
    if len(titles) > 3:
        raise ValueError(
            f"{what}: {len(titles)} titles given but IWFM reads exactly 3")
    for t in titles:
        if t is None:
            raise ValueError(f"{what}: a title is None")
        if not isinstance(t, str):
            raise TypeError(f"{what}: title {t!r} is not a string")
    padded = [t if t.strip() else "." for t in titles]
    padded += ["."] * (3 - len(padded))
    for t in padded:
        w.write_raw(f"    {t}")


def write_table_rows(
    w: IWFMFileWriter,
    df: pd.DataFrame,
    columns: list[str],
    widths: list[int] | None = None,
) -> None:
    """Write DataFrame *columns* as whitespace-delimited data rows.

    Raises on missing cells: a blank token would silently shift every
    later column in IWFM's list-directed read.
    """
    if widths is None:
        widths = [12] * len(columns)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"table is missing column(s) {missing}")
    for idx, row in df.iterrows():
        cells = [format_cell(row[c], what=f"column {c!r} at row {idx}")
                 for c in columns]
        w.write_data_line(cells, widths)   # numeric-with-comma check lives there


def check_layers_complete(
    df: pd.DataFrame,
    id_col: str,
    n_layers: int | None = None,
    what: str = "",
    layer_col: str = "layer",
) -> int:
    """Assert every id has layers ``1..NL`` exactly once; return NL.

    IWFM reads NL rows per node/element, so a missing or duplicated
    layer row shifts the whole table. *n_layers* defaults to the
    largest layer in the table.
    """
    label = what or "per-layer table"
    if df[layer_col].isna().any():
        raise ValueError(f"{label}: NaN in column {layer_col!r}")
    layers = pd.to_numeric(df[layer_col])
    if not (layers % 1 == 0).all():
        raise ValueError(f"{label}: non-integral layer numbers")
    layers = layers.astype(int)
    nl = int(n_layers) if n_layers is not None else int(layers.max())
    g = layers.groupby(df[id_col])
    stats = g.agg(["size", "nunique", "min", "max"])
    bad = stats[(stats["size"] != nl) | (stats["nunique"] != nl)
                | (stats["min"] != 1) | (stats["max"] != nl)]
    if len(bad):
        ident = bad.index[0]
        have = sorted(layers[df[id_col] == ident].tolist())
        raise ValueError(
            f"{label}: {id_col} {ident} has layers {have}, expected "
            f"1..{nl} exactly once (IWFM reads {nl} rows per id)")
    return nl


def write_node_layer_table(
    w: IWFMFileWriter,
    df: pd.DataFrame,
    param_names: list[str],
    leading_names: list[str] | None = None,
    n_layers: int | None = None,
) -> None:
    """Write a per-node, per-layer parameter table.

    The long-format *df* (one row per node-layer) is emitted as IWFM
    lays it out: the first layer's row carries the node id (and any
    other leading columns), subsequent layers are continuation rows
    holding only the parameters. Every node must have layers
    ``1..NL`` exactly once.
    """
    if leading_names is None:
        leading_names = ["node_id"]
    n_lead = len(leading_names)
    lead_widths = [10] + [16] * (n_lead - 1)
    param_widths = [14] * len(param_names)
    if len(df) == 0:
        return
    check_layers_complete(df, leading_names[0], n_layers,
                          what="node-layer parameter table")

    for _, group in df.groupby(leading_names[0], sort=True):
        group = group.sort_values("layer")
        first = True
        for _, row in group.iterrows():
            params = [format_cell(row[c], what=f"column {c!r}")
                      for c in param_names]
            if first:
                lead = [format_cell(row[c], what=f"column {c!r}",
                                    integer=(c == leading_names[0]))
                        for c in leading_names]
                w.write_data_line(lead + params, lead_widths + param_widths)
                first = False
            else:
                # Continuation rows: blank leading fields keep the
                # columns aligned; IWFM only counts tokens.
                w.write_data_line([""] * n_lead + params,
                                  lead_widths + param_widths)


def write_param_block(
    w: IWFMFileWriter,
    ngroup: int,
    factors: dict,
    factor_names: list[str],
    param_names: list[str],
    node_params: pd.DataFrame | None,
    parametric_grids: list[dict],
    time_units: dict | None = None,
) -> None:
    """Write a full NGROUP-style parameter section (GW/subsidence).

    Mirrors :func:`iwfm_io.readers._param_blocks.parse_param_block`.
    """
    w.write_keyed_value(ngroup, "NGROUP")

    w.write_data_line(
        [format_cell(factors.get(name, 1.0), what=name)
         for name in factor_names],
        widths=[12] * len(factor_names),
    )

    for keyword, value in (time_units or {}).items():
        w.write_keyed_value(value, keyword)

    if ngroup == 0:
        if node_params is None:
            raise ValueError(
                "NGROUP=0 but no parsed per-node parameter table is "
                "available to write")
        write_node_layer_table(w, node_params, param_names)
        return

    if len(parametric_grids) < ngroup:
        raise ValueError(
            f"NGROUP={ngroup} but only {len(parametric_grids)} parsed "
            "parametric grid groups are available to write")
    for grid in parametric_grids[:ngroup]:
        elements = grid.get("elements")
        params = grid.get("params")
        check_count(grid["nep"],
                    0 if elements is None else len(elements),
                    "parametric grid: NEP")
        if params is not None and len(params) > 0:
            check_count(grid["ndp"], params["node_id"].nunique(),
                        "parametric grid: NDP")
        w.write_data_line([format_cell(grid["node_range"],
                                       what="parametric grid node range")],
                          widths=[len(str(grid["node_range"])) + 3])
        # IWFM reads the node list with READCH, which keeps consuming
        # data lines until a comment line terminates the list -- this
        # comment is load-bearing, not decoration.
        w.write_comment("C  end of node list")
        w.write_keyed_value(grid["ndp"], "NDP")
        w.write_keyed_value(grid["nep"], "NEP")
        if elements is not None and len(elements) > 0:
            node_cols = [c for c in elements.columns if c != "element_id"]
            write_table_rows(
                w, elements, ["element_id"] + node_cols,
                widths=[10] + [10] * len(node_cols))
        if params is not None and len(params) > 0:
            write_node_layer_table(
                w, params, param_names,
                leading_names=["node_id", "x", "y"])


def write_element_groups(
    w: IWFMFileWriter,
    groups: list[dict],
    with_fractions: bool = False,
) -> None:
    """Write element-group tables (``ID NELEM ELEM [FRAC] ...``).

    Mirrors :func:`iwfm_io.readers._element_groups.parse_element_groups`:
    the first element (and its fraction, for recharge zones) shares the
    group's header line; remaining elements follow one per line.  A
    group's ``name`` is re-emitted as a ``/ name`` annotation on its
    header line.
    """
    for group in groups:
        elements = group["elements"]
        fractions = group.get("fractions") or []
        header = [fmt_int(group["group_id"], "element group id"),
                  fmt_int(len(elements), "element group size")]
        widths = [10, 8]
        if elements:
            header.append(fmt_int(elements[0], "element id"))
            widths.append(10)
            if with_fractions:
                header.append(format_cell(fractions[0], what="fraction"))
                widths.append(10)
        else:
            # Zero-element groups still carry a dummy entry in IWFM
            # template files ("4  0  0  0.0"); extra tokens on the line
            # are harmless to Fortran list-directed reads.
            header.append("0")
            widths.append(10)
            if with_fractions:
                header.append("0.0")
                widths.append(10)
        w.write_data_line(header, widths, note=group.get("name") or "")
        for i, elem in enumerate(elements[1:], start=1):
            cont: list = [fmt_int(elem, "element id")]
            cwidths = [28]
            if with_fractions:
                cont.append(format_cell(fractions[i], what="fraction"))
                cwidths.append(10)
            w.write_data_line(cont, cwidths)
