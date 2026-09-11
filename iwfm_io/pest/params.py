"""
Zone/group parameterization builder: declarative parameters → PEST
artifacts.

Hand-built calibrations maintain template files, parameter-data CSVs and
tie chains by hand (or with one-off scripts that get lost). Here a list
of :class:`ParamSpec` rows declares *what is parameterized and how it is
grouped*, and :func:`build_parameters` emits every artifact
consistently:

- one **template file** (``ptf ~`` CSV) per spec, whose rows carry the
  spec's key columns plus a marker — pairing 1:1 with the *value file*
  an :class:`~iwfm_io.pest.apply.ApplyAction` consumes in the forward
  run;
- the matching **initial value file** (so the forward run works before
  PEST ever writes anything);
- **parameter-data** and **parameter-group** tables in the PEST++ v2
  external-CSV layout, including tied-parameter chains;
- a built-in round-trip check (:meth:`ParamBundle.verify`): filling each
  template with ``parval1`` must reproduce the initial value file
  exactly.

Example — one multiplier per zone on stream conductance::

    spec = ParamSpec(
        name="strk",
        values_file="mult_strk.csv",
        keys=pd.DataFrame({"reach_id": [1, 2, 3, 4],
                           "zone": ["north", "north", "south", "south"]}),
        zone_col="zone", transform="log", lower=0.01, upper=100.0)
    bundle = build_parameters([spec])
    bundle.write(template_dir)
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from iwfm_io._writer import replace_file_text
from iwfm_io.pest.budget_obs import slugify_label

__all__ = ["ParamSpec", "ParamBundle", "build_parameters"]

logger = logging.getLogger(__name__)

_MARKER = "~"
_PAR_COLUMNS = ["parnme", "partrans", "parchglim", "parval1", "parlbnd",
                "parubnd", "pargp", "scale", "offset", "dercom", "partied"]
_PARGP_DEFAULTS = {
    "inctyp": "relative", "derinc": 0.01, "derinclb": 0.0,
    "forcen": "switch", "derincmul": 2.0, "dermthd": "parabolic",
}


@dataclass
class ParamSpec:
    """Declare one parameterized quantity and its grouping.

    Attributes
    ----------
    name : str
        Base name; parameter names become ``{name}_{zone}`` (or just
        ``{name}`` without zones).
    values_file : str
        The CSV PEST writes through the template — the same file an
        ``ApplyAction.values_file`` reads. Rows = *keys* rows, columns =
        key columns + ``value``.
    keys : pandas.DataFrame
        One row per value-file row: the key columns the apply step joins
        on (e.g. ``node_id, layer``), plus *zone_col* when zoned.
    zone_col : str, optional
        Column of *keys* naming each row's zone → one parameter per
        zone. ``None`` → a single global parameter.
    transform : {"log", "none"}, default "log"
    lower, upper, initial : float
        Bounds and initial value (defaults suit multipliers: 1.0 in
        [0.01, 100]).
    group : str, optional
        Parameter group (default: *name*).
    tied : dict, optional
        ``{zone: parent_zone}`` tie chains — tied zones get
        ``partrans="tied"`` and ``partied=<parent parameter>``.
    """

    name: str
    values_file: str
    keys: "pd.DataFrame"
    zone_col: Optional[str] = None
    transform: str = "log"
    lower: float = 0.01
    upper: float = 100.0
    initial: float = 1.0
    group: Optional[str] = None
    tied: Optional[Dict] = None

    def __post_init__(self):
        if self.transform not in ("log", "none"):
            raise ValueError(
                f"transform must be 'log' or 'none', got {self.transform!r}")
        if not (self.lower <= self.initial <= self.upper):
            raise ValueError(
                f"{self.name}: initial {self.initial} outside bounds "
                f"[{self.lower}, {self.upper}]")
        if self.transform == "log" and self.lower <= 0:
            raise ValueError(
                f"{self.name}: log transform requires lower bound > 0")
        if self.zone_col is not None \
                and self.zone_col not in self.keys.columns:
            raise ValueError(
                f"{self.name}: zone_col {self.zone_col!r} not in keys")
        if self.keys.empty:
            raise ValueError(f"{self.name}: keys frame is empty")

    # ------------------------------------------------------------- helpers
    @property
    def key_cols(self) -> "list[str]":
        return [c for c in self.keys.columns if c != self.zone_col]

    def _zone_of_rows(self) -> "pd.Series":
        if self.zone_col is None:
            return pd.Series("", index=self.keys.index)
        raw = self.keys[self.zone_col]
        if raw.isna().any():
            n = int(raw.isna().sum())
            raise ValueError(
                f"{self.name}: {n} row(s) have a missing zone in "
                f"{self.zone_col!r} -- fill it (a NaN would become a "
                "parameter named '..._nan')")
        slugs = raw.map(slugify_label)
        if (slugs == "").any():
            raise ValueError(
                f"{self.name}: zone label(s) slugify to an empty name, "
                f"e.g. {raw[slugs == ''].astype(str).head(3).tolist()}")
        # two different labels must not collapse onto one parameter
        pairs = pd.DataFrame({"raw": raw.astype(str), "slug": slugs})
        n_raw = pairs.drop_duplicates().groupby("slug")["raw"].nunique()
        clash = n_raw[n_raw > 1]
        if len(clash):
            slug = clash.index[0]
            labels = sorted(pairs.loc[pairs["slug"] == slug, "raw"].unique())
            raise ValueError(
                f"{self.name}: zone labels {labels} all slugify to "
                f"{slug!r} -- rename them so the parameters stay distinct")
        return slugs

    def parameter_names(self) -> "pd.Series":
        """Per-row parameter name (rows of one zone share a name)."""
        zones = self._zone_of_rows()
        base = slugify_label(self.name)
        return zones.map(lambda z: f"{base}_{z}" if z else base)


@dataclass
class ParamBundle:
    """Everything :func:`build_parameters` produced.

    ``par_data`` / ``pargp_data`` are PEST++ v2 external tables;
    ``tpl_texts`` / ``value_texts`` map file names to contents
    (``<values_file>.tpl`` and the initial ``<values_file>``).
    """

    par_data: "pd.DataFrame"
    pargp_data: "pd.DataFrame"
    tpl_texts: Dict[str, str]
    value_texts: Dict[str, str]

    def write(self, directory) -> None:
        """Write all templates and initial value files into *directory*."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for fname, text in {**self.tpl_texts, **self.value_texts}.items():
            replace_file_text(directory / fname, text)

    def verify(self) -> None:
        """Assert: filling each template with parval1 reproduces the
        initial value file exactly."""
        vals = self.par_data.set_index("parnme")["parval1"]
        for tpl_name, tpl in self.tpl_texts.items():
            values_name = tpl_name[:-len(".tpl")]
            filled_lines = []
            for line in tpl.splitlines()[1:]:          # skip 'ptf ~'
                def sub(m):
                    parname = m.group(1).strip()
                    return f"{vals[parname]:.10G}"
                filled_lines.append(
                    re.sub(rf"{_MARKER}([^{_MARKER}]+){_MARKER}", sub, line))
            filled = pd.read_csv(io.StringIO("\n".join(filled_lines)))
            expected = pd.read_csv(
                io.StringIO(self.value_texts[values_name]))
            if not np.allclose(filled["value"], expected["value"],
                               rtol=1e-9):
                raise AssertionError(
                    f"{tpl_name}: filled template does not reproduce "
                    f"{values_name}")
        logger.info("ParamBundle.verify: %d template(s) OK",
                    len(self.tpl_texts))


def build_parameters(specs: Sequence[ParamSpec],
                     pargp_overrides: Optional[Dict] = None) -> ParamBundle:
    """Build PEST parameter artifacts from declarative specs.

    Parameters
    ----------
    specs : sequence of ParamSpec
    pargp_overrides : dict, optional
        ``{group: {column: value}}`` overrides for parameter-group rows
        (columns follow the PEST++ pargp layout, e.g. ``derinc``).

    Returns
    -------
    ParamBundle

    Raises
    ------
    ValueError
        On duplicate parameter names across specs, duplicate value
        files, or ties referencing unknown zones.
    """
    if not specs:
        raise ValueError("specs must be non-empty")
    seen_files = set()
    par_rows, groups = [], {}
    tpl_texts, value_texts = {}, {}

    for spec in specs:
        if spec.values_file in seen_files:
            raise ValueError(f"duplicate values_file {spec.values_file!r}")
        seen_files.add(spec.values_file)
        group = slugify_label(spec.group or spec.name)
        groups.setdefault(group, dict(_PARGP_DEFAULTS))

        row_names = spec.parameter_names()
        unique = list(dict.fromkeys(row_names))
        tied = { }
        if spec.tied:
            base = slugify_label(spec.name)
            zone_to_par = {slugify_label(z): f"{base}_{slugify_label(z)}"
                           for z in (spec.keys[spec.zone_col].unique()
                                     if spec.zone_col else [])}
            for child, parent in spec.tied.items():
                c = zone_to_par.get(slugify_label(child))
                p = zone_to_par.get(slugify_label(parent))
                if c is None or p is None:
                    raise ValueError(
                        f"{spec.name}: tie {child!r}->{parent!r} references "
                        f"unknown zone(s)")
                if c == p:
                    raise ValueError(
                        f"{spec.name}: zone {child!r} cannot be tied to itself")
                tied[c] = p
            # PEST requires the parent of a tie to be adjustable: a
            # parent that is itself tied (a chain or a cycle such as
            # a->b, b->a) leaves every member 'tied' with no free value
            for c, p in tied.items():
                if p in tied:
                    raise ValueError(
                        f"{spec.name}: tie chain/cycle {c!r}->{p!r}->"
                        f"{tied[p]!r} -- a tie parent must be adjustable")

        for parname in unique:
            is_tied = parname in tied
            par_rows.append({
                "parnme": parname,
                "partrans": "tied" if is_tied else spec.transform,
                "parchglim": "factor",
                "parval1": spec.initial,
                "parlbnd": spec.lower,
                "parubnd": spec.upper,
                "pargp": group,
                "scale": 1, "offset": 0, "dercom": 1,
                "partied": tied.get(parname, ""),
            })

        # template + initial value file (CSV rows keyed like the apply step)
        key_cols = spec.key_cols
        header = ",".join(key_cols + ["value"])
        tpl_lines = [f"ptf {_MARKER}", header]
        val_lines = [header]
        # PEST writes the value into the marker field: a field narrower
        # than ~12 characters truncates the precision of every parameter
        width = max(max(len(n) for n in unique) + 2, 12)
        for i in spec.keys.index:
            keys = ",".join(str(spec.keys.at[i, c]) for c in key_cols)
            prefix = f"{keys}," if key_cols else ""
            tpl_lines.append(
                f"{prefix}{_MARKER}{row_names[i]:^{width}}{_MARKER}")
            val_lines.append(f"{prefix}{spec.initial:.10G}")
        tpl_texts[spec.values_file + ".tpl"] = "\n".join(tpl_lines) + "\n"
        value_texts[spec.values_file] = "\n".join(val_lines) + "\n"

    par_data = pd.DataFrame(par_rows, columns=_PAR_COLUMNS)
    dup = par_data["parnme"][par_data["parnme"].duplicated()]
    if len(dup):
        raise ValueError(
            f"duplicate parameter name(s) across specs: "
            f"{sorted(dup.unique())[:5]}")

    for g, overrides in (pargp_overrides or {}).items():
        if g not in groups:
            raise ValueError(f"pargp_overrides for unknown group {g!r}")
        groups[g].update(overrides)
    pargp_data = pd.DataFrame(
        [{"pargpnme": g, **cfg} for g, cfg in groups.items()])

    bundle = ParamBundle(par_data=par_data, pargp_data=pargp_data,
                         tpl_texts=tpl_texts, value_texts=value_texts)
    bundle.verify()
    return bundle
