"""
PEST++ run orchestration: agent replication, forward-run composition,
and finals reruns.

Replaces the batch-file layer of hand-built IES workflows:

- :func:`setup_agents` — stamp out N worker directories from an agent
  template by hardlinking (near-zero disk/time even for multi-GB
  templates), each with a generated start script pointing at the
  manager. :func:`write_manager_script` writes the matching manager
  starter.
- :func:`write_forward_run` — generate the fail-fast ``forward_run.py``
  the control file invokes: each step runs in order, any nonzero exit
  aborts with that code, so PEST++ marks the run failed instead of
  reading stale outputs.
- :func:`parrep_v2` / :func:`run_finals` — rerun a chosen realization:
  put an ensemble row's values into a PEST++ v2 control file's external
  parameter-data CSV (pyemu-free) with ``noptmax`` forced to 0, in a
  fresh hardlinked copy of the template.

Hardlink invariant: anything that modifies a file in a replicated
directory must *replace* it (write temp + rename), never edit in place —
all iwfm-io writers already do. Output-like suffixes (``.out``, ``.hdf``,
``.dss``, …) are always real-copied.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

import pandas as pd

from iwfm_io._writer import replace_file_text
from iwfm_io.scenario import _NEVER_LINK_SUFFIXES

__all__ = ["setup_agents", "write_manager_script", "write_forward_run",
           "parrep_v2", "run_finals"]

logger = logging.getLogger(__name__)


# ------------------------------------------------------------- replication
def _replicate_tree(base: Path, dest: Path, link: bool) -> None:
    """Copy *base* to *dest* entirely (root files included), hardlinking
    where safe. ``Results`` directories are recreated empty."""
    base, dest = Path(base), Path(dest)
    if dest.exists():
        raise FileExistsError(f"{dest} already exists")
    link_failed = False

    def copy_function(src, dst):
        nonlocal link_failed
        if link and not link_failed \
                and Path(src).suffix.lower() not in _NEVER_LINK_SUFFIXES:
            try:
                os.link(src, dst)
                return
            except OSError as exc:
                link_failed = True
                logger.warning("hardlink failed (%s) — copying instead", exc)
        shutil.copy2(src, dst)

    def ignore(dirpath, names):
        # results folders start empty in every agent
        return {n for n in names
                if n.lower() == "results"
                and (Path(dirpath) / n).is_dir()}

    shutil.copytree(base, dest, copy_function=copy_function, ignore=ignore)
    for p in base.rglob("Results"):
        if p.is_dir():
            (dest / p.relative_to(base)).mkdir(parents=True, exist_ok=True)


def setup_agents(template_dir, n: int, dest_root=None,
                 pst: Optional[str] = None, exe: str = "pestpp-ies",
                 host: str = "localhost", port: int = 4004,
                 link: bool = True, overwrite: bool = False) -> "list[Path]":
    """Create *n* PEST++ agent directories from a template.

    Parameters
    ----------
    template_dir : path
        The agent template (control file, tpl/ins files, model, run
        scripts). Replicated whole, root files included.
    n : int
        Number of agents (``agent_01`` … ``agent_NN``).
    dest_root : path, optional
        Parent for the agent dirs (default: the template's parent).
    pst : str, optional
        Control-file name; auto-detected when the template holds
        exactly one ``.pst``.
    exe : str, default "pestpp-es"-style executable name/path.
    host, port : manager address baked into each agent's start script.
    link : bool, default True
        Hardlink unchanged files (near-zero disk; same-volume only,
        silent fallback to copying).
    overwrite : bool, default False
        Remove existing agent dirs first (otherwise raise).

    Returns
    -------
    list of Path
        The created agent directories, each containing
        ``start_agent.bat`` (Windows) / ``start_agent.sh``.
    """
    template_dir = Path(template_dir)
    pst = pst or _find_pst(template_dir)
    dest_root = Path(dest_root) if dest_root else template_dir.parent
    ext, prefix = ((".bat", "") if os.name == "nt"
                   else (".sh", "#!/bin/sh\n"))
    agents = []
    for i in range(1, n + 1):
        dest = dest_root / f"agent_{i:02d}"
        if dest.exists():
            if not overwrite:
                raise FileExistsError(
                    f"{dest} already exists (pass overwrite=True)")
            shutil.rmtree(dest)
        _replicate_tree(template_dir, dest, link)
        script = dest / f"start_agent{ext}"
        script.write_text(
            f"{prefix}cd /d \"{dest}\"\n{exe} {pst} /h {host}:{port}\n"
            if os.name == "nt" else
            f"{prefix}cd \"{dest}\"\n{exe} {pst} /h {host}:{port}\n")
        agents.append(dest)
    logger.info("created %d agent dirs under %s (link=%s)",
                n, dest_root, link)
    return agents


def write_manager_script(directory, pst: Optional[str] = None,
                         exe: str = "pestpp-ies", port: int = 4004) -> Path:
    """Write the manager start script next to the control file."""
    directory = Path(directory)
    pst = pst or _find_pst(directory)
    ext = ".bat" if os.name == "nt" else ".sh"
    path = directory / f"start_manager{ext}"
    body = f"{exe} {pst} /h :{port}\n"
    if os.name != "nt":
        body = "#!/bin/sh\n" + body
    path.write_text(body)
    return path


def _find_pst(directory: Path) -> str:
    psts = sorted(p.name for p in Path(directory).glob("*.pst"))
    if len(psts) != 1:
        raise ValueError(
            f"expected exactly one .pst in {directory}, found {psts}")
    return psts[0]


# ------------------------------------------------------------- forward run
def write_forward_run(path, steps: Sequence, python: Optional[str] = None
                      ) -> Path:
    """Generate the fail-fast forward-run script PEST++ invokes.

    Parameters
    ----------
    path : path
        Destination, e.g. ``<template>/forward_run.py``. Use
        ``python forward_run.py`` as the PEST model command line.
    steps : sequence
        Each item is a shell command string or a ``(label, command)``
        pair. Steps run in order from the script's directory; the first
        nonzero exit aborts the script with that exit code (so PEST++
        drops the run rather than reading stale output files).
    python : str, optional
        Interpreter recorded in the header comment (informational).

    Returns
    -------
    Path
    """
    norm = []
    for s in steps:
        if isinstance(s, (tuple, list)):
            label, cmd = s
        else:
            label, cmd = str(s)[:40], s
        norm.append((str(label), str(cmd)))
    if not norm:
        raise ValueError("steps must be non-empty")
    lines = [
        "# -*- coding: utf-8 -*-",
        '"""Forward run script - generated by iwfm_io.pest (fail-fast).',
        f'Interpreter hint: {python or sys.executable}"""',
        "import os, subprocess, sys, time",
        "os.chdir(os.path.dirname(os.path.abspath(__file__)))",
        "steps = [",
    ]
    for label, cmd in norm:
        lines.append(f"    ({label!r}, {cmd!r}),")
    lines += [
        "]",
        "for label, cmd in steps:",
        "    t0 = time.time()",
        "    print(f'forward_run: {label} ...', flush=True)",
        "    rc = subprocess.call(cmd, shell=True)",
        "    print(f'forward_run: {label} done rc={rc} "
        "({time.time()-t0:.1f}s)', flush=True)",
        "    if rc != 0:",
        "        sys.exit(rc if rc else 1)",
        "print('forward_run: all steps completed')",
    ]
    path = Path(path)
    replace_file_text(path, "\n".join(lines) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ finals
def parrep_v2(pst_path, values, noptmax: int = 0) -> None:
    """Put parameter values into a PEST++ v2 control file, in place.

    Rewrites the external parameter-data CSV(s) referenced by the
    control file with ``parval1`` taken from *values*, and sets
    ``noptmax``. Only version-2 ("external") control files are
    supported — for classic inline files use pyemu's ``Pst.parrep``.

    Parameters
    ----------
    pst_path : path
        The ``.pst`` inside the (already replicated) run directory —
        modified in place along with its parameter-data CSV(s).
    values : pandas.Series
        Parameter values indexed by parameter name (e.g. one row of
        ``IesResults.par()``). Every adjustable parameter must be
        covered; extras are ignored.
    noptmax : int, default 0
    """
    pst_path = Path(pst_path)
    text = pst_path.read_text()
    if "* parameter data external" not in text:
        raise ValueError(
            f"{pst_path.name} is not a v2 external control file; "
            f"use pyemu for classic .pst files")
    values = pd.Series(values)
    values.index = values.index.astype(str).str.lower()

    par_files = _external_files(text, "parameter data external")
    for rel in par_files:
        csv_path = pst_path.parent / rel
        df = pd.read_csv(csv_path)
        names = df["parnme"].astype(str).str.lower()
        have = names.isin(values.index)
        adjustable = ~df["partrans"].astype(str).str.lower().isin(
            ["fixed", "tied"])
        missing = df.loc[adjustable & ~have, "parnme"]
        if len(missing):
            raise KeyError(
                f"values missing for {len(missing)} adjustable "
                f"parameter(s), e.g. {missing.head(3).tolist()}")
        df.loc[have, "parval1"] = values[names[have]].values
        replace_file_text(csv_path, df.to_csv(index=False))

    new_text, n_sub = re.subn(r"(?m)^(\s*noptmax\s+)\S+",
                              lambda m: f"{m.group(1)}{noptmax}", text)
    if not n_sub:
        raise ValueError(f"no 'noptmax' line found in {pst_path.name}")
    replace_file_text(pst_path, new_text)


def _external_files(text: str, section: str) -> "list[str]":
    lines = text.splitlines()
    out, active = [], False
    for line in lines:
        s = line.strip()
        if s.startswith("*"):
            active = s.lstrip("* ").lower().startswith(section)
            continue
        if active and s:
            out.append(s.split()[0])
    if not out:
        raise ValueError(f"no files listed under '* {section}'")
    return out


def run_finals(results, template_dir, dest_dir, iteration=None,
               realization: str = "base", pst: Optional[str] = None,
               noptmax: int = 0, link: bool = True,
               overwrite: bool = False) -> Path:
    """Stage a rerun of one ensemble realization (the "finals" run).

    Replicates *template_dir* to *dest_dir* (hardlinked), then writes the
    chosen realization's parameter values into the control file with
    ``noptmax`` (default 0 — a single verification run). Launch it with
    the returned directory's control file (e.g. via
    :func:`write_manager_script` or directly).

    Parameters
    ----------
    results : IesResults
    template_dir, dest_dir : path
    iteration : int, optional (default: last)
    realization : str, default "base"
    """
    par = results.par(iteration)
    if realization not in par.index:
        raise KeyError(
            f"realization {realization!r} not in iteration ensemble; "
            f"available e.g. {list(par.index[:5])}")
    dest = Path(dest_dir)
    if dest.exists():
        if not overwrite:
            raise FileExistsError(f"{dest} already exists")
        shutil.rmtree(dest)
    _replicate_tree(Path(template_dir), dest, link)
    pst_name = pst or _find_pst(dest)
    parrep_v2(dest / pst_name, par.loc[realization], noptmax=noptmax)
    logger.info("finals staged in %s (iter=%s, real=%s)", dest,
                iteration if iteration is not None else max(results.par_files),
                realization)
    return dest
