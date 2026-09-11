"""Scenario builder — copy a model and apply modifications.

The what-if workflow in three calls::

    from iwfm_io import create_scenario, set_keyed_value, compare_models
    from iwfm_io import run_model

    scenario = create_scenario(
        "runs/baseline", "runs/less_pumping",
        changes=[
            set_keyed_value("Simulation/Simulation_MAIN.IN",
                            "EDT", "09/30/1995_24:00"),
            replace_text("Simulation/GW/TSPumping.dat", "-2500.0", "-2000.0"),
        ],
    )
    run_model(scenario)
    report = compare_models("runs/baseline", scenario)

Changes are callables applied to the scenario root folder after the
copy. Use the ready-made factories :func:`set_keyed_value` and
:func:`replace_text`, or pass any ``callable(scenario_root)`` of your
own — e.g. one that round-trips a file through the ``iwfm_io``
readers/writers for structured edits.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path

from iwfm_io._tokens import _KEYED_SEP_RE, is_comment, split_keyed_line

logger = logging.getLogger(__name__)

_DEFAULT_SUBDIRS = ("Preprocessor", "Simulation", "Budget", "ZBudget", "Bin")

#: File suffixes always real-copied (never hardlinked) under
#: ``link_unchanged=True`` — the IWFM executables rewrite these during a
#: run (message/log files, the preprocessor binary, text and HDF5
#: budget outputs) or open them read-write (HEC-DSS), which through a
#: hardlink could mutate the base model's copy.
#: Output suffixes ``create_scenario(link_unchanged=True)`` always copies
#: (the executables and DLL inquiry mode rewrite these in place, so a
#: hardlink would leak scenario results into the base model).
NEVER_LINK_SUFFIXES = _NEVER_LINK_SUFFIXES = frozenset({".out", ".bin", ".bud", ".log", ".dss",
                                  ".hdf", ".h5"})

#: Subfolders that mix post-processor *inputs* (``Budget.in``,
#: ``ZoneDef_*.dat``) with baseline *outputs*. The outputs are skipped so
#: an un-run scenario can never serve the baseline's budgets as its own.
_OUTPUT_SUBDIRS = frozenset({"budget", "zbudget"})
_OUTPUT_SUFFIXES = frozenset({".bud", ".hdf", ".h5"})


def _is_output_file(name: str) -> bool:
    lower = name.lower()
    return (Path(lower).suffix in _OUTPUT_SUFFIXES
            or lower.endswith("messages.out"))


def _check_paths_disjoint(base_dir: Path, out_dir: Path) -> None:
    """Refuse identical or nested source/destination before touching disk."""
    base_r = base_dir.resolve()
    out_r = out_dir.resolve()
    if out_r == base_r:
        raise ValueError(
            f"out_dir {out_dir} is the base model itself — refusing to "
            "overwrite the baseline")
    if base_r in out_r.parents:
        raise ValueError(
            f"out_dir {out_dir} lies inside the base model {base_dir} — "
            "the copy would recurse into itself; choose a sibling folder")
    if out_r in base_r.parents:
        raise ValueError(
            f"out_dir {out_dir} contains the base model {base_dir} — "
            "overwriting it would delete the baseline")


def create_scenario(base_dir, out_dir, changes=None,
                    subdirs=_DEFAULT_SUBDIRS, overwrite=False,
                    link_unchanged=False, copy_outputs=False):
    """Copy a model folder and apply modifications to the copy.

    Parameters
    ----------
    base_dir : str or Path
        The baseline model root folder.
    out_dir : str or Path
        Destination folder for the scenario (created; must not already
        exist unless *overwrite* is True). It must not be the base
        folder, inside it, or contain it — ``ValueError`` otherwise,
        before anything is deleted or copied.
    changes : list of callables, optional
        Each is called with the scenario root ``Path`` after the copy.
        Use :func:`set_keyed_value` / :func:`replace_text`, or your own
        functions. If any change raises, the half-built scenario folder
        is removed again before the exception propagates.
    subdirs : tuple of str
        Which subfolders to copy. The default copies all inputs plus
        ``Bin/`` (so the scenario is runnable) and skips ``Results/``
        — an empty ``Results/`` folder is created for the outputs the
        run will write.
    overwrite : bool
        Delete an existing *out_dir* first (default False: raise).
    link_unchanged : bool
        Hardlink files into the scenario instead of copying them
        (default False). IWFM only reads its inputs during a run, and
        files modified by *changes* are replaced (write temp + rename)
        rather than edited in place, so the base model is never
        touched — copy-on-change semantics. This makes stamping out
        many worker copies of a large model near-instant with roughly
        zero marginal disk for shared inputs. If hardlinking fails
        (e.g. *out_dir* is on a different filesystem than *base_dir*),
        falls back to copying with a warning. ``Results/`` is always a
        real directory, and files the executables rewrite during a run
        (``.out``, ``.bin``, ``.bud``, ``.log``, ``.dss``, ``.hdf``,
        ``.h5``) are always real copies — the runtime may truncate or
        update them in place, which through a hardlink would corrupt
        the base model.

        **Invariant for custom change callables:** under this mode a
        change must *replace* a file it modifies (write to a temp file,
        then rename over the target) — editing a hardlinked file in
        place would silently mutate the base model's copy. The built-in
        factories (:func:`set_keyed_value`, :func:`replace_text`) and
        the ``iwfm_io`` writers already do this.
    copy_outputs : bool
        By default the baseline's post-processor *outputs* under
        ``Budget/`` and ``ZBudget/`` (``*.bud``, ``*.hdf``, ``*.h5``,
        ``*Messages.out``) are not copied — only the control files —
        so a scenario that has not been run yet has no budgets to
        serve. Pass True to copy them anyway.

    Returns
    -------
    pathlib.Path
        The scenario root folder, ready for :func:`iwfm_io.run_model`.
    """
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Base model folder not found: {base_dir}")
    _check_paths_disjoint(base_dir, out_dir)
    present = [sub for sub in subdirs if (base_dir / sub).is_dir()]
    if not present:
        raise FileNotFoundError(
            f"None of the subfolders {subdirs} exist under {base_dir}")
    if out_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{out_dir} already exists. Pass overwrite=True to replace it.")
        shutil.rmtree(out_dir)

    copy_function = shutil.copy2
    if link_unchanged:
        link_failed = False

        def copy_function(src, dst):
            nonlocal link_failed
            if (not link_failed
                    and Path(src).suffix.lower() not in _NEVER_LINK_SUFFIXES):
                try:
                    os.link(src, dst)
                    return
                except OSError as exc:
                    link_failed = True
                    logger.warning(
                        "create_scenario: hardlink failed (%s) — falling "
                        "back to copying. Are %s and %s on the same "
                        "filesystem?", exc, base_dir, out_dir)
            shutil.copy2(src, dst)

    def _ignore_outputs(directory, names):
        return {n for n in names if _is_output_file(n)
                and (Path(directory) / n).is_file()}

    out_dir.mkdir(parents=True)
    try:
        for sub in present:
            ignore = None
            if not copy_outputs and sub.lower() in _OUTPUT_SUBDIRS:
                ignore = _ignore_outputs
            shutil.copytree(base_dir / sub, out_dir / sub,
                            copy_function=copy_function, ignore=ignore)
        (out_dir / "Results").mkdir(exist_ok=True)
        logger.info("create_scenario: copied %s from %s to %s",
                    present, base_dir, out_dir)
        for change in changes or []:
            change(out_dir)
    except BaseException:
        # never leave a half-built scenario that looks complete
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

    return out_dir


# ---------------------------------------------------------------------------
# Text editing that preserves bytes the file already had
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    # surrogateescape keeps cp1252/latin-1 bytes of legacy decks intact
    with open(path, "r", encoding="utf-8", errors="surrogateescape",
              newline="") as fh:
        return fh.read()


def _write_text(path: Path, text: str) -> None:
    """Atomic replace (temp file + rename) — hardlink-safe."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape",
                       newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _scenario_file(root, relpath) -> Path:
    """``root/relpath`` — must stay inside the scenario."""
    root = Path(root).resolve()
    path = (root / relpath).resolve()
    if path != root and root not in path.parents:
        raise ValueError(
            f"{relpath!r} points outside the scenario folder {root}")
    return path


# ---------------------------------------------------------------------------
# Ready-made change factories
# ---------------------------------------------------------------------------

def set_keyed_value(relpath, keyword, value):
    """Change a ``VALUE / KEYWORD`` line in an IWFM input file.

    Returns a change callable for :func:`create_scenario` that finds the
    (single) non-comment line whose keyword is *keyword* and replaces its
    value, preserving the line's layout. Example::

        set_keyed_value("Simulation/Simulation_MAIN.IN", "EDT",
                        "09/30/1995_24:00")

    A blank entry (``/ KEYWORD`` — a disabled optional output) can be
    set the same way. Raises at apply time if the keyword is not found
    exactly once, or if *value* would span more than one line.
    """
    value_str = str(value)
    if "\n" in value_str or "\r" in value_str:
        raise ValueError("set_keyed_value: value must be a single line")

    def _apply(root):
        path = _scenario_file(root, relpath)
        lines = _read_text(path).splitlines(keepends=True)
        hits = []
        for i, line in enumerate(lines):
            if is_comment(line):
                continue
            val, key_part = split_keyed_line(line)
            if key_part and key_part.split()[0] == keyword:
                hits.append((i, val))
        if len(hits) != 1:
            raise ValueError(
                f"set_keyed_value: keyword {keyword!r} found "
                f"{len(hits)} times in {relpath} (expected exactly once)")
        i, old_val = hits[0]
        line = lines[i]
        eol = line[len(line.rstrip("\r\n")):]
        body = line.rstrip("\r\n")
        m = _KEYED_SEP_RE.search(body)
        if old_val == "" or m is None:
            # blank (leading-slash) entry: rebuild the line
            _, key_part = split_keyed_line(body)
            lines[i] = f"    {value_str}    / {key_part}{eol}"
        else:
            # replace only within the value span, never in the keyword
            # or the trailing comment
            left, right = body[:m.start()], body[m.start():]
            pos = left.find(old_val)
            lines[i] = left[:pos] + value_str + left[pos + len(old_val):] \
                + right + eol
        _write_text(path, "".join(lines))
        logger.info("set_keyed_value: %s %s: %r -> %r",
                    relpath, keyword, old_val, value)
    return _apply


def replace_text(relpath, old, new, count=-1):
    """Literal text replacement in one file of the scenario.

    Returns a change callable for :func:`create_scenario`. *count* limits
    the number of replacements (-1 = all). Raises at apply time if *old*
    does not occur in the file. The match is literal and unanchored —
    ``"-2500.0"`` also matches inside ``"-12500.0"`` — so prefer
    :func:`set_keyed_value` or the structured writers for anything but
    unique tokens.
    """
    def _apply(root):
        path = _scenario_file(root, relpath)
        text = _read_text(path)
        n = text.count(old)
        if n == 0:
            raise ValueError(
                f"replace_text: {old!r} not found in {relpath}")
        _write_text(path, text.replace(old, new, count))
        logger.info("replace_text: %s: %d occurrence(s) of %r replaced",
                    relpath, n if count == -1 else min(n, count), old)
    return _apply
