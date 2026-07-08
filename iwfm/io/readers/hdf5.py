"""Readers for IWFM HDF5 output files.

All IWFM HDF5 output files share a common structure:

Budget files (GW.hdf, StrmBud.hdf, LakeBud.hdf, RootZone.hdf, LWU.hdf,
DiverDetail.hdf, SWShed.hdf, UnsatZoneBud.hdf, StrmNodeBud.hdf):
    - Top-level groups are location/subregion dataset names.
    - Each dataset has shape (n_timesteps, n_cols).
    - Column 0 is an internal IWFM time marker (NOT a usable date); actual
      dates are reconstructed from the ``Attributes/`` group TimeStep metadata.
    - Columns 1+ are data values; column names come from the
      ``LocationDataN%cFullColumnHeaders`` attribute (which starts with a
      'Time' placeholder that is skipped).

Hydrograph files (GWHyd.hdf, StrmHyd.hdf, Subsidence.hdf, TileDrainFlows.hdf):
    - Single top-level dataset; all columns are data values (no date column).
    - Dates reconstructed from TimeStep attributes.
    - No column-header metadata available; generic names are used.

Head file (GWHeadAll.hdf):
    - Single dataset ``GWHeadAtAllNode`` with shape
      (n_timesteps, n_nodes * n_layers).
    - All columns are data; columns named ``node_N_layer_M`` when n_nodes and
      n_layers are supplied, otherwise ``col_1``, ``col_2``, …

Zone Budget files (GW_ZBud.hdf, RootZone_ZBud.hdf, LWU_ZBud.hdf,
UnsatZone_ZBud.hdf):
    - ``Attributes/`` group holds TimeStep metadata, ``FullDataNames``,
      ``Layer{N}_ElemDataColumns`` mapping arrays, and ``SystemData%*``
      datasets (element IDs/areas, face connectivity, node areas).
    - ``Layer_{N}/`` groups contain per-data-type datasets with shape
      ``(n_timesteps, n_cols)`` plus ``FaceFlows`` and ``VerticalFlows``.
    - Aggregation to user-defined zones requires a zone definition file.

Public API
----------
_excel_to_datetime(dates_array)
read_budget_hdf(path) -> dict
read_hydrograph_hdf(path) -> pandas.DataFrame
read_head_hdf(path, n_nodes=None, n_layers=None) -> pandas.DataFrame
read_zone_def(path) -> ZoneDefinition
read_zbudget_hdf(path, zone_def=None, interval=None) -> dict
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from iwfm.io.models.base import ZoneDefinition

try:
    import h5py
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "h5py is required for HDF5 file reading. "
        "Install it with:  pip install h5py"
    ) from exc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _excel_to_datetime(dates_array) -> List[datetime]:
    """Convert an array of Excel serial date numbers to Python datetime objects.

    IWFM stores some timestamps as floating-point days since the Excel epoch
    (1899-12-30).  This function converts an array (or scalar) of such values
    to a list of :class:`datetime.datetime` objects.

    Parameters
    ----------
    dates_array:
        A scalar, list, or numpy array of Excel serial date floats.

    Returns
    -------
    list of datetime
        One entry per input value.  Scalar input returns a one-element list.
    """
    base = datetime(1899, 12, 30)
    if np.isscalar(dates_array):
        return [base + timedelta(days=float(dates_array))]
    return [base + timedelta(days=float(d)) for d in dates_array]


def _parse_iwfm_date(date_str: str) -> datetime:
    """Parse an IWFM date string ``'MM/DD/YYYY_HH:MM'`` to a datetime.

    Hour 24:00 is treated as midnight on the following day, matching the
    IWFM convention for end-of-day timestamps.

    Parameters
    ----------
    date_str:
        Date string in IWFM format, e.g. ``'10/01/1990_24:00'``.

    Returns
    -------
    datetime
    """
    date_str = date_str.strip()
    date_part, time_part = date_str.split("_")
    month, day, year = date_part.split("/")
    hour, minute = time_part.split(":")
    hour = int(hour)
    minute = int(minute)

    if hour == 24:
        # End-of-day: advance to next calendar day at 00:00
        return datetime(int(year), int(month), int(day)) + timedelta(days=1)
    return datetime(int(year), int(month), int(day), hour, minute)


def _decode_bytes(value) -> str:
    """Decode a bytes or numpy bytes_ scalar to a stripped str."""
    if isinstance(value, (bytes, np.bytes_)):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _build_date_index(attrs: "h5py.AttributeManager") -> pd.DatetimeIndex:
    """Build a DatetimeIndex from IWFM TimeStep attributes.

    The Attributes group on every IWFM HDF5 file contains:
    - ``TimeStep%BeginDateAndTime``:  'MM/DD/YYYY_HH:MM' string
    - ``TimeStep%DeltaT_InMinutes``: integer minutes per step
    - ``NTimeSteps``:                number of time steps

    Parameters
    ----------
    attrs:
        HDF5 attribute manager for the ``Attributes/`` group.

    Returns
    -------
    pd.DatetimeIndex
        Length ``NTimeSteps``, one entry per model output step.
    """
    begin_raw = attrs.get("TimeStep%BeginDateAndTime", b"01/01/1900_00:00")
    begin_str = _decode_bytes(begin_raw)
    begin = _parse_iwfm_date(begin_str)

    n_ts = int(attrs.get("NTimeSteps", 0))

    # Monthly/annual steps are calendar intervals: DeltaT_InMinutes holds a
    # nominal length (1MON = 43200 min = 30 days), and stepping by it drifts
    # ~5 days/year against real month ends. Use calendar offsets instead.
    unit = _decode_bytes(attrs.get("TimeStep%Unit", b"")).strip().upper()
    m = re.match(r"^(\d+)(MON|YEAR)$", unit)
    if m:
        step = int(m.group(1))
        key = "months" if m.group(2) == "MON" else "years"
        dates = [begin + pd.DateOffset(**{key: step * i}) for i in range(n_ts)]
        return pd.DatetimeIndex(dates)

    delta_minutes = int(attrs.get("TimeStep%DeltaT_InMinutes", 1440))
    dates = [begin + timedelta(minutes=i * delta_minutes) for i in range(n_ts)]
    return pd.DatetimeIndex(dates)


def _extract_column_headers(
    root_attrs: "h5py.AttributeManager",
    location_index: int,
    n_data_cols: int,
) -> List[str]:
    """Extract column names for one budget location from root-level attributes.

    Attempts to read ``LocationDataN%cFullColumnHeaders`` where ``N`` is the
    1-based *location_index*.  Falls back to ``LocationData1`` when the
    per-location attribute is missing.  The first element of the header array
    is always the literal string 'Time' (an IWFM artifact) and is skipped;
    the remainder are used as column names.

    If no attribute can be found, or the attribute has fewer entries than
    expected, generic names ``col_1``, ``col_2``, … are generated for the
    remaining positions.

    Parameters
    ----------
    root_attrs:
        Attribute manager of the top-level ``Attributes/`` group.
    location_index:
        1-based index of the location within the file.
    n_data_cols:
        Number of data columns to name (excludes the internal time column 0).

    Returns
    -------
    list of str
        Length ``n_data_cols``.
    """
    # Try the per-location key first, then fall back to LocationData1
    candidates = [
        f"LocationData{location_index}%cFullColumnHeaders",
        "LocationData1%cFullColumnHeaders",
    ]
    raw_headers: Optional[np.ndarray] = None
    for key in candidates:
        if key in root_attrs:
            raw_headers = root_attrs[key]
            break

    if raw_headers is None:
        logger.debug(
            "No column header attribute found for location %d; "
            "using generic names.",
            location_index,
        )
        return [f"col_{i + 1}" for i in range(n_data_cols)]

    # Decode all header strings
    decoded = [_decode_bytes(h) for h in raw_headers]

    # The first entry is always 'Time' (internal marker, not a dataset column)
    # so skip it.
    data_headers = decoded[1:] if decoded and decoded[0].lower() == "time" else decoded

    if len(data_headers) < n_data_cols:
        logger.debug(
            "Header array has %d entries but %d data columns; "
            "padding with generic names.",
            len(data_headers),
            n_data_cols,
        )
        data_headers += [
            f"col_{i + 1 + len(data_headers)}"
            for i in range(n_data_cols - len(data_headers))
        ]

    return data_headers[:n_data_cols]


# ---------------------------------------------------------------------------
# Data-type constants (from Fortran Budget_Parameters.f90)
# ---------------------------------------------------------------------------

VR = 1            # Volumetric rate -> sum
VLB = 2           # Volume at beginning -> first
VLE = 3           # Volume at end -> last
AR = 4            # Area -> last
LT = 5            # Length -> last
VR_LWU_POTCUAW = 6    # Potential CUAW (special LWU)
VR_LWU_AGSUPPLYREQ = 7  # Ag supply requirement (special LWU)
VR_LWU_AGSHORT = 8      # Ag shortage (special LWU)
VR_LWU_AGPUMP = 9       # Ag pumping -> sum
VR_LWU_AGDIV = 10       # Ag deliveries -> sum
VR_LWU_AGOTHIN = 11     # Ag other inflows -> sum

_SUM_TYPES = {VR, VR_LWU_AGPUMP, VR_LWU_AGDIV, VR_LWU_AGOTHIN}
_FIRST_TYPES = {VLB}
_LAST_TYPES = {VLE, AR, LT}
_LWU_SPECIAL_TYPES = {VR_LWU_POTCUAW, VR_LWU_AGSUPPLYREQ, VR_LWU_AGSHORT}


# ---------------------------------------------------------------------------
# LWU iterative aggregation helpers
# ---------------------------------------------------------------------------

def _identify_lwu_groups(
    col_names: List[str],
    col_types: Dict[str, int],
) -> List[Dict[str, str]]:
    """Identify groups of LWU special columns that must be aggregated together.

    Each LWU group is a repeating pattern of columns with types 6 (PotCUAW),
    7 (AgSupplyReq), 8 (AgShort), 9 (AgPump), 10 (AgDiv).  The group may
    also contain a type-4 Area column preceding it.

    Returns a list of dicts, each mapping role -> column_name:
        ``{'pot_cuaw': ..., 'supply_req': ..., 'shortage': ...,
          'pumping': ..., 'deliveries': ...}``
    """
    groups: List[Dict[str, str]] = []

    # Walk columns looking for supply_req (type 7) as the anchor
    for i, col in enumerate(col_names):
        if col_types.get(col) != VR_LWU_AGSUPPLYREQ:
            continue

        group: Dict[str, str] = {"supply_req": col}

        # Look backwards for pot_cuaw (type 6) — usually immediately before
        for j in range(i - 1, max(i - 3, -1), -1):
            if col_types.get(col_names[j]) == VR_LWU_POTCUAW:
                group["pot_cuaw"] = col_names[j]
                break

        # Look forwards for pumping (9), deliveries (10), shortage (8)
        for j in range(i + 1, min(i + 5, len(col_names))):
            t = col_types.get(col_names[j])
            if t == VR_LWU_AGPUMP and "pumping" not in group:
                group["pumping"] = col_names[j]
            elif t == VR_LWU_AGDIV and "deliveries" not in group:
                group["deliveries"] = col_names[j]
            elif t == VR_LWU_AGSHORT and "shortage" not in group:
                group["shortage"] = col_names[j]

        groups.append(group)

    return groups


def _lwu_aggregate_group(
    supply_req: np.ndarray,
    pumping: np.ndarray,
    deliveries: np.ndarray,
    pot_cuaw: Optional[np.ndarray],
) -> Tuple[float, float, Optional[float]]:
    """Aggregate one LWU group over a resampling period using carry-over logic.

    Implements the Fortran ``ModifiedAgSupplyReq`` algorithm
    (Class_Budget.f90:1988-2002):

    For each timestep *t* within the period:
      - If ``prev_shortage <= 0``: ``modified_req = supply_req[t]``
      - Elif ``supply_req[t] > prev_shortage``:
            ``modified_req = supply_req[t] - prev_shortage``
      - Else: ``modified_req = supply_req[t]``
      - ``shortage[t] = modified_req - pumping[t] - deliveries[t]``
      - ``prev_shortage = shortage[t]``

    Parameters
    ----------
    supply_req, pumping, deliveries : 1-D arrays
        Raw values for timesteps within the period.
    pot_cuaw : 1-D array or None
        Raw potential CUAW values, if this group has one.

    Returns
    -------
    agg_supply_req : float
        Sum of modified supply requirements.
    agg_shortage : float
        Sum of computed shortages.
    agg_pot_cuaw : float or None
        Sum of scaled potential CUAW, or None if *pot_cuaw* is None.
    """
    n = len(supply_req)
    prev_shortage = 0.0
    agg_supply_req = 0.0
    agg_shortage = 0.0
    agg_pot_cuaw = 0.0 if pot_cuaw is not None else None

    for t in range(n):
        raw_req = supply_req[t]

        if prev_shortage <= 0:
            modified_req = raw_req
        elif raw_req > prev_shortage:
            modified_req = raw_req - prev_shortage
        else:
            modified_req = raw_req

        short = modified_req - pumping[t] - deliveries[t]
        agg_supply_req += modified_req
        agg_shortage += short

        if pot_cuaw is not None and raw_req != 0:
            scale = modified_req / raw_req
            agg_pot_cuaw += pot_cuaw[t] * scale
        elif pot_cuaw is not None:
            agg_pot_cuaw += pot_cuaw[t]

        prev_shortage = short

    return agg_supply_req, agg_shortage, agg_pot_cuaw


def _resample_budget_df(
    df: pd.DataFrame,
    rule: str,
    col_types: Dict[str, int],
) -> pd.DataFrame:
    """Resample a budget DataFrame using data-type-aware aggregation.

    Parameters
    ----------
    df : DataFrame
        Budget data with DatetimeIndex.
    rule : str
        Pandas resample rule (e.g. ``"ME"`` for month-end, ``"YE"`` for
        year-end).
    col_types : dict
        Mapping of column name -> IWFM data type code (1-11).
        Columns not in *col_types* default to sum aggregation.

    Returns
    -------
    DataFrame
        Resampled data.
    """
    if df.empty:
        return df.resample(rule).sum()

    # Check whether any LWU special columns exist
    lwu_cols = {c for c in df.columns if col_types.get(c, VR) in _LWU_SPECIAL_TYPES}

    if not lwu_cols:
        # Fast path: no LWU special columns — use vectorised operations
        return _resample_simple(df, rule, col_types)

    # Slow path: need iterative LWU aggregation
    return _resample_with_lwu(df, rule, col_types)


def _resample_simple(
    df: pd.DataFrame,
    rule: str,
    col_types: Dict[str, int],
) -> pd.DataFrame:
    """Resample without LWU special columns (vectorised fast path)."""
    sum_cols = [c for c in df.columns if col_types.get(c, VR) in _SUM_TYPES]
    first_cols = [c for c in df.columns if col_types.get(c, VR) in _FIRST_TYPES]
    last_cols = [c for c in df.columns if col_types.get(c, VR) in _LAST_TYPES]

    parts: List[pd.DataFrame] = []
    if sum_cols:
        parts.append(df[sum_cols].resample(rule).sum())
    if first_cols:
        parts.append(df[first_cols].resample(rule).first())
    if last_cols:
        parts.append(df[last_cols].resample(rule).last())

    if not parts:
        return df.resample(rule).sum()

    merged = pd.concat(parts, axis=1)
    # Restore original column order
    return merged[[c for c in df.columns if c in merged.columns]]


def _resample_with_lwu(
    df: pd.DataFrame,
    rule: str,
    col_types: Dict[str, int],
) -> pd.DataFrame:
    """Resample with LWU special column carry-over logic."""
    # Identify LWU groups
    lwu_groups = _identify_lwu_groups(list(df.columns), col_types)

    # Columns handled by LWU groups
    lwu_handled: set = set()
    for g in lwu_groups:
        lwu_handled.update(g.values())

    # Handle non-LWU columns with vectorised resampling
    non_lwu_cols = [c for c in df.columns if c not in lwu_handled]
    non_lwu_types = {c: col_types.get(c, VR) for c in non_lwu_cols}

    if non_lwu_cols:
        non_lwu_result = _resample_simple(df[non_lwu_cols], rule, non_lwu_types)
    else:
        non_lwu_result = None

    # Handle LWU groups with iterative aggregation
    grouper = df.resample(rule)
    period_indices = list(grouper.indices.values())
    period_labels = list(grouper.indices.keys())

    lwu_results: Dict[str, List[float]] = {
        col: [] for col in lwu_handled
    }

    for period_idx in period_indices:
        period_df = df.iloc[period_idx]

        for g in lwu_groups:
            supply_req_col = g["supply_req"]
            pumping_col = g.get("pumping")
            deliveries_col = g.get("deliveries")
            shortage_col = g.get("shortage")
            pot_cuaw_col = g.get("pot_cuaw")

            raw_supply = period_df[supply_req_col].values
            raw_pump = period_df[pumping_col].values if pumping_col else np.zeros(len(period_df))
            raw_deliv = period_df[deliveries_col].values if deliveries_col else np.zeros(len(period_df))
            raw_cuaw = period_df[pot_cuaw_col].values if pot_cuaw_col else None

            agg_req, agg_short, agg_cuaw = _lwu_aggregate_group(
                raw_supply, raw_pump, raw_deliv, raw_cuaw
            )

            lwu_results[supply_req_col].append(agg_req)
            if shortage_col:
                lwu_results[shortage_col].append(agg_short)
            if pot_cuaw_col:
                lwu_results[pot_cuaw_col].append(
                    agg_cuaw if agg_cuaw is not None else 0.0
                )
            # Pumping and deliveries are sum types but handled via the group
            if pumping_col:
                lwu_results[pumping_col].append(float(raw_pump.sum()))
            if deliveries_col:
                lwu_results[deliveries_col].append(float(raw_deliv.sum()))

    # Build LWU DataFrame
    lwu_index = non_lwu_result.index if non_lwu_result is not None else pd.DatetimeIndex(period_labels)
    lwu_df = pd.DataFrame(lwu_results, index=lwu_index)

    # Merge and restore column order
    if non_lwu_result is not None:
        merged = pd.concat([non_lwu_result, lwu_df], axis=1)
    else:
        merged = lwu_df

    return merged[[c for c in df.columns if c in merged.columns]]


# ---------------------------------------------------------------------------
# Public readers
# ---------------------------------------------------------------------------

def read_budget_hdf(
    path: Union[str, Path],
    interval: Optional[str] = None,
) -> Dict:
    """Read an IWFM budget HDF5 file into a dictionary of DataFrames.

    Supports all multi-location budget files:
    ``GW.hdf``, ``StrmBud.hdf``, ``StrmNodeBud.hdf``, ``LakeBud.hdf``,
    ``RootZone.hdf``, ``LWU.hdf``, ``DiverDetail.hdf``, ``SWShed.hdf``,
    ``UnsatZoneBud.hdf``, and any future files following the same pattern.

    File layout
    -----------
    - ``Attributes/`` group holds TimeStep metadata and column-header arrays.
    - Every other top-level group is a location dataset with shape
      ``(n_timesteps, n_cols)`` where column 0 is an internal IWFM time
      marker (discarded here) and columns 1+ are the actual budget values.

    Parameters
    ----------
    path:
        Path to the HDF5 budget file.
    interval:
        Optional temporal resampling interval.  ``"1MON"`` for monthly,
        ``"1YEAR"`` for annual.  ``None`` returns native timestep data.
        Aggregation is data-type-aware: volumetric rates are summed,
        beginning storage uses first value, ending storage/area/length use
        last value, and LWU special columns use iterative carry-over logic.

    Returns
    -------
    dict with keys:

    ``'locations'`` : list of str
        Location/subregion names in file order.
    ``'data'`` : dict mapping location_name -> :class:`pandas.DataFrame`
        Each DataFrame has a :class:`pandas.DatetimeIndex` and columns named
        from the ``LocationDataN%cFullColumnHeaders`` attribute (first 'Time'
        entry stripped).  Generic names ``col_1``, ``col_2``, … are used when
        the attribute is absent.
    ``'data_types'`` : dict mapping column_name -> int
        IWFM data type code for each column (1-11).  Same mapping applies to
        all locations (controlled by ``NLocationData``).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    OSError
        If h5py cannot open the file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    resample_rule = None
    if interval is not None:
        rule_map = {"1MON": "ME", "1YEAR": "YE"}
        resample_rule = rule_map.get(interval.upper())
        if resample_rule is None:
            raise ValueError(
                f"Unsupported interval '{interval}'. Use '1MON' or '1YEAR'."
            )

    result: Dict = {"locations": [], "data": {}, "data_types": {}}

    with h5py.File(path, "r") as f:
        # Build shared DatetimeIndex from TimeStep attributes
        date_index = _build_date_index(f["Attributes"].attrs)
        root_attrs = f["Attributes"].attrs

        # Read data column types (same for all locations)
        raw_col_types: Optional[np.ndarray] = None
        type_key = "LocationData1%iDataColumnTypes"
        if type_key in root_attrs:
            raw_col_types = np.asarray(root_attrs[type_key])

        # Collect location dataset names (everything except 'Attributes')
        location_names = [k for k in f.keys() if k != "Attributes"]
        result["locations"] = location_names

        for loc_idx, loc_name in enumerate(location_names, start=1):
            item = f[loc_name]
            if not isinstance(item, h5py.Dataset):
                # Some files may nest groups; skip non-dataset items
                logger.debug("Skipping non-dataset item: %s", loc_name)
                continue

            raw = item[()]  # shape (n_timesteps, n_cols)

            if raw.ndim != 2:
                logger.warning(
                    "Unexpected dataset shape %s for '%s'; skipping.",
                    raw.shape,
                    loc_name,
                )
                continue

            n_rows, n_cols = raw.shape

            # The dataset holds exactly NDataColumns data columns — time is
            # normally NOT stored in the data matrix (it is reconstructed
            # from the TimeStep attributes); the header array merely starts
            # with a literal 'Time' artifact. Only drop a leading column if
            # the dataset really is one wider than NDataColumns.
            n_expected = int(
                root_attrs.get(
                    f"LocationData{loc_idx}%NDataColumns",
                    root_attrs.get("LocationData1%NDataColumns", 0),
                )
            )
            if n_expected and n_cols == n_expected + 1:
                data_cols = raw[:, 1:]
            else:
                data_cols = raw
            n_data_cols = data_cols.shape[1]

            col_names = _extract_column_headers(root_attrs, loc_idx, n_data_cols)

            # Build column-name -> data-type-code mapping
            col_types: Dict[str, int] = {}
            if raw_col_types is not None:
                for ci, cn in enumerate(col_names):
                    if ci < len(raw_col_types):
                        col_types[cn] = int(raw_col_types[ci])
                    else:
                        col_types[cn] = VR  # default to sum

            # Expose data_types on first location (all locations share types)
            if loc_idx == 1:
                result["data_types"] = dict(col_types)

            # Align DatetimeIndex length to actual row count (guard against
            # attribute/data mismatch)
            if n_rows != len(date_index):
                logger.warning(
                    "Location '%s': NTimeSteps attr=%d but dataset rows=%d; "
                    "truncating date index.",
                    loc_name,
                    len(date_index),
                    n_rows,
                )
                idx = date_index[:n_rows]
            else:
                idx = date_index

            df = pd.DataFrame(data_cols, index=idx, columns=col_names)
            df.index.name = "datetime"

            if resample_rule is not None and col_types:
                df = _resample_budget_df(df, resample_rule, col_types)
            elif resample_rule is not None:
                df = df.resample(resample_rule).sum()

            result["data"][loc_name] = df

    return result


def read_hydrograph_hdf(path: Union[str, Path]) -> pd.DataFrame:
    """Read an IWFM hydrograph HDF5 file into a single DataFrame.

    Handles single-dataset files: ``GWHyd.hdf``, ``StrmHyd.hdf``,
    ``Subsidence.hdf``, and ``TileDrainFlows.hdf``.

    Unlike budget files, these files do not store a time/date column within
    the dataset.  All columns are data values.  Dates are reconstructed from
    the ``Attributes/`` group TimeStep metadata.

    Column names are generated as ``col_1``, ``col_2``, … because individual
    location labels (well IDs, stream node IDs, etc.) are not stored in HDF5
    attributes for these file types.

    Parameters
    ----------
    path:
        Path to the HDF5 hydrograph file.

    Returns
    -------
    pandas.DataFrame
        Shape ``(n_timesteps, n_data_cols)`` with a :class:`pandas.DatetimeIndex`.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file contains no recognisable dataset (only the Attributes group).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    with h5py.File(path, "r") as f:
        date_index = _build_date_index(f["Attributes"].attrs)

        # Find the single data dataset (exclude the 'Attributes' group)
        data_keys = [k for k in f.keys() if k != "Attributes"]

        if not data_keys:
            raise ValueError(
                f"No data datasets found in {path.name}. "
                "File may be empty or use an unsupported layout."
            )

        if len(data_keys) > 1:
            logger.warning(
                "%s contains %d datasets; expected 1 for hydrograph format. "
                "Reading only the first: '%s'.",
                path.name,
                len(data_keys),
                data_keys[0],
            )

        dataset_name = data_keys[0]
        raw = f[dataset_name][()]  # shape (n_timesteps, n_cols)

        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)

        n_rows, n_cols = raw.shape

        # All columns are data; generate generic names
        col_names = [f"col_{i + 1}" for i in range(n_cols)]

        if n_rows != len(date_index):
            logger.warning(
                "%s: NTimeSteps attr=%d but dataset rows=%d; "
                "truncating date index.",
                path.name,
                len(date_index),
                n_rows,
            )
            idx = date_index[:n_rows]
        else:
            idx = date_index

        df = pd.DataFrame(raw, index=idx, columns=col_names)
        df.index.name = "datetime"

    return df


def read_head_hdf(
    path: Union[str, Path],
    n_nodes: Optional[int] = None,
    n_layers: Optional[int] = None,
) -> pd.DataFrame:
    """Read the IWFM groundwater-head-at-all-nodes HDF5 file (``GWHeadAll.hdf``).

    The file contains a single dataset ``GWHeadAtAllNode`` with shape
    ``(n_timesteps, n_nodes * n_layers)`` stored in layer-major order (all
    layer-1 nodes first, then all layer-2 nodes, …).  For example, 441 nodes
    and 2 layers gives 882 columns ordered as::

        node_1_layer_1, node_2_layer_1, …, node_441_layer_1,
        node_1_layer_2, node_2_layer_2, …, node_441_layer_2

    Parameters
    ----------
    path:
        Path to ``GWHeadAll.hdf`` (or any file with the same layout).
    n_nodes:
        Number of model nodes.  If *None*, column naming falls back to
        ``col_1``, ``col_2``, …
    n_layers:
        Number of model layers.  If *None*, column naming falls back to
        ``col_1``, ``col_2``, …

    Returns
    -------
    pandas.DataFrame
        Shape ``(n_timesteps, n_nodes * n_layers)`` with a
        :class:`pandas.DatetimeIndex`.  Column names are
        ``node_1_layer_1``, ``node_1_layer_2``, … when *n_nodes* and
        *n_layers* are provided; otherwise ``col_1``, ``col_2``, …

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If *n_nodes* and *n_layers* are provided but their product does not
        match the actual number of dataset columns.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    with h5py.File(path, "r") as f:
        date_index = _build_date_index(f["Attributes"].attrs)

        # Locate the dataset — for GWHeadAll.hdf it is always 'GWHeadAtAllNode'
        # but we search generically for robustness.
        data_keys = [k for k in f.keys() if k != "Attributes"]
        if not data_keys:
            raise ValueError(
                f"No data datasets found in {path.name}."
            )

        dataset_name = data_keys[0]
        if len(data_keys) > 1:
            logger.debug(
                "%s has %d datasets; using first: '%s'.",
                path.name,
                len(data_keys),
                dataset_name,
            )

        raw = f[dataset_name][()]  # shape (n_timesteps, n_nodes * n_layers)

        if raw.ndim == 1:
            raw = raw.reshape(-1, 1)

        n_rows, n_total_cols = raw.shape

    # Build column names
    if n_nodes is not None and n_layers is not None:
        expected = n_nodes * n_layers
        if expected != n_total_cols:
            raise ValueError(
                f"n_nodes={n_nodes} * n_layers={n_layers} = {expected} "
                f"does not match dataset columns ({n_total_cols}) in {path.name}."
            )
        # Dataset is in layer-major order:
        #   cols 0 .. n_nodes-1          -> layer 1, nodes 1..n_nodes
        #   cols n_nodes .. 2*n_nodes-1  -> layer 2, nodes 1..n_nodes
        # etc.
        col_names: List[str] = []
        for layer in range(1, n_layers + 1):
            for node in range(1, n_nodes + 1):
                col_names.append(f"node_{node}_layer_{layer}")
    else:
        if n_nodes is not None or n_layers is not None:
            logger.warning(
                "Both n_nodes and n_layers must be supplied to use named "
                "columns; falling back to generic names."
            )
        col_names = [f"col_{i + 1}" for i in range(n_total_cols)]

    if n_rows != len(date_index):
        logger.warning(
            "%s: NTimeSteps attr=%d but dataset rows=%d; "
            "truncating date index.",
            path.name,
            len(date_index),
            n_rows,
        )
        idx = date_index[:n_rows]
    else:
        idx = date_index

    df = pd.DataFrame(raw, index=idx, columns=col_names)
    df.index.name = "datetime"
    return df


# ---------------------------------------------------------------------------
# Zone definition reader
# ---------------------------------------------------------------------------

def read_zone_def(path: Union[str, Path]) -> ZoneDefinition:
    """Read an IWFM zone definition file for Z-Budget post-processing.

    Zone definition files are plain-text files with Fortran-style ``C``
    comment lines.  They specify how model elements are grouped into zones
    for aggregating Z-Budget output.

    File layout
    -----------
    - Comment lines start with ``C`` (case-insensitive).
    - First data value: ``ZEXTENT`` (1 = horizontal / same for all layers,
      0 = vertical / layer-specific).
    - Zone name table: pairs of ``ZID  ZNAME``.
    - Element assignment table: ``IE  ZONE`` (horizontal) or
      ``IE  LAYER  ZONE`` (vertical).

    Parameters
    ----------
    path:
        Path to the zone definition ``.dat`` file.

    Returns
    -------
    ZoneDefinition
        Parsed zone definition with *extent*, *zones* dict, and
        *element_zones* DataFrame.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file cannot be parsed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Zone definition file not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    # Strip comment lines (start with C, case-insensitive) and blank lines
    data_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("C"):
            continue
        # Strip inline comments after '/'
        if "/" in stripped:
            stripped = stripped[: stripped.index("/")].strip()
        if stripped:
            data_lines.append(stripped)

    if not data_lines:
        raise ValueError(f"No data lines found in {path}")

    # First data value: ZEXTENT
    zextent = int(data_lines[0].split()[0])
    extent = "horizontal" if zextent == 1 else "vertical"

    # Parse zone name table: read lines with exactly 2 tokens where first
    # token is an integer, until we hit the element assignment section.
    # Heuristic: zone IDs are small sequential integers; element assignment
    # lines have 2 tokens (horizontal) or 3 tokens (vertical).
    zones: Dict[int, str] = {}
    elem_start = 1  # index into data_lines where element assignments begin

    for i in range(1, len(data_lines)):
        tokens = data_lines[i].split()
        if len(tokens) < 2:
            continue

        zid = int(tokens[0])
        # Detect transition to element section: if we already have zones
        # and see a line whose second token is a pure integer that could be
        # a zone ID we've already seen, we're in the element section.
        if zones and len(tokens) == 2:
            try:
                second_val = int(tokens[1])
                if second_val in zones:
                    elem_start = i
                    break
            except ValueError:
                pass
        if zones and len(tokens) == 3:
            # Vertical: IE LAYER ZONE — all numeric
            try:
                int(tokens[1])
                int(tokens[2])
                elem_start = i
                break
            except ValueError:
                pass

        # This is a zone name line
        zones[zid] = tokens[1]

    # Parse element assignment lines
    elem_ids: List[int] = []
    layers: List[int] = []
    zone_ids: List[int] = []

    for i in range(elem_start, len(data_lines)):
        tokens = data_lines[i].split()
        if extent == "horizontal":
            if len(tokens) >= 2:
                elem_ids.append(int(tokens[0]))
                zone_ids.append(int(tokens[1]))
        else:
            if len(tokens) >= 3:
                elem_ids.append(int(tokens[0]))
                layers.append(int(tokens[1]))
                zone_ids.append(int(tokens[2]))

    if extent == "horizontal":
        element_zones = pd.DataFrame(
            {"element_id": elem_ids, "zone_id": zone_ids}
        )
    else:
        element_zones = pd.DataFrame(
            {"element_id": elem_ids, "layer": layers, "zone_id": zone_ids}
        )

    return ZoneDefinition(extent=extent, zones=zones, element_zones=element_zones)


# ---------------------------------------------------------------------------
# Z-Budget HDF5 reader
# ---------------------------------------------------------------------------

def _build_element_zone_map(
    zone_def: ZoneDefinition, n_elements: int, layer: int
) -> np.ndarray:
    """Build an array mapping element index (0-based) to zone ID.

    Returns an array of length *n_elements* where ``result[i]`` is the zone
    ID for element ``i+1``, or ``-99`` if not assigned.
    """
    zone_map = np.full(n_elements, -99, dtype=np.int32)
    df = zone_def.element_zones

    if zone_def.extent == "horizontal":
        for _, row in df.iterrows():
            eid = int(row["element_id"])
            if 1 <= eid <= n_elements:
                zone_map[eid - 1] = int(row["zone_id"])
    else:
        # Vertical: filter to the requested layer
        layer_df = df[df["layer"] == layer]
        for _, row in layer_df.iterrows():
            eid = int(row["element_id"])
            if 1 <= eid <= n_elements:
                zone_map[eid - 1] = int(row["zone_id"])

    return zone_map


def _aggregate_to_zones(
    elem_data: np.ndarray,
    elem_col_map: np.ndarray,
    zone_map: np.ndarray,
    zone_ids: List[int],
    n_timesteps: int,
) -> Dict[int, np.ndarray]:
    """Sum element-level data to zones.

    Parameters
    ----------
    elem_data : ndarray, shape (n_timesteps, n_dataset_cols)
        Raw dataset from the HDF5 file.
    elem_col_map : ndarray, shape (n_elements,)
        1-based column index into *elem_data* for each element, or 0 if
        no data for that element.
    zone_map : ndarray, shape (n_elements,)
        Zone ID for each element (0-based element index).
    zone_ids : list of int
        Unique zone IDs to aggregate to.
    n_timesteps : int
        Number of time steps.

    Returns
    -------
    dict mapping zone_id -> 1-D ndarray of length *n_timesteps*.
    """
    result: Dict[int, np.ndarray] = {zid: np.zeros(n_timesteps) for zid in zone_ids}

    for elem_idx in range(len(elem_col_map)):
        col = elem_col_map[elem_idx]
        if col <= 0:
            continue  # no data for this element
        zid = zone_map[elem_idx]
        if zid == -99 or zid not in result:
            continue
        result[zid] += elem_data[:, col - 1]  # col is 1-based

    return result


def _compute_face_flow_exchanges(
    face_flows: np.ndarray,
    face_elements: np.ndarray,
    zone_map: np.ndarray,
    zone_ids: List[int],
    n_timesteps: int,
) -> Dict[Tuple[int, int], np.ndarray]:
    """Compute inter-zone face flow exchanges.

    For each face connecting elements in different zones, the face flow
    contributes to the exchange between those two zones.

    Parameters
    ----------
    face_flows : ndarray, shape (n_timesteps, n_faces)
    face_elements : ndarray, shape (n_faces, 2)
        1-based element IDs for each face (0 = boundary/no element).
    zone_map : ndarray, shape (n_elements,)
    zone_ids : list of int
    n_timesteps : int

    Returns
    -------
    dict mapping ``(zone_a, zone_b)`` -> 1-D ndarray of shape
    ``(n_timesteps,)``, where ``zone_a < zone_b``.
    """
    zone_set = set(zone_ids)
    exchanges: Dict[Tuple[int, int], np.ndarray] = {}

    for face_idx in range(face_elements.shape[0]):
        e1 = face_elements[face_idx, 0]  # 1-based
        e2 = face_elements[face_idx, 1]
        if e1 <= 0 or e2 <= 0:
            continue  # boundary face
        z1 = zone_map[e1 - 1]
        z2 = zone_map[e2 - 1]
        if z1 == z2 or z1 == -99 or z2 == -99:
            continue
        if z1 not in zone_set or z2 not in zone_set:
            continue

        key = (min(z1, z2), max(z1, z2))
        if key not in exchanges:
            exchanges[key] = np.zeros(n_timesteps)
        # Convention: positive flow is from element 1 to element 2.
        # If z1 < z2, keep sign; if z1 > z2, flip sign.
        if z1 < z2:
            exchanges[key] += face_flows[:, face_idx]
        else:
            exchanges[key] -= face_flows[:, face_idx]

    return exchanges


def read_zbudget_hdf(
    path: Union[str, Path],
    zone_def: Union[ZoneDefinition, str, Path, None] = None,
    interval: Optional[str] = None,
) -> Dict:
    """Read an IWFM Zone Budget HDF5 file.

    Supports two modes:

    - **Raw mode** (``zone_def=None``): Returns element-level data per
      layer, keyed by data type name.
    - **Aggregated mode** (``zone_def`` provided): Sums element values to
      user-defined zones and returns per-zone DataFrames.

    Parameters
    ----------
    path:
        Path to the ZBudget HDF5 file (e.g. ``GW_ZBud.hdf``).
    zone_def:
        Zone definition for aggregation.  Can be a :class:`ZoneDefinition`
        instance, or a path to a zone definition ``.dat`` file (which will
        be parsed via :func:`read_zone_def`).  ``None`` returns raw
        element-level data.
    interval:
        Optional temporal resampling interval.  ``"1MON"`` for monthly,
        ``"1YEAR"`` for annual.  ``None`` returns native (daily) data.
        Aggregation is data-type-aware: volumetric rates are summed,
        area/length use last value, and LWU special columns use iterative
        carry-over logic matching the Fortran DLL.

    Returns
    -------
    dict with keys:

    ``'metadata'`` : dict
        File metadata including ``n_elements``, ``n_layers``,
        ``n_timesteps``, ``data_names``, ``data_types``,
        ``element_areas``, ``begin_date``, ``delta_minutes``.

    ``'zones'`` : dict (only when *zone_def* is provided)
        ``zone_ids`` and ``zone_names`` lists.

    ``'data'`` : dict
        When *zone_def* is provided: maps zone name -> DataFrame with
        DatetimeIndex and one column per data type name.
        When *zone_def* is ``None``: maps ``"Layer_N"`` -> dict mapping
        data type name -> DataFrame(DatetimeIndex, columns=element_ids).

    ``'face_flows'`` : dict (only when *zone_def* is provided)
        Maps ``(zone_a, zone_b)`` tuples -> DataFrame with column
        ``"flow"``, one row per timestep.

    Raises
    ------
    FileNotFoundError
        If *path* or zone definition file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"HDF5 file not found: {path}")

    # Parse zone_def if given as a path
    if zone_def is not None and not isinstance(zone_def, ZoneDefinition):
        zone_def = read_zone_def(zone_def)

    resample_rule = None
    if interval is not None:
        rule_map = {"1MON": "ME", "1YEAR": "YE"}
        resample_rule = rule_map.get(interval.upper())
        if resample_rule is None:
            raise ValueError(
                f"Unsupported interval '{interval}'. Use '1MON' or '1YEAR'."
            )

    result: Dict = {"metadata": {}, "data": {}}

    with h5py.File(path, "r") as f:
        attrs_grp = f["Attributes"]
        attrs = attrs_grp.attrs

        # Build date index
        date_index = _build_date_index(attrs)
        n_timesteps = len(date_index)

        # Read metadata
        n_elements = int(attrs.get("SystemData%NElements", 0))
        n_layers = int(attrs.get("SystemData%NLayers", 0))
        n_data = int(attrs.get("NData", 0))

        # Read data names and types from datasets
        full_names_raw = attrs_grp["FullDataNames"][()]
        data_names = [_decode_bytes(n) for n in full_names_raw]
        data_types_raw = attrs_grp["DataTypes"][()]
        data_types = data_types_raw.tolist()

        # Read data HDF paths
        data_paths_raw = attrs_grp["DataHDFPaths"][()]
        data_paths = [_decode_bytes(p) for p in data_paths_raw]

        # Read element areas
        element_areas = attrs_grp["SystemData%ElementAreas"][()]
        element_ids = attrs_grp["SystemData%ElementIDs"][()]

        # Read ElemDataColumns for each layer
        elem_data_cols: Dict[int, np.ndarray] = {}
        for layer in range(1, n_layers + 1):
            key = f"Layer{layer}_ElemDataColumns"
            if key in attrs_grp:
                elem_data_cols[layer] = attrs_grp[key][()]

        begin_raw = attrs.get("TimeStep%BeginDateAndTime", b"01/01/1900_00:00")
        begin_str = _decode_bytes(begin_raw)
        delta_minutes = int(attrs.get("TimeStep%DeltaT_InMinutes", 1440))

        result["metadata"] = {
            "n_elements": n_elements,
            "n_layers": n_layers,
            "n_timesteps": n_timesteps,
            "data_names": data_names,
            "data_types": data_types,
            "element_areas": element_areas,
            "begin_date": begin_str,
            "delta_minutes": delta_minutes,
        }

        if zone_def is None:
            # --- Raw mode: element-level data per layer ---
            for layer in range(1, n_layers + 1):
                layer_key = f"Layer_{layer}"
                if layer_key not in f:
                    continue
                layer_grp = f[layer_key]
                layer_data: Dict[str, pd.DataFrame] = {}

                edc = elem_data_cols.get(layer)

                for dtype_idx, dname in enumerate(data_names):
                    ds_name = data_paths[dtype_idx]
                    if ds_name not in layer_grp:
                        continue
                    ds = layer_grp[ds_name]
                    if ds.shape[1] == 0:
                        continue  # empty dataset

                    raw = ds[()]
                    n_rows = raw.shape[0]
                    idx = date_index[:n_rows] if n_rows != n_timesteps else date_index

                    if edc is not None:
                        # Map columns back to element IDs
                        col_map = edc[dtype_idx]  # shape (n_elements,)
                        active_elems = np.nonzero(col_map)[0]
                        if len(active_elems) == 0:
                            continue
                        cols = col_map[active_elems] - 1  # to 0-based
                        eids = element_ids[active_elems]
                        df = pd.DataFrame(
                            raw[:, cols], index=idx,
                            columns=[int(eid) for eid in eids],
                        )
                    else:
                        df = pd.DataFrame(
                            raw, index=idx,
                            columns=[f"col_{i+1}" for i in range(raw.shape[1])],
                        )

                    df.index.name = "datetime"
                    if resample_rule is not None:
                        # All columns in this DataFrame share the same data
                        # type (one dtype per element-level dataset).
                        dtype_code = data_types[dtype_idx] if dtype_idx < len(data_types) else VR
                        per_col_types = {c: dtype_code for c in df.columns}
                        df = _resample_budget_df(df, resample_rule, per_col_types)
                    layer_data[dname] = df

                result["data"][layer_key] = layer_data

        else:
            # --- Aggregated mode: sum to zones ---
            zone_ids = sorted(zone_def.zones.keys())
            zone_names = [zone_def.zones[zid] for zid in zone_ids]

            result["zones"] = {
                "zone_ids": zone_ids,
                "zone_names": zone_names,
            }

            # Initialize per-zone data: {zone_name: {data_name: 1-D array}}
            zone_data: Dict[str, Dict[str, np.ndarray]] = {
                zone_def.zones[zid]: {dn: np.zeros(n_timesteps) for dn in data_names}
                for zid in zone_ids
            }

            # Also track which data names actually have data
            active_data_names: set = set()

            for layer in range(1, n_layers + 1):
                layer_key = f"Layer_{layer}"
                if layer_key not in f:
                    continue
                layer_grp = f[layer_key]
                edc = elem_data_cols.get(layer)
                if edc is None:
                    continue

                zone_map = _build_element_zone_map(zone_def, n_elements, layer)

                for dtype_idx, dname in enumerate(data_names):
                    ds_name = data_paths[dtype_idx]
                    if ds_name not in layer_grp:
                        continue
                    ds = layer_grp[ds_name]
                    if ds.shape[1] == 0:
                        continue

                    raw = ds[()]
                    col_map = edc[dtype_idx]  # shape (n_elements,)

                    aggregated = _aggregate_to_zones(
                        raw, col_map, zone_map, zone_ids, n_timesteps
                    )

                    for zid, values in aggregated.items():
                        zname = zone_def.zones[zid]
                        zone_data[zname][dname] += values
                        if np.any(values != 0):
                            active_data_names.add(dname)

            # Build DataFrames per zone (only include data names with data)
            ordered_active = [dn for dn in data_names if dn in active_data_names]

            # Build column-name -> data-type-code mapping for zone DataFrames
            zone_col_types: Dict[str, int] = {}
            for di, dn in enumerate(data_names):
                if dn in active_data_names and di < len(data_types):
                    zone_col_types[dn] = data_types[di]

            # --- Compute face flow exchanges (raw arrays, summed across layers) ---
            face_elements = attrs_grp["SystemData%FaceElements"][()]
            raw_exchanges: Dict[Tuple[int, int], np.ndarray] = {}

            for layer in range(1, n_layers + 1):
                layer_key = f"Layer_{layer}"
                if layer_key not in f:
                    continue
                layer_grp = f[layer_key]
                if "FaceFlows" not in layer_grp:
                    continue

                face_flows_raw = layer_grp["FaceFlows"][()]
                zone_map = _build_element_zone_map(zone_def, n_elements, layer)

                exchanges = _compute_face_flow_exchanges(
                    face_flows_raw, face_elements, zone_map,
                    zone_ids, n_timesteps,
                )

                for key, values in exchanges.items():
                    if key not in raw_exchanges:
                        raw_exchanges[key] = np.zeros(n_timesteps)
                    raw_exchanges[key] += values

            # --- Build DataFrames per zone, including face flow columns ---
            for zname_idx, zname in enumerate(zone_names):
                zid = zone_ids[zname_idx]

                data_dict = {dn: zone_data[zname][dn] for dn in ordered_active}

                # Add per-neighbor subsurface inflow/outflow columns
                for (za, zb), exch_values in sorted(raw_exchanges.items()):
                    if zid not in (za, zb):
                        continue

                    neighbor_id = zb if zid == za else za
                    neighbor_name = zone_def.zones[neighbor_id]

                    # exchanges[(za,zb)] positive = flow from za to zb
                    if zid == za:
                        net_to_zone = -exch_values  # flip: inflow to za
                    else:
                        net_to_zone = exch_values

                    in_col = f"Subsurface Inflow from {neighbor_name} (+)"
                    out_col = f"Subsurface Outflow to {neighbor_name} (-)"

                    data_dict[in_col] = np.maximum(0.0, net_to_zone)
                    data_dict[out_col] = np.maximum(0.0, -net_to_zone)

                    # Volumetric rates → sum during resampling
                    zone_col_types[in_col] = VR
                    zone_col_types[out_col] = VR

                df = pd.DataFrame(data_dict, index=date_index)
                df.index.name = "datetime"
                if resample_rule is not None:
                    df = _resample_budget_df(df, resample_rule, zone_col_types)
                result["data"][zname] = df

            # --- Also build face_flows dict (net per zone pair) ---
            face_flows_result: Dict[Tuple[int, int], pd.DataFrame] = {}
            for key, values in raw_exchanges.items():
                ff_df = pd.DataFrame({"flow": values}, index=date_index)
                ff_df.index.name = "datetime"
                if resample_rule is not None:
                    ff_df = ff_df.resample(resample_rule).sum()
                face_flows_result[key] = ff_df

            result["face_flows"] = face_flows_result

    return result
