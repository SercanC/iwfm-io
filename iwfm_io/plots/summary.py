"""Summary and diagnostic visualizations for IWFM model results.

Provides seven high-level plotting functions that summarize budget data,
aquifer parameters, stream rating curves, and supply/demand balances.
All functions follow a common pattern: accept an optional ``ax`` and
``figsize`` for embedding in larger figures, return ``(fig, ax)``, and
optionally save to disk via *save_path*.

Functions
---------
plot_budget_pie
    Pie chart of average absolute flow by budget component.
plot_budget_monthly_average
    Grouped bar chart of monthly averages with std-dev error bars.
plot_budget_annual_bars
    Grouped or stacked bar chart of annual budget totals.
plot_rating_curve
    Stage-discharge rating curves for one or more stream nodes.
plot_aquifer_parameter_histograms
    Histogram grid of Kh, Kv, Sy, Ss for a single aquifer layer.
plot_water_balance_summary
    Horizontal bar chart splitting inflows and outflows.
plot_supply_vs_demand
    Grouped bars comparing supply requirements to shortages.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from . import CUFT_TO_AF, savefig, excel_date_to_datetime, _has_df_methods


# ──────────────────────────────────────────────────────────────────
# Color palette
# ──────────────────────────────────────────────────────────────────

_DEFAULT_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
]

_MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ──────────────────────────────────────────────────────────────────
# 21. Budget Pie Chart
# ──────────────────────────────────────────────────────────────────

def plot_budget_pie(
    model,
    budget_type,
    location,
    begin_date,
    end_date,
    interval="1MON",
    length_unit="FT",
    area_unit="SQ_FT",
    volume_unit="CU_FT",
    fact_lt=1.0,
    fact_ar=1.0,
    fact_vl=CUFT_TO_AF,
    other_threshold=0.03,
    combine_storage=True,
    engine="matplotlib",
    ax=None,
    figsize=(8, 8),
    save_path=None,
    title=None,
):
    """Pie chart of average absolute flow by budget component.

    ``engine="plotly"`` renders an interactive donut (save as ``.html``,
    or ``.png`` with kaleido); returns ``(plotly Figure, None)``.

    ``combine_storage=True`` (default) replaces the cumulative
    Beginning/Ending Storage columns with a single flux-scale
    "Change in Storage" component.

    Components whose fraction of total absolute flow falls below
    *other_threshold* are grouped into an "Other" slice.

    Parameters
    ----------
    model : IWFMModel
        Open model instance (inquiry mode).
    budget_type : int
        Budget type identifier.
    location : int
        Location (e.g. subregion) index for the budget query.
    begin_date, end_date : str
        IWFM-format date strings (``'MM/DD/YYYY_HH:MM'``).
    interval : str, optional
        Time-series interval (default ``'1MON'``).
    length_unit, area_unit, volume_unit : str
        Unit labels forwarded to ``get_budget_column_titles``.
    fact_lt, fact_ar, fact_vl : float
        Conversion factors forwarded to ``get_budget_timeseries``.
    other_threshold : float, optional
        Fractional threshold below which components are grouped
        into "Other" (default 0.03, i.e. 3 %).
    ax : matplotlib.axes.Axes, optional
        Axes to draw on.  A new figure is created if *None*.
    figsize : tuple, optional
        Figure size when creating a new figure.
    save_path : str or pathlib.Path, optional
        If given the figure is saved to this path.
    title : str, optional
        Plot title.  Auto-generated when *None*.

    Returns
    -------
    fig, ax
    """
    # Fetch column titles (skip "Time" column at index 0)
    titles = model.get_budget_column_titles(
        budget_type, location, length_unit, area_unit, volume_unit
    )
    n_cols = len(titles)
    columns = list(range(1, n_cols + 1))

    ts = model.get_budget_timeseries(
        budget_type=budget_type,
        location=location,
        columns=columns,
        begin_date=begin_date,
        end_date=end_date,
        interval=interval,
        fact_lt=fact_lt,
        fact_ar=fact_ar,
        fact_vl=fact_vl,
    )
    values = np.asarray(ts["values"])  # (n_times, n_cols)

    if combine_storage:
        from . import combine_storage_terms
        titles, values = combine_storage_terms(titles, values)
        n_cols = len(titles)

    # Average absolute value per component
    avg_abs = np.abs(values).mean(axis=0)
    total = avg_abs.sum()
    if total == 0:
        total = 1.0  # prevent division by zero

    # Group small slices into "Other"
    fractions = avg_abs / total
    labels = list(titles)
    keep_idx = [i for i in range(n_cols) if fractions[i] >= other_threshold]
    other_val = sum(avg_abs[i] for i in range(n_cols) if fractions[i] < other_threshold)

    pie_vals = [avg_abs[i] for i in keep_idx]
    pie_labels = [labels[i] for i in keep_idx]
    if other_val > 0:
        pie_vals.append(other_val)
        pie_labels.append("Other")

    pie_vals = np.array(pie_vals)

    if engine == "plotly":
        from . import _plotly
        return _plotly.donut(
            pie_labels, pie_vals,
            title or f"Budget Composition (avg |flow|) — Location {location}",
            save_path, figsize)

    colors = _DEFAULT_COLORS[: len(pie_vals)]

    # Plot
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    wedges, texts, autotexts = ax.pie(
        pie_vals,
        labels=pie_labels,
        autopct="%1.1f%%",
        colors=colors,
        startangle=140,
        pctdistance=0.8,
    )
    for t in autotexts:
        t.set_fontsize(9)

    ax.set_title(title or f"Budget Composition (avg |flow|) — Location {location}")

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 22. Budget Monthly Average (grouped bars + error bars)
# ──────────────────────────────────────────────────────────────────

def plot_budget_monthly_average(
    model,
    budget_type,
    location,
    begin_date,
    end_date,
    fact_vl=CUFT_TO_AF,
    max_components=8,
    combine_storage=True,
    engine="matplotlib",
    ax=None,
    figsize=(12, 6),
    save_path=None,
    title=None,
):
    """Grouped bar chart of monthly-average budget flows.

    ``engine="plotly"`` renders an interactive version; returns
    ``(plotly Figure, None)``.

    Each budget component gets one bar per month (12 groups).
    Error bars show one standard deviation.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    budget_type : int
        Budget type identifier.
    location : int
        Budget location index.
    begin_date, end_date : str
        IWFM-format date strings.
    fact_vl : float, optional
        Volume conversion factor (default 1.0).
    max_components : int, optional
        Maximum number of components to display.  The components
        with the largest mean absolute flow are selected; the rest
        are omitted for readability.
    ax : matplotlib.axes.Axes, optional
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, ax
    """
    result = model.get_budget_monthly_average(
        budget_type=budget_type,
        location=location,
        begin_date=begin_date,
        end_date=end_date,
        fact_vl=fact_vl,
    )
    names = result["names"]           # list[str]
    flows = np.asarray(result["flows"])       # (n_flows, 12)
    std_devs = np.asarray(result["std_devs"])  # (n_flows, 12)

    if combine_storage:
        from . import combine_storage_terms
        names, flows, std_devs = combine_storage_terms(
            names, flows, extras=std_devs, component_axis=0)

    n_flows = flows.shape[0]

    # Select top components by mean absolute flow
    mean_abs = np.abs(flows).mean(axis=1)
    if n_flows > max_components:
        top_idx = np.argsort(mean_abs)[::-1][:max_components]
        top_idx = np.sort(top_idx)  # keep original order
    else:
        top_idx = np.arange(n_flows)

    sel_names = [names[i] for i in top_idx]
    sel_flows = flows[top_idx, :]
    sel_std = std_devs[top_idx, :]
    n_sel = len(sel_names)

    if engine == "plotly":
        from . import _plotly
        series = [(n, sel_flows[k]) for k, n in enumerate(sel_names)]
        return _plotly.grouped_bars(
            _MONTH_LABELS, series,
            title or f"Monthly Average Budget — Location {location}",
            "Volume (AF)", save_path, figsize,
            error_bars=[sel_std[k] for k in range(n_sel)])

    # Bar layout
    x = np.arange(12)
    bar_width = 0.8 / max(n_sel, 1)
    offsets = np.linspace(
        -0.4 + bar_width / 2, 0.4 - bar_width / 2, n_sel
    )

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    for k, (name, offset) in enumerate(zip(sel_names, offsets)):
        color = _DEFAULT_COLORS[k % len(_DEFAULT_COLORS)]
        ax.bar(
            x + offset,
            sel_flows[k],
            width=bar_width,
            label=name,
            color=color,
            yerr=sel_std[k],
            capsize=2,
            error_kw={"linewidth": 0.8},
        )

    ax.set_xticks(x)
    ax.set_xticklabels(_MONTH_LABELS)
    ax.set_ylabel("Flow")
    ax.set_title(title or f"Monthly Average Budget — Location {location}")
    ax.legend(fontsize=8, loc="best", ncol=2)
    ax.axhline(0, color="black", linewidth=0.5)
    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 23. Budget Annual Bars
# ──────────────────────────────────────────────────────────────────

def plot_budget_annual_bars(
    model,
    budget_type,
    location,
    begin_date,
    end_date,
    fact_vl=CUFT_TO_AF,
    stacked=False,
    max_components=8,
    combine_storage=True,
    engine="matplotlib",
    ax=None,
    figsize=(14, 6),
    save_path=None,
    title=None,
):
    """Grouped or stacked bar chart of annual budget totals.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    budget_type : int
        Budget type identifier.
    location : int
        Budget location index.
    begin_date, end_date : str
        IWFM-format date strings.
    fact_vl : float, optional
        Volume conversion factor (default 1.0).
    stacked : bool, optional
        If *True* draw a stacked bar chart; otherwise grouped
        (default *False*).
    max_components : int, optional
        Maximum components to show (default 8).
    ax : matplotlib.axes.Axes, optional
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, ax
    """
    result = model.get_budget_annual(
        budget_type=budget_type,
        location=location,
        begin_date=begin_date,
        end_date=end_date,
        fact_vl=fact_vl,
    )
    names = result["names"]                 # list[str]
    flows = np.asarray(result["flows"])     # (n_flows, n_years)
    years = np.asarray(result["years"])     # (n_years,)

    if combine_storage:
        from . import combine_storage_terms
        names, flows = combine_storage_terms(names, flows, component_axis=0)

    n_flows, n_years = flows.shape

    # Select top components
    mean_abs = np.abs(flows).mean(axis=1)
    if n_flows > max_components:
        top_idx = np.argsort(mean_abs)[::-1][:max_components]
        top_idx = np.sort(top_idx)
    else:
        top_idx = np.arange(n_flows)

    sel_names = [names[i] for i in top_idx]
    sel_flows = flows[top_idx, :]
    n_sel = len(sel_names)

    if engine == "plotly":
        from . import _plotly
        series = [(n, sel_flows[k]) for k, n in enumerate(sel_names)]
        return _plotly.grouped_bars(
            [str(y) for y in years], series,
            title or f"Annual Budget — Location {location}",
            "Annual volume (AF)", save_path, figsize,
            barmode="relative" if stacked else "group")

    x = np.arange(n_years)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if stacked:
        # Separate positive and negative for clean stacking
        bottom_pos = np.zeros(n_years)
        bottom_neg = np.zeros(n_years)
        for k in range(n_sel):
            color = _DEFAULT_COLORS[k % len(_DEFAULT_COLORS)]
            vals = sel_flows[k]
            pos = np.where(vals >= 0, vals, 0)
            neg = np.where(vals < 0, vals, 0)
            ax.bar(x, pos, bottom=bottom_pos, label=sel_names[k],
                   color=color, edgecolor="white", linewidth=0.3)
            ax.bar(x, neg, bottom=bottom_neg, color=color,
                   edgecolor="white", linewidth=0.3)
            bottom_pos += pos
            bottom_neg += neg
    else:
        bar_width = 0.8 / max(n_sel, 1)
        offsets = np.linspace(
            -0.4 + bar_width / 2, 0.4 - bar_width / 2, n_sel
        )
        for k, offset in enumerate(offsets):
            color = _DEFAULT_COLORS[k % len(_DEFAULT_COLORS)]
            ax.bar(x + offset, sel_flows[k], width=bar_width,
                   label=sel_names[k], color=color)

    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, ha="right")
    ax.set_ylabel("Annual volume (AF)")
    ax.set_title(title or f"Annual Budget — Location {location}")
    ax.legend(fontsize=8, loc="best", ncol=2)
    ax.axhline(0, color="black", linewidth=0.5)
    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 24. Rating Curve
# ──────────────────────────────────────────────────────────────────

def plot_rating_curve(
    model,
    stream_nodes,
    log_scale=False,
    ax=None,
    figsize=(8, 6),
    save_path=None,
    title=None,
):
    """Stage-discharge rating curves for one or more stream nodes.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    stream_nodes : int or list[int]
        One or more stream-node IDs whose rating tables will be
        plotted.
    log_scale : bool, optional
        Use logarithmic scale on both axes (default *False*).
    ax : matplotlib.axes.Axes, optional
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, ax
    """
    if np.isscalar(stream_nodes):
        stream_nodes = [stream_nodes]

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    if _has_df_methods(model):
        rt_df = model.stream_rating_tables_df()

    for k, sn in enumerate(stream_nodes):
        if _has_df_methods(model):
            sub = rt_df[rt_df["stream_node_id"] == int(sn)]
            stage = sub["stage"].values
            flow = sub["flow"].values
        else:
            stage, flow = model.get_stream_rating_table(int(sn))
            stage = np.asarray(stage)
            flow = np.asarray(flow)
        color = _DEFAULT_COLORS[k % len(_DEFAULT_COLORS)]
        ax.plot(flow, stage, marker="o", markersize=4, linewidth=1.5,
                color=color, label=f"Node {sn}")

    if log_scale:
        ax.set_xscale("log")
        ax.set_yscale("log")

    ax.set_xlabel("Flow")
    ax.set_ylabel("Stage")
    ax.set_title(title or "Stream Rating Curves")
    ax.legend(fontsize=9, loc="best")
    ax.grid(True, which="both", linestyle="--", linewidth=0.4, alpha=0.7)
    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 25. Aquifer Parameter Histograms
# ──────────────────────────────────────────────────────────────────

def plot_aquifer_parameter_histograms(
    model,
    layer=1,
    bins=40,
    include_aquitard_kv=True,
    ax=None,
    figsize=(12, 8),
    save_path=None,
    title=None,
):
    """Histogram grid of aquifer parameters for a single layer.

    Plots histograms of horizontal hydraulic conductivity (Kh),
    vertical hydraulic conductivity (Kv), specific yield (Sy),
    and specific storage (Ss).  Optionally includes aquitard Kv
    in a fifth panel.

    Each subplot is annotated with mean, median, and standard
    deviation.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    layer : int, optional
        Aquifer layer number (1-based, default 1).
    bins : int, optional
        Number of histogram bins (default 40).
    include_aquitard_kv : bool, optional
        If *True* (default), add a panel for aquitard vertical K.
    ax : None
        Ignored; subplots are always created internally.
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, axes : Figure and array of Axes objects.
    """
    idx = layer - 1  # 0-based

    kh = np.asarray(model.get_aquifer_horizontal_k())[:, idx]
    kv = np.asarray(model.get_aquifer_vertical_k())[:, idx]
    sy = np.asarray(model.get_aquifer_specific_yield())[:, idx]
    ss = np.asarray(model.get_aquifer_specific_storage())[:, idx]

    params = [
        ("Horizontal K (Kh)", kh, "#1f77b4"),
        ("Vertical K (Kv)", kv, "#ff7f0e"),
        ("Specific Yield (Sy)", sy, "#2ca02c"),
        ("Specific Storage (Ss)", ss, "#d62728"),
    ]

    if include_aquitard_kv:
        aq_kv = np.asarray(model.get_aquitard_vertical_k())[:, idx]
        params.append(("Aquitard Kv", aq_kv, "#9467bd"))

    n_params = len(params)
    if n_params <= 4:
        nrows, ncols = 2, 2
    else:
        nrows, ncols = 2, 3

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    axes_flat = axes.flatten()

    for i, (label, data, color) in enumerate(params):
        ax_i = axes_flat[i]
        valid = data[np.isfinite(data)]
        if len(valid) == 0:
            ax_i.set_title(f"{label} — no data")
            continue

        ax_i.hist(valid, bins=bins, color=color, edgecolor="white",
                  linewidth=0.4, alpha=0.85)
        ax_i.set_title(label, fontsize=11)
        ax_i.set_xlabel("Value")
        ax_i.set_ylabel("Count")
        ax_i.yaxis.set_major_locator(MaxNLocator(integer=True))

        # Statistics annotation
        mean_val = np.mean(valid)
        med_val = np.median(valid)
        std_val = np.std(valid)
        stats_text = (
            f"Mean: {mean_val:.4g}\n"
            f"Median: {med_val:.4g}\n"
            f"Std: {std_val:.4g}\n"
            f"N: {len(valid)}"
        )
        ax_i.text(
            0.97, 0.95, stats_text,
            transform=ax_i.transAxes,
            fontsize=8,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="gray", alpha=0.85),
        )

    # Hide unused subplots
    for j in range(n_params, len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.suptitle(
        title or f"Aquifer Parameter Distributions — Layer {layer}",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    if save_path:
        savefig(fig, save_path)

    return fig, axes


# ──────────────────────────────────────────────────────────────────
# 26. Water Balance Summary (horizontal bars)
# ──────────────────────────────────────────────────────────────────

def plot_water_balance_summary(
    model,
    budget_type,
    location,
    begin_date,
    end_date,
    interval="1MON",
    length_unit="FT",
    area_unit="SQ_FT",
    volume_unit="CU_FT",
    fact_lt=1.0,
    fact_ar=1.0,
    fact_vl=CUFT_TO_AF,
    combine_storage=True,
    ax=None,
    figsize=(10, 7),
    save_path=None,
    title=None,
):
    """Horizontal bar chart of mean inflows (positive) and outflows (negative).

    Components are classified by the sign of their time-averaged
    value: positive means inflow, negative means outflow.  Bars
    extend to the right for inflows and to the left for outflows,
    giving an intuitive visual balance.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    budget_type : int
        Budget type identifier.
    location : int
        Budget location index.
    begin_date, end_date : str
        IWFM-format date strings.
    interval : str, optional
        Time-series interval (default ``'1MON'``).
    length_unit, area_unit, volume_unit : str
        Unit labels for column titles.
    fact_lt, fact_ar, fact_vl : float
        Conversion factors.
    ax : matplotlib.axes.Axes, optional
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, ax
    """
    titles = model.get_budget_column_titles(
        budget_type, location, length_unit, area_unit, volume_unit
    )
    n_cols = len(titles)
    columns = list(range(1, n_cols + 1))

    ts = model.get_budget_timeseries(
        budget_type=budget_type,
        location=location,
        columns=columns,
        begin_date=begin_date,
        end_date=end_date,
        interval=interval,
        fact_lt=fact_lt,
        fact_ar=fact_ar,
        fact_vl=fact_vl,
    )
    values = np.asarray(ts["values"])  # (n_times, n_cols)

    if combine_storage:
        from . import combine_storage_terms
        titles, values = combine_storage_terms(titles, values)

    # Sign magnitudes by their label direction ((+)/(-) tags) so the
    # in/out classification below is physical
    from . import sign_budget_components
    titles, means = sign_budget_components(titles, values.mean(axis=0))
    n_cols = len(titles)

    # Separate into inflows and outflows
    inflow_idx = [i for i in range(n_cols) if means[i] > 0]
    outflow_idx = [i for i in range(n_cols) if means[i] < 0]
    # Components with exactly zero mean are omitted

    in_names = [titles[i] for i in inflow_idx]
    in_vals = [means[i] for i in inflow_idx]
    out_names = [titles[i] for i in outflow_idx]
    out_vals = [means[i] for i in outflow_idx]  # negative values

    # Sort by magnitude within each group
    in_order = np.argsort(in_vals)[::-1]
    out_order = np.argsort([-v for v in out_vals])[::-1]

    sorted_names = [in_names[j] for j in in_order] + [out_names[j] for j in out_order]
    sorted_vals = [in_vals[j] for j in in_order] + [out_vals[j] for j in out_order]

    n_bars = len(sorted_names)
    if n_bars == 0:
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = ax.figure
        ax.set_title(title or "Water Balance — no non-zero components")
        return fig, ax

    y_pos = np.arange(n_bars)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    colors = []
    n_in = len(in_order)
    for k in range(n_bars):
        if k < n_in:
            colors.append("#2ca02c")  # green for inflows
        else:
            colors.append("#d62728")  # red for outflows

    ax.barh(y_pos, sorted_vals, color=colors, edgecolor="white",
            linewidth=0.4, height=0.7)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(sorted_names, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Mean Flow (positive = inflow, negative = outflow)")
    ax.set_title(title or f"Water Balance Summary — Location {location}")

    # Add a divider line between inflows and outflows
    if n_in > 0 and len(out_order) > 0:
        ax.axhline(n_in - 0.5, color="gray", linewidth=0.8, linestyle="--")

    # Value annotations on bars
    for k in range(n_bars):
        val = sorted_vals[k]
        ha = "left" if val >= 0 else "right"
        offset = abs(val) * 0.02 + abs(max(sorted_vals, key=abs)) * 0.01
        x_text = val + offset if val >= 0 else val - offset
        ax.text(x_text, y_pos[k], f"{val:,.1f}", va="center", ha=ha,
                fontsize=8, color="black")

    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 27. Supply vs Demand
# ──────────────────────────────────────────────────────────────────

def plot_supply_vs_demand(
    model,
    location_type,
    locations,
    supply_type,
    supplies,
    factor=1.0,
    ax=None,
    figsize=(12, 6),
    save_path=None,
    title=None,
):
    """Grouped bar chart of supply requirements vs shortages.

    For each location or supply, four bars are shown:
    agricultural requirement, agricultural shortage, urban
    requirement, and urban shortage.

    Parameters
    ----------
    model : IWFMModel
        Open model instance.
    location_type : int
        Location type ID (e.g., element or subregion).
    locations : array-like of int
        Location IDs to query for requirements.
    supply_type : int
        Supply type ID (e.g., diversion or pumping).
    supplies : array-like of int
        Supply IDs to query for shortages.
    factor : float, optional
        Conversion factor (default 1.0).
    ax : matplotlib.axes.Axes, optional
    figsize : tuple, optional
    save_path : str or pathlib.Path, optional
    title : str, optional

    Returns
    -------
    fig, ax
    """
    locations = np.atleast_1d(locations)
    supplies = np.atleast_1d(supplies)

    req_ag = np.asarray(
        model.get_supply_requirement_ag(location_type, locations, factor)
    )
    req_urban = np.asarray(
        model.get_supply_requirement_urban(location_type, locations, factor)
    )
    short_ag = np.asarray(
        model.get_supply_short_at_origin_ag(supply_type, supplies, factor)
    )
    short_urban = np.asarray(
        model.get_supply_short_at_origin_urban(supply_type, supplies, factor)
    )

    # Build labels — use location/supply IDs or subregion names
    n_loc = len(locations)
    n_sup = len(supplies)
    n_groups = max(n_loc, n_sup)

    group_labels = []
    for i in range(n_groups):
        if i < n_loc:
            try:
                name = model.get_subregion_name(int(locations[i]))
                group_labels.append(name)
            except Exception:
                group_labels.append(f"Loc {locations[i]}")
        else:
            group_labels.append(f"Supply {supplies[i]}")

    # Pad arrays to same length for consistent plotting
    def _pad(arr, n):
        if len(arr) >= n:
            return arr[:n]
        return np.concatenate([arr, np.zeros(n - len(arr))])

    req_ag = _pad(req_ag, n_groups)
    req_urban = _pad(req_urban, n_groups)
    short_ag = _pad(short_ag, n_groups)
    short_urban = _pad(short_urban, n_groups)

    x = np.arange(n_groups)
    bar_width = 0.18

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    ax.bar(x - 1.5 * bar_width, req_ag, width=bar_width,
           label="Ag Requirement", color="#2ca02c")
    ax.bar(x - 0.5 * bar_width, np.abs(short_ag), width=bar_width,
           label="Ag Shortage", color="#98df8a")
    ax.bar(x + 0.5 * bar_width, req_urban, width=bar_width,
           label="Urban Requirement", color="#1f77b4")
    ax.bar(x + 1.5 * bar_width, np.abs(short_urban), width=bar_width,
           label="Urban Shortage", color="#aec7e8")

    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Volume")
    ax.set_title(title or "Supply Requirements vs Shortages")
    ax.legend(fontsize=9, loc="best")
    ax.axhline(0, color="black", linewidth=0.5)
    fig.tight_layout()

    if save_path:
        savefig(fig, save_path)

    return fig, ax


# ──────────────────────────────────────────────────────────────────
# Main — example usage
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm_io

    # Adjust paths to your model
    PP_FILE = ".assets/sample_model/Simulation/PreProcessor.bin"
    SIM_FILE = ".assets/sample_model/Simulation/Simulation_MAIN.IN"
    BEGIN = "10/01/1990_24:00"
    END = "09/30/2000_24:00"

    with iwfm_io.dll.IWFMModel(
        preprocessor_file=PP_FILE,
        simulation_file=SIM_FILE,
        is_for_inquiry=True,
    ) as model:

        # Discover available budgets
        budgets = model.get_budget_list()
        if budgets:
            bt = budgets[0]["budget_type"]
            loc = 1

            # 21. Pie chart
            fig, ax = plot_budget_pie(
                model, bt, loc, BEGIN, END,
                save_path="budget_pie.png",
            )
            plt.close(fig)

            # 22. Monthly average
            fig, ax = plot_budget_monthly_average(
                model, bt, loc, BEGIN, END,
                save_path="budget_monthly_avg.png",
            )
            plt.close(fig)

            # 23. Annual bars
            fig, ax = plot_budget_annual_bars(
                model, bt, loc, BEGIN, END,
                save_path="budget_annual.png",
            )
            plt.close(fig)

            # 26. Water balance summary
            fig, ax = plot_water_balance_summary(
                model, bt, loc, BEGIN, END,
                save_path="water_balance.png",
            )
            plt.close(fig)

        # 24. Rating curves
        sn_ids = model.get_stream_node_ids()
        if len(sn_ids) >= 3:
            fig, ax = plot_rating_curve(
                model, sn_ids[:3].tolist(),
                log_scale=True,
                save_path="rating_curves.png",
            )
            plt.close(fig)

        # 25. Aquifer parameter histograms
        fig, axes = plot_aquifer_parameter_histograms(
            model, layer=1,
            save_path="aquifer_params.png",
        )
        plt.close(fig)

        # 27. Supply vs demand
        sub_ids = model.get_subregion_ids()
        if len(sub_ids) > 0:
            try:
                fig, ax = plot_supply_vs_demand(
                    model,
                    location_type=1,
                    locations=sub_ids[:3],
                    supply_type=1,
                    supplies=sub_ids[:3],
                    save_path="supply_demand.png",
                )
                plt.close(fig)
            except Exception as exc:
                print(f"Supply vs demand skipped: {exc}")

    print("Done — all summary plots generated.")
