"""DLL-faithful temporal aggregation for IWFM budget and zone-budget data.

This module implements the exact aggregation semantics of the IWFM DLL /
Budget post-processor, verified against the IWFM 2025.0.1747 Fortran source
(public issues #33/#34):

- ``Class_Budget.f90`` (``ReadData_SelectedColumns_FromHDFFile``): the
  window loop and the per-data-type accumulation rules.
- ``Class_ZBudget.f90`` (``AccumulateData``): the same rules applied per
  element *before* zone summation.
- ``TimeSeriesUtilities.f90`` (``IncrementJulianDateAndMinutesAfterMidnight``):
  output windows advance by *calendar* months/years from the output begin
  time (with end-of-month stickiness for 24:00 stamps), which in this
  library's 24:00-converted datetime space is exactly
  ``period_begin + DateOffset(months=n)``.

Key semantics (all confirmed in the Fortran):

- **Windows are anchored to the data begin**, not the calendar: ``1YEAR``
  means consecutive 12-month blocks starting at the first timestep — for
  the usual October-start California models that is the water year, stamped
  ``09/30_24:00``. A trailing partial window is *not* emitted (the DLL
  exits before printing it).
- **Per-type rules**: volumetric rates (types 1, 9, 10, 11) sum; beginning
  storage (2) takes the window's first value; ending storage (3), area (4)
  and length (5) take the last value.
- **LWU carry-over** (types 6/7/8): within a window the modified ag supply
  requirement is ``req[t] - prev_short`` when ``prev_short > 0`` and
  ``req[t] > prev_short``, else ``req[t]`` — where ``prev_short`` is the
  *raw* shortage column value of the previous native step (NOT the
  recomputed shortage), reset to 0 at each window start. Supply
  requirement (7) sums the modified values; shortage (8) sums
  ``modified - pumping - deliveries`` minus the summed other-inflow column
  (type 11) when present — signed, never clipped; potential CUAW (6) sums
  ``potcuaw[t] * modified[t] / req[t]``, contributing nothing at steps
  where ``req[t] == 0``. Windows containing a single native step take the
  raw column values directly.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data-type constants (from Fortran Budget_Parameters.f90)
# ---------------------------------------------------------------------------

VR = 1            # Volumetric rate -> sum
VLB = 2           # Volume at beginning -> first
VLE = 3           # Volume at end -> last
AR = 4            # Area -> last
LT = 5            # Length -> last
VR_LWU_POTCUAW = 6      # Potential CUAW (special LWU)
VR_LWU_AGSUPPLYREQ = 7  # Ag supply requirement (special LWU)
VR_LWU_AGSHORT = 8      # Ag shortage (special LWU)
VR_LWU_AGPUMP = 9       # Ag pumping -> sum
VR_LWU_AGDIV = 10       # Ag deliveries -> sum
VR_LWU_AGOTHIN = 11     # Ag other inflows -> sum

_SUM_TYPES = {VR, VR_LWU_AGPUMP, VR_LWU_AGDIV, VR_LWU_AGOTHIN}
_FIRST_TYPES = {VLB}
_LAST_TYPES = {VLE, AR, LT}
_LWU_SPECIAL_TYPES = {VR_LWU_POTCUAW, VR_LWU_AGSUPPLYREQ, VR_LWU_AGSHORT}

#: Supported resampling interval tokens. ``1MON`` and ``1YEAR`` follow DLL
#: semantics (windows anchored to the data begin, trailing partial window
#: dropped); ``1CALYEAR`` aggregates over calendar years (Jan-anchored, all
#: windows kept — possibly partial at both ends).
SUPPORTED_INTERVALS = ("1MON", "1YEAR", "1CALYEAR")

_MARKER_RE = re.compile(r"\s*@[^@]*@")


def strip_zbudget_marker(name: str) -> str:
    """Strip the ``@...@`` unit-template annotation from a zbudget data name.

    Zone-budget ``FullDataNames`` entries carry a marker section holding a
    unit template (e.g. ``'Non-ponded Ag. Area@        (2)@'``); the DLL's
    ``GetFullColumnHeaders`` replaces it with unit text.  This library
    serves raw file units, so the marker is simply removed:
    ``'Non-ponded Ag. Area'``.
    """
    return _MARKER_RE.sub("", name).strip()


# ---------------------------------------------------------------------------
# Simulation-anchored aggregation windows
# ---------------------------------------------------------------------------

def native_step_offset(
    native_unit: Optional[str] = None,
    delta_minutes: Optional[Union[int, float]] = None,
    index: Optional[pd.DatetimeIndex] = None,
):
    """Best-effort native timestep as a DateOffset/timedelta.

    Month/year units use calendar offsets (their minute counts are nominal);
    anything else uses ``delta_minutes``, falling back to the index spacing
    and finally to one day.
    """
    unit = (native_unit or "").strip().upper()
    m = re.match(r"^(\d+)(MON|YEAR)$", unit)
    if m:
        n = int(m.group(1))
        if m.group(2) == "MON":
            return pd.DateOffset(months=n)
        return pd.DateOffset(years=n)
    if delta_minutes:
        return timedelta(minutes=int(delta_minutes))
    if index is not None and len(index) > 1:
        return index[1] - index[0]
    return timedelta(days=1)


def window_end_labels(
    index: pd.DatetimeIndex,
    interval: str,
    native_unit: Optional[str] = None,
    delta_minutes: Optional[Union[int, float]] = None,
) -> Tuple[pd.DatetimeIndex, np.ndarray]:
    """Assign each timestamp to its aggregation window (DLL semantics).

    Timestamps are the library's 24:00-converted end-of-step stamps (a step
    stamped ``T`` covers ``(T - step, T]``).  Window *n* covers stamps in
    ``(anchor + n*interval, anchor + (n+1)*interval]`` where *anchor* is the
    begin of the first step (``index[0] - native_step``) for ``1MON``/
    ``1YEAR`` — the DLL's output-begin anchoring — or January 1 of the first
    step's owning year for ``1CALYEAR``.  The label is the window's end
    boundary, which equals the IWFM end-of-window stamp (e.g.
    ``09/30/1988_24:00`` -> ``1988-10-01``).

    Returns
    -------
    labels : DatetimeIndex
        Window end label for each entry of *index*.
    complete : ndarray of bool
        False for rows in a trailing partial window (label beyond the last
        stamp).  The DLL does not emit that window; drop these rows for
        DLL-faithful output.  For ``1CALYEAR`` all rows are True (partial
        first/last calendar years are kept).
    """
    interval_u = str(interval).upper()
    if interval_u not in SUPPORTED_INTERVALS:
        raise ValueError(
            f"Unsupported interval '{interval}'. "
            f"Use one of {', '.join(SUPPORTED_INTERVALS)}."
        )
    if len(index) == 0:
        return pd.DatetimeIndex([]), np.zeros(0, dtype=bool)

    step_months = 1 if interval_u == "1MON" else 12
    step = native_step_offset(native_unit, delta_minutes, index)
    first_begin = index[0] - step
    if interval_u == "1CALYEAR":
        anchor = pd.Timestamp(year=first_begin.year, month=1, day=1)
    else:
        anchor = pd.Timestamp(first_begin)

    last = index[-1]
    bounds: List[pd.Timestamp] = []
    i = 1
    while True:
        b = anchor + pd.DateOffset(months=step_months * i)
        bounds.append(b)
        if b >= last:
            break
        i += 1
    bounds_idx = pd.DatetimeIndex(bounds)

    pos = np.searchsorted(bounds_idx.values, index.values, side="left")
    labels = bounds_idx[pos]

    if interval_u == "1CALYEAR":
        complete = np.ones(len(index), dtype=bool)
    else:
        complete = labels.values <= np.datetime64(last)
    return labels, complete


def _window_starts(labels: np.ndarray) -> np.ndarray:
    """0-based start row of each window in an ordered label array."""
    if len(labels) == 0:
        return np.zeros(0, dtype=np.intp)
    change = np.r_[True, labels[1:] != labels[:-1]]
    return np.flatnonzero(change)


# ---------------------------------------------------------------------------
# LWU group identification
# ---------------------------------------------------------------------------

_LWU_ROLE_TYPES = (
    ("pot_cuaw", VR_LWU_POTCUAW),
    ("supply_req", VR_LWU_AGSUPPLYREQ),
    ("shortage", VR_LWU_AGSHORT),
    ("pumping", VR_LWU_AGPUMP),
    ("deliveries", VR_LWU_AGDIV),
    ("other_inflow", VR_LWU_AGOTHIN),
)


def identify_lwu_groups(
    col_names: List[str],
    col_types: Dict[str, int],
) -> List[Dict[str, str]]:
    """Identify LWU column groups that must be aggregated together.

    When exactly one type-7 (supply requirement) column exists, the group is
    formed from the first occurrence of each LWU type — the DLL's
    ``LocateInList`` semantics, robust to column reordering.  With multiple
    type-7 columns an adjacency walk is used: each anchors a group with the
    nearest type-6 before it and types 8/9/10/11 after it (stopping at the
    next group's columns).

    Returns a list of dicts mapping role -> column name; roles are among
    ``pot_cuaw``, ``supply_req``, ``shortage``, ``pumping``, ``deliveries``,
    ``other_inflow``.
    """
    anchors = [c for c in col_names if col_types.get(c) == VR_LWU_AGSUPPLYREQ]

    if len(anchors) == 1:
        group: Dict[str, str] = {}
        for role, tcode in _LWU_ROLE_TYPES:
            for c in col_names:
                if col_types.get(c) == tcode:
                    group[role] = c
                    break
        return [group]

    groups: List[Dict[str, str]] = []
    for i, col in enumerate(col_names):
        if col_types.get(col) != VR_LWU_AGSUPPLYREQ:
            continue

        group = {"supply_req": col}

        # Look backwards for pot_cuaw (type 6) — usually immediately before
        for j in range(i - 1, max(i - 3, -1), -1):
            if col_types.get(col_names[j]) == VR_LWU_POTCUAW:
                group["pot_cuaw"] = col_names[j]
                break

        # Look forwards for pumping (9), deliveries (10), other inflow (11),
        # shortage (8); stop at the next group's anchor columns.
        for j in range(i + 1, min(i + 7, len(col_names))):
            t = col_types.get(col_names[j])
            if t in (VR_LWU_POTCUAW, VR_LWU_AGSUPPLYREQ):
                break
            if t == VR_LWU_AGPUMP and "pumping" not in group:
                group["pumping"] = col_names[j]
            elif t == VR_LWU_AGDIV and "deliveries" not in group:
                group["deliveries"] = col_names[j]
            elif t == VR_LWU_AGOTHIN and "other_inflow" not in group:
                group["other_inflow"] = col_names[j]
            elif t == VR_LWU_AGSHORT and "shortage" not in group:
                group["shortage"] = col_names[j]

        groups.append(group)

    return groups


# ---------------------------------------------------------------------------
# Vectorized LWU carry-over aggregation
# ---------------------------------------------------------------------------

def lwu_aggregate_arrays(
    starts: np.ndarray,
    req: np.ndarray,
    short: Optional[np.ndarray],
    pump: Optional[np.ndarray],
    div: Optional[np.ndarray],
    other: Optional[np.ndarray],
    potcuaw: Optional[np.ndarray],
) -> Dict[str, np.ndarray]:
    """DLL LWU carry-over aggregation over precomputed windows.

    Arrays are ``(T,)`` or ``(T, K)`` (K independent series, e.g. elements)
    ordered chronologically; *starts* are the window start rows.  ``None``
    inputs are treated as zeros (``potcuaw=None`` omits that output).

    Returns a dict with ``'supply_req'``, ``'shortage'`` and (when *potcuaw*
    is given) ``'pot_cuaw'`` mapped to ``(W,)`` / ``(W, K)`` aggregates.
    """
    req = np.asarray(req, dtype=np.float64)
    T = req.shape[0]

    def _z(x):
        return np.zeros_like(req) if x is None else np.asarray(x, dtype=np.float64)

    short_r = _z(short)
    pump_r = _z(pump)
    div_r = _z(div)
    other_r = _z(other)

    # prev_short[t] = raw shortage of the previous native step, reset to 0
    # at each window start (Class_Budget.f90: rAgShortPrevious).
    prev = np.empty_like(short_r)
    prev[1:] = short_r[:-1]
    prev[0] = 0.0
    prev[starts] = 0.0

    modified = np.where((prev > 0.0) & (req > prev), req - prev, req)

    def _rsum(x):
        return np.add.reduceat(x, starts, axis=0)

    out: Dict[str, np.ndarray] = {}
    out["supply_req"] = _rsum(modified)
    out["shortage"] = _rsum(modified - pump_r - div_r) - _rsum(other_r)
    if potcuaw is not None:
        pc = np.asarray(potcuaw, dtype=np.float64)
        scaled = np.zeros_like(pc)
        np.divide(modified * pc, req, out=scaled, where=(req != 0.0))
        out["pot_cuaw"] = _rsum(scaled)

    # Single-step windows take the raw column value (Fortran
    # NAccumIntervals == 1 branch) — notably PotCUAW even when req == 0.
    sizes = np.diff(np.r_[starts, T])
    single = sizes == 1
    if single.any():
        rows = starts[single]
        out["supply_req"][single] = req[rows]
        if short is not None:
            out["shortage"][single] = short_r[rows]
        else:
            out["shortage"][single] = (req - pump_r - div_r - other_r)[rows]
        if potcuaw is not None:
            out["pot_cuaw"][single] = np.asarray(potcuaw, dtype=np.float64)[rows]

    return out


# ---------------------------------------------------------------------------
# Frame-level aggregation
# ---------------------------------------------------------------------------

def aggregate_frame(
    df: pd.DataFrame,
    col_types: Dict[str, int],
    labels,
    complete_mask: Optional[np.ndarray] = None,
    default_type: int = VR,
) -> pd.DataFrame:
    """Aggregate a wide DataFrame over window labels with IWFM type rules.

    Parameters
    ----------
    df : DataFrame
        Chronologically ordered data (one column per budget component).
    col_types : dict
        column name -> IWFM data type code (1-11).  Missing columns use
        *default_type*.
    labels : array-like
        Window label per row (datetimes from :func:`window_end_labels`, or
        any ordered labels such as water-year integers).
    complete_mask : ndarray of bool, optional
        Rows to keep (False rows — a trailing partial window — are dropped
        before aggregation).

    Returns
    -------
    DataFrame indexed by the unique window labels, same columns as *df*.
    """
    labels_arr = np.asarray(labels)
    if complete_mask is not None and not np.all(complete_mask):
        df = df.loc[np.asarray(complete_mask)]
        labels_arr = labels_arr[np.asarray(complete_mask)]

    index_name = df.index.name or "datetime"
    if len(df) == 0:
        empty_idx = pd.DatetimeIndex([], name=index_name) \
            if np.issubdtype(labels_arr.dtype, np.datetime64) \
            else pd.Index([], name=index_name)
        return pd.DataFrame(columns=df.columns, index=empty_idx, dtype=float)

    starts = _window_starts(labels_arr)
    ends = np.r_[starts[1:], len(labels_arr)] - 1
    ulabels = labels_arr[starts]

    values = df.to_numpy(dtype=np.float64)
    columns = list(df.columns)
    types = np.array([col_types.get(c, default_type) for c in columns])
    out = np.zeros((len(starts), len(columns)))

    sum_cols = np.flatnonzero(np.isin(types, list(_SUM_TYPES)))
    if len(sum_cols):
        out[:, sum_cols] = np.add.reduceat(values[:, sum_cols], starts, axis=0)
    first_cols = np.flatnonzero(np.isin(types, list(_FIRST_TYPES)))
    if len(first_cols):
        out[:, first_cols] = values[np.ix_(starts, first_cols)]
    last_cols = np.flatnonzero(np.isin(types, list(_LAST_TYPES)))
    if len(last_cols):
        out[:, last_cols] = values[np.ix_(ends, last_cols)]

    lwu_cols = np.flatnonzero(np.isin(types, list(_LWU_SPECIAL_TYPES)))
    if len(lwu_cols):
        colpos = {c: i for i, c in enumerate(columns)}
        handled: set = set()
        for group in identify_lwu_groups(columns, col_types):
            if "supply_req" not in group:
                continue

            def _arr(role):
                return values[:, colpos[group[role]]] if role in group else None

            res = lwu_aggregate_arrays(
                starts,
                _arr("supply_req"), _arr("shortage"), _arr("pumping"),
                _arr("deliveries"), _arr("other_inflow"), _arr("pot_cuaw"),
            )
            for role, key in (("supply_req", "supply_req"),
                              ("shortage", "shortage"),
                              ("pot_cuaw", "pot_cuaw")):
                if role in group and key in res:
                    out[:, colpos[group[role]]] = res[key]
                    handled.add(group[role])
        orphans = [columns[i] for i in lwu_cols if columns[i] not in handled]
        if orphans:
            logger.warning(
                "LWU special columns %s have no identifiable supply-"
                "requirement group; aggregating as plain sums.", orphans)
            for c in orphans:
                i = colpos[c]
                out[:, i] = np.add.reduceat(values[:, i], starts)

    if np.issubdtype(labels_arr.dtype, np.datetime64):
        idx = pd.DatetimeIndex(ulabels, name=index_name)
    else:
        idx = pd.Index(ulabels, name=index_name)
    return pd.DataFrame(out, index=idx, columns=df.columns)
