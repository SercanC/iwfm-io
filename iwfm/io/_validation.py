"""
Data integrity checks for parsed IWFM model data.

These functions validate relationships between parsed components
(e.g., element-node references, stratigraphy consistency).
"""

from __future__ import annotations

from typing import Any


def validate_nodes(node_file: Any) -> list[str]:
    """Validate a parsed node file.

    Checks:
    - No duplicate node IDs.
    - All coordinates are finite.

    Parameters
    ----------
    node_file : NodeFile

    Returns
    -------
    list of str
        Error messages. Empty list means validation passed.
    """
    errors: list[str] = []
    if node_file.data is None:
        errors.append("NodeFile has no data.")
        return errors

    df = node_file.data
    if "node_id" not in df.columns:
        errors.append("NodeFile data missing 'node_id' column.")
        return errors

    # Check for duplicate node IDs
    dupes = df["node_id"][df["node_id"].duplicated()]
    if len(dupes) > 0:
        errors.append(
            f"Duplicate node IDs: {dupes.tolist()}"
        )

    # Check for non-finite coordinates
    for col in ["x", "y"]:
        if col in df.columns:
            bad = df[~df[col].apply(lambda v: isinstance(v, (int, float)) and v == v)]
            if len(bad) > 0:
                errors.append(
                    f"Non-finite values in '{col}' column for nodes: "
                    f"{bad['node_id'].tolist()}"
                )

    return errors


def validate_elements(element_file: Any, node_file: Any | None = None) -> list[str]:
    """Validate a parsed element file.

    Checks:
    - No duplicate element IDs.
    - All node references are valid (if node_file provided).
    - Triangle elements have node4 == 0.

    Parameters
    ----------
    element_file : ElementFile
    node_file : NodeFile, optional

    Returns
    -------
    list of str
        Error messages.
    """
    errors: list[str] = []
    if element_file.data is None:
        errors.append("ElementFile has no data.")
        return errors

    df = element_file.data
    if "element_id" not in df.columns:
        errors.append("ElementFile data missing 'element_id' column.")
        return errors

    # Duplicate element IDs
    dupes = df["element_id"][df["element_id"].duplicated()]
    if len(dupes) > 0:
        errors.append(f"Duplicate element IDs: {dupes.tolist()}")

    # Check node references
    if node_file is not None and node_file.data is not None:
        valid_nodes = set(node_file.data["node_id"].tolist())
        valid_nodes.add(0)  # 0 is valid for triangles (node4)
        for col in ["node1", "node2", "node3", "node4"]:
            if col in df.columns:
                bad_refs = df[~df[col].isin(valid_nodes)]
                if len(bad_refs) > 0:
                    errors.append(
                        f"Invalid node references in '{col}' for elements: "
                        f"{bad_refs['element_id'].tolist()}"
                    )

    return errors


def validate_stratigraphy(strata_file: Any, node_file: Any | None = None) -> list[str]:
    """Validate a parsed stratigraphy file.

    Checks:
    - All node IDs in stratigraphy exist in node file (if provided).
    - Layer elevations decrease monotonically for each node.

    Parameters
    ----------
    strata_file : StratigraphyFile
    node_file : NodeFile, optional

    Returns
    -------
    list of str
        Error messages.
    """
    errors: list[str] = []
    if strata_file.data is None:
        errors.append("StratigraphyFile has no data.")
        return errors

    df = strata_file.data

    # Check node reference validity
    if node_file is not None and node_file.data is not None:
        valid_nodes = set(node_file.data["node_id"].tolist())
        bad_nodes = df[~df["node_id"].isin(valid_nodes)]
        if len(bad_nodes) > 0:
            errors.append(
                f"Stratigraphy references unknown nodes: "
                f"{bad_nodes['node_id'].tolist()[:10]}"
            )

    # Check monotonic layer elevations (elevation should decrease)
    layer_cols = [c for c in df.columns if c not in ("node_id", "elevation")]
    if "elevation" in df.columns and layer_cols:
        all_elev_cols = ["elevation"] + layer_cols
        for _, row in df.iterrows():
            elevs = [row[c] for c in all_elev_cols if c in row.index]
            for i in range(1, len(elevs)):
                if elevs[i] > elevs[i - 1]:
                    errors.append(
                        f"Node {row.get('node_id', '?')}: layer elevations "
                        f"not monotonically decreasing at index {i}"
                    )
                    break

    return errors


def validate_preprocessor(pp: Any) -> list[str]:
    """Validate a complete preprocessor file set.

    Checks cross-references between nodes, elements, stratigraphy,
    and stream geometry.

    Parameters
    ----------
    pp : PreprocessorMain

    Returns
    -------
    list of str
        Error messages.
    """
    errors: list[str] = []

    children = getattr(pp, "children", {}) or {}

    node_file = children.get("node")
    element_file = children.get("element")
    strata_file = children.get("strata")

    if node_file is not None:
        errors.extend(validate_nodes(node_file))

    if element_file is not None:
        errors.extend(validate_elements(element_file, node_file))

    if strata_file is not None:
        errors.extend(validate_stratigraphy(strata_file, node_file))

    # Check node count consistency
    if node_file is not None and strata_file is not None:
        if node_file.data is not None and strata_file.data is not None:
            n_nodes = len(node_file.data)
            n_strata = len(strata_file.data)
            if n_nodes != n_strata:
                errors.append(
                    f"Node count mismatch: {n_nodes} nodes vs "
                    f"{n_strata} stratigraphy entries"
                )

    return errors
