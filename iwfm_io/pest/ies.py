"""
Load PEST++-IES output files into tidy pandas structures.

A PESTPP-IES run for control file ``<case>.pst`` scatters its results over
many files: per-iteration parameter and observation ensembles
(``<case>.<iter>.par.csv`` / ``.obs.csv``, or ``.jcb`` binaries when
``ies_save_binary`` is on), objective-function summaries
(``<case>.phi.composite.csv`` and friends), per-group phi
(``<case>.phi.group.csv``), prior-data conflict (``<case>.pdc.csv``),
observation-plus-noise realizations, and per-iteration base-realization
residual files (``<case>.<iter>.base.rei``).

:func:`load_ies_ensembles` discovers whatever subset of these exists and
returns an :class:`IesResults` handle that loads each file lazily (ensemble
CSVs for large models can run to hundreds of MB) and caches what it reads.

Example::

    from iwfm_io.pest import load_ies_ensembles

    r = load_ies_ensembles("master_dir/Calsim_IES_1.pst")
    r.iterations                # [0, 1, 2]
    r.phi()                     # tidy: iteration, real_name, phi
    r.par()                     # last-iteration parameter ensemble
    r.best_realization()        # e.g. "base"
    r.par_all()                 # all iterations, (iteration, real_name) index
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

__all__ = ["IesResults", "load_ies_ensembles", "read_rei"]

#: phi flavors PESTPP-IES writes (``<case>.phi.<kind>.csv``)
PHI_KINDS = ("composite", "actual", "meas", "regul")

#: identity (non-realization) columns in phi CSVs
_PHI_ID_COLS = ["iteration", "total_runs", "mean", "standard_deviation",
                "min", "max"]


def read_rei(path) -> "pd.DataFrame":
    """Read a PEST residual file (``.rei`` / ``.res``).

    Returns a DataFrame with columns ``name, group, measured, modelled,
    residual, weight`` (lowercase). The header row is located by scanning
    for the line whose first token is ``Name``, so leading title/blank
    lines of any count are tolerated.
    """
    path = Path(path)
    with open(path, "r") as f:
        lines = f.read().splitlines()
    for i, line in enumerate(lines):
        if line.split() and line.split()[0].lower() == "name":
            header_row = i
            break
    else:
        raise ValueError(f"no header row found in residual file {path}")
    # parse from the same buffer we scanned — avoids line-counting
    # disagreements with the CSV parser over stray \r characters
    df = pd.read_csv(io.StringIO("\n".join(lines[header_row:])), sep=r"\s+")
    df.columns = [c.lower() for c in df.columns]
    return df


def _tidy_phi(path: Path) -> "pd.DataFrame":
    raw = pd.read_csv(path)
    real_cols = [c for c in raw.columns
                 if c not in _PHI_ID_COLS and not c.startswith("Unnamed")]
    tidy = raw.melt(
        id_vars=["iteration"], value_vars=real_cols,
        var_name="real_name", value_name="phi",
    ).dropna(subset=["phi"])
    tidy["real_name"] = tidy["real_name"].astype(str)
    return tidy.reset_index(drop=True)


@dataclass
class IesResults:
    """Handle to a discovered set of PESTPP-IES output files.

    Build with :func:`load_ies_ensembles`. All readers are lazy and cache
    their result; ensemble frames are indexed by ``real_name`` (string —
    PESTPP-IES uses integer names plus ``"base"``).

    Attributes
    ----------
    directory : Path
        Directory the outputs live in (usually the IES master directory).
    case : str
        Control-file stem (``<case>.pst``).
    """

    directory: Path
    case: str
    par_files: Dict[int, Path] = field(default_factory=dict)
    obs_files: Dict[int, Path] = field(default_factory=dict)
    phi_files: Dict[str, Path] = field(default_factory=dict)
    group_phi_file: Optional[Path] = None
    pdc_file: Optional[Path] = None
    noise_file: Optional[Path] = None
    rei_files: Dict[int, Path] = field(default_factory=dict)
    _cache: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------- discovery
    @property
    def iterations(self) -> list:
        """Sorted iterations for which any ensemble file exists."""
        return sorted(set(self.par_files) | set(self.obs_files))

    def _resolve_iteration(self, iteration, files: dict, what: str) -> int:
        if not files:
            raise FileNotFoundError(
                f"no {what} ensemble files found for case {self.case!r} "
                f"in {self.directory}"
            )
        if iteration is None or iteration == -1:
            return max(files)
        if iteration not in files:
            raise KeyError(
                f"no {what} ensemble for iteration {iteration}; "
                f"available: {sorted(files)}"
            )
        return iteration

    # ------------------------------------------------------------- ensembles
    def _read_ensemble(self, path: Path, kind: str) -> "pd.DataFrame":
        key = ("ens", str(path))
        if key not in self._cache:
            if path.suffix.lower() == ".jcb":
                self._cache[key] = self._read_ensemble_binary(path, kind)
            else:
                # ensemble CSVs are extremely wide (one column per
                # observation); pyarrow parses them orders of magnitude
                # faster than the C engine when available
                try:
                    df = pd.read_csv(path, engine="pyarrow")
                    df = df.set_index(df.columns[0])
                except ImportError:
                    df = pd.read_csv(path, index_col=0, low_memory=False)
                df.index = df.index.astype(str)
                df.index.name = "real_name"
                self._cache[key] = df
        return self._cache[key]

    def _read_ensemble_binary(self, path: Path, kind: str) -> "pd.DataFrame":
        try:
            import pyemu
        except ImportError:
            raise RuntimeError(
                f"{path.name} is a PEST++ binary ensemble (ies_save_binary); "
                f"reading it requires pyemu (pip install iwfm-io[pest]), or "
                f"convert the run's .jcb files to .csv once with pyemu "
                f"elsewhere"
            ) from None
        pst = pyemu.Pst(str(self.directory / f"{self.case}.pst"))
        cls = (pyemu.ParameterEnsemble if kind == "par"
               else pyemu.ObservationEnsemble)
        ens = cls.from_binary(pst=pst, filename=str(path))
        # modern pyemu wraps the frame in ._df; older subclassed DataFrame
        df = pd.DataFrame(getattr(ens, "_df", ens))
        df.index = df.index.astype(str)
        df.index.name = "real_name"
        return df

    def par(self, iteration=None) -> "pd.DataFrame":
        """Parameter ensemble for one iteration (default: last available).

        Returns a DataFrame indexed by ``real_name`` with one column per
        parameter.
        """
        it = self._resolve_iteration(iteration, self.par_files, "parameter")
        return self._read_ensemble(self.par_files[it], "par")

    def obs(self, iteration=None) -> "pd.DataFrame":
        """Simulated-observation ensemble for one iteration (default: last)."""
        it = self._resolve_iteration(iteration, self.obs_files, "observation")
        return self._read_ensemble(self.obs_files[it], "obs")

    def par_all(self) -> "pd.DataFrame":
        """All parameter ensembles, ``(iteration, real_name)`` MultiIndex."""
        return pd.concat(
            {it: self.par(it) for it in sorted(self.par_files)},
            names=["iteration"],
        )

    def obs_all(self) -> "pd.DataFrame":
        """All observation ensembles, ``(iteration, real_name)`` MultiIndex."""
        return pd.concat(
            {it: self.obs(it) for it in sorted(self.obs_files)},
            names=["iteration"],
        )

    # ------------------------------------------------------------------- phi
    def phi(self, kind: str = "composite") -> "pd.DataFrame":
        """Tidy phi: columns ``iteration, real_name, phi``.

        ``kind`` is one of ``"composite"``, ``"actual"``, ``"meas"``,
        ``"regul"``. Realizations dropped by IES mid-run appear only in
        the iterations they survived.
        """
        if kind not in self.phi_files:
            raise FileNotFoundError(
                f"no phi.{kind} file for case {self.case!r}; "
                f"available: {sorted(self.phi_files)}"
            )
        key = ("phi", kind)
        if key not in self._cache:
            self._cache[key] = _tidy_phi(self.phi_files[kind])
        return self._cache[key]

    def phi_summary(self, kind: str = "composite") -> "pd.DataFrame":
        """Per-iteration phi summary (total_runs, mean, std, min, max)."""
        if kind not in self.phi_files:
            raise FileNotFoundError(
                f"no phi.{kind} file for case {self.case!r}; "
                f"available: {sorted(self.phi_files)}"
            )
        raw = pd.read_csv(self.phi_files[kind])
        cols = [c for c in _PHI_ID_COLS if c in raw.columns]
        return raw[cols].set_index("iteration")

    def phi_groups(self) -> "pd.DataFrame":
        """Tidy per-group phi: columns ``iteration, real_name, group, phi``."""
        if self.group_phi_file is None:
            raise FileNotFoundError(
                f"no phi.group file for case {self.case!r}"
            )
        key = ("phi", "group")
        if key not in self._cache:
            raw = pd.read_csv(self.group_phi_file)
            id_cols = ["iteration", "total_runs",
                       "obs_realization", "par_realization"]
            groups = [c for c in raw.columns
                      if c not in id_cols and not c.startswith("Unnamed")]
            raw = raw.rename(columns={"par_realization": "real_name"})
            raw["real_name"] = raw["real_name"].astype(str)
            self._cache[key] = raw.melt(
                id_vars=["iteration", "real_name"], value_vars=groups,
                var_name="group", value_name="phi",
            ).dropna(subset=["phi"]).reset_index(drop=True)
        return self._cache[key]

    # ---------------------------------------------------------------- extras
    def pdc(self) -> "Optional[pd.DataFrame]":
        """Prior-data-conflict table (``<case>.pdc.csv``), or None."""
        if self.pdc_file is None:
            return None
        key = ("pdc",)
        if key not in self._cache:
            self._cache[key] = pd.read_csv(self.pdc_file, index_col=0)
        return self._cache[key]

    def obs_plus_noise(self) -> "Optional[pd.DataFrame]":
        """Observation-plus-noise realizations, or None if not written."""
        if self.noise_file is None:
            return None
        return self._read_ensemble(self.noise_file, "obs")

    def base_rei(self, iteration=None) -> "pd.DataFrame":
        """Base-realization residuals (``<case>.<iter>.base.rei``)."""
        it = self._resolve_iteration(iteration, self.rei_files, "base.rei")
        key = ("rei", it)
        if key not in self._cache:
            self._cache[key] = read_rei(self.rei_files[it])
        return self._cache[key]

    # ------------------------------------------------------------- selection
    def best_realization(self, iteration=None, kind: str = "composite") -> str:
        """Name of the minimum-phi realization in an iteration (default last)."""
        phi = self.phi(kind)
        it = phi["iteration"].max() if iteration in (None, -1) else iteration
        sub = phi[phi["iteration"] == it]
        if sub.empty:
            raise KeyError(
                f"no phi values for iteration {iteration}; "
                f"available: {sorted(phi['iteration'].unique())}"
            )
        return sub.loc[sub["phi"].idxmin(), "real_name"]

    def describe(self) -> dict:
        """JSON-serializable inventory + phi summary (agent-friendly)."""
        out = {
            "case": self.case,
            "directory": str(self.directory),
            "iterations": self.iterations,
            "par_iterations": sorted(self.par_files),
            "obs_iterations": sorted(self.obs_files),
            "phi_kinds": sorted(self.phi_files),
            "has_group_phi": self.group_phi_file is not None,
            "has_pdc": self.pdc_file is not None,
            "has_obs_plus_noise": self.noise_file is not None,
            "rei_iterations": sorted(self.rei_files),
        }
        if "composite" in self.phi_files:
            out["phi_mean_by_iteration"] = (
                self.phi_summary()["mean"].round(2).to_dict()
            )
        return out


def _discover_case(path) -> "tuple[Path, str]":
    """Resolve (directory, case) from a .pst path, a directory, or a prefix."""
    p = Path(path)
    if p.suffix.lower() == ".pst":
        return p.parent, p.stem
    if p.is_dir():
        # a case is identified by its phi.composite file (always written),
        # falling back to a unique .pst
        cases = sorted(
            f.name[: -len(".phi.composite.csv")]
            for f in p.glob("*.phi.composite.csv")
        )
        if not cases:
            cases = sorted(f.stem for f in p.glob("*.pst"))
        if len(cases) == 1:
            return p, cases[0]
        if not cases:
            raise FileNotFoundError(
                f"no PEST++-IES outputs (*.phi.composite.csv) or .pst "
                f"found in {p}"
            )
        raise ValueError(
            f"multiple cases in {p}: {cases}; pass the .pst path or "
            f"'<dir>/<case>' prefix instead"
        )
    if p.parent.is_dir():
        return p.parent, p.name  # treated as a case prefix
    raise FileNotFoundError(f"{path} is not a .pst file, directory, or prefix")


def load_ies_ensembles(path) -> IesResults:
    """Discover PESTPP-IES output files and return an :class:`IesResults`.

    Parameters
    ----------
    path : str or Path
        One of: the ``<case>.pst`` control-file path, the master directory
        (works when it holds a single case), or a ``<dir>/<case>`` prefix.

    Returns
    -------
    IesResults
        Lazy, cached accessors for ensembles, phi, prior-data conflict,
        obs+noise, and base-realization residuals. CSV ensembles are read
        directly; ``.jcb`` binaries require pyemu (clear error otherwise);
        when both exist for an iteration the CSV wins.

    Examples
    --------
    >>> r = load_ies_ensembles("master/Calsim_IES_1.pst")
    >>> r.describe()["iterations"]
    [0, 1, 2]
    """
    directory, case = _discover_case(path)
    esc = re.escape(case)
    pats = {
        "par": re.compile(rf"^{esc}\.(\d+)\.par\.(csv|jcb)$"),
        "obs": re.compile(rf"^{esc}\.(\d+)\.obs\.(csv|jcb)$"),
        "phi": re.compile(rf"^{esc}\.phi\.({'|'.join(PHI_KINDS)})\.csv$"),
        "rei": re.compile(rf"^{esc}\.(\d+)\.base\.rei$"),
        "noise": re.compile(rf"^{esc}\.obs\+noise\.(csv|jcb)$"),
    }
    res = IesResults(directory=directory, case=case)

    def keep(existing: Optional[Path], candidate: Path) -> Path:
        # prefer csv over jcb when both are present
        if existing is not None and existing.suffix.lower() == ".csv":
            return existing
        return candidate

    for f in sorted(directory.iterdir()):
        name = f.name
        if m := pats["par"].match(name):
            it = int(m.group(1))
            res.par_files[it] = keep(res.par_files.get(it), f)
        elif m := pats["obs"].match(name):
            it = int(m.group(1))
            res.obs_files[it] = keep(res.obs_files.get(it), f)
        elif m := pats["phi"].match(name):
            res.phi_files[m.group(1)] = f
        elif m := pats["rei"].match(name):
            res.rei_files[int(m.group(1))] = f
        elif pats["noise"].match(name):
            res.noise_file = keep(res.noise_file, f)
        elif name == f"{case}.phi.group.csv":
            res.group_phi_file = f
        elif name == f"{case}.pdc.csv":
            res.pdc_file = f

    if not (res.par_files or res.obs_files or res.phi_files):
        raise FileNotFoundError(
            f"no PEST++-IES output files found for case {case!r} in "
            f"{directory} (looked for {case}.<iter>.par/obs.csv|.jcb and "
            f"{case}.phi.*.csv)"
        )
    return res
