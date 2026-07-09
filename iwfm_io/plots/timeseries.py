"""Time-series visualization functions for the IWFM Python wrapper.

Provides seven plotting functions for groundwater heads, stream flow and
stage, budget and zone-budget components, cumulative groundwater storage
change, and land-use area evolution over time.

All functions follow a consistent interface:

- Accept an ``IWFMModel`` instance as the first argument.
- Accept optional *ax*, *figsize*, and *save_path* keyword arguments.
- Return ``(fig, ax)`` so the caller can further customise the plot.
- Convert IWFM Excel serial dates to ``datetime`` via
  :func:`excel_date_to_datetime`.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from . import CUFT_TO_AF, excel_date_to_datetime, savefig


# ──────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────

def _prepare_axes(ax, figsize):
    """Return (fig, ax), creating a new figure when *ax* is None."""
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    return fig, ax


def _format_date_axis(ax, rotation=30):
    """Apply sensible date formatting to the x-axis."""
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in ax.get_xticklabels():
        label.set_rotation(rotation)
        label.set_ha("right")


def _finalise(fig, ax, title, ylabel, save_path, dpi, legend=True):
    """Apply common finishing touches and optionally save."""
    if title:
        ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Date")
    ax.grid(True, linestyle="--", alpha=0.5)
    if legend:
        # Deduplicate labels (e.g. a column present in both the positive
        # and negative stacks of a stacked budget plot)
        handles, labels = ax.get_legend_handles_labels()
        dedup = {}
        for h, l in zip(handles, labels):
            dedup.setdefault(l, h)
        ax.legend(dedup.values(), dedup.keys(), loc="best",
                  fontsize="small", framealpha=0.8)
    _format_date_axis(ax)
    fig.tight_layout()
    if save_path:
        savefig(fig, save_path, dpi=dpi)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 12. Groundwater head hydrographs
# ──────────────────────────────────────────────────────────────────

def plot_gw_head_hydrographs(
    model,
    node_indices,
    layer=1,
    begin_date=None,
    end_date=None,
    interval="1MON",
    layers=None,
    factor=1.0,
    title="Groundwater Head Hydrographs",
    ylabel="Head (ft)",
    ax=None,
    figsize=(12, 5),
    save_path=None,
    dpi=150,
):
    """Multi-line plot of groundwater head vs. time at selected nodes.

    Parameters
    ----------
    model : IWFMModel
        Active model instance.
    node_indices : list[int]
        Zero-based node indices to plot.
    layer : int, optional
        Layer number (1-based).  Used when *layers* is ``None``.
    begin_date, end_date : str
        IWFM date strings (``'MM/DD/YYYY_HH:MM'``).  If ``None`` the full
        simulation period is used.
    interval : str, optional
        Output time-step label, default ``'1MON'``.
    layers : list[int] or None
        If given **and** *node_indices* contains exactly one node, plot
        that node across all listed layers (multi-layer overlay).
    factor : float, optional
        Length conversion factor passed to ``get_gw_heads_for_layer``.
    title, ylabel : str
    ax : matplotlib.axes.Axes or None
    figsize : tuple
    save_path : str or None
    dpi : int

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    fig, ax = _prepare_axes(ax, figsize)

    node_ids = model.get_node_ids()

    # Multi-layer overlay for a single node
    if layers is not None and len(node_indices) == 1:
        nidx = node_indices[0]
        nid = int(node_ids[nidx])
        for lyr in layers:
            dates_arr, heads = model.get_gw_heads_for_layer(
                lyr, begin_date, end_date, factor=factor
            )
            datetimes = excel_date_to_datetime(dates_arr)
            ax.plot(datetimes, heads[nidx, :], label=f"Node {nid} - Layer {lyr}")
    else:
        # Single layer, multiple nodes
        dates_arr, heads = model.get_gw_heads_for_layer(
            layer, begin_date, end_date, factor=factor
        )
        datetimes = excel_date_to_datetime(dates_arr)
        for nidx in node_indices:
            nid = int(node_ids[nidx])
            ax.plot(datetimes, heads[nidx, :], label=f"Node {nid}")

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 13. Stream flow hydrograph
# ──────────────────────────────────────────────────────────────────

def plot_stream_flow_hydrograph(
    model,
    stream_node_indices,
    begin_date=None,
    end_date=None,
    interval="1MON",
    fact_lt=1.0,
    fact_vl=1.0,
    title="Stream Flow Hydrograph",
    ylabel="Flow (cfs)",
    ax=None,
    figsize=(12, 5),
    save_path=None,
    dpi=150,
):
    """Plot stream flow vs. time at selected stream nodes.

    Uses the hydrograph API with the ``'Stream flow'`` hydrograph type.

    Parameters
    ----------
    model : IWFMModel
    stream_node_indices : list[int]
        Zero-based indices into the stream-node ID array.
    begin_date, end_date : str or None
    interval : str
    fact_lt, fact_vl : float
        Length and volumetric conversion factors.
    title, ylabel : str
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    fig, ax = _prepare_axes(ax, figsize)

    # Identify the flow hydrograph type
    hyd_types = model.get_hydrograph_type_list()
    flow_type = None
    for ht in hyd_types:
        if "flow" in ht["name"].lower():
            flow_type = ht["location_type"]
            break
    if flow_type is None:
        flow_type = hyd_types[0]["location_type"]

    stream_ids = model.get_stream_node_ids()

    for sn_idx in stream_node_indices:
        sn_id = int(stream_ids[sn_idx])
        dates_arr, values = model.get_hydrograph(
            flow_type, sn_idx, 1, begin_date, end_date, interval,
            fact_lt=fact_lt, fact_vl=fact_vl,
        )
        datetimes = excel_date_to_datetime(dates_arr)
        ax.plot(datetimes, values, label=f"Stream Node {sn_id}")

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 14. Stream stage hydrograph
# ──────────────────────────────────────────────────────────────────

def plot_stream_stage_hydrograph(
    model,
    stream_node_indices,
    begin_date=None,
    end_date=None,
    interval="1MON",
    fact_lt=1.0,
    fact_vl=1.0,
    title="Stream Stage Hydrograph",
    ylabel="Stage (ft)",
    ax=None,
    figsize=(12, 5),
    save_path=None,
    dpi=150,
):
    """Plot stream stage (water surface elevation) vs. time.

    Parameters
    ----------
    model : IWFMModel
    stream_node_indices : list[int]
        Zero-based indices into the stream-node ID array.
    begin_date, end_date : str or None
    interval : str
    fact_lt, fact_vl : float
    title, ylabel : str
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    fig, ax = _prepare_axes(ax, figsize)

    # Identify the stage hydrograph type
    hyd_types = model.get_hydrograph_type_list()
    stage_type = None
    for ht in hyd_types:
        if "stage" in ht["name"].lower():
            stage_type = ht["location_type"]
            break
    if stage_type is None:
        # Fallback: pick the second type if available, else the first
        stage_type = hyd_types[1]["location_type"] if len(hyd_types) > 1 else hyd_types[0]["location_type"]

    stream_ids = model.get_stream_node_ids()

    for sn_idx in stream_node_indices:
        sn_id = int(stream_ids[sn_idx])
        dates_arr, values = model.get_hydrograph(
            stage_type, sn_idx, 1, begin_date, end_date, interval,
            fact_lt=fact_lt, fact_vl=fact_vl,
        )
        datetimes = excel_date_to_datetime(dates_arr)
        ax.plot(datetimes, values, label=f"Stream Node {sn_id}")

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 15. Budget time series
# ──────────────────────────────────────────────────────────────────

def plot_budget_timeseries(
    model,
    budget_type,
    location,
    begin_date=None,
    end_date=None,
    interval="1MON",
    stacked=True,
    columns=None,
    fact_lt=1.0,
    fact_ar=1.0,
    fact_vl=CUFT_TO_AF,
    combine_storage=True,
    title=None,
    ylabel="Volume (AF)",
    ax=None,
    figsize=(12, 6),
    save_path=None,
    dpi=150,
):
    """Plot budget components as a stacked area chart or multi-line chart.

    Parameters
    ----------
    model : IWFMModel
    budget_type : str
        Budget type name (e.g. from ``model.get_budget_list()``).
    location : int
        Location identifier (subregion ID, element ID, etc.).
    begin_date, end_date : str or None
    interval : str
    stacked : bool
        If ``True`` (default) produce a stacked area chart for positive
        and negative components; otherwise a simple multi-line chart.
    columns : list[int] or None
        Column indices to retrieve.  ``None`` retrieves all columns.
    fact_lt, fact_ar, fact_vl : float
        Unit conversion factors.
    combine_storage : bool
        Replace the cumulative Beginning/Ending Storage columns with a
        single flux-scale "Change in Storage" (ending − beginning)
        column, so storage doesn't dwarf the other components
        (default True).
    title, ylabel : str
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    # Column titles for legend labels (result["data_types"] holds
    # integer type codes, not names)
    try:
        titles = list(model.get_budget_column_titles(budget_type, location))
    except Exception:
        titles = None

    if columns is None:
        n_cols = len(titles) if titles else \
            model.get_budget_n_columns(budget_type, location)
        columns = list(range(1, n_cols + 1))

    result = model.get_budget_timeseries(
        budget_type, location, columns, begin_date, end_date,
        interval, fact_lt, fact_ar, fact_vl,
    )

    dates_arr = result["dates"]
    values = np.asarray(result["values"])       # (n_times, n_cols)
    if titles:
        col_names = [titles[c - 1] if 1 <= c <= len(titles) else f"Column {c}"
                     for c in columns]
    else:
        col_names = [f"Column {c}" for c in columns]

    if combine_storage:
        from . import combine_storage_terms
        col_names, values = combine_storage_terms(col_names, values)

    datetimes = excel_date_to_datetime(dates_arr)

    fig, ax = _prepare_axes(ax, figsize)

    if stacked:
        # Separate positive and negative components for a clean stack
        pos = np.clip(values, 0, None)
        neg = np.clip(values, None, 0)

        has_pos = pos.sum(axis=0) > 0
        has_neg = neg.sum(axis=0) < 0

        if has_pos.any():
            ax.stackplot(
                datetimes,
                pos[:, has_pos].T,
                labels=[col_names[i] for i, hp in enumerate(has_pos) if hp],
                alpha=0.75,
            )
        if has_neg.any():
            ax.stackplot(
                datetimes,
                neg[:, has_neg].T,
                labels=[col_names[i] for i, hn in enumerate(has_neg) if hn],
                alpha=0.75,
            )
    else:
        for j in range(values.shape[1]):
            ax.plot(datetimes, values[:, j], label=col_names[j])

    if title is None:
        title = f"Budget: {budget_type} (Location {location})"

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 16. Zone budget time series
# ──────────────────────────────────────────────────────────────────

def plot_zbudget_timeseries(
    model,
    zbudget_type,
    zone_id,
    columns,
    zone_extent,
    elements,
    layers,
    zone_ids,
    begin_date=None,
    end_date=None,
    interval="1MON",
    fact_ar=1.0,
    fact_vl=CUFT_TO_AF,
    title=None,
    ylabel="Volume (AF)",
    stacked=False,
    ax=None,
    figsize=(12, 6),
    save_path=None,
    dpi=150,
):
    """Plot zone-budget components over time.

    Parameters
    ----------
    model : IWFMModel
    zbudget_type : str
        Zone budget type name.
    zone_id : int
        Zone identifier.
    columns : list[int]
        Column indices to retrieve.
    zone_extent, elements, layers, zone_ids
        Passed directly to ``model.get_zbudget_timeseries``.
    begin_date, end_date : str or None
    interval : str
    fact_ar, fact_vl : float
    title, ylabel : str
    stacked : bool
        If ``True`` produce a stacked area chart; otherwise lines.
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    result = model.get_zbudget_timeseries(
        zbudget_type, zone_id, columns, zone_extent, elements, layers,
        zone_ids, begin_date, end_date, interval, fact_ar, fact_vl,
    )

    dates_arr = result["dates"]
    values = result["values"]       # (n_times, n_cols)
    col_names = result.get("data_types", [f"Column {c}" for c in columns])

    datetimes = excel_date_to_datetime(dates_arr)

    fig, ax = _prepare_axes(ax, figsize)

    if stacked:
        pos = np.clip(values, 0, None)
        neg = np.clip(values, None, 0)
        has_pos = pos.sum(axis=0) > 0
        has_neg = neg.sum(axis=0) < 0

        if has_pos.any():
            ax.stackplot(
                datetimes,
                pos[:, has_pos].T,
                labels=[col_names[i] for i, hp in enumerate(has_pos) if hp],
                alpha=0.75,
            )
        if has_neg.any():
            ax.stackplot(
                datetimes,
                neg[:, has_neg].T,
                labels=[col_names[i] for i, hn in enumerate(has_neg) if hn],
                alpha=0.75,
            )
    else:
        for j in range(values.shape[1]):
            ax.plot(datetimes, values[:, j], label=col_names[j])

    if title is None:
        title = f"Zone Budget: {zbudget_type} (Zone {zone_id})"

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 17. Cumulative groundwater storage change
# ──────────────────────────────────────────────────────────────────

def plot_cumulative_gw_storage_change(
    model,
    subregions,
    begin_date=None,
    end_date=None,
    interval="1MON",
    fact_vl=1.0,
    title="Cumulative GW Storage Change",
    ylabel="Cumulative Storage Change (AF)",
    ax=None,
    figsize=(12, 5),
    save_path=None,
    dpi=150,
):
    """Line chart of cumulative groundwater storage change.

    Parameters
    ----------
    model : IWFMModel
    subregions : int or list[int]
        One or more subregion IDs.
    begin_date, end_date : str or None
    interval : str
    fact_vl : float
        Volumetric conversion factor.
    title, ylabel : str
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    if isinstance(subregions, (int, np.integer)):
        subregions = [subregions]

    fig, ax = _prepare_axes(ax, figsize)

    for sub_id in subregions:
        dates_arr, values = model.get_budget_cum_gw_storage_change(
            sub_id, begin_date, end_date, interval, fact_vl,
        )
        datetimes = excel_date_to_datetime(dates_arr)
        sub_name = model.get_subregion_name(sub_id)
        label = f"{sub_name} (ID {sub_id})" if sub_name else f"Subregion {sub_id}"
        ax.plot(datetimes, values, label=label)

    ax.axhline(0, color="black", linewidth=0.6, linestyle="--")

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# 18. Land use area time series
# ──────────────────────────────────────────────────────────────────

def plot_land_use_area_timeseries(
    model,
    begin_date=None,
    end_date=None,
    lu_types=None,
    fact_area=1.0,
    title="Land Use Area Over Time",
    ylabel="Area (acres)",
    ax=None,
    figsize=(12, 6),
    save_path=None,
    dpi=150,
):
    """Stacked area chart of land-use categories over time.

    Retrieves area time series for each land-use type and stacks them
    to show the evolution of total and component-wise land use.

    Parameters
    ----------
    model : IWFMModel
    begin_date, end_date : str or None
    lu_types : list[dict] or None
        Each dict must have ``'lu_type'`` (land use type identifier) and
        ``'lu'`` (specific land-use index) and optionally ``'label'``.
        When ``None`` a default set is constructed from
        ``model.get_n_ag_crops()`` plus urban and native/riparian
        categories.
    fact_area : float
        Area conversion factor.
    title, ylabel : str
    ax, figsize, save_path, dpi : optional

    Returns
    -------
    (fig, ax)
    """
    if begin_date is None or end_date is None:
        specs = model.get_time_specs()
        if begin_date is None:
            begin_date = specs["dates"][0]
        if end_date is None:
            end_date = specs["dates"][-1]

    # Build default land-use type list if not provided
    if lu_types is None:
        n_crops = model.get_n_ag_crops()
        lu_types = []
        for c in range(1, n_crops + 1):
            lu_types.append({"lu_type": "AG", "lu": c, "label": f"Ag Crop {c}"})
        lu_types.append({"lu_type": "Urban", "lu": 1, "label": "Urban"})
        lu_types.append({
            "lu_type": "NativeRiparian", "lu": 1, "label": "Native/Riparian",
        })

    fig, ax = _prepare_axes(ax, figsize)

    all_areas = []
    labels = []
    datetimes = None

    for entry in lu_types:
        lu_type = entry["lu_type"]
        lu = entry["lu"]
        label = entry.get("label", f"{lu_type} {lu}")

        areas = model.get_land_use_areas(
            begin_date, end_date, lu_type, lu, fact_area=fact_area,
        )
        # areas shape: (n_elements, n_times) -- sum across elements
        total_by_time = areas.sum(axis=0)

        # Resolve datetimes from model time specs on first iteration
        if datetimes is None:
            specs = model.get_time_specs()
            all_dates = specs["dates"]
            # Determine how many time steps were returned
            n_times = total_by_time.shape[0]
            # Use last n_times dates from the period
            date_strs = all_dates[:n_times] if n_times <= len(all_dates) else all_dates
            from . import iwfm_datestr_to_datetime
            datetimes = [iwfm_datestr_to_datetime(d) for d in date_strs]

        all_areas.append(total_by_time)
        labels.append(label)

    if all_areas:
        stacked = np.row_stack(all_areas)
        ax.stackplot(datetimes, stacked, labels=labels, alpha=0.8)

    return _finalise(fig, ax, title, ylabel, save_path, dpi)


# ──────────────────────────────────────────────────────────────────
# Main block — example usage
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("IWFM Time-Series Plotting Examples")
    print("=" * 50)
    print()
    print("This module is intended to be imported and used with an active")
    print("IWFMModel instance.  Example usage:")
    print()
    print("    from iwfm_io import IWFMModel")
    print("    from iwfm_io.plots.timeseries import (")
    print("        plot_gw_head_hydrographs,")
    print("        plot_stream_flow_hydrograph,")
    print("        plot_stream_stage_hydrograph,")
    print("        plot_budget_timeseries,")
    print("        plot_zbudget_timeseries,")
    print("        plot_cumulative_gw_storage_change,")
    print("        plot_land_use_area_timeseries,")
    print("    )")
    print()
    print("    model = IWFMModel(preprocessor_file='Preprocessor.in',")
    print("                       simulation_file='Simulation.in')")
    print()
    print("    # 12. Groundwater head hydrographs at nodes 0, 5, 10")
    print("    fig, ax = plot_gw_head_hydrographs(")
    print("        model, node_indices=[0, 5, 10], layer=1,")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='gw_heads.png',")
    print("    )")
    print()
    print("    # Multi-layer overlay for a single node")
    print("    fig, ax = plot_gw_head_hydrographs(")
    print("        model, node_indices=[0], layers=[1, 2, 3],")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("    )")
    print()
    print("    # 13. Stream flow hydrograph")
    print("    fig, ax = plot_stream_flow_hydrograph(")
    print("        model, stream_node_indices=[0, 10],")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='stream_flow.png',")
    print("    )")
    print()
    print("    # 14. Stream stage hydrograph")
    print("    fig, ax = plot_stream_stage_hydrograph(")
    print("        model, stream_node_indices=[0, 10],")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='stream_stage.png',")
    print("    )")
    print()
    print("    # 15. Budget time series (stacked area)")
    print("    budgets = model.get_budget_list()")
    print("    fig, ax = plot_budget_timeseries(")
    print("        model, budget_type=budgets[0]['name'], location=1,")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        stacked=True, save_path='budget.png',")
    print("    )")
    print()
    print("    # 16. Zone budget time series")
    print("    zbudgets = model.get_zbudget_list()")
    print("    fig, ax = plot_zbudget_timeseries(")
    print("        model, zbudget_type=zbudgets[0]['name'], zone_id=1,")
    print("        columns=[0, 1, 2], zone_extent='Zone',")
    print("        elements=None, layers=None, zone_ids=None,")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='zbudget.png',")
    print("    )")
    print()
    print("    # 17. Cumulative GW storage change")
    print("    sub_ids = model.get_subregion_ids()")
    print("    fig, ax = plot_cumulative_gw_storage_change(")
    print("        model, subregions=sub_ids[:3],")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='gw_storage_change.png',")
    print("    )")
    print()
    print("    # 18. Land use area time series")
    print("    fig, ax = plot_land_use_area_timeseries(")
    print("        model,")
    print("        begin_date='10/01/1990_24:00', end_date='09/30/2010_24:00',")
    print("        save_path='land_use.png',")
    print("    )")
    print()
    print("    model.kill()")
