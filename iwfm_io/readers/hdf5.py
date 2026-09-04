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

from iwfm_io.models.base import ZoneDefinition

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
# Data-type constants and DLL-faithful aggregation engine
# ---------------------------------------------------------------------------
# The temporal-aggregation engine lives in iwfm_io._budget_agg (shared with
# iwfm_io.collect.aggregate_budget); the type constants are re-exported here
# for backward compatibility.

from iwfm_io._budget_agg import (  # noqa: F401  (re-exported)
    AR,
    LT,
    SUPPORTED_INTERVALS,
    VLB,
    VLE,
    VR,
    VR_LWU_AGDIV,
    VR_LWU_AGOTHIN,
    VR_LWU_AGPUMP,
    VR_LWU_AGSHORT,
    VR_LWU_AGSUPPLYREQ,
    VR_LWU_POTCUAW,
    _FIRST_TYPES,
    _LAST_TYPES,
    _LWU_SPECIAL_TYPES,
    _SUM_TYPES,
    _window_starts,
    aggregate_frame,
    identify_lwu_groups,
    lwu_aggregate_arrays,
    strip_zbudget_marker,
    window_end_labels,
)


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
        Optional temporal resampling interval.  ``None`` returns native
        timestep data.  ``"1MON"`` and ``"1YEAR"`` follow the IWFM DLL's
        semantics exactly: aggregation windows are consecutive calendar
        months / 12-month blocks anchored to the data begin (for the usual
        October-start models ``"1YEAR"`` is the water year), each window is
        stamped at its end using the library's 24:00 convention (e.g. the
        window ending ``09/30/1988_24:00`` is stamped ``1988-10-01``), and
        a trailing partial window is dropped — matching
        ``IWFMBudget.get_values(..., "1YEAR")`` stamps and values.
        ``"1CALYEAR"`` aggregates over calendar years instead (January
        anchored; partial first/last years are kept).
        Aggregation is data-type-aware: volumetric rates are summed,
        beginning storage uses first value, ending storage/area/length use
        last value, and LWU special columns use the DLL's carry-over logic
        (see :mod:`iwfm_io._budget_agg`).

    Returns
    -------
    dict with keys:

    ``'locations'`` : list of str
        Location/subregion names in the file's native location order — the
        same order the IWFM DLL reports (read from the
        ``Attributes/cLocationNames`` dataset, e.g. subregions first, then
        'ENTIRE MODEL AREA').  Falls back to alphabetical HDF5 iteration
        order when that dataset is absent.
    ``'data'`` : dict mapping location_name -> :class:`pandas.DataFrame`
        Each DataFrame has a :class:`pandas.DatetimeIndex` and columns named
        from the ``LocationDataN%cFullColumnHeaders`` attribute (first 'Time'
        entry stripped).  Generic names ``col_1``, ``col_2``, … are used when
        the attribute is absent.  Iterates in the same order as
        ``'locations'``.
    ``'data_types'`` : dict mapping column_name -> int
        IWFM data type code for each column (1-11).  Same mapping applies to
        all locations (controlled by ``NLocationData``).
    ``'interval'`` : str or None
        The file's native output interval from the ``TimeStep%Unit``
        attribute (e.g. ``'1DAY'``, ``'1MON'``), regardless of any
        resampling requested via *interval*.

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

    resample_interval = None
    if interval is not None:
        resample_interval = interval.upper()
        if resample_interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"Unsupported interval '{interval}'. "
                f"Use one of {', '.join(SUPPORTED_INTERVALS)}."
            )

    result: Dict = {"locations": [], "data": {}, "data_types": {},
                    "interval": None}

    with h5py.File(path, "r") as f:
        # Build shared DatetimeIndex from TimeStep attributes
        date_index = _build_date_index(f["Attributes"].attrs)
        root_attrs = f["Attributes"].attrs

        # Native output interval, e.g. b'1DAY' / b'1MON'
        native_unit = root_attrs.get("TimeStep%Unit")
        if native_unit is not None:
            if isinstance(native_unit, bytes):
                native_unit = native_unit.decode()
            result["interval"] = str(native_unit).strip()

        # Read data column types (same for all locations)
        raw_col_types: Optional[np.ndarray] = None
        type_key = "LocationData1%iDataColumnTypes"
        if type_key in root_attrs:
            raw_col_types = np.asarray(root_attrs[type_key])

        # Collect location dataset names (everything except 'Attributes').
        # h5py iterates alphabetically, which is not IWFM's location order
        # (e.g. 'NODE 19' sorts before 'NODE 8', and 'ENTIRE MODEL AREA'
        # before the subregions).  The DLL's order is stored in the
        # Attributes/cLocationNames dataset — use it when it matches the
        # group names so positional selection agrees with DLL semantics
        # and LocationData{N} attributes align with the right dataset.
        location_names = [k for k in f.keys() if k != "Attributes"]
        attrs_group = f["Attributes"]
        if isinstance(attrs_group, h5py.Group) and \
                "cLocationNames" in attrs_group:
            ordered = [
                (s.decode() if isinstance(s, bytes) else str(s)).strip()
                for s in attrs_group["cLocationNames"][()]
            ]
            if sorted(ordered) == sorted(location_names):
                location_names = ordered
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

            if resample_interval is not None:
                labels, complete = window_end_labels(
                    idx, resample_interval,
                    native_unit=result["interval"],
                    delta_minutes=root_attrs.get("TimeStep%DeltaT_InMinutes"),
                )
                df = aggregate_frame(df, col_types, labels, complete)

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


def _clean_data_names(data_names: List[str]) -> Dict[str, str]:
    """Map raw zbudget data names to display names (``@...@`` stripped).

    On the (unexpected) event that two raw names clean to the same string,
    the later one keeps its raw name so columns stay unique.
    """
    mapping: Dict[str, str] = {}
    used: set = set()
    for dn in data_names:
        clean = strip_zbudget_marker(dn) or dn
        if clean in used and clean != dn:
            clean = dn
        mapping[dn] = clean
        used.add(clean)
    return mapping


_LWU_ROLE_BY_TYPE = {
    VR_LWU_POTCUAW: "pot_cuaw",
    VR_LWU_AGSUPPLYREQ: "supply_req",
    VR_LWU_AGSHORT: "shortage",
}

_LWU_ELEM_CHUNK = 4096  # elements per block in per-element LWU aggregation


def _lwu_elementwise(
    raw_cache: Dict[int, Optional[np.ndarray]],
    layer_grp: "h5py.Group",
    data_paths: List[str],
    edc: np.ndarray,
    group_idx: Dict[str, int],
    out_didx: int,
    out_role: str,
    row_keep: np.ndarray,
    starts: np.ndarray,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Per-element DLL LWU aggregation for one output dataset in one layer.

    Implements Class_ZBudget.f90 ``AccumulateData`` for data types 6/7/8:
    the carry-over runs on each element's own series (gathered from the
    group's related datasets via the per-dataset ``ElemDataColumns`` maps)
    *before* any spatial summation.

    Parameters
    ----------
    raw_cache : dict
        dataset index -> loaded raw array (populated lazily; shared across
        the group's output datasets so each file dataset is read once).
    edc : ndarray, shape (n_data, n_elements)
        The layer's ElemDataColumns map (1-based columns, 0 = no data).
    group_idx : dict
        role -> dataset index for this LWU group.
    out_didx, out_role :
        The dataset to produce and its role (``pot_cuaw`` / ``supply_req``
        / ``shortage``).
    row_keep : ndarray of bool
        Native rows to keep (complete aggregation windows).
    starts : ndarray
        Window start rows within the kept rows.

    Returns
    -------
    (elem_sel, agg) or None
        0-based indices of elements with data in the output dataset, and
        the ``(n_windows, len(elem_sel))`` aggregated values.  None when
        the group's supply-requirement dataset is unavailable.
    """
    def _load(didx: int) -> Optional[np.ndarray]:
        if didx not in raw_cache:
            ds_name = data_paths[didx]
            if ds_name in layer_grp and layer_grp[ds_name].shape[1] > 0:
                raw_cache[didx] = layer_grp[ds_name][()]
            else:
                raw_cache[didx] = None
        return raw_cache[didx]

    req_didx = group_idx.get("supply_req")
    if req_didx is None or _load(req_didx) is None:
        return None

    elem_sel = np.flatnonzero(edc[out_didx])
    if len(elem_sel) == 0:
        return None

    keep_rows = np.flatnonzero(row_keep)

    def _gather(didx: Optional[int], chunk: np.ndarray) -> Optional[np.ndarray]:
        if didx is None:
            return None
        raw = _load(didx)
        mat = np.zeros((len(keep_rows), len(chunk)))
        if raw is not None:
            cols = edc[didx][chunk]
            valid = cols >= 1
            if valid.any():
                mat[:, valid] = raw[np.ix_(keep_rows, cols[valid] - 1)]
        return mat

    parts: List[np.ndarray] = []
    for s in range(0, len(elem_sel), _LWU_ELEM_CHUNK):
        chunk = elem_sel[s:s + _LWU_ELEM_CHUNK]
        res = lwu_aggregate_arrays(
            starts,
            _gather(req_didx, chunk),
            _gather(group_idx.get("shortage"), chunk),
            _gather(group_idx.get("pumping"), chunk),
            _gather(group_idx.get("deliveries"), chunk),
            _gather(group_idx.get("other_inflow"), chunk),
            _gather(out_didx, chunk) if out_role == "pot_cuaw" else None,
        )
        parts.append(res[out_role])

    return elem_sel, np.concatenate(parts, axis=1)


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
        Optional temporal resampling interval.  ``None`` returns native
        data.  ``"1MON"`` and ``"1YEAR"`` follow the IWFM DLL's semantics:
        windows are anchored to the data begin (``"1YEAR"`` is the water
        year for October-start models), stamped at the window end with the
        24:00 convention, and a trailing partial window is dropped —
        matching ``IWFMZBudget.get_values_for_zone``.  ``"1CALYEAR"``
        aggregates over calendar years (January anchored, partial years
        kept).  Aggregation is data-type-aware: volumetric rates are
        summed, area/length use last value, and the LWU carry-over columns
        (Potential CUAW / Ag. Supply Requirement / Ag. Shortage) are
        aggregated **per element before zone summation**, exactly as the
        DLL does (the carry-over clipping does not commute with spatial
        sums).

    Returns
    -------
    dict with keys:

    ``'metadata'`` : dict
        File metadata including ``n_elements``, ``n_layers``,
        ``n_timesteps``, ``data_names`` (raw, with the ``@...@`` unit
        annotations), ``data_names_clean`` (display names, annotations
        stripped), ``data_types``, ``element_areas``, ``begin_date``,
        ``delta_minutes``.

    ``'zones'`` : dict (only when *zone_def* is provided)
        ``zone_ids`` and ``zone_names`` lists.

    ``'data'`` : dict
        When *zone_def* is provided: maps zone name -> DataFrame with
        DatetimeIndex and one column per dataset, in ``data_names`` order
        — every dataset appears (all-zero when it has no active elements,
        as the DLL reports), named by its clean display name (the raw
        ``@...@`` unit annotation is stripped) — followed by the
        per-neighbor subsurface inflow/outflow columns.
        When *zone_def* is ``None``: maps ``"Layer_N"`` -> dict mapping
        raw data name -> DataFrame(DatetimeIndex, columns=element_ids).

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

    resample_interval = None
    if interval is not None:
        resample_interval = interval.upper()
        if resample_interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"Unsupported interval '{interval}'. "
                f"Use one of {', '.join(SUPPORTED_INTERVALS)}."
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
        native_unit = _decode_bytes(attrs.get("TimeStep%Unit", b""))

        clean_names = _clean_data_names(data_names)

        result["metadata"] = {
            "n_elements": n_elements,
            "n_layers": n_layers,
            "n_timesteps": n_timesteps,
            "data_names": data_names,
            "data_names_clean": [clean_names[dn] for dn in data_names],
            "data_types": data_types,
            "element_areas": element_areas,
            "begin_date": begin_str,
            "delta_minutes": delta_minutes,
        }

        # Precompute aggregation windows and LWU dataset groups
        name_types = {dn: int(t) for dn, t in zip(data_names, data_types)}
        agg_labels = agg_complete = agg_starts = agg_ulabels = None
        special_group_for: Dict[int, Dict[str, int]] = {}
        if resample_interval is not None:
            agg_labels, agg_complete = window_end_labels(
                date_index, resample_interval,
                native_unit=native_unit, delta_minutes=delta_minutes,
            )
            _masked = np.asarray(agg_labels)[agg_complete]
            agg_starts = _window_starts(_masked)
            agg_ulabels = pd.DatetimeIndex(
                _masked[agg_starts], name="datetime")

            # Map each LWU special dataset (types 6/7/8) to its group of
            # related dataset indices, for per-element aggregation.
            if any(t in _LWU_SPECIAL_TYPES for t in name_types.values()):
                name_pos = {dn: i for i, dn in enumerate(data_names)}
                for g in identify_lwu_groups(data_names, name_types):
                    gidx = {role: name_pos[dn] for role, dn in g.items()}
                    for role in ("pot_cuaw", "supply_req", "shortage"):
                        if role in gidx:
                            special_group_for[gidx[role]] = gidx

        if zone_def is None:
            # --- Raw mode: element-level data per layer ---
            for layer in range(1, n_layers + 1):
                layer_key = f"Layer_{layer}"
                if layer_key not in f:
                    continue
                layer_grp = f[layer_key]
                layer_data: Dict[str, pd.DataFrame] = {}

                edc = elem_data_cols.get(layer)
                raw_cache: Dict[int, Optional[np.ndarray]] = {}

                for dtype_idx, dname in enumerate(data_names):
                    ds_name = data_paths[dtype_idx]
                    if ds_name not in layer_grp:
                        continue
                    ds = layer_grp[ds_name]
                    if ds.shape[1] == 0:
                        continue  # empty dataset

                    dtype_code = name_types.get(dname, VR)

                    # LWU special datasets (types 6/7/8): the DLL carry-over
                    # runs on each element's own series, pulling the related
                    # supply-req/shortage/pumping/delivery series from the
                    # group's other datasets.
                    if (resample_interval is not None
                            and dtype_code in _LWU_SPECIAL_TYPES
                            and edc is not None
                            and dtype_idx in special_group_for
                            and ds.shape[0] == n_timesteps):
                        res = _lwu_elementwise(
                            raw_cache, layer_grp, data_paths, edc,
                            special_group_for[dtype_idx], dtype_idx,
                            _LWU_ROLE_BY_TYPE[dtype_code],
                            agg_complete, agg_starts,
                        )
                        if res is not None:
                            elem_sel, agg = res
                            df = pd.DataFrame(
                                agg, index=agg_ulabels,
                                columns=[int(eid)
                                         for eid in element_ids[elem_sel]],
                            )
                            df.index.name = "datetime"
                            layer_data[dname] = df
                            continue

                    raw = raw_cache.get(dtype_idx)
                    if raw is None:
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
                    if resample_interval is not None:
                        # All columns in this DataFrame share the same data
                        # type (one dtype per element-level dataset).
                        if n_rows != n_timesteps:
                            labels, complete = window_end_labels(
                                idx, resample_interval,
                                native_unit=native_unit,
                                delta_minutes=delta_minutes,
                            )
                        else:
                            labels, complete = agg_labels, agg_complete
                        per_col_types = {c: dtype_code for c in df.columns}
                        df = aggregate_frame(df, per_col_types, labels,
                                             complete)
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
            # Every dataset gets a column — an all-zero one when it has no
            # active elements, matching the DLL's full column set.
            zone_data: Dict[str, Dict[str, np.ndarray]] = {
                zone_def.zones[zid]: {dn: np.zeros(n_timesteps) for dn in data_names}
                for zid in zone_ids
            }

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

            # Column-name (display) -> data-type-code for zone DataFrames
            zone_col_types: Dict[str, int] = {
                clean_names[dn]: name_types.get(dn, VR) for dn in data_names
            }

            # --- Per-element LWU carry-over (types 6/7/8) ---
            # The DLL aggregates these on each element's own series before
            # summing to zones (the clipping does not commute with spatial
            # sums), so the naively-resampled zone columns are replaced
            # below with per-element aggregates summed to zones.
            corrected: Dict[str, Dict[str, np.ndarray]] = {
                zname: {} for zname in zone_names
            }
            if resample_interval is not None and special_group_for:
                for layer in range(1, n_layers + 1):
                    layer_key = f"Layer_{layer}"
                    if layer_key not in f:
                        continue
                    layer_grp = f[layer_key]
                    edc = elem_data_cols.get(layer)
                    if edc is None:
                        continue
                    zone_map = _build_element_zone_map(
                        zone_def, n_elements, layer)
                    raw_cache: Dict[int, Optional[np.ndarray]] = {}

                    for out_didx, gidx in special_group_for.items():
                        dname = data_names[out_didx]
                        res = _lwu_elementwise(
                            raw_cache, layer_grp, data_paths, edc, gidx,
                            out_didx, _LWU_ROLE_BY_TYPE[name_types[dname]],
                            agg_complete, agg_starts,
                        )
                        if res is None:
                            continue
                        elem_sel, agg = res  # agg: (n_windows, n_elems)
                        elem_zones = zone_map[elem_sel]
                        for zid in zone_ids:
                            in_zone = elem_zones == zid
                            if not in_zone.any():
                                continue
                            zname = zone_def.zones[zid]
                            summed = agg[:, in_zone].sum(axis=1)
                            if dname in corrected[zname]:
                                corrected[zname][dname] += summed
                            else:
                                corrected[zname][dname] = summed

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

                data_dict = {clean_names[dn]: zone_data[zname][dn]
                             for dn in data_names}

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
                if resample_interval is not None:
                    # LWU special columns get a placeholder rule here; the
                    # DLL-faithful per-element aggregates computed above
                    # overwrite them right after.
                    placeholder_types = {
                        c: (VR if t in _LWU_SPECIAL_TYPES else t)
                        for c, t in zone_col_types.items()
                    }
                    df = aggregate_frame(df, placeholder_types,
                                         agg_labels, agg_complete)
                    for dn, arr in corrected[zname].items():
                        df[clean_names[dn]] = arr
                result["data"][zname] = df

            # --- Also build face_flows dict (net per zone pair) ---
            face_flows_result: Dict[Tuple[int, int], pd.DataFrame] = {}
            for key, values in raw_exchanges.items():
                if resample_interval is not None:
                    kept = values[np.asarray(agg_complete)]
                    summed = np.add.reduceat(kept, agg_starts) \
                        if len(kept) else kept
                    ff_df = pd.DataFrame({"flow": summed}, index=agg_ulabels)
                else:
                    ff_df = pd.DataFrame({"flow": values}, index=date_index)
                ff_df.index.name = "datetime"
                face_flows_result[key] = ff_df

            result["face_flows"] = face_flows_result

    return result
