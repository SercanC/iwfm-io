"""
Generated API index — the "does a function for this already exist?" lookup.

``iwfm_io`` exports several hundred public names. Anything that is not in
front of a reader (or an AI agent) tends to get written from scratch, and
hand-rolled IWFM code gets the subtle things wrong: the ``24:00`` date
convention, the ``Cc*`` comment characters, load-bearing terminating
comments, simulation-anchored budget windows. This module keeps a
one-line-per-name index of the whole public surface, so checking costs
one command::

    iwfm-io api budget          # matching names, with signatures
    iwfm-io api                 # the whole index, grouped by intent
    iwfm-io api --path          # where the index file lives

and, in process::

    import iwfm_io
    iwfm_io.find("water year")

The index ships as ``iwfm_io/API_INDEX.md`` (copied to
``docs/API_INDEX.md``) and is regenerated from the live package with::

    python -m iwfm_io._api_index --write

``tests/io/test_api_index.py`` fails when the shipped file has drifted
from the code, so the index cannot go stale.
"""

from __future__ import annotations

import inspect
import pkgutil
import re
import sys
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional

__all__ = ["Entry", "build_index", "load_index", "index_path", "search",
           "find", "format_entries"]

INDEX_FILENAME = "API_INDEX.md"

MAX_SIGNATURE = 88
MAX_SUMMARY = 120


class Entry(NamedTuple):
    """One public name in the index."""

    qualname: str      # how it is typed, e.g. "open_model" or ".heads_df"
    signature: str     # "(model_root, *, strict=True)", "" for constants
    summary: str       # first docstring sentence, one line
    group: str         # intent heading it lives under
    parent: str        # owning class for methods, else ""

    @property
    def line(self) -> str:
        """The markdown list item for this entry."""
        indent = "  " if self.parent else ""
        return f"{indent}- `{self.qualname}{self.signature}` - {self.summary}"


# --------------------------------------------------------------- grouping
# Ordered: the first matching module prefix wins, so more specific
# prefixes come first. A new module with no entry lands in "Other", and
# the drift test makes that visible.
GROUPS = [
    ("iwfm_io.model_adapter", "Start here - open a model"),
    ("iwfm_io._discovery", "Start here - open a model"),
    ("iwfm_io._api_index", "Start here - open a model"),
    ("iwfm_io._tokens", "Dates, water years & IWFM conventions"),
    ("iwfm_io.readers.hdf5",
     "Read model outputs (heads, budgets, hydrographs)"),
    ("iwfm_io.readers.text_output",
     "Read model outputs (heads, budgets, hydrographs)"),
    ("iwfm_io.readers", "Read input files"),
    ("iwfm_io.writers", "Write input files"),
    ("iwfm_io.collect", "Aggregate & collect across runs"),
    ("iwfm_io.compare", "Compare model runs"),
    ("iwfm_io.scenario", "Scenarios & running IWFM"),
    ("iwfm_io.run", "Scenarios & running IWFM"),
    ("iwfm_io._validation", "Validate a model"),
    ("iwfm_io.wells", "Observation wells & stream gauges"),
    ("iwfm_io.gauges", "Observation wells & stream gauges"),
    ("iwfm_io.dss", "HEC-DSS / CalSim coupling"),
    ("iwfm_io.gis", "GIS & VTK export"),
    ("iwfm_io.vtk", "GIS & VTK export"),
    ("iwfm_io.plots", "Plotting (iwfm_io.plots)"),
    ("iwfm_io.pest", "Calibration (iwfm_io.pest)"),
    ("iwfm_io.dll", "DLL wrapper (iwfm_io.dll - Windows x64, optional)"),
    ("iwfm_io._parser", "Low-level parsing primitives & data models"),
    ("iwfm_io._writer", "Low-level parsing primitives & data models"),
    ("iwfm_io._strict", "Low-level parsing primitives & data models"),
    ("iwfm_io.models", "Low-level parsing primitives & data models"),
]

GROUP_ORDER = []
for _prefix, _title in GROUPS:
    if _title not in GROUP_ORDER:
        GROUP_ORDER.append(_title)
GROUP_ORDER.append("Other")

# Prose under a group heading, where the group needs a warning more than
# it needs another list item.
GROUP_NOTES = {
    "Start here - open a model":
        "`open_model()` finds the model's main files and results; "
        "`describe()` says what it contains. The adapter's DataFrame "
        "accessors answer most questions without touching a reader.",
    "Dates, water years & IWFM conventions":
        "Never parse IWFM dates by hand - `MM/DD/YYYY_24:00` means the "
        "END of that day, and `iwfm_day` owns the off-by-one.",
    "Write input files":
        "Writers regenerate a whole file from its DataFrames and refuse "
        "cells IWFM would misread (NaN, `/` in a name, missing layers). "
        "Edit the DataFrame and write it - never patch the text.",
    "Plotting (iwfm_io.plots)":
        "All plot functions take an `IWFMModel` or `IOModelAdapter` and "
        "return `(fig, ax)`; most accept `save_path=` and `close=`.",
}


def safe_print(text: str) -> None:
    """``print`` that survives a non-UTF-8 console.

    Docstring summaries carry en-dashes and arrows; a redirected stdout
    on Windows is cp1252 and raises ``UnicodeEncodeError`` on them.
    Unencodable characters are replaced rather than losing the output.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(text.encode(encoding, "replace").decode(encoding, "replace"))


def _group_for(module: str) -> str:
    for prefix, title in GROUPS:
        if module == prefix or module.startswith(prefix + "."):
            return title
    return "Other"


# ------------------------------------------------------------ extraction
# Docstrings use typographic punctuation; the index is read on consoles
# that are still cp1252 (a redirected stdout on Windows), where those
# characters would be lost. Fold them to ASCII while building, so the
# shipped file and every console render the same.
_ASCII = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": " - ", "―": "-", "−": "-", "→": "->",
    "←": "<-", "⇒": "=>", "≤": "<=", "≥": ">=",
    "≠": "!=", "≈": "~=", "×": "x", "…": "...",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    " ": " ", "•": "*", "·": "*", "′": "'",
}


def _to_ascii(text: str) -> str:
    """Fold typographic punctuation to ASCII (see ``_ASCII``)."""
    for char, replacement in _ASCII.items():
        if char in text:
            text = text.replace(char, replacement)
    return text.encode("ascii", "replace").decode("ascii")


def _summarize(obj) -> str:
    """First docstring sentence of ``obj``, collapsed to one ASCII line."""
    doc = inspect.getdoc(obj) or ""
    if not callable(obj) and not inspect.isclass(obj) \
            and doc == (inspect.getdoc(type(obj)) or ""):
        # A plain constant: ``getdoc`` fell through to its builtin type
        # ("Built-in immutable sequence"), which says nothing useful.
        value = _to_ascii(repr(obj))
        if len(value) > MAX_SUMMARY - 20:
            value = value[:MAX_SUMMARY - 23].rstrip() + "..."
        return f"{type(obj).__name__} constant: {value}"
    if not doc.strip():
        return "(undocumented)"
    para = " ".join(_to_ascii(doc.strip().split("\n\n")[0]).split())
    match = re.match(r"(.+?[.!?])(?:\s|$)", para)
    text = match.group(1) if match else para
    if len(text) > MAX_SUMMARY:
        text = text[:MAX_SUMMARY - 1].rstrip() + "..."
    return text


def _signature(obj, drop_self: bool = False) -> str:
    """Rendered call signature, or "" when ``obj`` is not callable.

    ``drop_self`` removes the leading ``self``/``cls`` parameter, so a
    method reads the way it is called (``.budget_df(budget_name, ...)``).
    """
    if not callable(obj):
        return ""
    try:
        sig = " ".join(_to_ascii(str(inspect.signature(obj))).split())
    except (TypeError, ValueError):
        return "(...)"
    if drop_self:
        for first in ("(self, ", "(cls, "):
            if sig.startswith(first):
                sig = "(" + sig[len(first):]
                break
        else:
            if sig in ("(self)", "(cls)"):
                sig = "()"

    # Split off a return annotation so truncation never cuts through it
    # and leaves a dangling "->". The arrow that ends the parameter list
    # is the one following the closing paren.
    params, returns = sig, ""
    head, arrow, tail = sig.rpartition(" -> ")
    if arrow and head.endswith(")"):
        params, returns = head, f" -> {tail}"

    if len(params) + len(returns) > MAX_SIGNATURE:
        room = MAX_SIGNATURE - len(returns) - 6
        if room < 24:                      # annotation is hogging the line
            returns, room = "", MAX_SIGNATURE - 6
        params = params[:room].rstrip(", ") + ", ...)"
    return params + returns


def _public_members(cls) -> List[str]:
    """Public methods and properties ``cls`` itself defines."""
    names = []
    for name, member in vars(cls).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(member) or isinstance(
                member, (property, staticmethod, classmethod)):
            names.append(name)
    return sorted(names)


def _member_function(cls, name):
    member = vars(cls)[name]
    if isinstance(member, property):
        return member.fget
    if isinstance(member, (staticmethod, classmethod)):
        return member.__func__
    return member


def _origin_module(name, obj, owner_module: str) -> str:
    """Where ``obj`` is defined, for grouping.

    Constants carry no ``__module__``, so the package's own already
    imported modules are searched for the same object under the same
    name (sorted, so the result does not depend on import order).
    """
    module = getattr(obj, "__module__", None)
    if module:
        return module
    for module_name in sorted(sys.modules):
        if not module_name.startswith("iwfm_io."):
            continue
        found = sys.modules[module_name]
        if found is not None and vars(found).get(name, None) is obj:
            return module_name
    return owner_module


def _entries_for(name, obj, owner_module, seen) -> List[Entry]:
    """Index entries for one exported name, plus its methods if a class."""
    group = _group_for(_origin_module(name, obj, owner_module))

    key = id(obj)
    if key in seen:
        return [Entry(name, "", f"Alias of `{seen[key]}`.", group, "")]
    seen[key] = name

    entries = [Entry(name, _signature(obj), _summarize(obj), group, "")]
    if inspect.isclass(obj):
        for member in _public_members(obj):
            is_property = isinstance(vars(obj)[member], property)
            target = _member_function(obj, member)
            entries.append(Entry(
                f".{member}",
                "" if is_property else _signature(target, drop_self=True),
                _summarize(target), group, name))
    return entries


def _namespace_entries(module, prefix, seen) -> List[Entry]:
    """Entries for every name in ``module.__all__``, ``prefix``-qualified."""
    entries: List[Entry] = []
    for name in sorted(getattr(module, "__all__", [])):
        obj = getattr(module, name, None)
        if obj is None or inspect.ismodule(obj):
            continue
        for entry in _entries_for(name, obj, module.__name__, seen):
            if not prefix:
                entries.append(entry)
            elif entry.parent:
                entries.append(entry._replace(
                    parent=f"{prefix}{entry.parent}"))
            else:
                entries.append(entry._replace(
                    qualname=f"{prefix}{entry.qualname}"))
    return entries


def _plot_functions(plots) -> List[tuple]:
    """Every public ``plot_*`` / ``animate_*`` across the plot modules.

    The plot functions live in the subpackage's modules rather than in
    its ``__all__``, so they are walked the way the smoke test does.
    """
    import importlib

    found = []
    for info in sorted(pkgutil.iter_modules(plots.__path__),
                       key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{plots.__name__}.{info.name}")
        for name, obj in sorted(vars(module).items()):
            if not (name.startswith("plot_") or name.startswith("animate_")):
                continue
            if not inspect.isfunction(obj):
                continue
            if obj.__module__ != module.__name__:
                continue
            found.append((info.name, name, obj))
    for name, obj in sorted(vars(plots).items()):
        if not (name.startswith("plot_") or name.startswith("animate_")):
            continue
        if inspect.isfunction(obj) and obj.__module__ == plots.__name__:
            found.append(("", name, obj))
    return found


def collect_entries() -> List[Entry]:
    """Introspect the live package into index entries."""
    import importlib

    import iwfm_io

    seen: dict = {}
    entries = [e for e in _namespace_entries(iwfm_io, "", seen)
               if e.qualname not in ("plots", "dll", "pest")]

    plots = importlib.import_module("iwfm_io.plots")
    for module_name, name, obj in _plot_functions(plots):
        qualname = f"plots.{module_name}.{name}" if module_name \
            else f"plots.{name}"
        entries.append(Entry(qualname, _signature(obj), _summarize(obj),
                             "Plotting (iwfm_io.plots)", ""))

    entries += _namespace_entries(
        importlib.import_module("iwfm_io.pest"), "pest.", seen)
    entries += _namespace_entries(
        importlib.import_module("iwfm_io.dll"), "dll.", seen)
    return entries


# -------------------------------------------------------------- rendering
HEADER = """\
# iwfm-io API index

Every public name in `iwfm-io`, one line each, grouped by what you are
trying to do. **Check here before writing a function that reads, writes,
parses, converts or aggregates IWFM data - if it is in this list, call it
instead of reimplementing it.** Hand-rolled IWFM code gets the `24:00`
date convention, the `Cc*` comment characters, load-bearing terminating
comments and simulation-anchored budget windows wrong.

Search it from anywhere:

```bash
iwfm-io api budget        # matching names, with signatures
iwfm-io api --path        # this file's location on disk
```

`import iwfm_io` then `iwfm_io.find("water year")` runs the same search
in process. Names shown as `plots.x`, `pest.x` and `dll.x` live in those
subpackages; everything else is top-level (`from iwfm_io import
open_model`). Full argument semantics live in `docs/api-reference.md`
(<https://github.com/SercanC/iwfm-io/blob/main/docs/api-reference.md>).

*Generated from the package by `python -m iwfm_io._api_index --write` -
edit the docstrings, not this file.*
"""


# Names that lead their group, whatever the alphabet says.
PRIORITY = ["open_model", "find", "IOModelAdapter"]


def _sorted_blocks(members: List[Entry]) -> List[Entry]:
    """Order a group's entries, keeping each class's methods under it."""
    blocks: List[List[Entry]] = []
    for entry in members:
        if entry.parent and blocks:
            blocks[-1].append(entry)
        else:
            blocks.append([entry])
    blocks.sort(key=lambda block: (
        PRIORITY.index(block[0].qualname)
        if block[0].qualname in PRIORITY else len(PRIORITY),
        block[0].qualname.lower()))
    return [entry for block in blocks for entry in block]


def format_entries(entries: Iterable[Entry], *, notes: bool = True) -> str:
    """Render ``entries`` as markdown, grouped by intent."""
    entries = list(entries)
    out: List[str] = []
    for group in GROUP_ORDER:
        members = [e for e in entries if e.group == group]
        if not members:
            continue
        out.append(f"## {group}")
        out.append("")
        if notes and group in GROUP_NOTES:
            out.append(GROUP_NOTES[group])
            out.append("")
        out.extend(entry.line for entry in _sorted_blocks(members))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def build_index() -> str:
    """Build the whole index markdown from the live package."""
    entries = collect_entries()
    names = sum(1 for e in entries if not e.parent)
    return f"{HEADER}\n*{names} public names.*\n\n{format_entries(entries)}"


# ----------------------------------------------------------------- lookup
def index_path() -> Path:
    """Path of the shipped index file."""
    return Path(__file__).with_name(INDEX_FILENAME)


def load_index() -> str:
    """The shipped index text, rebuilt on the fly when it is missing."""
    path = index_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return build_index()


# The whole backticked spec is captured as one piece and split at its
# first "(" -- a signature can carry a return annotation after the
# closing paren ("-> 'pd.DataFrame'"), so it is not simply parenthesized.
_LINE_RE = re.compile(r"^(\s*)- `([^`]+)`\s+-\s+(.*)$")


def _index_entries() -> List[Entry]:
    """Parse the shipped index back into entries (no package imports)."""
    entries: List[Entry] = []
    group, parent = "Other", ""
    for raw in load_index().splitlines():
        if raw.startswith("## "):
            group, parent = raw[3:].strip(), ""
            continue
        match = _LINE_RE.match(raw)
        if not match:
            continue
        indent, spec, summary = match.groups()
        split = spec.find("(")
        name, signature = (spec, "") if split < 0 \
            else (spec[:split], spec[split:])
        if indent:
            entries.append(Entry(name, signature or "", summary, group,
                                 parent))
        else:
            parent = name
            entries.append(Entry(name, signature or "", summary, group, ""))
    return entries


def search(query: Optional[str] = None) -> List[Entry]:
    """Index entries matching ``query``.

    Parameters
    ----------
    query : str, optional
        Words to look for; an entry matches when every word appears in
        its name, summary or group heading (case-insensitive). ``None``
        returns the whole index.

    Returns
    -------
    list of Entry
    """
    entries = _index_entries()
    if not query:
        return entries
    words = query.lower().split()
    return [e for e in entries
            if all(word in " ".join(
                (e.parent, e.qualname, e.summary, e.group)).lower()
                for word in words)]


def find(query: Optional[str] = None) -> List[Entry]:
    """Print the public names matching ``query``, and return them.

    The in-process twin of ``iwfm-io api <query>``. Use it before
    writing any helper that touches IWFM data::

        >>> import iwfm_io
        >>> iwfm_io.find("water year")            # doctest: +SKIP
        - `iwfm_day(times)` - The day each timestamp *belongs to* ...
        - `water_year(times)` - Water year each timestamp belongs to ...

    Parameters
    ----------
    query : str, optional
        Words to look for; ``None`` lists the whole index.

    Returns
    -------
    list of Entry
        The matches, also printed one per line.
    """
    hits = search(query)
    if not hits:
        safe_print(f"no iwfm-io name matches {query!r} - `iwfm-io api` "
                   f"lists the whole index. If nothing there fits, "
                   f"writing it yourself is the right call.")
        return hits
    for entry in hits:
        safe_print(f"- `{entry.parent}{entry.qualname}{entry.signature}` "
                   f"- {entry.summary}")
    return hits


def _main(argv=None) -> int:
    """``python -m iwfm_io._api_index [--write]`` - print or write it."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m iwfm_io._api_index",
        description="Generate the iwfm-io API index.")
    parser.add_argument(
        "--write", action="store_true",
        help="write iwfm_io/API_INDEX.md and docs/API_INDEX.md")
    args = parser.parse_args(argv)

    text = build_index()
    if not args.write:
        safe_print(text)
        return 0

    targets = [index_path()]
    docs = Path(__file__).resolve().parent.parent / "docs"
    if docs.is_dir():
        targets.append(docs / INDEX_FILENAME)
    for target in targets:
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
