"""
Parameter write-back: apply PEST-estimated values to IWFM input files.

IWFM inputs are rigid fixed-format files, so embedding template markers
in them is brittle. The robust pattern (the pyemu ``PstFrom`` idiom):
PEST writes small *value files* (CSV, via simple templates), and an
apply step inside the forward run merges them onto the base parameter
tables and regenerates the model input through the package's round-trip
writers. :func:`apply_parameters` is that apply step, driven by a list
of declarative :class:`ApplyAction` rows and audited by a bookkeeping
CSV (the ``mult2model_info`` role).

Also provided: IWFM's native groundwater *parameter overwrite file*
(:func:`write_gw_overwrite` / :func:`read_gw_overwrite`) — the injection
point IWFM itself offers for aquifer/subsidence parameters (rows of
``node layer PKH PS PN PV PL SCE SCI`` with ``-1`` meaning "keep the
main-file value").

Example::

    actions = [ApplyAction(
        reader="gw_main",
        path="Simulation/Groundwater/GW_MAIN.dat",
        table="aquifer_params", column="kh",
        values_file="mult_kh.csv", key_cols=("node_id", "layer"),
        op="multiply", lower=1e-4, upper=1e4)]
    apply_parameters(run_dir, actions)     # a forward_run.py step
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
import shutil
import warnings
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from iwfm_io._writer import replace_file_text

__all__ = ["ApplyAction", "apply_parameters",
           "write_gw_overwrite", "read_gw_overwrite",
           "OVERWRITE_COLUMNS"]

logger = logging.getLogger(__name__)

#: value columns of the GW overwrite file, in file order
OVERWRITE_COLUMNS = ["pkh", "ps", "pn", "pv", "pl", "sce", "sci"]


def _registry():
    from iwfm_io.readers.groundwater import read_gw_main, read_subsidence
    from iwfm_io.readers.stream import read_stream_main
    from iwfm_io.writers.groundwater import write_gw_main, write_subsidence
    from iwfm_io.writers.stream import write_stream_main
    return {
        "gw_main": (read_gw_main, write_gw_main),
        "stream_main": (read_stream_main, write_stream_main),
        "subsidence": (read_subsidence, write_subsidence),
    }


@dataclass
class ApplyAction:
    """One declarative write-back: value file → model-input table column.

    Attributes
    ----------
    reader : str
        ``"gw_main"``, ``"stream_main"``, or ``"subsidence"``.
    path : str
        Model-input file, relative to the run directory.
    table : str
        DataFrame attribute on the parsed dataclass (e.g.
        ``"aquifer_params"``, ``"reach_params"``,
        ``"subsidence_params"``). Dotted paths reach nested tables
        through list indices and dict keys — e.g.
        ``"parametric_grids.0.params"`` for the parameter table of an
        NGROUP>0 groundwater main's first parametric grid.
    column : str
        Column to modify (e.g. ``"kh"``, ``"conductance"``).
    values_file : str
        CSV written by PEST (through a template): the *key_cols* plus a
        ``value`` column. Every row must match table rows; a value row
        matching nothing is an error (silent no-ops hide broken keys).
    key_cols : tuple of str
        Join keys (e.g. ``("node_id", "layer")``); empty tuple applies
        the single value to every row.
    op : {"multiply", "replace", "add"}
    lower, upper : float, optional
        Clip applied results (bounds enforcement after the operation).
    base_dir : str, optional
        The simulation working directory (the folder of the simulation
        main file), relative to the run directory — passed to the
        component writer so referenced file paths are re-written
        relative to it, exactly as IWFM resolves them. Without it the
        writer emits the parsed path strings as-is, which survives one
        rewrite only when the run directory equals the simulation
        working directory. Actions sharing a target file must agree on
        it.
    """

    reader: str
    path: str
    table: str
    column: str
    values_file: str
    key_cols: Tuple[str, ...] = ()
    op: str = "multiply"
    lower: Optional[float] = None
    upper: Optional[float] = None
    base_dir: Optional[str] = None

    def __post_init__(self):
        if self.op not in ("multiply", "replace", "add"):
            raise ValueError(
                f"op must be 'multiply', 'replace', or 'add', got {self.op!r}")
        if self.reader not in ("gw_main", "stream_main", "subsidence"):
            raise ValueError(f"unknown reader {self.reader!r}")


def _walk_table_path(obj, parts):
    for p in parts:
        if isinstance(obj, (list, tuple)):
            obj = obj[int(p)]
        elif isinstance(obj, dict):
            obj = obj[p]
        else:
            obj = getattr(obj, p)
    return obj


def _resolve_table(obj, table: str):
    """Fetch a (possibly nested) table: attributes, list indices, dict
    keys along a dotted path (``"parametric_grids.0.params"``)."""
    try:
        return _walk_table_path(obj, str(table).split("."))
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        return None


def _assign_table(obj, table: str, value) -> None:
    parts = str(table).split(".")
    parent = _walk_table_path(obj, parts[:-1])
    last = parts[-1]
    if isinstance(parent, list):
        parent[int(last)] = value
    elif isinstance(parent, dict):
        parent[last] = value
    else:
        setattr(parent, last, value)


def _apply_one(df, action: ApplyAction, values: "pd.DataFrame"):
    col = action.column
    if col not in df.columns:
        raise KeyError(
            f"{action.table} has no column {col!r}; available: "
            f"{list(df.columns)}")
    if not action.key_cols:
        if len(values) != 1:
            raise ValueError(
                f"{action.values_file}: keyless action needs exactly one "
                f"value row, found {len(values)}")
        v = float(values["value"].iloc[0])
        applied = pd.Series(v, index=df.index)
        mask = pd.Series(True, index=df.index)
    else:
        for k in action.key_cols:
            if k not in df.columns or k not in values.columns:
                raise KeyError(
                    f"key column {k!r} missing from "
                    f"{'table' if k not in df.columns else 'values file'}")
        keys = list(action.key_cols)
        if len(values) == 0:
            raise ValueError(
                f"{action.values_file}: no value rows (header only)")
        dup = values.duplicated(keys)
        if dup.any():
            raise ValueError(
                f"{action.values_file}: {int(dup.sum())} duplicate key "
                f"row(s), e.g. {values.loc[dup, keys].head(3).to_dict('records')}")
        merged = df[keys].merge(values, on=keys, how="left")
        if len(merged) != len(df):
            raise ValueError(
                f"{action.table}: key columns {keys} are not unique in the "
                "table — cannot apply values by key")
        unmatched = values.merge(
            df[list(action.key_cols)].drop_duplicates(),
            on=list(action.key_cols), how="left", indicator=True)
        bad = unmatched[unmatched["_merge"] == "left_only"]
        if len(bad):
            raise KeyError(
                f"{action.values_file}: {len(bad)} value row(s) match no "
                f"{action.table} row, e.g. "
                f"{bad[list(action.key_cols)].head(3).to_dict('records')}")
        applied = pd.Series(merged["value"].values, index=df.index)
        mask = applied.notna()

    finite = np.isfinite(pd.to_numeric(values["value"], errors="coerce")
                         .to_numpy(dtype=float))
    if not finite.all():
        raise ValueError(
            f"{action.values_file}: {int((~finite).sum())} non-numeric, NaN "
            "or infinite value(s) — a PEST value file must be complete")
    base = pd.to_numeric(df[col], errors="coerce")
    if action.op == "multiply":
        new = base.where(~mask, base * applied)
    elif action.op == "add":
        new = base.where(~mask, base + applied)
    else:
        new = base.where(~mask, applied)
    if action.lower is not None or action.upper is not None:
        clipped = new.clip(lower=action.lower, upper=action.upper)
        n_clip = int((clipped != new)[mask].sum())
        if n_clip:
            logger.warning("%s.%s: %d value(s) clipped to bounds",
                           action.table, col, n_clip)
        new = clipped
    df = df.copy()
    df[col] = new
    return df, int(mask.sum())


PRISTINE_SUFFIX = ".base"


def pristine_path(target) -> Path:
    """The pristine snapshot a target file is parameterised from
    (``<file>.base`` next to it)."""
    target = Path(target)
    return target.with_name(target.name + PRISTINE_SUFFIX)


def ensure_pristine(target, *, warn: bool = True) -> Path:
    """Create ``<file>.base`` from *target* if it does not exist yet.

    :class:`~iwfm_io.pest.setup.PestSetup` creates the snapshots at
    template time; creating one lazily here means the first apply in
    this directory defines "pristine" — fine on a fresh template, and
    warned about because on a directory that has already been
    parameterised it would freeze the current values as the base.
    """
    target = Path(target)
    base = pristine_path(target)
    if not base.exists():
        if not target.is_file():
            raise FileNotFoundError(f"apply target not found: {target}")
        shutil.copy2(target, base)
        if warn:
            warnings.warn(
                f"created pristine snapshot {base.name} from the current "
                f"{target.name}; run PestSetup.write on a fresh model copy "
                "to snapshot at template time", stacklevel=3)
    return base


def apply_parameters(run_dir, actions: Sequence[ApplyAction],
                     log_path: str = "apply_parameters_log.csv") -> "pd.DataFrame":
    """Apply all value files onto the model inputs (forward-run step).

    Reads each target's **pristine snapshot** (``<file>.base``, created
    by :meth:`PestSetup.write` or on first use) once, applies every
    action to it, and rewrites the live file atomically through the
    package writer — so repeated forward runs in the same directory
    never compound multipliers. A bookkeeping CSV records what was
    applied where.

    Parameters
    ----------
    run_dir : path
        The run directory (paths inside actions are relative to it).
    actions : sequence of ApplyAction
    log_path : str
        Bookkeeping CSV (relative to *run_dir*); pass None to skip.

    Returns
    -------
    pandas.DataFrame
        The bookkeeping table: one row per action with counts and
        value ranges.
    """
    run_dir = Path(run_dir)
    registry = _registry()
    by_file: dict = {}
    for a in actions:
        by_file.setdefault((a.reader, a.path), []).append(a)

    log_rows = []
    for (reader, rel), acts in by_file.items():
        read_fn, write_fn = registry[reader]
        target = run_dir / rel
        bases = {a.base_dir for a in acts}
        if len(bases) > 1:
            raise ValueError(
                f"actions targeting {rel} disagree on base_dir: "
                f"{sorted(str(b) for b in bases)}")
        base_dir = bases.pop()
        if base_dir is None:
            raise ValueError(
                f"actions targeting {rel} need base_dir (the simulation "
                "working directory, relative to the run directory) — "
                "without it the writer emits absolute paths IWFM rejects")
        obj = read_fn(ensure_pristine(target))
        for a in acts:
            df = _resolve_table(obj, a.table)
            if not isinstance(df, pd.DataFrame):
                raise KeyError(
                    f"{reader} result has no DataFrame table {a.table!r}")
            values = pd.read_csv(run_dir / a.values_file)
            if "value" not in values.columns:
                raise ValueError(
                    f"{a.values_file} needs a 'value' column")
            new_df, n = _apply_one(df, a, values)
            _assign_table(obj, a.table, new_df)
            log_rows.append({
                "reader": reader, "path": rel, "table": a.table,
                "column": a.column, "op": a.op,
                "values_file": a.values_file, "n_applied": n,
                "min_value": float(values["value"].min()),
                "max_value": float(values["value"].max()),
            })
        write_fn(obj, target, base_dir=run_dir / base_dir)
    log = pd.DataFrame(log_rows)
    if log_path is not None:
        replace_file_text(run_dir / log_path, log.to_csv(index=False))
    return log


# ------------------------------------------------------- overwrite file
_OVW_HEADER = """C*******************************************************************************
C  IWFM Groundwater Parameter Over-write File
C  (generated by iwfm_io.pest — rows: node, layer, {cols};
C   -1 keeps the value from the main file)
C*******************************************************************************
"""


def write_gw_overwrite(path, df, factors=None,
                       time_unit: str = "1MON") -> None:
    """Write an IWFM groundwater parameter overwrite file.

    Parameters
    ----------
    path : path
    df : pandas.DataFrame
        Columns ``node, layer`` plus any of ``pkh, ps, pn, pv, pl,
        sce, sci``. Missing columns / NaN cells become ``-1`` (keep the
        main-file value).
    factors : sequence of 7 floats, optional
        FKH, FS, FN, FV, FL, FSCE, FSCI conversion factors (default all
        1.0).
    time_unit : str, default "1MON"
        Time unit for the conductivity entries (TUNITKH/TUNITV/TUNITL).
    """
    if not {"node", "layer"} <= set(df.columns):
        raise ValueError("df needs 'node' and 'layer' columns")
    factors = list(factors) if factors is not None else [1.0] * 7
    if len(factors) != 7:
        raise ValueError("factors must have 7 entries (FKH FS FN FV FL "
                         "FSCE FSCI)")
    work = df.copy()
    for c in OVERWRITE_COLUMNS:
        if c not in work.columns:
            work[c] = -1.0
    work[OVERWRITE_COLUMNS] = work[OVERWRITE_COLUMNS].fillna(-1.0)

    lines = [_OVW_HEADER.format(cols=" ".join(
        c.upper() for c in OVERWRITE_COLUMNS)).rstrip("\n")]
    lines.append(f"    {len(work)}                     / NWRITE")
    lines.append("    " + "  ".join(f"{f:g}" for f in factors)
                 + "        / FKH FS FN FV FL FSCE FSCI")
    for kw in ("TUNITKH", "TUNITV", "TUNITL"):
        lines.append(f"    {time_unit}                  / {kw}")
    for _, r in work.iterrows():
        vals = "\t".join(f"{float(r[c]):.6G}" for c in OVERWRITE_COLUMNS)
        lines.append(f"\t{int(r['node'])}\t{int(r['layer'])}\t{vals}")
    replace_file_text(Path(path), "\n".join(lines) + "\n")


def read_gw_overwrite(path) -> "pd.DataFrame":
    """Read an IWFM groundwater parameter overwrite file.

    Returns a DataFrame ``node, layer, pkh, ps, pn, pv, pl, sce, sci``
    (``-1`` = not overwritten) with ``.attrs["factors"]`` and
    ``.attrs["time_unit"]``.
    """
    rows, factors, time_unit, nwrite = [], None, None, None
    for raw in Path(path).read_text().splitlines():
        if not raw.strip() or raw.lstrip()[0] in "Cc*/":
            continue
        data = raw.split("/")[0].split()
        if nwrite is None:
            nwrite = int(data[0])
            continue
        if factors is None:
            factors = [float(x) for x in data[:7]]
            continue
        if time_unit is None and not data[0].lstrip("-+").replace(
                ".", "").isdigit():
            if time_unit is None:
                time_unit = data[0]
            continue
        if len(data) >= 9:
            rows.append([int(data[0]), int(data[1])]
                        + [float(x) for x in data[2:9]])
    out = pd.DataFrame(rows, columns=["node", "layer"] + OVERWRITE_COLUMNS)
    if nwrite is not None and len(out) != nwrite:
        logger.warning("%s: NWRITE=%d but %d row(s) parsed",
                       path, nwrite, len(out))
    out.attrs["factors"] = factors
    out.attrs["time_unit"] = time_unit
    return out
