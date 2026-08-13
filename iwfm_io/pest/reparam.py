"""
Physically-constrained reparameterization + Texture2Par file hooks.

Ensemble methods draw parameters independently, so independent
end-member parameters (e.g. Kmin/Kmax for coarse and fine texture) can
produce physically invalid realizations (``Kmin > Kmax``, fine more
conductive than coarse). The proven fix from a C2VSimCG-scale IES
calibration: reparameterize as an *anchor* plus bounded ratio/exponent
parameters so **no draw within bounds can violate the ordering** — e.g.
the K "diamond"::

    chain = RatioChain()
    chain.add_parameter("kxc", bounds=(20, 450), transform="log")
    chain.add_parameter("dt",  bounds=(0.7, 4.0))
    chain.add_parameter("pa",  bounds=(0.05, 0.95))
    chain.add_parameter("pb",  bounds=(0.05, 0.95))
    chain.add_derived("kmax_coarse", "kxc")
    chain.add_derived("kmin_coarse", "kxc * 10**(-pa*dt)")
    chain.add_derived("kmax_fine",   "kxc * 10**(-pb*dt)")
    chain.add_derived("kmin_fine",   "kxc * 10**(-dt)")
    chain.assert_ordering([("kmax_coarse", ">=", "kmin_coarse"),
                           ("kmax_coarse", ">=", "kmax_fine"),
                           ("kmin_fine",   "<=", "kmin_coarse")])

``assert_ordering`` checks every bound corner (plus the midpoint), so
for the monotone expressions these chains use, a passing check is a
guarantee over the whole box. ``evaluate()`` is the forward-run step
(PEST parameters in, physical end-members out) and ``par_data()`` emits
the PEST++ v2 parameter rows for the free parameters.

Texture2Par hooks: :func:`read_t2p_pilot_points` /
:func:`write_t2p_pilot_points` handle the ``BEGIN PP_LOCS`` block files
(``.ppaq``/``.ppaqt``) that T2P workflows use for pilot-point locations.
"""

from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from iwfm_io._writer import replace_file_text

__all__ = ["RatioChain", "read_t2p_pilot_points", "write_t2p_pilot_points"]

logger = logging.getLogger(__name__)

_SAFE_FUNCS = {"log10": np.log10, "log": np.log, "exp": np.exp,
               "sqrt": np.sqrt, "abs": abs, "min": min, "max": max}
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b, "<": lambda a, b: a < b}


@dataclass
class RatioChain:
    """Anchor + bounded-ratio parameter chains with ordering guarantees."""

    _params: "dict" = field(default_factory=dict)      # name -> cfg
    _derived: "dict" = field(default_factory=dict)     # name -> expr

    # ------------------------------------------------------------- declare
    def add_parameter(self, name: str, bounds: Tuple[float, float],
                      initial: Optional[float] = None,
                      transform: str = "none", group: Optional[str] = None
                      ) -> "RatioChain":
        """Declare a free (PEST-adjustable) parameter."""
        name = str(name).lower()
        if not _NAME_RE.match(name):
            raise ValueError(f"invalid parameter name {name!r}")
        if name in self._params or name in self._derived:
            raise ValueError(f"duplicate name {name!r}")
        lo, hi = float(bounds[0]), float(bounds[1])
        if not lo < hi:
            raise ValueError(f"{name}: bounds must satisfy lower < upper")
        if transform not in ("log", "none"):
            raise ValueError(f"{name}: transform must be 'log' or 'none'")
        if transform == "log" and lo <= 0:
            raise ValueError(f"{name}: log transform requires lower > 0")
        if initial is None:
            initial = 10 ** ((np.log10(lo) + np.log10(hi)) / 2) \
                if transform == "log" else (lo + hi) / 2
        if not lo <= initial <= hi:
            raise ValueError(f"{name}: initial outside bounds")
        self._params[name] = {"bounds": (lo, hi), "initial": float(initial),
                              "transform": transform,
                              "group": group or name}
        return self

    def add_derived(self, name: str, expr: str) -> "RatioChain":
        """Declare a derived quantity as an expression over previously
        declared parameters and derived names."""
        name = str(name).lower()
        if not _NAME_RE.match(name):
            raise ValueError(f"invalid derived name {name!r}")
        if name in self._params or name in self._derived:
            raise ValueError(f"duplicate name {name!r}")
        # fail fast on unknown symbols
        ns = {k: 1.0 for k in
              itertools.chain(self._params, self._derived)}
        try:
            eval(expr, {"__builtins__": {}}, {**_SAFE_FUNCS, **ns})
        except NameError as exc:
            raise ValueError(f"{name}: expression references unknown "
                             f"name ({exc})") from None
        except SyntaxError as exc:
            raise ValueError(f"{name}: bad expression: {exc}") from None
        self._derived[name] = expr
        return self

    # ------------------------------------------------------------ evaluate
    def evaluate(self, values: Dict[str, float]) -> "dict":
        """PEST parameter values in → all derived quantities out."""
        vals = {str(k).lower(): float(v) for k, v in dict(values).items()}
        missing = set(self._params) - set(vals)
        if missing:
            raise KeyError(f"values missing for parameter(s): "
                           f"{sorted(missing)}")
        ns = dict(vals)
        for name, expr in self._derived.items():
            ns[name] = float(
                eval(expr, {"__builtins__": {}}, {**_SAFE_FUNCS, **ns}))
        return {k: ns[k] for k in self._derived}

    def assert_ordering(self, constraints: Sequence[Tuple[str, str, str]],
                        include_midpoint: bool = True) -> None:
        """Check ordering constraints at every bound corner.

        Parameters
        ----------
        constraints : sequence of (left, op, right)
            ``op`` one of ``>= <= > <``; sides are parameter or derived
            names.

        Raises
        ------
        AssertionError
            Listing the first violated constraint and the corner's
            parameter values. For monotone chain expressions a pass is
            a whole-box guarantee; for non-monotone expressions treat
            it as a strong spot check.
        """
        names = list(self._params)
        if len(names) > 16:
            raise ValueError(
                "corner check limited to 16 free parameters "
                f"({len(names)} declared)")
        for lhs, op, rhs in constraints:
            if op not in _OPS:
                raise ValueError(f"unknown operator {op!r}")
        corners = list(itertools.product(
            *[self._params[n]["bounds"] for n in names]))
        if include_midpoint:
            corners.append(tuple(self._params[n]["initial"] for n in names))
        for corner in corners:
            vals = dict(zip(names, corner))
            out = {**vals, **self.evaluate(vals)}
            for lhs, op, rhs in constraints:
                a = out[str(lhs).lower()]
                b = out[str(rhs).lower()]
                if not _OPS[op](a, b):
                    raise AssertionError(
                        f"ordering violated: {lhs} {op} {rhs} fails at "
                        f"{vals} ({lhs}={a:.6G}, {rhs}={b:.6G})")
        logger.info("assert_ordering: %d constraint(s) hold at %d "
                    "corner(s)", len(constraints), len(corners))

    # ----------------------------------------------------------- PEST side
    def par_data(self, name_format: str = "{name}") -> "pd.DataFrame":
        """PEST++ v2 parameter-data rows for the free parameters.

        ``name_format`` may inject a zone suffix, e.g.
        ``"{name}_z01"``.
        """
        rows = []
        for name, cfg in self._params.items():
            lo, hi = cfg["bounds"]
            rows.append({
                "parnme": name_format.format(name=name),
                "partrans": cfg["transform"],
                "parchglim": "factor",
                "parval1": cfg["initial"],
                "parlbnd": lo, "parubnd": hi,
                "pargp": cfg["group"],
                "scale": 1, "offset": 0, "dercom": 1, "partied": "",
            })
        return pd.DataFrame(rows)

    @property
    def parameters(self) -> "list[str]":
        return list(self._params)

    @property
    def derived(self) -> "list[str]":
        return list(self._derived)


# ----------------------------------------------------------- Texture2Par
def read_t2p_pilot_points(path) -> "pd.DataFrame":
    """Read a Texture2Par pilot-point locations file (``BEGIN PP_LOCS``).

    Returns
    -------
    pandas.DataFrame
        ``pp_id, x, y, zone``.
    """
    lines = Path(path).read_text().splitlines()
    rows, active = [], False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("BEGIN") and "PP_LOCS" in up:
            active = True
            continue
        if up.startswith("END"):
            active = False
            continue
        if active and not s.startswith("#"):
            parts = s.split()
            if len(parts) >= 4:
                rows.append((parts[0], float(parts[1]), float(parts[2]),
                             parts[3]))
    if not rows:
        raise ValueError(f"no PP_LOCS entries found in {path}")
    return pd.DataFrame(rows, columns=["pp_id", "x", "y", "zone"])


def write_t2p_pilot_points(path, df) -> None:
    """Write a Texture2Par ``BEGIN PP_LOCS`` pilot-point file.

    *df* needs ``pp_id, x, y, zone`` (the layout
    :func:`~iwfm_io.pest.pilot_points.place_pilot_points_grid` produces,
    with any zone labels).
    """
    for c in ("pp_id", "x", "y", "zone"):
        if c not in df.columns:
            raise ValueError(f"df is missing column {c!r}")
    lines = ["BEGIN PP_LOCS", "#ID          X           Y Zone"]
    for _, r in df.iterrows():
        lines.append(f"{r['pp_id']}\t{r['x']:.10G}\t{r['y']:.10G}\t{r['zone']}")
    lines.append("END PP_LOCS")
    replace_file_text(Path(path), "\n".join(lines) + "\n")
