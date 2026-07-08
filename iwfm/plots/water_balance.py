"""Water balance storytelling visualizations.

37. Sankey diagram — full system water balance
38. Butterfly chart — inflows vs outflows mirrored bar chart
39. Cumulative departure plot — running sum of (inflow − outflow)
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.sankey import Sankey
from . import excel_date_to_datetime, savefig


# ──────────────────────────────────────────────────────────────────
# 37. Sankey diagram
# ──────────────────────────────────────────────────────────────────

def plot_water_balance_sankey(names, values, title="Water Balance",
                               ax=None, figsize=(14, 8),
                               save_path=None):
    """Sankey diagram of water balance components.

    Parameters
    ----------
    names : list of str
        Component names (e.g. from budget column titles).
    values : list of float
        Average flows. Positive = inflow, negative = outflow.
    title : str
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    # Filter out near-zero flows and the Time column
    filtered = [(n, v) for n, v in zip(names, values)
                if abs(v) > 1e-10 and "time" not in n.lower()]

    if not filtered:
        ax.text(0.5, 0.5, "No significant flows", ha="center", va="center",
                transform=ax.transAxes)
        return fig, ax

    f_names, f_values = zip(*filtered)

    # Normalize for Sankey (positive = in, negative = out)
    sankey = Sankey(ax=ax, unit="", format="%.0f", scale=1.0 / max(abs(v) for v in f_values))
    sankey.add(
        flows=list(f_values),
        labels=list(f_names),
        orientations=[0] * len(f_values),
        pathlengths=[0.4] * len(f_values),
        facecolor="lightsteelblue",
        edgecolor="steelblue",
    )
    sankey.finish()

    ax.set_title(title, fontsize=14)
    ax.axis("off")

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_budget_sankey(model, budget_type, location, begin_date, end_date,
                       interval="1MON", ax=None, figsize=(14, 8),
                       save_path=None):
    """Sankey from model budget time-series averages.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    """
    titles = model.get_budget_column_titles(budget_type, location)
    n_cols = len(titles)
    ts = model.get_budget_timeseries(
        budget_type, location, list(range(1, n_cols + 1)),
        begin_date, end_date, interval,
    )
    avg_vals = ts["values"].mean(axis=0)

    return plot_water_balance_sankey(
        titles, avg_vals.tolist(),
        title=f"Water Balance Sankey — Location {location}",
        ax=ax, figsize=figsize, save_path=save_path,
    )


# ──────────────────────────────────────────────────────────────────
# 38. Butterfly chart
# ──────────────────────────────────────────────────────────────────

def plot_butterfly_chart(names, values, title="Inflows vs Outflows",
                          ax=None, figsize=(10, 8), save_path=None):
    """Mirrored horizontal bar chart: inflows left, outflows right.

    Parameters
    ----------
    names : list of str
    values : list of float
        Positive = inflow, negative = outflow.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    # Separate inflows and outflows
    inflows = [(n, v) for n, v in zip(names, values)
               if v > 0 and "time" not in n.lower()]
    outflows = [(n, abs(v)) for n, v in zip(names, values)
                if v < 0 and "time" not in n.lower()]

    # Sort by magnitude
    inflows.sort(key=lambda x: x[1], reverse=True)
    outflows.sort(key=lambda x: x[1], reverse=True)

    max_len = max(len(inflows), len(outflows))
    y_pos = np.arange(max_len)

    # Inflows (positive direction — right)
    if inflows:
        in_names, in_vals = zip(*inflows)
        ax.barh(y_pos[:len(in_vals)], in_vals, color="steelblue",
                alpha=0.8, label="Inflows")
        for i, (n, v) in enumerate(inflows):
            ax.text(v * 0.5, i, n, ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")

    # Outflows (negative direction — left)
    if outflows:
        out_names, out_vals = zip(*outflows)
        ax.barh(y_pos[:len(out_vals)], [-v for v in out_vals],
                color="indianred", alpha=0.8, label="Outflows")
        for i, (n, v) in enumerate(outflows):
            ax.text(-v * 0.5, i, n, ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")

    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks([])
    ax.set_xlabel("Flow magnitude")
    ax.set_title(title, fontsize=14)
    ax.legend(loc="lower right")
    ax.grid(True, axis="x", alpha=0.3)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_budget_butterfly(model, budget_type, location, begin_date, end_date,
                           interval="1MON", ax=None, figsize=(10, 8),
                           save_path=None):
    """Butterfly chart from model budget time-series averages."""
    titles = model.get_budget_column_titles(budget_type, location)
    n_cols = len(titles)
    ts = model.get_budget_timeseries(
        budget_type, location, list(range(1, n_cols + 1)),
        begin_date, end_date, interval,
    )
    avg_vals = ts["values"].mean(axis=0)

    return plot_butterfly_chart(
        titles, avg_vals.tolist(),
        title=f"Butterfly Chart — Location {location}",
        ax=ax, figsize=figsize, save_path=save_path,
    )


# ──────────────────────────────────────────────────────────────────
# 39. Cumulative departure plot
# ──────────────────────────────────────────────────────────────────

def plot_cumulative_departure(model, budget_type, location,
                               begin_date, end_date, interval="1MON",
                               inflow_cols=None, outflow_cols=None,
                               ax=None, figsize=(12, 5),
                               save_path=None):
    """Running sum of (total inflow − total outflow) over time.

    Upward trend = net storage gain.
    Downward trend = net storage loss.

    Parameters
    ----------
    inflow_cols, outflow_cols : list of int, optional
        Column indices for inflows and outflows. If None, positive-mean
        columns are treated as inflows and negative-mean as outflows.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    titles = model.get_budget_column_titles(budget_type, location)
    n_cols = len(titles)
    ts = model.get_budget_timeseries(
        budget_type, location, list(range(1, n_cols + 1)),
        begin_date, end_date, interval,
    )
    dates = excel_date_to_datetime(ts["dates"])
    values = ts["values"]

    # Auto-classify columns if not specified
    if inflow_cols is None or outflow_cols is None:
        means = values.mean(axis=0)
        # Skip time-like columns (column 0 often is time)
        inflow_cols = [i for i in range(n_cols)
                       if means[i] > 0 and "time" not in titles[i].lower()]
        outflow_cols = [i for i in range(n_cols)
                        if means[i] < 0 and "time" not in titles[i].lower()]

    total_in = values[:, inflow_cols].sum(axis=1) if inflow_cols else np.zeros(len(dates))
    total_out = np.abs(values[:, outflow_cols].sum(axis=1)) if outflow_cols else np.zeros(len(dates))
    net = total_in - total_out
    cumulative = np.cumsum(net)

    ax.fill_between(dates, cumulative, 0,
                    where=cumulative >= 0, color="steelblue", alpha=0.4,
                    label="Net gain")
    ax.fill_between(dates, cumulative, 0,
                    where=cumulative < 0, color="indianred", alpha=0.4,
                    label="Net loss")
    ax.plot(dates, cumulative, "k-", linewidth=1)
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")

    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative departure")
    ax.set_title("Cumulative Departure — Net Water Balance")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm

    with iwfm.IWFMModel(
        preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
        simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as m:
        budgets = m.get_budget_list()
        if budgets:
            bt = budgets[0]["budget_type"]
            bd, ed = "10/01/1990_24:00", "09/30/2000_24:00"
            plot_budget_sankey(m, bt, 1, bd, ed, save_path="sankey.png")
            plot_budget_butterfly(m, bt, 1, bd, ed, save_path="butterfly.png")
            plot_cumulative_departure(m, bt, 1, bd, ed, save_path="cum_dep.png")
    plt.show()
