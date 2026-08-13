"""
Paired model-output / PEST instruction-file writers.

In hand-built PEST setups the instruction (``.ins``) file and the
post-processor that writes the output it parses are maintained
separately — when they drift, PEST misreads values silently or the run
dies. Here one :class:`ObsFileSpec` is the single source of truth: it
writes the model-output file (:meth:`~ObsFileSpec.write_output`, called
inside the forward run) *and* the matching instruction file
(:meth:`~ObsFileSpec.write_ins`, written once at setup), so name, column
and order consistency hold by construction. :meth:`~ObsFileSpec.read_output`
parses an output file back with the same semantics, giving a built-in
round-trip check (:meth:`~ObsFileSpec.verify_round_trip`).

Two layouts:

- ``fixed`` (default) — one observation per line,
  ``<name padded>  <value>``; instruction lines use the classic
  fixed-column form ``l1 [name]start:end`` (the layout of DWR-style
  ``.pout`` files).
- ``csv`` — ``name,value`` lines; instruction lines use marker/free
  form ``l1 ~,~ !name!`` (PEST++-friendly).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from iwfm_io._writer import replace_file_text
from iwfm_io.pest.names import validate_obs_names

__all__ = ["ObsFileSpec"]


@dataclass
class ObsFileSpec:
    """Spec for one model-output file and its instruction file.

    Parameters
    ----------
    names : sequence of str
        Observation names, in output-file order (the contract both
        files share).
    layout : {"fixed", "csv"}
    value_format : str, default ``"%16.8E"``
        C-style float format for output values (``fixed`` layout).
    marker : str, default ``"#"``
        PEST instruction-file marker delimiter character.

    Examples
    --------
    >>> spec = ObsFileSpec(["gwh_w1_20001031", "gwh_w1_20001130"])
    >>> spec.write_ins("gw.ins")                    # doctest: +SKIP
    >>> spec.write_output(values, "gw.pout")        # doctest: +SKIP
    """

    names: "list"
    layout: str = "fixed"
    value_format: str = "%16.8E"
    marker: str = "#"
    _label_width: int = field(init=False, repr=False, default=0)

    def __post_init__(self):
        self.names = [str(n) for n in self.names]
        if not self.names:
            raise ValueError("names must be non-empty")
        if self.layout not in ("fixed", "csv"):
            raise ValueError(
                f"layout must be 'fixed' or 'csv', got {self.layout!r}")
        problems = validate_obs_names(self.names)
        if problems:
            raise ValueError("invalid observation names: "
                             + "; ".join(problems))
        self._label_width = max(len(n) for n in self.names)

    # ------------------------------------------------------------ geometry
    @property
    def _value_span(self) -> "tuple[int, int]":
        """1-based (start, end) columns of the value field (fixed layout)."""
        width = len(self.value_format % 0.0)
        start = self._label_width + 2       # label, one space, value field
        return start, start + width - 1

    # ------------------------------------------------------------- writers
    def write_ins(self, path) -> None:
        """Write the PEST instruction file."""
        lines = [f"pif {self.marker}"]
        if self.layout == "fixed":
            start, end = self._value_span
            lines += [f"l1 [{n}]{start}:{end}" for n in self.names]
        else:
            lines += [f"l1 ~,~ !{n}!" for n in self.names]
        replace_file_text(Path(path), "\n".join(lines) + "\n")

    def _format_lines(self, values) -> "list[str]":
        vals = self._align(values)
        if self.layout == "fixed":
            return [f"{n:<{self._label_width}} {self.value_format % v}"
                    for n, v in zip(self.names, vals)]
        return [f"{n},{self.value_format % v}".replace(" ", "")
                for n, v in zip(self.names, vals)]

    def write_output(self, values, path) -> None:
        """Write the model-output file (the forward-run fast path).

        Parameters
        ----------
        values : Series/dict (by observation name) or ordered sequence
            Missing names raise — PEST would otherwise read stale or
            misaligned values.
        """
        replace_file_text(Path(path),
                          "\n".join(self._format_lines(values)) + "\n")

    def _align(self, values) -> "np.ndarray":
        if isinstance(values, dict):
            values = pd.Series(values)
        if isinstance(values, pd.Series):
            values.index = values.index.astype(str)
            missing = [n for n in self.names if n not in values.index]
            if missing:
                raise KeyError(
                    f"values missing for {len(missing)} observation(s), "
                    f"e.g. {missing[:3]}")
            arr = values.reindex(self.names).to_numpy(dtype=float)
        else:
            arr = np.asarray(list(values), dtype=float)
            if arr.shape != (len(self.names),):
                raise ValueError(
                    f"expected {len(self.names)} values in spec order, "
                    f"got {arr.shape}")
        if not np.isfinite(arr).all():
            bad = [self.names[i] for i in np.where(~np.isfinite(arr))[0][:3]]
            raise ValueError(
                f"non-finite value(s) for e.g. {bad} — PEST cannot read "
                f"NaN/inf; filter or fill before writing")
        return arr

    # ------------------------------------------------------------- readers
    def read_output(self, path) -> "pd.Series":
        """Parse an output file using this spec's semantics (the same
        columns/markers PEST would use)."""
        text = Path(path).read_text()
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) != len(self.names):
            raise ValueError(
                f"{path}: expected {len(self.names)} data line(s), "
                f"found {len(lines)}")
        vals = []
        if self.layout == "fixed":
            start, end = self._value_span
            for n, line in zip(self.names, lines):
                vals.append(float(line[start - 1:end]))
        else:
            for n, line in zip(self.names, lines):
                vals.append(float(line.split(",", 1)[1]))
        return pd.Series(vals, index=self.names, name="value")

    def verify_round_trip(self, values=None) -> None:
        """Assert write → parse reproduces the values (setup-time check).

        Uses synthetic values when none are given. Raises ``AssertionError``
        on any mismatch.
        """
        if values is None:
            values = pd.Series(
                np.linspace(-1.0, 1.0, len(self.names)) * 1234.5678,
                index=self.names)
        buf_lines = self._format_lines(values)
        tmp = io.StringIO("\n".join(buf_lines))
        aligned = self._align(values)
        if self.layout == "fixed":
            start, end = self._value_span
            parsed = [float(l[start - 1:end]) for l in buf_lines]
        else:
            parsed = [float(l.split(",", 1)[1]) for l in buf_lines]
        rel = np.abs(np.array(parsed) - aligned)
        tol = np.maximum(1e-7 * np.abs(aligned), 1e-12)
        if not (rel <= tol).all():
            i = int(np.argmax(rel - tol))
            raise AssertionError(
                f"round-trip mismatch at {self.names[i]!r}: wrote "
                f"{aligned[i]!r}, parsed {parsed[i]!r} — widen "
                f"value_format")

    # --------------------------------------------------------- conveniences
    @classmethod
    def from_frame(cls, df, name_col: str = "obsnme", **kwargs) -> "ObsFileSpec":
        """Build a spec from any frame with an observation-name column."""
        return cls(list(df[name_col].astype(str)), **kwargs)

    def obs_data(self, values=None, weight=1.0, group=None) -> "pd.DataFrame":
        """Starter observation-data rows (PEST++ v2 external layout)."""
        out = pd.DataFrame({"obsnme": self.names})
        out["obsval"] = (self._align(values) if values is not None else 0.0)
        out["weight"] = weight
        out["obgnme"] = group if group is not None else "obs"
        return out
