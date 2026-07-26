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
from pathlib import Path

from iwfm_io._tokens import is_comment, split_keyed_line
from iwfm_io._writer import replace_file_text as _replace_file_text

logger = logging.getLogger(__name__)

_DEFAULT_SUBDIRS = ("Preprocessor", "Simulation", "Budget", "ZBudget", "Bin")

#: File suffixes always real-copied (never hardlinked) under
#: ``link_unchanged=True`` — the IWFM executables rewrite these during a
#: run (message/log files, the preprocessor binary, text and HDF5
#: budget outputs) or open them read-write (HEC-DSS), which through a
#: hardlink could mutate the base model's copy.
_NEVER_LINK_SUFFIXES = frozenset({".out", ".bin", ".bud", ".log", ".dss",
                                  ".hdf", ".h5"})


def create_scenario(base_dir, out_dir, changes=None,
                    subdirs=_DEFAULT_SUBDIRS, overwrite=False,
                    link_unchanged=False):
    """Copy a model folder and apply modifications to the copy.

    Parameters
    ----------
    base_dir : str or Path
        The baseline model root folder.
    out_dir : str or Path
        Destination folder for the scenario (created; must not already
        exist unless *overwrite* is True).
    changes : list of callables, optional
        Each is called with the scenario root ``Path`` after the copy.
        Use :func:`set_keyed_value` / :func:`replace_text`, or your own
        functions.
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

    Returns
    -------
    pathlib.Path
        The scenario root folder, ready for :func:`iwfm_io.run_model`.
    """
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Base model folder not found: {base_dir}")
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

    out_dir.mkdir(parents=True)
    copied = []
    for sub in subdirs:
        src = base_dir / sub
        if src.is_dir():
            shutil.copytree(src, out_dir / sub, copy_function=copy_function)
            copied.append(sub)
    if not copied:
        raise FileNotFoundError(
            f"None of the subfolders {subdirs} exist under {base_dir}")
    (out_dir / "Results").mkdir(exist_ok=True)
    logger.info("create_scenario: copied %s from %s to %s",
                copied, base_dir, out_dir)

    for change in changes or []:
        change(out_dir)

    return out_dir


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

    Raises at apply time if the keyword is not found exactly once.
    """
    def _apply(root):
        path = Path(root) / relpath
        lines = path.read_text().splitlines(keepends=True)
        hits = []
        for i, line in enumerate(lines):
            if is_comment(line):
                continue
            val, key_part = split_keyed_line(line)
            if key_part and key_part.split()[0] == keyword and val:
                hits.append((i, val))
        if len(hits) != 1:
            raise ValueError(
                f"set_keyed_value: keyword {keyword!r} found "
                f"{len(hits)} times in {relpath} (expected exactly once)")
        i, old_val = hits[0]
        # Replace the value in place, preserving surrounding layout
        lines[i] = lines[i].replace(str(old_val), str(value), 1)
        _replace_file_text(path, "".join(lines))
        logger.info("set_keyed_value: %s %s: %r -> %r",
                    relpath, keyword, old_val, value)
    return _apply


def replace_text(relpath, old, new, count=-1):
    """Literal text replacement in one file of the scenario.

    Returns a change callable for :func:`create_scenario`. *count* limits
    the number of replacements (-1 = all). Raises at apply time if *old*
    does not occur in the file.
    """
    def _apply(root):
        path = Path(root) / relpath
        text = path.read_text()
        n = text.count(old)
        if n == 0:
            raise ValueError(
                f"replace_text: {old!r} not found in {relpath}")
        _replace_file_text(path, text.replace(old, new, count))
        logger.info("replace_text: %s: %d occurrence(s) of %r replaced",
                    relpath, n if count == -1 else min(n, count), old)
    return _apply
