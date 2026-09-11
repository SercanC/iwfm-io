"""Shared helpers for the hostile-QA regression suite.

The root ``tests/conftest.py`` provides the sample-model fixtures; this
module adds the few file-editing / process helpers the imported
reproductions relied on.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.conftest import SAMPLE_MODEL, copy_sample_model


def edit_line(path, lineno: int, text: str) -> None:
    """Replace 1-based line *lineno* of a text file with *text*."""
    path = Path(path)
    lines = path.read_text().splitlines(keepends=True)
    lines[lineno - 1] = text + "\n"
    path.write_text("".join(lines))


def copy_model(dest, results=()) -> Path:
    """Copy the sample model's inputs (no Results) into *dest*, then copy
    only the named ``Results/`` files. Lets a test control exactly which
    outputs ``open_model`` can discover (e.g. text-only heads)."""
    dest = copy_sample_model(dest, results=False)
    for name in results:
        shutil.copy2(SAMPLE_MODEL / "Results" / name, dest / "Results" / name)
    return dest


def run_python(code: str, timeout: float) -> "subprocess.CompletedProcess | subprocess.TimeoutExpired":
    """Run *code* in a fresh interpreter; return the CompletedProcess, or
    the TimeoutExpired exception (the child is killed) when it overruns."""
    try:
        return subprocess.run([sys.executable, "-c", code], timeout=timeout,
                              capture_output=True, text=True, errors="replace")
    except subprocess.TimeoutExpired as exc:
        return exc


def rmtree_deep(path) -> None:
    """Best-effort removal of a tree that may exceed MAX_PATH on Windows."""
    p = str(Path(path).resolve())
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        p = "\\\\?\\" + p
    shutil.rmtree(p, ignore_errors=True)
