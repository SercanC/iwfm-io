"""Shared parser for IWFM element-group tables.

Delivery element groups (diversion specs, well specs, element pumping)
and recharge zones share one structure::

    ID  NELEM  IELEM(1) [FERELS(1)]
               IELEM(2) [FERELS(2)]
               ...

— a group id, the number of elements it covers, then that many elements
(one or more per line, wrapping onto continuation lines); recharge zones
carry an extra fraction after each element. Once NELEM entries are read
the next group begins.
"""

from __future__ import annotations

from iwfm_io._tokens import is_comment


def element_groups_to_df(groups):
    """Flatten parsed element groups into a long-format DataFrame.

    Columns: ``group_id``, ``element_id`` and, when the groups carry
    fractions (recharge-zone layout), ``fraction``; a ``name`` column
    is added when any group carries one (repeated on each of the
    group's rows).  Returns an empty DataFrame when *groups* is empty.
    """
    import pandas as pd

    has_fractions = any("fractions" in g for g in groups)
    has_names = any(g.get("name") for g in groups)
    records = []
    for g in groups:
        fractions = g.get("fractions") or []
        for i, elem in enumerate(g["elements"]):
            row = {"group_id": g["group_id"], "element_id": elem}
            if has_fractions:
                row["fraction"] = fractions[i] if i < len(fractions) else None
            if has_names:
                row["name"] = g.get("name", "")
            records.append(row)
    columns = ["group_id", "element_id"] + (
        ["fraction"] if has_fractions else []) + (
        ["name"] if has_names else [])
    return pd.DataFrame(records, columns=columns)


def parse_element_groups(lines, n_groups, with_fractions=False):
    """Parse *n_groups* element groups from IWFM data *lines*.

    Parameters
    ----------
    lines : iterable of str
        Raw file lines positioned at the first group row. Comment lines
        are skipped; tokens may wrap across lines arbitrarily.
    n_groups : int
        Number of groups to read.
    with_fractions : bool
        If True each entry is an ``(element, fraction)`` pair
        (recharge-zone layout); otherwise entries are element ids.

    Returns
    -------
    (groups, n_lines_consumed) : (list[dict], int)
        Each group dict has ``group_id``, ``elements`` (list[int]),
        ``name`` (the annotation on the group's header line — an
        inline ``/`` comment or a trailing non-numeric tail; empty
        string when absent) and, when *with_fractions*, ``fractions``
        (list[float]).  ``n_lines_consumed`` is how many of *lines*
        were used (so the caller can continue parsing what follows).
    """
    groups = []
    tokens: list[str] = []
    lines_used = 0
    last_note = ""
    it = iter(lines)

    def _next_line_tokens() -> list[str]:
        """Numeric tokens of the next non-comment line (may be empty).

        Also captures the line's annotation into ``last_note``: the
        text after the first ``/`` — including ones glued to a number
        with no whitespace ("31745/ Carrier Canal") — and/or a
        non-numeric tail with the slash missing entirely
        ("37 118 29567 NKWSD - CLASS 1").
        """
        nonlocal lines_used, last_note
        while True:
            line = next(it)  # StopIteration -> ValueError below
            lines_used += 1
            if is_comment(line):
                continue
            # Group tables are purely numeric, so anything from the
            # first "/" on is an inline comment; numbers stop at the
            # first non-numeric token.
            data_part, _, note = line.partition("/")
            note = note.strip()
            raw = data_part.split()
            toks: list[str] = []
            for i, tok in enumerate(raw):
                try:
                    float(tok)
                except ValueError:
                    tail = " ".join(raw[i:])
                    note = f"{tail} {note}".strip() if note else tail
                    break
                toks.append(tok)
            if toks:
                last_note = note
                return toks

    def _need(n):
        """Ensure at least n tokens are buffered; raise on EOF."""
        while len(tokens) < n:
            tokens.extend(_next_line_tokens())

    try:
        for _ in range(n_groups):
            # Fortran list-directed reads start each group on a fresh
            # line and discard leftover tokens of the previous one —
            # e.g. a zero-element recharge zone "4  0  0  0.0" carries
            # a dummy pair that must not bleed into the next group.
            tokens = _next_line_tokens()
            # The group's name/annotation rides on its header line
            name = last_note
            _need(2)
            group_id = int(float(tokens.pop(0)))
            n_elem = int(float(tokens.pop(0)))
            per_entry = 2 if with_fractions else 1
            elements: list[int] = []
            fractions: list[float] = []
            for _ in range(n_elem):
                _need(per_entry)
                elements.append(int(float(tokens.pop(0))))
                if with_fractions:
                    fractions.append(float(tokens.pop(0)))
            group = {"group_id": group_id, "elements": elements,
                     "name": name}
            if with_fractions:
                group["fractions"] = fractions
            groups.append(group)
    except StopIteration:
        raise ValueError(
            f"Element-group table ended early: got {len(groups)} of "
            f"{n_groups} groups before running out of data lines")

    return groups, lines_used
