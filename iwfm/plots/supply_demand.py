"""Supply–demand narrative visualizations.

45. Supply gap timeline — requirement vs delivery over time
46. Pumping depth vs shortage scatter
"""

import numpy as np
import matplotlib.pyplot as plt
from . import excel_date_to_datetime, savefig


# ──────────────────────────────────────────────────────────────────
# 45. Supply gap timeline
# ──────────────────────────────────────────────────────────────────

def plot_supply_gap_timeline(dates, requirement, actual,
                              label="Water Supply",
                              ax=None, figsize=(12, 5),
                              save_path=None):
    """Stacked area: requirement on top, actual delivery below, gap in red.

    Parameters
    ----------
    dates : list of datetime
    requirement : array-like
        Required supply at each time step.
    actual : array-like
        Actual delivery at each time step.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    requirement = np.asarray(requirement, dtype=float)
    actual = np.asarray(actual, dtype=float)
    shortage = requirement - actual

    ax.fill_between(dates, 0, actual, color="steelblue", alpha=0.6,
                    label="Delivered")
    ax.fill_between(dates, actual, requirement,
                    where=requirement > actual,
                    color="indianred", alpha=0.6, label="Shortage")
    ax.plot(dates, requirement, "k-", linewidth=1.5, label="Requirement")
    ax.plot(dates, actual, "b-", linewidth=1, alpha=0.8)

    ax.set_xlabel("Date")
    ax.set_ylabel("Flow")
    ax.set_title(f"Supply Gap — {label}")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_budget_supply_gap(model, budget_type, location,
                            supply_col, demand_col,
                            begin_date, end_date, interval="1MON",
                            ax=None, figsize=(12, 5), save_path=None):
    """Supply gap timeline from budget time-series columns.

    Parameters
    ----------
    supply_col, demand_col : int
        1-based column indices for actual supply and demand.
    """
    titles = model.get_budget_column_titles(budget_type, location)
    ts = model.get_budget_timeseries(
        budget_type, location, [supply_col, demand_col],
        begin_date, end_date, interval,
    )
    dates = excel_date_to_datetime(ts["dates"])
    actual = np.abs(ts["values"][:, 0])
    requirement = np.abs(ts["values"][:, 1])

    return plot_supply_gap_timeline(
        dates, requirement, actual,
        label=f"Location {location}",
        ax=ax, figsize=figsize, save_path=save_path,
    )


# ──────────────────────────────────────────────────────────────────
# 46. Pumping depth vs shortage scatter
# ──────────────────────────────────────────────────────────────────

def plot_pumping_depth_vs_shortage(depth_to_gw, shortage,
                                    location_labels=None,
                                    ax=None, figsize=(8, 6),
                                    save_path=None):
    """Scatter plot correlating depth-to-GW with supply shortfall.

    Reveals when pumping becomes uneconomic or insufficient.

    Parameters
    ----------
    depth_to_gw : array-like
        Average depth to groundwater for each location.
    shortage : array-like
        Supply shortage for each location.
    location_labels : list of str, optional
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    depth_to_gw = np.asarray(depth_to_gw, dtype=float)
    shortage = np.asarray(shortage, dtype=float)

    ax.scatter(depth_to_gw, shortage, c="indianred", s=60, alpha=0.7,
               edgecolors="darkred", linewidths=0.5)

    # Label points if provided
    if location_labels is not None:
        for i, label in enumerate(location_labels):
            ax.annotate(label, (depth_to_gw[i], shortage[i]),
                        fontsize=7, ha="left", va="bottom",
                        xytext=(5, 5), textcoords="offset points")

    # Trend line
    if len(depth_to_gw) > 2:
        valid = np.isfinite(depth_to_gw) & np.isfinite(shortage)
        if valid.sum() > 2:
            z = np.polyfit(depth_to_gw[valid], shortage[valid], 1)
            p = np.poly1d(z)
            x_line = np.linspace(depth_to_gw[valid].min(),
                                 depth_to_gw[valid].max(), 100)
            ax.plot(x_line, p(x_line), "k--", linewidth=1, alpha=0.5,
                    label=f"Trend (slope={z[0]:.2f})")
            ax.legend()

    ax.set_xlabel("Average depth to groundwater")
    ax.set_ylabel("Supply shortage")
    ax.set_title("Pumping Depth vs Supply Shortage")
    ax.grid(True, alpha=0.3)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_subregion_depth_vs_shortage(model, supply_type, factor=1.0,
                                      ax=None, figsize=(8, 6),
                                      save_path=None):
    """Depth vs shortage for all subregions using model API.

    Parameters
    ----------
    model : IWFMModel (at a simulation timestep)
    supply_type : int
        Supply type ID (e.g. SupplyTypeID.Diversion).
    """
    sub_ids = model.get_subregion_ids()
    n = len(sub_ids)

    depth = model.get_subregion_ag_pumping_avg_depth_to_gw()
    shortage = model.get_supply_short_at_origin_ag(
        supply_type, list(range(1, n + 1)), factor,
    )

    labels = [model.get_subregion_name(int(sid)) for sid in sub_ids]

    return plot_pumping_depth_vs_shortage(
        depth, shortage, location_labels=labels,
        ax=ax, figsize=figsize, save_path=save_path,
    )


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # These plots typically require active simulation data
    # (supply/demand is only available during or after simulation).
    print("Supply-demand plots require simulation-time data.")
    print("See function docstrings for usage patterns.")
