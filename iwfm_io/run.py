"""Run the IWFM executables from Python (Windows only).

Completes the scenario loop: read a model with ``iwfm_io``, modify it
(:func:`iwfm_io.create_scenario`), **run it**, then compare results
(:func:`iwfm_io.compare_models`).

Each IWFM tool is a console executable that takes its main input file as
a single argument and runs in that file's folder — exactly how the DWR
batch files invoke them::

    from iwfm_io import run_model

    results = run_model("path/to/my_model")        # preprocessor + simulation
    results = run_model("path/to/my_model",
                        steps=("preprocessor", "simulation",
                               "budget", "zbudget"))

    # Or step by step:
    from iwfm_io import run_preprocessor, run_simulation
    run_preprocessor("path/to/my_model")
    run_simulation("path/to/my_model", timeout=3600)

Executable discovery: ``bin_dir`` argument → ``<model_dir>/Bin`` →
``IWFM_BIN_DIR`` environment variable.

Failure detection: IWFM exits with code 0 even on fatal errors (the
Fortran logger prints ``* FATAL:`` and executes a plain ``STOP``), so
the console output and the tool's Messages file are scanned for that
banner; the lines that follow it carry the reason and are kept in
``RunResult.errors``. Pass ``timeout=`` for unattended runs — the
ZBudget tool is known to spin forever when its print interval exceeds
the simulated span, and a timeout turns that into a failed result
instead of a wedged process.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

#: The IWFM message logger's fatal banner (MessageLogger.f90) and the
#: Intel Fortran runtime's error prefix.
_FATAL_RE = re.compile(r"^\*\s*FATAL\b|^forrtl:", re.IGNORECASE)
#: Detail lines the logger prints after the banner.
_DETAIL_RE = re.compile(r"^\*\s{1,}\S")
_MAX_DETAIL_LINES = 12
_STDOUT_TAIL_LINES = 40

# step name -> (exe name pattern, input-file subfolder, input patterns,
#               conventional messages file)
_STEPS = {
    "preprocessor": ("preprocessor", "Preprocessor", ("preproc",),
                     "PreprocessorMessages.out"),
    "simulation": ("simulation", "Simulation", ("simulation", "sim_"),
                   "SimulationMessages.out"),
    "budget": ("budget", "Budget", ("budget",), "BudgetMessages.out"),
    "zbudget": ("zbudget", "ZBudget", ("zbudget",), "ZBudgetMessages.out"),
}


@dataclass
class RunResult:
    """Outcome of one IWFM tool run."""

    step: str
    exe: str
    input_file: str
    returncode: int
    elapsed: float
    success: bool
    errors: list = field(default_factory=list)
    #: True when the run was killed after ``timeout`` seconds.
    timed_out: bool = False
    #: Last lines of the tool's console output (diagnostics on failure).
    stdout_tail: str = ""

    def __repr__(self):
        status = "OK" if self.success else (
            "TIMED OUT" if self.timed_out else "FAILED")
        return (f"<RunResult {self.step}: {status} "
                f"in {self.elapsed:.1f}s>")


class RunError(RuntimeError):
    """A step failed under ``run_model(check=True)``.

    ``results`` holds the :class:`RunResult` of every step executed so
    far (including the failed one) so earlier outcomes are not lost.
    """

    def __init__(self, message, results):
        super().__init__(message)
        self.results = results


def _find_bin_dir(model_dir, bin_dir=None):
    if bin_dir is not None:
        bin_dir = Path(bin_dir)
        if bin_dir.is_dir():
            return bin_dir
        raise FileNotFoundError(f"bin_dir does not exist: {bin_dir}")
    candidate = Path(model_dir) / "Bin"
    if candidate.is_dir():
        return candidate
    env = os.environ.get("IWFM_BIN_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    raise FileNotFoundError(
        f"No IWFM executables found. Looked for {candidate} and the "
        "IWFM_BIN_DIR environment variable. Pass bin_dir= explicitly."
    )


def _find_exe(bin_dir, step_key):
    """Find the executable for a step, e.g. Simulation_x64.exe."""
    matches = []
    for exe in sorted(Path(bin_dir).glob("*.exe")):
        name = exe.name.lower()
        if step_key == "budget" and "zbudget" in name:
            continue
        if step_key in name:
            matches.append(exe)
    if not matches:
        raise FileNotFoundError(
            f"No *{step_key}*.exe found in {bin_dir}")
    return matches[0]


def _find_input_file(model_dir, step):
    from iwfm_io.model_adapter import _find_main_file
    _, subdir, patterns, _ = _STEPS[step]
    found = _find_main_file(Path(model_dir), subdir, patterns)
    if found is None:
        raise FileNotFoundError(
            f"No {step} input file found under {model_dir} "
            f"(looked in {subdir}/ for *.in/*.dat matching {patterns})")
    return found


def _scan_for_errors(text):
    """Fatal banners plus the detail lines that follow each one."""
    errors = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if _FATAL_RE.match(line):
            block = [line]
            j = i + 1
            while (j < len(lines) and len(block) <= _MAX_DETAIL_LINES
                   and _DETAIL_RE.match(lines[j].strip())):
                block.append(lines[j].strip())
                j += 1
            errors.append("\n".join(block))
            i = j
        else:
            i += 1
    return errors


def _tail(text, n=_STDOUT_TAIL_LINES):
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def run_step(step, model_dir, input_file=None, bin_dir=None,
             timeout=None, quiet=False):
    """Run one IWFM tool for a model folder.

    Parameters
    ----------
    step : str
        ``"preprocessor"``, ``"simulation"``, ``"budget"``, or ``"zbudget"``.
    model_dir : str or Path
        The model root folder.
    input_file : str or Path, optional
        Main input file for the tool. Discovered automatically when None;
        a relative path is taken relative to *model_dir*.
    bin_dir : str or Path, optional
        Folder containing the IWFM executables. Default: ``<model_dir>/Bin``,
        then the ``IWFM_BIN_DIR`` environment variable.
    timeout : float, optional
        Seconds before the run is killed (None = no limit). A killed run
        is returned as a failed :class:`RunResult` with ``timed_out``
        set, never raised.
    quiet : bool
        Suppress the one-line progress message.

    Returns
    -------
    RunResult
        ``success`` is True when the exit code is 0 and no ``* FATAL``
        banner appears in the tool's console output or its Messages file.
    """
    if os.name != "nt":
        raise OSError("The IWFM executables are Windows-only; "
                      "iwfm_io works on any OS, but running models does not.")
    if step not in _STEPS:
        raise ValueError(f"Unknown step {step!r}; expected one of {list(_STEPS)}")

    model_dir = Path(model_dir)
    exe = _find_exe(_find_bin_dir(model_dir, bin_dir), _STEPS[step][0])
    if input_file is None:
        input_file = _find_input_file(model_dir, step)
    input_file = Path(input_file)
    if not input_file.is_absolute():
        input_file = model_dir / input_file
    if not input_file.is_file():
        raise FileNotFoundError(f"{step} input file not found: {input_file}")
    workdir = input_file.parent
    messages_name = _STEPS[step][3]

    if not quiet:
        print(f"Running {step} ({exe.name} {input_file.name}) ...",
              end="", flush=True)

    start_wall = time.time()
    t0 = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(
            [str(exe), input_file.name],
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        returncode = proc.returncode
        console = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:  # child already killed
        timed_out = True
        returncode = -1
        out = exc.stdout or b""
        console = out.decode(errors="replace") if isinstance(out, bytes) \
            else str(out)
    elapsed = time.perf_counter() - t0

    errors = _scan_for_errors(console)
    if timed_out:
        errors.append(f"{step} timed out after {timeout} s "
                      "(process killed)")
    # Only scan the Messages file if this run (re)wrote it — a stale file
    # from an earlier run must not fail a clean one. 2 s slack for
    # filesystem timestamp granularity.
    messages = workdir / messages_name
    if messages.is_file() and messages.stat().st_mtime >= start_wall - 2:
        errors += _scan_for_errors(messages.read_text(errors="replace"))
    success = returncode == 0 and not errors and not timed_out

    if not quiet:
        status = "OK" if success else ("TIMED OUT" if timed_out else "FAILED")
        print(f" {status} ({elapsed:.1f}s)")

    return RunResult(
        step=step,
        exe=str(exe),
        input_file=str(input_file),
        returncode=returncode,
        elapsed=elapsed,
        success=success,
        errors=errors,
        timed_out=timed_out,
        stdout_tail=_tail(console),
    )


def run_preprocessor(model_dir, **kwargs):
    """Run the IWFM PreProcessor. See :func:`run_step` for options."""
    return run_step("preprocessor", model_dir, **kwargs)


def run_simulation(model_dir, **kwargs):
    """Run the IWFM Simulation. See :func:`run_step` for options."""
    return run_step("simulation", model_dir, **kwargs)


def run_budget(model_dir, **kwargs):
    """Run the IWFM Budget post-processor. See :func:`run_step`."""
    return run_step("budget", model_dir, **kwargs)


def run_zbudget(model_dir, **kwargs):
    """Run the IWFM ZBudget post-processor. See :func:`run_step`."""
    return run_step("zbudget", model_dir, **kwargs)


def run_model(model_dir, steps=("preprocessor", "simulation"),
              bin_dir=None, timeout=None, quiet=False, check=True):
    """Run the IWFM toolchain for a model folder.

    Parameters
    ----------
    model_dir : str or Path
        The model root folder (containing ``Preprocessor/``,
        ``Simulation/``, and usually ``Bin/``).
    steps : tuple of str
        Which tools to run, in order. Default runs the preprocessor and
        the simulation; add ``"budget"`` / ``"zbudget"`` if the model has
        those post-processor configurations.
    bin_dir : str or Path, optional
        Folder with the IWFM executables (default ``<model_dir>/Bin``).
    timeout : float, optional
        Per-step timeout in seconds. Strongly recommended for
        unattended runs (see the module notes on ZBudget).
    quiet : bool
        Suppress progress messages.
    check : bool
        Raise :class:`RunError` (a ``RuntimeError`` carrying the partial
        ``results``) on the first failed step (default). When False,
        later steps are still skipped after a failure, but no exception
        is raised — inspect the returned results instead.

    Returns
    -------
    dict[str, RunResult]
        One entry per executed step.
    """
    results = {}
    for step in steps:
        result = run_step(step, model_dir, bin_dir=bin_dir,
                          timeout=timeout, quiet=quiet)
        results[step] = result
        if not result.success:
            detail = "\n".join(result.errors[:5]) or \
                f"exit code {result.returncode}"
            if check:
                raise RunError(
                    f"IWFM {step} failed for {model_dir}:\n{detail}",
                    results)
            break
    return results
