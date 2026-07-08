"""
Readers for IWFM text output files (.out and .bud).

All functions return pandas DataFrames.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import pandas as pd


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
            # Check for known metadata labels
            for label in ["HYDROGRAPH ID", "LAYER", "NODE", "NODES", "ELEMENT"]:
                if label in stripped.upper():
                    # Extract the values after the label
                    # Format: "* LABEL    val1    val2    val3 ..."
                    parts = stripped.lstrip("* ")
                    # Remove the label text
                    label_upper = label
                    idx = parts.upper().find(label_upper)
                    if idx >= 0:
                        after = parts[idx + len(label_upper):]
                        vals = after.split()
                        metadata[label.lower()] = vals
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
        Columns: date (str), then one column per node per layer.
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

    # Parse data: group lines by timestep
    dates: list[str] = []
    all_values: list[list[float]] = []

    current_vals: list[float] = []
    current_date: str | None = None

    for i in range(data_start, len(lines)):
        line = lines[i].rstrip()
        if not line.strip():
            continue
        tokens = line.split()
        if not tokens:
            continue

        # Check if line starts with a date
        if "/" in tokens[0] and "_" in tokens[0]:
            # Save previous record
            if current_date is not None:
                dates.append(current_date)
                all_values.append(current_vals)
            current_date = tokens[0]
            current_vals = [float(t) for t in tokens[1:]]
        else:
            # Continuation line (next layer)
            current_vals.extend(float(t) for t in tokens)

    # Save last record
    if current_date is not None:
        dates.append(current_date)
        all_values.append(current_vals)

    if not dates:
        return pd.DataFrame()

    n_cols = max(len(r) for r in all_values)
    col_names = [f"col_{i + 1}" for i in range(n_cols)]
    for r in all_values:
        while len(r) < n_cols:
            r.append(float("nan"))

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
    col_headers: list[str] = []
    data_start = 0
    dash_count = 0
    last_comment_between_dashes = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("C") or stripped.startswith("c"):
            if "---" in stripped:
                dash_count += 1
                # After 3rd dash, data starts
                if dash_count == 3:
                    # Parse column headers from the comment between dashes 2-3
                    if last_comment_between_dashes:
                        # Strip the C prefix and parse
                        hdr = last_comment_between_dashes.lstrip("Cc").strip()
                        col_headers = hdr.split()
                    data_start = i + 1
                    break
                last_comment_between_dashes = ""
            else:
                # Track comment lines between dashes for header extraction
                if dash_count >= 2:
                    last_comment_between_dashes = stripped
            continue

        # Check for scale factor line (e.g., "1.0 / FACTHP")
        if "/" in stripped and any(kw in stripped.upper() for kw in ["FACT", "SCALE"]):
            parts = stripped.split("/")
            try:
                scale_factor = float(parts[0].strip())
            except ValueError:
                pass
            continue

    # Parse data
    rows: list[list] = []
    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line or line.startswith("C") or line.startswith("c"):
            continue
        tokens = line.split()
        if not tokens:
            continue
        row: list = []
        for j, t in enumerate(tokens):
            try:
                if j == 0:
                    row.append(int(t))  # ID column
                else:
                    row.append(float(t) * scale_factor)
            except ValueError:
                row.append(t)
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

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    pd.DataFrame
    """
    return read_hydrograph_out(path)


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
        col_header_lines: list[str] = []
        data_start = 0
        dash_count = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Look for BUDGET line with section name
            if "BUDGET" in stripped.upper() and "FOR" in stripped.upper():
                # Extract name after "FOR"
                idx = stripped.upper().find("FOR")
                section_name = stripped[idx + 3:].strip()
            elif "BUDGET" in stripped.upper() and not section_name:
                section_name = stripped

            # Count dashed separators
            if re.match(r"^-{5,}", stripped):
                dash_count += 1
                if dash_count == 1:
                    # Collect column header lines between dashes
                    col_header_lines = []
                elif dash_count == 2:
                    data_start = i + 1
                    break
            elif dash_count == 1:
                col_header_lines.append(stripped)

        if not section_name:
            section_name = f"section_{len(sections) + 1}"

        # Parse column headers (may span multiple lines)
        # For simplicity, use the last header line as column names
        if col_header_lines:
            # Combine multi-line headers by taking tokens from each
            # The last line typically has the most complete set
            col_names = col_header_lines[-1].split()
            if col_names and col_names[0].upper() == "TIME":
                col_names[0] = "date"
        else:
            col_names = []

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
