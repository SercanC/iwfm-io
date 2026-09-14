"""
Readers for IWFM text output files (.out and .bud).

All functions return pandas DataFrames.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd

from iwfm_io._parser import IWFMParseError, IWFMReadWarning
from iwfm_io._tokens import is_iwfm_date

#: Fortran fixed-width overflow markers (``*******``) in output files.
_OVERFLOW_RE = re.compile(r"^\*+$")


def _float_or_nan(tok: str, path, lineno: int, what: str) -> float:
    """``float(tok)``; an all-asterisk overflow field is NaN, anything
    else that is not a number raises ``IWFMParseError``."""
    try:
        return float(tok)
    except ValueError:
        if _OVERFLOW_RE.match(tok):
            return float("nan")
        raise IWFMParseError(
            f"{what}: not a number: {tok!r}", path=path, lineno=lineno
        ) from None


def _parse_hydrograph_out(path: Union[str, Path]) -> dict:
    """Parse a generic IWFM hydrograph .out file.

    Common format for GWHyd.out, StrmHyd.out, BoundaryFlow.out,
    TileDrainFlows.out, Subsidence.out.

    Returns
    -------
    dict with keys:
        'metadata': dict of metadata rows (e.g., HYDROGRAPH ID, LAYER, NODE)
        'data': pd.DataFrame with 'date' column and value columns
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    # Find the banner end and metadata rows.
    # Banner lines start with * and contain the title/units.
    # Metadata rows start with * and contain HYDROGRAPH ID, LAYER, NODE, etc.
    # TIME row marks end of header.
    metadata = {}
    data_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Detect TIME row — marks end of header
        if stripped.startswith("*") and "TIME" in stripped.upper():
            data_start = i + 1
            break

        # Detect metadata rows (after banner)
        if stripped.startswith("*"):
            # Known metadata labels, matched as whole words (longest
            # first so "NODES" is not read as "NODE" + a stray "S").
            # Format: "* LABEL    val1    val2    val3 ..."
            parts = stripped.lstrip("* ")
            for label in ("HYDROGRAPH ID", "ELEMENTS", "ELEMENT", "LAYERS",
                          "LAYER", "NODES", "NODE"):
                m = re.search(r"\b" + re.escape(label) + r"\b", parts.upper())
                if m:
                    vals = parts[m.end():].split()
                    metadata[label.lower()] = vals
                    if label in ("NODES", "ELEMENTS", "LAYERS"):
                        # singular alias -- the key callers look up
                        metadata.setdefault(label.lower()[:-1], vals)
                    break

    # Parse data rows
    dates: list[str] = []
    rows: list[list[float]] = []

    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith("*"):
            continue
        tokens = line.split()
        if not tokens:
            continue
        # First token should be an IWFM date
        if "/" in tokens[0] and "_" in tokens[0]:
            dates.append(tokens[0])
            vals = []
            for t in tokens[1:]:
                try:
                    vals.append(float(t))
                except ValueError:
                    vals.append(float("nan"))
            rows.append(vals)

    if not dates:
        return {"metadata": metadata, "data": pd.DataFrame()}

    # Determine column count
    n_cols = max(len(r) for r in rows)
    col_names = [f"col_{i + 1}" for i in range(n_cols)]

    # Pad short rows
    for r in rows:
        while len(r) < n_cols:
            r.append(float("nan"))

    df = pd.DataFrame(rows, columns=col_names)
    df.insert(0, "date", dates)

    return {"metadata": metadata, "data": df}


def read_hydrograph_out(path: Union[str, Path]) -> pd.DataFrame:
    """Read GWHyd.out, StrmHyd.out, or similar hydrograph text output.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Columns: date (str), col_1, col_2, ...
    """
    result = _parse_hydrograph_out(path)
    return result["data"]


def read_hydrograph_out_with_metadata(path: Union[str, Path]) -> dict:
    """Read hydrograph .out file with metadata.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    dict
        Keys: 'metadata' (dict of column metadata), 'data' (DataFrame).
    """
    return _parse_hydrograph_out(path)


def read_head_all_out(path: Union[str, Path]) -> pd.DataFrame:
    """Read GWHeadAll.out — groundwater heads at all nodes.

    This file has multi-line records: one line per layer per timestep.
    Lines with timestamps start a new timestep; continuation lines
    (no timestamp) contain the next layer's data.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Columns: date (str), then one column per node per layer named
        ``node_<id>_layer_<L>`` (layer-major, mirroring
        :func:`~iwfm_io.readers.hdf5.read_head_hdf`), using the node IDs
        from the file's ``TIME`` header line.  Falls back to generic
        ``col_1``, ``col_2``, … names when the header node IDs cannot be
        matched to the data width.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    # Find header end (TIME row)
    data_start = 0
    node_ids: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("*") and "TIME" in stripped.upper():
            # The line before or at this position has the node IDs
            # Parse node IDs from the TIME+node line
            parts = stripped.lstrip("* ")
            # Remove TIME label
            idx = parts.upper().find("TIME")
            if idx >= 0:
                after = parts[idx + 4:]
                node_ids = after.split()
            data_start = i + 1
            break

    # Parse data: group lines by timestep.  A record is one dated line
    # (layer 1) plus one continuation line per additional layer; every
    # line holds one value per node and every record the same width.
    dates: list[str] = []
    all_values: list[list[float]] = []
    line_widths: set[int] = set()

    current_vals: list[float] = []
    current_date: str | None = None
    current_lines = 0
    lines_per_record: int | None = None

    def _flush(lineno: int) -> None:
        nonlocal lines_per_record
        if current_date is None:
            return
        if lines_per_record is None:
            lines_per_record = current_lines
        elif current_lines != lines_per_record:
            raise IWFMParseError(
                f"record {current_date} spans {current_lines} lines but "
                f"earlier records span {lines_per_record}",
                path=path, lineno=lineno)
        if all_values and len(current_vals) != len(all_values[0]):
            raise IWFMParseError(
                f"record {current_date} has {len(current_vals)} values "
                f"but the first record has {len(all_values[0])}",
                path=path, lineno=lineno)
        dates.append(current_date)
        all_values.append(current_vals)

    for i in range(data_start, len(lines)):
        line = lines[i].rstrip()
        if not line.strip() or line.lstrip().startswith("*"):
            continue
        tokens = line.split()
        if not tokens:
            continue

        if is_iwfm_date(tokens[0]):
            _flush(i)
            current_date = tokens[0]
            current_vals = [_float_or_nan(t, path, i + 1, "head value")
                            for t in tokens[1:]]
            current_lines = 1
            line_widths.add(len(tokens) - 1)
        elif current_date is None:
            raise IWFMParseError(
                "data before the first dated record: "
                f"{line.strip()[:60]!r}", path=path, lineno=i + 1)
        else:
            # Continuation line (next layer)
            current_vals.extend(_float_or_nan(t, path, i + 1, "head value")
                                for t in tokens)
            current_lines += 1
            line_widths.add(len(tokens))

    _flush(len(lines))

    if not dates:
        return pd.DataFrame()

    n_cols = len(all_values[0])
    n_nodes = len(node_ids)
    if (node_ids and line_widths == {n_nodes}
            and n_cols % n_nodes == 0):
        n_layers = n_cols // n_nodes
        col_names = [
            f"node_{nid}_layer_{layer}"
            for layer in range(1, n_layers + 1)
            for nid in node_ids
        ]
    else:
        if node_ids:
            warnings.warn(
                f"{path}: the header lists {n_nodes} node ids but data "
                f"lines hold {sorted(line_widths)} values; columns are "
                "labelled col_N instead of node_<id>_layer_<L>",
                IWFMReadWarning, stacklevel=2)
        col_names = [f"col_{i + 1}" for i in range(n_cols)]

    df = pd.DataFrame(all_values, columns=col_names)
    df.insert(0, "date", dates)
    return df


def read_final_state_out(path: Union[str, Path]) -> pd.DataFrame:
    """Read a final state file (FinalGWHeads.out, FinalLakeElev.out, etc.).

    These files have C-prefixed comment headers, a scale factor line,
    column headers (also C-prefixed), then node-indexed data.

    Format::

        C*** banner ***
        C---
        1.0  / FACTHP
        C---
        C   ID    HP[1]    HP[2]
        C---
        1   290.0  291.17
        ...

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Columns depend on file: typically ID + value columns per layer.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    scale_factor = 1.0
    scale_seen = False
    col_headers: list[str] = []
    data_start = 0
    dash_count = 0
    last_comment_between_dashes = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped[0] in "Cc*":
            if "---" in stripped:
                dash_count += 1
                # After 3rd dash, data starts
                if dash_count == 3:
                    # Parse column headers from the comment between dashes 2-3
                    if last_comment_between_dashes:
                        # Strip the C prefix and parse
                        hdr = last_comment_between_dashes.lstrip("Cc*").strip()
                        col_headers = hdr.split()
                    data_start = i + 1
                    break
                last_comment_between_dashes = ""
            else:
                # Track comment lines between dashes for header extraction
                if dash_count >= 2:
                    last_comment_between_dashes = stripped
            continue

        # Scale factor line: "1.0 / FACTHP", or — in hand-written
        # initial-conditions files — a bare "1.0" with no keyword. IWFM
        # reads it list-directed, so the first non-comment line holding
        # a single number is the factor; data rows have >= 2 tokens.
        if not scale_seen:
            value_part = stripped.split("/")[0].strip()
            tokens = value_part.split()
            if len(tokens) == 1:
                try:
                    scale_factor = float(tokens[0])
                    scale_seen = True
                    continue
                except ValueError:
                    pass

        # First data line reached without a dashed header block
        # (hand-written restart files): data starts here.
        data_start = i
        break

    # Parse data
    rows: list[list] = []
    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line or lines[i][0] in "Cc*":
            continue
        tokens = line.split("/")[0].split()
        if not tokens:
            continue
        row: list = []
        for j, t in enumerate(tokens):
            if j == 0:
                try:
                    row.append(int(t))  # ID column
                except ValueError:
                    raise IWFMParseError(
                        f"row id is not an integer: {t!r}",
                        path=path, lineno=i + 1) from None
            else:
                row.append(_float_or_nan(t, path, i + 1, "state value")
                           * scale_factor)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    n_cols = max(len(r) for r in rows)
    if col_headers and len(col_headers) >= n_cols:
        names = col_headers[:n_cols]
    else:
        names = [f"col_{i + 1}" for i in range(n_cols)]

    for r in rows:
        while len(r) < n_cols:
            r.append(float("nan"))

    return pd.DataFrame(rows, columns=names)


def read_flow_out(path: Union[str, Path]) -> pd.DataFrame:
    """Read a flow output file (BoundaryFlow.out, FaceFlow.out, VerticalFlow.out).

    These use the same hydrograph-style format.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Columns: date (str), col_1, col_2, ...
    """
    return read_hydrograph_out(path)


def read_velocity_out(path: Union[str, Path]) -> pd.DataFrame:
    """Read GWVelocities.out — element centroid velocities per timestep.

    The file opens with a centroid coordinate table, then per-timestep
    blocks: the block's first row carries the date, and every row holds
    one element's ``VX VY VZ`` per layer.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
        Long format, one row per element per timestep: ``date`` (str),
        ``element_id``, then ``vx_layer_1, vy_layer_1, vz_layer_1, ...``
        for each layer.  Fortran overflow fields (``*******``) are NaN.
    """
    import io as _io

    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    # The velocity header is the last "* TIME ..." line; the centroid
    # table before it has its own "* ELEMENT X Y" header.
    data_start = None
    layer_tokens: list[str] = []
    for i, line in enumerate(lines):
        if not line.startswith("*"):
            continue
        upper = line.upper()
        if "TIME" in upper and "ELEMENT" in upper:
            data_start = i + 1
        elif "LAYER" in upper:
            layer_tokens = line.lstrip("* ").split()[1:]
    if data_start is None:
        raise IWFMParseError(
            "no '* TIME ... ELEMENT ...' header found",
            path=path, lineno=len(lines) or None)

    body_idx = [i for i in range(data_start, len(lines))
                if lines[i].strip() and not lines[i].lstrip().startswith("*")]
    if not body_idx:
        return pd.DataFrame(columns=["date", "element_id"])

    s = pd.Series([lines[i] for i in body_idx]).str.lstrip()
    first_tok = s.str.split(n=1, expand=True)[0]
    is_date = first_tok.str.contains("/", regex=False)
    if not is_date.iloc[0]:
        raise IWFMParseError(
            "first velocity row does not start with a date",
            path=path, lineno=body_idx[0] + 1)
    bad = [d for d in first_tok[is_date] if not is_iwfm_date(d)]
    if bad:
        raise IWFMParseError(
            f"invalid IWFM date {bad[0]!r} in a velocity block",
            path=path)
    split = s[is_date].str.split(n=1, expand=True)
    body = s.copy()
    body[is_date] = split[1]
    dates = pd.Series(np.nan, index=s.index, dtype=object)
    dates[is_date] = split[0]

    try:
        df = pd.read_csv(_io.StringIO("\n".join(body)), sep=r"\s+",
                         header=None)
    except (ValueError, pd.errors.ParserError) as exc:
        raise IWFMParseError(
            f"velocity rows are not rectangular data ({exc})",
            path=path) from None
    if df.isna().any().any():
        r = int(df.index[df.isna().any(axis=1)][0])
        raise IWFMParseError(
            "velocity row has fewer values than the others",
            path=path, lineno=body_idx[r] + 1)
    for c in df.columns:
        if df[c].dtype == object:
            col = pd.to_numeric(df[c], errors="coerce")
            bad_mask = col.isna() & ~df[c].astype(str).str.match(r"^\*+$")
            if bad_mask.any():
                r = int(df.index[bad_mask][0])
                raise IWFMParseError(
                    f"velocity value is not a number: {df.at[r, c]!r}",
                    path=path, lineno=body_idx[r] + 1)
            df[c] = col

    n_vals = len(df.columns) - 1
    if n_vals % 3 != 0:
        raise IWFMParseError(
            f"velocity rows hold {n_vals} values, not a multiple of 3 "
            "(VX VY VZ per layer)", path=path, lineno=body_idx[0] + 1)
    n_layers = n_vals // 3
    if layer_tokens and len(layer_tokens) != n_vals:
        warnings.warn(
            f"{path}: the LAYER header lists {len(layer_tokens)} columns "
            f"but rows hold {n_vals} values", IWFMReadWarning,
            stacklevel=2)
    names = ["element_id"]
    for layer in range(1, n_layers + 1):
        names += [f"vx_layer_{layer}", f"vy_layer_{layer}",
                  f"vz_layer_{layer}"]
    df.columns = names
    elem = df["element_id"]
    if (elem != elem.round()).any():
        r = int(elem.index[elem != elem.round()][0])
        raise IWFMParseError(
            f"element id is not an integer: {elem[r]!r}",
            path=path, lineno=body_idx[r] + 1)
    df["element_id"] = elem.astype(int)
    df.insert(0, "date", dates.ffill().to_numpy())

    # every timestep block must list the same elements
    block_sizes = df.groupby("date", sort=False).size()
    if block_sizes.nunique() > 1:
        odd = block_sizes[block_sizes != block_sizes.iloc[0]].index[0]
        raise IWFMParseError(
            f"timestep {odd} lists {block_sizes[odd]} elements but the "
            f"first block lists {block_sizes.iloc[0]}", path=path)
    dup = df.duplicated(["date", "element_id"])
    if dup.any():
        r = int(df.index[dup][0])
        raise IWFMParseError(
            f"element {int(df.at[r, 'element_id'])} appears twice in the "
            f"{df.at[r, 'date']} block", path=path,
            lineno=body_idx[r] + 1)
    return df


def _is_dash_line(line: str) -> bool:
    """A budget separator: dashes and blanks only, nothing else.

    Both the full-width rules around the header block and the shorter
    per-group underlines match; the caller distinguishes them by
    position.
    """
    t = line.strip()
    return bool(t) and set(t) <= {"-", " "} and t.count("-") >= 5


def _budget_title_lines(lines: list, data_start: int) -> tuple:
    """``(title_lines, groups)`` for one budget section.

    A section header is bracketed by dash rules.  A budget with column
    *groups* (the Land & Water Use budget's "Agricultural Area" /
    "Urban Area") carries an extra banner line underlined by its own
    segmented rule::

        ------------------------------------------   <- rule
                    Agricultural Area                 <- group banner
            --------------------    ------------      <- group underline
              Potential   Agricultural                <- title lines
        Time    CUAW        Supply       ...
        ------------------------------------------   <- rule
        10/31/1973_24:00   15918.6  ...               <- data

    The per-column titles are the lines between the last two rules, so
    the banner -- which spans many columns -- is not sliced into
    nonsense.  It is returned separately as *groups*: ``(lo, hi,
    label)`` per segment of the underline, so the caller can prefix the
    columns it covers ("Agricultural Area (AC)" vs "Urban Area (AC)").
    """
    dashes = [i for i in range(data_start) if _is_dash_line(lines[i])]
    if not dashes:
        return [], []
    lo = dashes[-2] if len(dashes) >= 2 else -1
    titles = [lines[i].rstrip() for i in range(lo + 1, dashes[-1])
              if not _is_dash_line(lines[i])]

    groups: list = []
    if len(dashes) >= 3:
        rule = lines[dashes[-2]]
        banner = " ".join(lines[i] for i in range(dashes[-3] + 1, dashes[-2])
                          if not _is_dash_line(lines[i]))
        segments = [(m.start(), m.end())
                    for m in re.finditer(r"-{5,}", rule)]
        if len(segments) > 1:
            for seg_lo, seg_hi in segments:
                label = " ".join(
                    ph.group() for ph in re.finditer(r"\S+(?: \S+)*", banner)
                    if seg_lo <= (ph.start() + ph.end()) / 2 < seg_hi)
                if label:
                    groups.append((seg_lo, seg_hi, label))
    return titles, groups


def _budget_text_columns(header_lines: list, data_line: str,
                         groups: list = ()) -> list:
    """Column titles of a text budget, one per data column.

    IWFM prints each title right-aligned over its fixed-width column,
    across as many lines as the longest title needs.  Column spans come
    from the tokens of *data_line* (the first data row); every *word* of
    every header line is assigned to the column its midpoint falls in --
    slicing the line by span instead would cut words whose title is
    wider than the column it labels.  Duplicate names get a ``_2``
    suffix so the frame keeps one name per data column.
    """
    if not header_lines or not data_line:
        return []
    toks = list(re.finditer(r"\S+", data_line.rstrip("\n")))
    if not toks:
        return []
    # column i owns everything from the end of column i-1 to its own end
    spans = [(0 if i == 0 else toks[i - 1].end(), m.end())
             for i, m in enumerate(toks)]
    def _column_of(lo_hi):
        """(column index, share of the piece that column covers)."""
        lo, hi = lo_hi
        best, best_ov = 0, -1
        for i, (a, b) in enumerate(spans):
            ov = min(hi, b) - max(lo, a)
            if ov > best_ov:
                best, best_ov = i, ov
        return best, best_ov / max(hi - lo, 1)

    frags: list = [[] for _ in spans]
    for ln in header_lines:
        # A title is a phrase whose words are single-spaced, and two or
        # more spaces separate one column's title from the next -- but
        # neighbouring titles can also end up a single space apart
        # ("inside Model outside Model" over two columns).  So a phrase
        # is kept whole only when one column covers most of it;
        # otherwise it really spans columns and is split word by word.
        for phrase in re.finditer(r"\S+(?: \S+)*", ln):
            col, share = _column_of((phrase.start(), phrase.end()))
            if share >= 0.7:
                frags[col].append(phrase.group())
                continue
            for w in re.finditer(r"\S+", phrase.group()):
                lo = phrase.start() + w.start()
                col, _ = _column_of((lo, lo + len(w.group())))
                frags[col].append(w.group())
    names = [" ".join(f) for f in frags]
    # a grouped budget repeats plain titles ("Area (AC)") under each
    # group; the banner is what tells them apart
    for i, (lo, hi) in enumerate(spans):
        mid = (lo + hi) / 2
        for g_lo, g_hi, label in groups:
            if g_lo <= mid < g_hi and names[i]:
                title, lab = names[i].split(), label.split()
                # "Agricultural Area" + "Area (AC)" reads better as
                # "Agricultural Area (AC)"
                if title and lab and title[0] in (lab[-1], lab[0]):
                    title = title[1:]
                names[i] = " ".join(lab + title)
                break
    if names and names[0].upper() == "TIME":
        names[0] = "date"
    seen: dict = {}
    for i, n in enumerate(names):
        if not n:
            n = f"col_{i}"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 1
        names[i] = n
    return names


def read_budget_text(path: Union[str, Path]) -> dict:
    """Read a text budget file (.bud) into a dict of DataFrames.

    Budget text files contain multiple sections (one per subregion),
    each with its own header block.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    dict
        Keys: section name (str), values: pd.DataFrame per section.
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    # Split into sections by looking for the package identification line
    # Pattern: "IWFM ... PACKAGE" or major section header
    sections: dict[str, pd.DataFrame] = {}

    # Split on blank-line-separated blocks
    # Each section starts with "IWFM" or a package identification
    section_blocks = re.split(r"\n\s*\n\s*\n", content)

    for block in section_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 5:
            continue

        # Find section name from the BUDGET line
        section_name = ""
        col_header_lines: list[str] = []   # raw (un-stripped) lines
        data_start = len(lines)

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Look for BUDGET line with section name
            if "BUDGET" in stripped.upper() and "FOR" in stripped.upper():
                # Extract name after "FOR"
                idx = stripped.upper().find("FOR")
                section_name = stripped[idx + 3:].strip()
            elif "BUDGET" in stripped.upper() and not section_name:
                section_name = stripped

            # The data starts at the first dated row; the header block
            # is everything above it (a group underline is a dash line
            # too, so counting rules cannot delimit it -- see
            # _budget_title_lines).
            if stripped and "/" in stripped.split()[0] \
                    and "_" in stripped.split()[0]:
                data_start = i
                break

        if not section_name:
            section_name = f"section_{len(sections) + 1}"

        # Column titles span several header lines, right-aligned over
        # their fixed-width data column; they are assembled per column
        # from the spans of the first data row (see _budget_text_columns)
        col_header_lines, col_groups = _budget_title_lines(lines, data_start)
        col_names: list[str] = []

        # Parse data rows
        dates: list[str] = []
        rows: list[list[float]] = []

        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or re.match(r"^-{5,}", line):
                continue
            tokens = line.split()
            if not tokens:
                continue
            # First token should be a date
            if "/" in tokens[0] and "_" in tokens[0]:
                dates.append(tokens[0])
                vals = []
                for t in tokens[1:]:
                    try:
                        vals.append(float(t))
                    except ValueError:
                        vals.append(float("nan"))
                rows.append(vals)

        if not dates:
            continue

        n_data_cols = max(len(r) for r in rows) if rows else 0
        first_data = next(
            (lines[i] for i in range(data_start, len(lines))
             if lines[i].strip() and "/" in lines[i].split()[0]), "")
        col_names = _budget_text_columns(col_header_lines, first_data,
                                         col_groups)
        # Use generic column names if header parsing didn't provide enough
        if len(col_names) < n_data_cols + 1:  # +1 for date
            data_col_names = [f"col_{i + 1}" for i in range(n_data_cols)]
        else:
            data_col_names = col_names[1: n_data_cols + 1]

        for r in rows:
            while len(r) < n_data_cols:
                r.append(float("nan"))

        df = pd.DataFrame(rows, columns=data_col_names)
        df.insert(0, "date", dates)
        sections[section_name] = df

    return sections
