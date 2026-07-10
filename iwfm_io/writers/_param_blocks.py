"""Shared serializers for IWFM writer modules.

Counterparts to ``iwfm_io.readers._param_blocks`` and
``iwfm_io.readers._element_groups``: they regenerate NGROUP-style
parameter sections and element-group tables from the parsed
DataFrames, so writers never depend on stored raw text.
"""

from __future__ import annotations

import pandas as pd

from iwfm_io._writer import IWFMFileWriter


def fmt_num(value) -> str:
    """Format a number the way IWFM list-directed reads expect.

    Integral floats are written without a decimal point; other floats
    use Python's shortest round-tripping representation (Fortran
    accepts ``1e-06`` style exponents).
    """
    if isinstance(value, str):
        return value
    if pd.isna(value):
        return ""
    f = float(value)
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(f)


def write_table_rows(
    w: IWFMFileWriter,
    df: pd.DataFrame,
    columns: list[str],
    widths: list[int] | None = None,
) -> None:
    """Write DataFrame *columns* as whitespace-delimited data rows."""
    if widths is None:
        widths = [12] * len(columns)
    for _, row in df.iterrows():
        w.write_data_line([fmt_num(row[c]) for c in columns], widths)


def write_node_layer_table(
    w: IWFMFileWriter,
    df: pd.DataFrame,
    param_names: list[str],
    leading_names: list[str] | None = None,
) -> None:
    """Write a per-node, per-layer parameter table.

    The long-format *df* (one row per node-layer) is emitted as IWFM
    lays it out: the first layer's row carries the node id (and any
    other leading columns), subsequent layers are continuation rows
    holding only the parameters.
    """
    if leading_names is None:
        leading_names = ["node_id"]
    n_lead = len(leading_names)
    lead_widths = [10] + [16] * (n_lead - 1)
    param_widths = [14] * len(param_names)

    for _, group in df.groupby(leading_names[0], sort=True):
        group = group.sort_values("layer")
        first = True
        for _, row in group.iterrows():
            params = [fmt_num(row[c]) for c in param_names]
            if first:
                lead = [fmt_num(row[c]) for c in leading_names]
                w.write_data_line(lead + params, lead_widths + param_widths)
                first = False
            else:
                # Continuation rows: blank leading fields keep the
                # columns aligned; IWFM only counts tokens.
                pad = " " * sum(lead_widths)
                vals = "".join(
                    p.rjust(wd) for p, wd in zip(params, param_widths))
                w.write_raw(pad + vals)


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
        [fmt_num(factors.get(name, 1.0)) for name in factor_names],
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
        w.write_raw(f"   {grid['node_range']}")
        # IWFM reads the node list with READCH, which keeps consuming
        # data lines until a comment line terminates the list — this
        # comment is load-bearing, not decoration.
        w.write_comment("C  end of node list")
        w.write_keyed_value(grid["ndp"], "NDP")
        w.write_keyed_value(grid["nep"], "NEP")
        elements = grid.get("elements")
        if elements is not None and len(elements) > 0:
            node_cols = [c for c in elements.columns if c != "element_id"]
            write_table_rows(
                w, elements, ["element_id"] + node_cols,
                widths=[10] + [10] * len(node_cols))
        params = grid.get("params")
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
    group's header line; remaining elements follow one per line.
    """
    for group in groups:
        elements = group["elements"]
        fractions = group.get("fractions") or []
        header = [group["group_id"], len(elements)]
        widths = [10, 8]
        if elements:
            header.append(elements[0])
            widths.append(10)
            if with_fractions:
                header.append(fmt_num(fractions[0]))
                widths.append(10)
        else:
            # Zero-element groups still carry a dummy entry in IWFM
            # template files ("4  0  0  0.0"); extra tokens on the line
            # are harmless to Fortran list-directed reads.
            header.append(0)
            widths.append(10)
            if with_fractions:
                header.append("0.0")
                widths.append(10)
        w.write_data_line(header, widths)
        for i, elem in enumerate(elements[1:], start=1):
            cont: list = [elem]
            cwidths = [28]
            if with_fractions:
                cont.append(fmt_num(fractions[i]))
                cwidths.append(10)
            w.write_data_line(cont, cwidths)
