"""Shared parser for IWFM NGROUP-style parameter sections.

The groundwater main and subsidence files both carry a parameter section
with the same shape::

    NGROUP                          (keyed int)
    FX  F1  F2 ... Fn               (one line of conversion factors)
    [TUNIT* keyed lines]            (GW main only)
    Option 1 (NGROUP > 0): one block per parametric grid group:
        node-range line             (e.g. "1-441" or "0")
        NDP / NEP                   (keyed ints)
        NEP parametric element rows (IE NODE1 NODE2 NODE3 NODE4)
        NDP parametric node blocks  (ID PX PY p1..pn, then one
                                     continuation line of p1..pn per
                                     additional layer)
    Option 2 (NGROUP == 0): per-node blocks:
        ID p1..pn                   (layer 1)
        p1..pn                      (one line per additional layer)

Values are stored exactly as they appear in the file — apply the
conversion factors for model units.
"""

from __future__ import annotations

import pandas as pd

from iwfm_io._tokens import is_comment, split_keyed_line, tokenize_data_line


class LineCursor:
    """Minimal data-line cursor over a list of raw file lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._pos = 0

    @property
    def eof(self) -> bool:
        self._skip_comments()
        return self._pos >= len(self._lines)

    def _skip_comments(self) -> None:
        while self._pos < len(self._lines) and is_comment(self._lines[self._pos]):
            self._pos += 1

    def peek(self) -> str | None:
        """Next data line without consuming it, or None at EOF."""
        self._skip_comments()
        if self._pos >= len(self._lines):
            return None
        return self._lines[self._pos]

    def next(self) -> str:
        line = self.peek()
        if line is None:
            raise StopIteration("End of data lines")
        self._pos += 1
        return line

    def peek_keyword(self) -> str:
        """Uppercased first word of the next data line's ``/ keyword`` part."""
        line = self.peek()
        if line is None:
            return ""
        _, keyword = split_keyed_line(line)
        return keyword.split()[0].upper() if keyword else ""

    def read_keyed_value(self) -> tuple[str, str]:
        value, keyword = split_keyed_line(self.next())
        return value, keyword


def expand_node_range(spec: str) -> list[int]:
    """Expand an IWFM node-range string like ``1-100,205,301-359``.

    ``0`` (no nodes) yields an empty list.
    """
    nodes: list[int] = []
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            nodes.extend(range(int(lo), int(hi) + 1))
        else:
            value = int(part)
            if value != 0:
                nodes.append(value)
    return nodes


def _numeric_tokens(line: str) -> list[float] | None:
    """All tokens of *line* as floats, or None if any token is non-numeric."""
    tokens = tokenize_data_line(line)
    if not tokens:
        return None
    try:
        return [float(t) for t in tokens]
    except ValueError:
        return None


def parse_node_layer_table(
    cursor: LineCursor,
    param_names: list[str],
    n_leading: int = 1,
    leading_names: list[str] | None = None,
    max_blocks: int | None = None,
) -> pd.DataFrame | None:
    """Parse an IWFM per-node, per-layer parameter table.

    Each node starts with a row of ``n_leading`` id/coordinate values
    followed by the layer-1 parameters; each additional layer is a
    continuation row holding only the parameters.  The layer count is
    inferred from the continuation rows.

    Parsing stops at EOF, at a keyed line, at a row whose token count
    matches neither pattern, or after *max_blocks* node blocks.

    Returns a long-format DataFrame (one row per node-layer) or None if
    no rows were parsed.
    """
    if leading_names is None:
        leading_names = ["node_id"]
    n_params = len(param_names)
    records: list[list[float]] = []
    current_lead: list[float] | None = None
    layer = 0
    blocks = 0

    while True:
        line = cursor.peek()
        if line is None:
            break
        vals = _numeric_tokens(line)
        if vals is None:
            break
        if len(vals) == n_leading + n_params:
            if max_blocks is not None and blocks >= max_blocks:
                break
            current_lead = vals[:n_leading]
            layer = 1
            blocks += 1
            params = vals[n_leading:]
        elif len(vals) == n_params and current_lead is not None:
            layer += 1
            params = vals
        else:
            break
        cursor.next()
        records.append(current_lead + [layer] + params)

    if not records:
        return None
    columns = leading_names + ["layer"] + param_names
    df = pd.DataFrame(records, columns=columns)
    for col in leading_names[:1] + ["layer"]:
        if col in ("node_id", "layer"):
            df[col] = df[col].astype(int)
    return df


def parse_param_block(
    cursor: LineCursor,
    param_names: list[str],
    factor_names: list[str],
) -> dict:
    """Parse a full NGROUP-style parameter section.

    Parameters
    ----------
    cursor : LineCursor
        Positioned at the NGROUP keyed line.
    param_names : list[str]
        Column names for the per-layer parameters, in file order
        (e.g. ``["kh", "ss", "sy", "aquitard_kv", "kv"]``).
    factor_names : list[str]
        Names for the conversion-factor line values, in file order
        (e.g. ``["fx", "fkh", "fs", "fn", "fv", "fl"]``).

    Returns
    -------
    dict with keys ``ngroup`` (int), ``factors`` (dict), ``time_units``
    (dict, keyed lines whose keyword starts with TUNIT), ``node_params``
    (DataFrame or None; Option 2), ``parametric_grids`` (list of dicts;
    Option 1: node_range, nodes, ndp, nep, elements, params).
    """
    value, _ = cursor.read_keyed_value()
    ngroup = int(value)

    factor_vals = _numeric_tokens(cursor.next()) or []
    factors = {
        name: (factor_vals[i] if i < len(factor_vals) else 1.0)
        for i, name in enumerate(factor_names)
    }

    time_units: dict[str, str] = {}
    while cursor.peek_keyword().startswith("TUNIT"):
        value, keyword = cursor.read_keyed_value()
        time_units[keyword.split()[0].upper()] = value

    node_params = None
    parametric_grids: list[dict] = []

    if ngroup == 0:
        node_params = parse_node_layer_table(cursor, param_names)
    else:
        for _ in range(ngroup):
            line = cursor.peek()
            if line is None:
                break
            node_range = tokenize_data_line(line)[0]
            cursor.next()
            ndp_val, _ = cursor.read_keyed_value()
            nep_val, _ = cursor.read_keyed_value()
            ndp = int(ndp_val)
            nep = int(nep_val)

            element_rows = []
            for _ in range(nep):
                vals = _numeric_tokens(cursor.next()) or []
                row = {"element_id": int(vals[0])}
                for i, v in enumerate(vals[1:5], start=1):
                    row[f"node_{i}"] = int(v)
                element_rows.append(row)
            elements = pd.DataFrame(element_rows) if element_rows else None

            params = parse_node_layer_table(
                cursor, param_names,
                n_leading=3, leading_names=["node_id", "x", "y"],
                max_blocks=ndp,
            )
            parametric_grids.append({
                "node_range": node_range,
                "nodes": expand_node_range(node_range),
                "ndp": ndp,
                "nep": nep,
                "elements": elements,
                "params": params,
            })

    return {
        "ngroup": ngroup,
        "factors": factors,
        "time_units": time_units,
        "node_params": node_params,
        "parametric_grids": parametric_grids,
    }
