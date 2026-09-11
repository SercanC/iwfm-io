"""
Multi-run output collection helpers.

Each function reads one or more HDF5 output files from multiple model runs
and returns a single long-form (tidy) pandas DataFrame ready for comparison,
aggregation, and export.

All functions follow the same calling convention::

    runs : Dict[str, Path]
        Mapping of run label → Results/ directory for that run.
    *_files : Dict[str, str]
        Mapping of a short type label → HDF5 filename within Results/.
    begin_date, end_date : str, optional
        ISO date strings (``"1995-01-01"``) to slice the time axis.

Example::

    from pathlib import Path
    from iwfm_io import collect_budgets, collect_gwheads

    RUNS = {
        "baseline": Path("runs/baseline/Results"),
        "drought":  Path("runs/drought/Results"),
    }

    df = collect_budgets(
        runs=RUNS,
        budget_files={"GW": "GW.hdf", "Stream": "StrmBud.hdf"},
        begin_date="1995-01-01",
    )
    # run  budget_type  location  datetime  component  value
    # ...

    heads = collect_gwheads(RUNS, n_nodes=441, n_layers=2, layers=[1])
    # run  node  layer  datetime  head
    # ...
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _date_mask(index, begin_date=None, end_date=None):
    """Boolean mask selecting ``index`` entries within a date window.

    Bounds may be IWFM strings (``10/01/1990_24:00`` — compared as the
    instant they denote), plain dates (``"1990-10-01"``, ``date`` — the
    *owning day* under the 24:00 convention, so ``end_date="1991-09-30"``
    keeps the ``09/30/1991_24:00`` stamp that is stored as Oct 1
    midnight), or timestamps with a time of day (compared directly).
    """
    import numpy as np
    from iwfm_io._tokens import is_iwfm_date, iwfm_day, parse_iwfm_date

    idx = pd.DatetimeIndex(index)
    mask = np.ones(len(idx), dtype=bool)
    days = None
    for bound, is_begin in ((begin_date, True), (end_date, False)):
        if bound is None or bound == "":
            continue
        if isinstance(bound, str) and is_iwfm_date(bound):
            inst = pd.Timestamp(parse_iwfm_date(bound))
            mask &= (idx >= inst) if is_begin else (idx <= inst)
            continue
        ts = pd.Timestamp(bound)
        if ts == ts.normalize():
            if days is None:
                days = iwfm_day(idx)
            mask &= (days >= ts) if is_begin else (days <= ts)
        else:
            mask &= (idx >= ts) if is_begin else (idx <= ts)
    return mask



def _run_collect_tasks(tasks, fn, max_workers):
    """Run collection tasks and flatten their frame lists, preserving order.

    With ``max_workers > 1`` the tasks run in a thread pool — h5py releases
    the GIL during reads, so collecting many runs/files overlaps their I/O.
    """
    if max_workers and max_workers > 1 and len(tasks) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(fn, tasks))
    else:
        results = [fn(t) for t in tasks]
    return [frame for sub in results for frame in sub]

# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


def collect_budgets(
    runs: Dict[str, Path],
    budget_files: Dict[str, str],
    locations: Optional[List[str]] = None,
    budget_types: Optional[List[str]] = None,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: Optional[str] = None,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    """Collect budget HDF5 files from multiple model runs into a long-form DataFrame.

    Parameters
    ----------
    runs : dict
        Mapping of run label → Results/ directory path.
    budget_files : dict
        Mapping of budget type label → HDF5 filename within Results/.
        Example: ``{"GW": "GW.hdf", "Stream": "StrmBud.hdf"}``.
    locations : list of str, optional
        Restrict to these location names. ``None`` = all locations.
    budget_types : list of str, optional
        Restrict to these type keys from *budget_files*. ``None`` = all.
    begin_date, end_date : str, optional
        ISO date strings (``"1995-01-01"``) to slice the time axis after loading.
    interval : str, optional
        Temporal resampling interval passed to :func:`~iwfm_io.read_budget_hdf`
        (``"1MON"`` for monthly, ``"1YEAR"`` for annual). ``None`` = native step.
    max_workers : int, optional
        When > 1, read the run/budget files concurrently in a thread pool.

    Returns
    -------
    pandas.DataFrame
        Long-form table with columns:
        ``run, budget_type, location, datetime, component, value``.

        Missing files are silently skipped (logged at DEBUG level).
    """
    from .readers.hdf5 import read_budget_hdf

    active_types = budget_types or list(budget_files.keys())
    tasks = [
        (run_label, Path(results_dir), btype)
        for run_label, results_dir in runs.items()
        for btype in active_types
        if budget_files.get(btype) is not None
    ]

    def _load(task):
        run_label, results_dir, btype = task
        fname = budget_files[btype]
        path = results_dir / fname
        if not path.exists():
            logger.debug(
                "collect_budgets: skip %s/%s — %s not found",
                run_label, btype, fname,
            )
            return []

        result = read_budget_hdf(path, interval=interval)
        loc_names = result["locations"]
        if locations is not None:
            loc_names = [loc for loc in loc_names if loc in locations]

        out = []
        for loc in loc_names:
            df = result["data"][loc].copy()
            if begin_date is not None or end_date is not None:
                df = df[_date_mask(df.index, begin_date, end_date)]

            df.index.name = "datetime"
            df_long = (
                df.reset_index()
                  .melt(id_vars="datetime", var_name="component", value_name="value")
            )
            df_long["run"] = run_label
            df_long["budget_type"] = btype
            df_long["location"] = loc
            out.append(df_long)

        logger.debug(
            "collect_budgets: ok %s/%s — %d location(s)",
            run_label, btype, len(loc_names),
        )
        return out

    frames = _run_collect_tasks(tasks, _load, max_workers)

    if not frames:
        return pd.DataFrame(
            columns=["run", "budget_type", "location", "datetime", "component", "value"]
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[
        ["run", "budget_type", "location", "datetime", "component", "value"]
    ]
    combined["datetime"] = pd.to_datetime(combined["datetime"])
    return combined


# ---------------------------------------------------------------------------
# Zone budget
# ---------------------------------------------------------------------------


def collect_zbudgets(
    runs: Dict[str, Path],
    zbudget_files: Dict[str, str],
    zone_def: Union[str, Path, None] = None,
    zones: Optional[List[str]] = None,
    zbudget_types: Optional[List[str]] = None,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval: Optional[str] = None,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    """Collect zone-budget HDF5 files from multiple runs into a long-form DataFrame.

    Parameters
    ----------
    runs : dict
        Mapping of run label → Results/ directory path.
    zbudget_files : dict
        Mapping of zbudget type label → HDF5 filename within Results/.
        Example: ``{"GW": "GW_ZBud.hdf", "RootZone": "RootZone_ZBud.hdf"}``.
    zone_def : str, Path, or ZoneDefinition, optional
        Zone definition for aggregation. Passed directly to
        :func:`~iwfm_io.read_zbudget_hdf`.  Provide a path to a ``.dat``
        zone definition file or a :class:`~iwfm_io.models.ZoneDefinition`
        instance.  ``None`` returns raw element-level data (columns = element
        IDs) which produces a much larger DataFrame.
    zones : list of str, optional
        Restrict to these zone names after aggregation. ``None`` = all zones.
        Only effective when *zone_def* is not ``None``.
    zbudget_types : list of str, optional
        Restrict to these type keys from *zbudget_files*. ``None`` = all.
    begin_date, end_date : str, optional
        ISO date strings to slice the time axis.
    interval : str, optional
        Temporal resampling interval (``"1MON"``, ``"1YEAR"``).
    max_workers : int, optional
        When > 1, read the run/zbudget files concurrently in a thread pool.

    Returns
    -------
    pandas.DataFrame
        **When** *zone_def* **is provided** — long-form table with columns:
        ``run, zbudget_type, zone, datetime, component, value``.

        **When** *zone_def* **is** ``None`` — long-form table with columns:
        ``run, zbudget_type, layer, element, datetime, component, value``.

        Missing files are silently skipped (logged at DEBUG level).
    """
    from .readers.hdf5 import read_zbudget_hdf

    active_types = zbudget_types or list(zbudget_files.keys())
    tasks = [
        (run_label, Path(results_dir), ztype)
        for run_label, results_dir in runs.items()
        for ztype in active_types
        if zbudget_files.get(ztype) is not None
    ]

    def _load(task):
        run_label, results_dir, ztype = task
        fname = zbudget_files[ztype]
        path = results_dir / fname
        if not path.exists():
            logger.debug(
                "collect_zbudgets: skip %s/%s — %s not found",
                run_label, ztype, fname,
            )
            return []

        result = read_zbudget_hdf(path, zone_def=zone_def, interval=interval)
        out = []

        if zone_def is not None:
            # Aggregated: data maps zone_name → DataFrame(DatetimeIndex, cols=components)
            zone_names = list(result["data"].keys())
            if zones is not None:
                zone_names = [z for z in zone_names if z in zones]

            for zone_name in zone_names:
                df = result["data"][zone_name].copy()
                if begin_date is not None or end_date is not None:
                    df = df[_date_mask(df.index, begin_date, end_date)]
                df.index.name = "datetime"
                df_long = (
                    df.reset_index()
                      .melt(id_vars="datetime", var_name="component", value_name="value")
                )
                df_long["run"] = run_label
                df_long["zbudget_type"] = ztype
                df_long["zone"] = zone_name
                out.append(df_long)

            logger.debug(
                "collect_zbudgets: ok %s/%s — %d zone(s)",
                run_label, ztype, len(zone_names),
            )

        else:
            # Raw: data maps "Layer_N" → {component_name → DataFrame(DatetimeIndex, cols=elements)}
            for layer_key, data_dict in result["data"].items():
                for comp_name, df in data_dict.items():
                    df = df.copy()
                    if begin_date is not None or end_date is not None:
                        df = df[_date_mask(df.index, begin_date, end_date)]
                    df.index.name = "datetime"
                    df_long = (
                        df.reset_index()
                          .melt(id_vars="datetime", var_name="element", value_name="value")
                    )
                    df_long["run"] = run_label
                    df_long["zbudget_type"] = ztype
                    df_long["layer"] = layer_key
                    df_long["component"] = comp_name
                    out.append(df_long)

            logger.debug(
                "collect_zbudgets: ok %s/%s — raw element-level",
                run_label, ztype,
            )
        return out

    frames = _run_collect_tasks(tasks, _load, max_workers)

    if not frames:
        if zone_def is not None:
            cols = ["run", "zbudget_type", "zone", "datetime", "component", "value"]
        else:
            cols = ["run", "zbudget_type", "layer", "element", "datetime", "component", "value"]
        return pd.DataFrame(columns=cols)

    combined = pd.concat(frames, ignore_index=True)
    combined["datetime"] = pd.to_datetime(combined["datetime"])

    if zone_def is not None:
        combined = combined[
            ["run", "zbudget_type", "zone", "datetime", "component", "value"]
        ]
    else:
        combined = combined[
            ["run", "zbudget_type", "layer", "element", "datetime", "component", "value"]
        ]
    return combined


# ---------------------------------------------------------------------------
# Hydrographs
# ---------------------------------------------------------------------------


def collect_hydrographs(
    runs: Dict[str, Path],
    hydrograph_files: Dict[str, str],
    site_names: Optional[List[str]] = None,
    sites: Optional[List[str]] = None,
    hydrograph_types: Optional[List[str]] = None,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    """Collect hydrograph HDF5 files from multiple runs into a long-form DataFrame.

    Handles ``GWHyd.hdf``, ``StrmHyd.hdf``, ``Subsidence.hdf``,
    ``TileDrainFlows.hdf``, and any HDF5 file that follows the same
    single-dataset layout.

    Because IWFM does not embed site IDs in these HDF5 files, column names
    default to ``col_1``, ``col_2``, …  Supply *site_names* to assign
    meaningful labels (must match the number of data columns exactly).

    Parameters
    ----------
    runs : dict
        Mapping of run label → Results/ directory path.
    hydrograph_files : dict
        Mapping of hydrograph type label → HDF5 filename within Results/.
        Example: ``{"GW": "GWHyd.hdf", "Stream": "StrmHyd.hdf"}``.
    site_names : list of str, optional
        Override the generic ``col_N`` column names with these site labels.
        The list length must match the number of data columns in the file.
        All runs are assumed to share the same site layout.
    sites : list of str, optional
        After name assignment, restrict to these site names. ``None`` = all.
    hydrograph_types : list of str, optional
        Restrict to these type keys from *hydrograph_files*. ``None`` = all.
    begin_date, end_date : str, optional
        ISO date strings to slice the time axis.
    max_workers : int, optional
        When > 1, read the run/hydrograph files concurrently in a thread pool.

    Returns
    -------
    pandas.DataFrame
        Long-form table with columns:
        ``run, hydrograph_type, site, datetime, value``.

        Missing files are silently skipped (logged at DEBUG level).
    """
    from .readers.hdf5 import read_hydrograph_hdf

    active_types = hydrograph_types or list(hydrograph_files.keys())
    tasks = [
        (run_label, Path(results_dir), htype)
        for run_label, results_dir in runs.items()
        for htype in active_types
        if hydrograph_files.get(htype) is not None
    ]

    def _load(task):
        run_label, results_dir, htype = task
        fname = hydrograph_files[htype]
        path = results_dir / fname
        if not path.exists():
            logger.debug(
                "collect_hydrographs: skip %s/%s — %s not found",
                run_label, htype, fname,
            )
            return []

        df = read_hydrograph_hdf(path)

        if site_names is not None:
            if len(site_names) != len(df.columns):
                raise ValueError(
                    f"site_names has {len(site_names)} entries but "
                    f"{fname} has {len(df.columns)} data columns"
                )
            df = df.copy()
            df.columns = site_names

        if sites is not None:
            available = [s for s in sites if s in df.columns]
            if not available:
                logger.debug(
                    "collect_hydrographs: %s/%s — none of the requested "
                    "sites found after name assignment",
                    run_label, htype,
                )
                return []
            df = df[available]

        if begin_date is not None or end_date is not None:
            df = df[_date_mask(df.index, begin_date, end_date)]

        df.index.name = "datetime"
        df_long = (
            df.reset_index()
              .melt(id_vars="datetime", var_name="site", value_name="value")
        )
        df_long["run"] = run_label
        df_long["hydrograph_type"] = htype

        logger.debug(
            "collect_hydrographs: ok %s/%s — %d site(s)",
            run_label, htype, len(df.columns),
        )
        return [df_long]

    frames = _run_collect_tasks(tasks, _load, max_workers)

    if not frames:
        return pd.DataFrame(
            columns=["run", "hydrograph_type", "site", "datetime", "value"]
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[["run", "hydrograph_type", "site", "datetime", "value"]]
    combined["datetime"] = pd.to_datetime(combined["datetime"])
    return combined


# ---------------------------------------------------------------------------
# GW heads (all nodes)
# ---------------------------------------------------------------------------


def collect_gwheads(
    runs: Dict[str, Path],
    head_file: str = "GWHeadAll.hdf",
    nodes: Optional[List[int]] = None,
    layers: Optional[List[int]] = None,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    n_nodes: Optional[int] = None,
    n_layers: Optional[int] = None,
    max_workers: Optional[int] = None,
) -> pd.DataFrame:
    """Collect GW-head-at-all-nodes HDF5 files from multiple runs into a long-form DataFrame.

    For large models (many nodes, long simulations) the resulting DataFrame
    can be very large.  Use *nodes* and *layers* to restrict the output, and
    supply *n_nodes*/*n_layers* so the column parser can filter before melting.

    Parameters
    ----------
    runs : dict
        Mapping of run label → Results/ directory path.
    head_file : str, optional
        HDF5 filename within each Results/ directory.
        Default: ``"GWHeadAll.hdf"``.
    nodes : list of int, optional
        Restrict to these 1-based node IDs. ``None`` = all nodes.
        Requires *n_nodes* and *n_layers* to be provided.
    layers : list of int, optional
        Restrict to these layer numbers. ``None`` = all layers.
        Requires *n_nodes* and *n_layers* to be provided.
    begin_date, end_date : str, optional
        ISO date strings to slice the time axis.
    n_nodes : int, optional
        Number of model nodes.  Passed to :func:`~iwfm_io.read_head_hdf` so
        that columns are named ``node_N_layer_M``.  Strongly recommended —
        without it, *nodes* and *layers* filtering is unavailable.
    n_layers : int, optional
        Number of model layers.  Required alongside *n_nodes*.
    max_workers : int, optional
        When > 1, read the runs' head files concurrently in a thread pool.

    Returns
    -------
    pandas.DataFrame
        Long-form table with columns:
        ``run, node, layer, datetime, head``.

        When *n_nodes*/*n_layers* are not provided, ``node`` holds the
        generic column label (``col_K``) and ``layer`` is ``None``.

        Missing files are silently skipped (logged at DEBUG level).
    """
    from .readers.hdf5 import read_head_hdf

    have_metadata = n_nodes is not None and n_layers is not None
    if not have_metadata and (nodes is not None or layers is not None):
        raise ValueError(
            "collect_gwheads: filtering by nodes/layers needs n_nodes and "
            "n_layers (the head file carries no node ids) -- pass both, or "
            "drop the filters to get every column")
    tasks = [(run_label, Path(results_dir)) for run_label, results_dir in runs.items()]

    def _load(task):
        run_label, results_dir = task
        path = results_dir / head_file
        if not path.exists():
            logger.debug(
                "collect_gwheads: skip %s — %s not found",
                run_label, head_file,
            )
            return []

        df = read_head_hdf(path, n_nodes=n_nodes, n_layers=n_layers)

        # Filter columns by node/layer before melting (avoids huge intermediate frames)
        if have_metadata and (nodes is not None or layers is not None):
            keep = []
            for col in df.columns:
                # col format: "node_N_layer_M"
                parts = col.split("_")
                n = int(parts[1])
                lyr = int(parts[3])
                if (nodes is None or n in nodes) and (layers is None or lyr in layers):
                    keep.append(col)
            df = df[keep]

        if begin_date is not None or end_date is not None:
            df = df[_date_mask(df.index, begin_date, end_date)]

        df.index.name = "datetime"
        df_long = (
            df.reset_index()
              .melt(id_vars="datetime", var_name="_col", value_name="head")
        )
        df_long["run"] = run_label

        if have_metadata:
            split = df_long["_col"].str.extract(r"node_(\d+)_layer_(\d+)")
            df_long["node"] = split[0].astype(int)
            df_long["layer"] = split[1].astype(int)
        else:
            df_long["node"] = df_long["_col"]
            df_long["layer"] = None

        df_long = df_long.drop(columns="_col")

        logger.debug(
            "collect_gwheads: ok %s — %d columns, %d timesteps",
            run_label, len(df.columns), len(df),
        )
        return [df_long]

    frames = _run_collect_tasks(tasks, _load, max_workers)

    if not frames:
        return pd.DataFrame(columns=["run", "node", "layer", "datetime", "head"])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[["run", "node", "layer", "datetime", "head"]]
    combined["datetime"] = pd.to_datetime(combined["datetime"])
    return combined


# ---------------------------------------------------------------------------
# Component-aware budget aggregation
# ---------------------------------------------------------------------------

#: Label column written by :func:`aggregate_budget` for each period kind.
_PERIOD_LABELS = {"WY": "water_year", "CY": "year", "MON": "month"}


def budget_component_agg(name) -> str:
    """How an IWFM budget component aggregates over a period.

    Most budget columns are *flows* and sum over the period, but the
    storage columns are *stocks* and must not be summed:

    - ``Beginning Storage`` → the period's **first** value
    - ``Ending Storage`` → the period's **last** value
    - ``Cumulative …`` (e.g. Cumulative Subsidence) → the **last** value
    - everything else → ``sum``

    Returns ``"first"``, ``"last"``, or ``"sum"``.
    """
    u = str(name).upper()
    if "STORAGE" in u:
        if "BEGINNING" in u:
            return "first"
        if "ENDING" in u:
            return "last"
    if "CUMULATIVE" in u:
        return "last"
    return "sum"


def _period_labels(times, period: str):
    from iwfm_io._tokens import iwfm_day, water_year

    if period == "WY":
        return water_year(times)
    day = iwfm_day(times)
    accessor = day.dt if isinstance(day, pd.Series) else day
    if period == "CY":
        return accessor.year
    if period == "MON":
        return accessor.to_period("M")
    raise ValueError(f"period must be 'WY', 'CY', or 'MON', got {period!r}")


def _effective_col_types(columns, data_types):
    """column -> IWFM data-type code, falling back to the name heuristic."""
    from iwfm_io._budget_agg import VLB, VLE, VR

    heur_code = {"sum": VR, "first": VLB, "last": VLE}
    eff = {}
    for col in columns:
        t = data_types.get(col)
        eff[col] = int(t) if t is not None else \
            heur_code[budget_component_agg(col)]
    return eff


def aggregate_budget(df: pd.DataFrame, period: str = "WY",
                     data_types: Optional[dict] = None) -> pd.DataFrame:
    """Aggregate IWFM budget output over water years, calendar years,
    or months — with the right rule per component.

    Flow components sum over the period; the storage *stocks* do not:
    ``Beginning Storage`` keeps the period's first value, ``Ending
    Storage`` and ``Cumulative …`` columns keep the last (see
    :func:`budget_component_agg`). Period membership honors IWFM's
    ``24:00`` convention via :func:`iwfm_io.water_year` /
    :func:`iwfm_io.iwfm_day`, so a ``09/30_24:00`` stamp lands in the
    water year ending that day.

    Pass the ``data_types`` mapping that :func:`read_budget_hdf` returns
    to get the DLL's exact per-type rules instead of the name heuristic:
    volumetric rates (types 1/9/10/11) sum, beginning storage (2) keeps
    the first value, ending storage (3), area (4) and length (5) keep the
    last — so a monthly Area column no longer sums to ~12x its real value
    — and the LWU trio (Potential CUAW 6 / Ag. Supply Requirement 7 /
    Ag. Shortage 8) uses the DLL's carry-over accumulation (signed
    shortage, previous *raw* shortage carried within each period; see
    :mod:`iwfm_io._budget_agg`).  Columns missing from ``data_types``
    fall back to the name heuristic.

    Parameters
    ----------
    df : DataFrame
        Either a **wide** budget frame — DatetimeIndex, one column per
        component (from ``model.budget_df()`` / ``read_budget_hdf``) —
        or the **long** frame from :func:`collect_budgets` (columns
        ``datetime``, ``component``, ``value`` plus any of ``run``,
        ``budget_type``, ``location``).
    period : str
        ``"WY"`` water years (labeled by ending year), ``"CY"``
        calendar years, or ``"MON"`` months.
    data_types : dict, optional
        component/column name -> IWFM data-type code (1-11), as returned
        by :func:`read_budget_hdf` under ``'data_types'``.

    Returns
    -------
    DataFrame
        Wide input → wide output indexed by the period label.  Long
        input → long output with the label column (``water_year`` /
        ``year`` / ``month``) replacing ``datetime``.
    """
    label_name = _PERIOD_LABELS.get(period)
    if label_name is None:
        raise ValueError(f"period must be one of {sorted(_PERIOD_LABELS)}, "
                         f"got {period!r}")

    long_form = {"datetime", "component", "value"}.issubset(df.columns)
    if long_form:
        keys = [c for c in ("run", "budget_type", "location")
                if c in df.columns]
        if len(df) == 0:
            return pd.DataFrame(columns=keys + [label_name, "component",
                                                "value"])

        if data_types is not None:
            # Type-aware path: pivot each key group to a wide frame so the
            # LWU carry-over can see its companion columns, aggregate,
            # then melt back to long form.
            from iwfm_io._budget_agg import aggregate_frame

            src = df.sort_values("datetime")
            groups = src.groupby(keys, observed=True) if keys \
                else [((), src)]
            pieces = []
            for key_vals, sub in groups:
                if not isinstance(key_vals, tuple):
                    key_vals = (key_vals,)
                wide = sub.pivot_table(
                    index="datetime", columns="component", values="value",
                    aggfunc="first", observed=True)
                # Restore first-appearance component order (pivot_table
                # sorts alphabetically, which would break LWU adjacency)
                order = list(dict.fromkeys(sub["component"]))
                wide = wide[[c for c in order if c in wide.columns]]
                labels = _period_labels(wide.index, period)
                agg = aggregate_frame(
                    wide, _effective_col_types(wide.columns, data_types),
                    np.asarray(labels))
                agg.index.name = label_name
                long_out = agg.reset_index().melt(
                    id_vars=label_name, var_name="component",
                    value_name="value")
                for k, v in zip(keys, key_vals):
                    long_out[k] = v
                pieces.append(long_out[keys + [label_name, "component",
                                               "value"]])
            result = pd.concat(pieces, ignore_index=True)
            return result.sort_values(
                keys + [label_name, "component"]).reset_index(drop=True)

        out = df.sort_values("datetime").copy()
        out[label_name] = _period_labels(out["datetime"], period).values
        how = out["component"].map(budget_component_agg)
        pieces = []
        for rule in ("sum", "first", "last"):
            part = out[how.values == rule]
            if len(part):
                pieces.append(
                    part.groupby(keys + [label_name, "component"],
                                 observed=True)["value"]
                    .agg(rule).reset_index())
        result = pd.concat(pieces, ignore_index=True)
        # a window with a missing step is unknown, not "the sum of the
        # rest" -- match the typed path, which propagates NaN
        gkeys = keys + [label_name, "component"]
        has_nan = (out.assign(_nan=out["value"].isna())
                   .groupby(gkeys, observed=True)["_nan"].any()
                   .rename("_nan").reset_index())
        result = result.merge(has_nan, on=gkeys, how="left")
        result.loc[result["_nan"].fillna(False).astype(bool), "value"] = np.nan
        result = result.drop(columns="_nan")
        return result.sort_values(
            keys + [label_name, "component"]).reset_index(drop=True)

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            "aggregate_budget expects a wide budget frame with a "
            "DatetimeIndex, or a long frame with datetime/component/"
            "value columns")
    df = df.sort_index()
    labels = _period_labels(df.index, period)

    if data_types is not None:
        from iwfm_io._budget_agg import aggregate_frame

        out = aggregate_frame(
            df, _effective_col_types(df.columns, data_types),
            np.asarray(labels))
        out.index.name = label_name
        return out

    agg = {col: budget_component_agg(col) for col in df.columns}
    grouper = pd.Index(labels, name=label_name)
    out = df.groupby(grouper).agg(agg)
    # a window with a missing step is unknown, not "the sum of the rest"
    # (the typed path propagates NaN; keep both paths consistent)
    nan_any = df.isna().groupby(grouper).any()
    return out.mask(nan_any.reindex(out.index)[out.columns])
