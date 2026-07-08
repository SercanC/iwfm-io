"""Seasonal and periodic pattern visualizations.

47. Ridgeline plot — overlapping annual hydrographs
48. Calendar heatmap — monthly budget values in a year×month grid
49. Radial/polar seasonal plot — 12-month budget on polar axes
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from . import excel_date_to_datetime, savefig


# ──────────────────────────────────────────────────────────────────
# 47. Ridgeline plot
# ──────────────────────────────────────────────────────────────────

def plot_ridgeline(dates, values, value_label="Head",
                   ax=None, figsize=(10, 10), cmap="viridis",
                   overlap=0.6, save_path=None):
    """Overlapping monthly hydrographs for successive years.

    Shows how seasonal patterns shift over time.

    Parameters
    ----------
    dates : array-like of datetime
    values : array-like of float
        Same length as dates.
    overlap : float
        Vertical overlap factor (0 = no overlap, 1 = full overlap).
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    dates = list(dates)
    values = np.asarray(values, dtype=float)

    # Group by year
    years = sorted(set(d.year for d in dates))
    n_years = len(years)
    cmap_fn = plt.cm.get_cmap(cmap)
    colors = [cmap_fn(i / max(n_years - 1, 1)) for i in range(n_years)]

    v_range = np.nanmax(values) - np.nanmin(values)
    spacing = v_range * (1 - overlap) if v_range > 0 else 1

    for i, year in enumerate(years):
        mask = [d.year == year for d in dates]
        yr_dates = [d for d, m in zip(dates, mask) if m]
        yr_vals = values[mask]

        # Normalize month position (0-12)
        month_pos = np.array([d.month + d.day / 30.0 for d in yr_dates])

        offset = i * spacing
        ax.fill_between(month_pos, offset, yr_vals - np.nanmin(values) + offset,
                        color=colors[i], alpha=0.5, linewidth=0)
        ax.plot(month_pos, yr_vals - np.nanmin(values) + offset,
                color=colors[i], linewidth=1)
        ax.text(0.3, offset + spacing * 0.3, str(year), fontsize=8,
                color=colors[i], fontweight="bold", va="bottom")

    ax.set_xlabel("Month")
    ax.set_ylabel(value_label)
    ax.set_title(f"Ridgeline — {value_label} by Year")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J",
                        "J", "A", "S", "O", "N", "D"])
    ax.set_yticks([])

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 48. Calendar heatmap
# ──────────────────────────────────────────────────────────────────

def plot_calendar_heatmap(dates, values, value_label="Flow",
                           cmap="YlGnBu", ax=None, figsize=(12, 6),
                           save_path=None):
    """Year × month heatmap of monthly values.

    Parameters
    ----------
    dates : list of datetime
        One per month (or per timestep — will be grouped to monthly).
    values : array-like of float
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    dates = list(dates)
    values = np.asarray(values, dtype=float)

    # Group into year-month averages
    from collections import defaultdict
    ym = defaultdict(list)
    for d, v in zip(dates, values):
        ym[(d.year, d.month)].append(v)

    years = sorted(set(k[0] for k in ym))
    months = list(range(1, 13))

    grid = np.full((len(years), 12), np.nan)
    for i, yr in enumerate(years):
        for j, mn in enumerate(months):
            vals = ym.get((yr, mn), [])
            if vals:
                grid[i, j] = np.nanmean(vals)

    im = ax.imshow(grid, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
                       fontsize=8)
    ax.set_yticks(range(len(years)))
    ax.set_yticklabels(years, fontsize=8)
    ax.set_xlabel("Month")
    ax.set_ylabel("Year")
    ax.set_title(f"Calendar Heatmap — {value_label}")
    fig.colorbar(im, ax=ax, label=value_label, shrink=0.8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 49. Radial/polar seasonal plot
# ──────────────────────────────────────────────────────────────────

def plot_polar_seasonal(monthly_values, labels=None,
                        title="Seasonal Pattern",
                        ax=None, figsize=(8, 8), save_path=None):
    """12-month values on a polar axis.

    Parameters
    ----------
    monthly_values : dict or list
        If dict, keys are component names and values are length-12 arrays.
        If list/array of length 12, plots a single series.
    labels : list of str, optional
        Month labels.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize,
                               subplot_kw={"projection": "polar"})
    else:
        fig = ax.figure

    if labels is None:
        labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    # Angles for 12 months
    angles = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    angles_closed = np.concatenate([angles, [angles[0]]])

    if isinstance(monthly_values, dict):
        colors = plt.cm.tab10(np.linspace(0, 1, len(monthly_values)))
        for (name, vals), color in zip(monthly_values.items(), colors):
            vals = np.asarray(vals, dtype=float)
            vals_closed = np.concatenate([vals, [vals[0]]])
            ax.fill(angles_closed, vals_closed, alpha=0.2, color=color)
            ax.plot(angles_closed, vals_closed, "-o", markersize=4,
                    color=color, label=name, linewidth=1.5)
    else:
        vals = np.asarray(monthly_values, dtype=float)
        vals_closed = np.concatenate([vals, [vals[0]]])
        ax.fill(angles_closed, vals_closed, alpha=0.3, color="steelblue")
        ax.plot(angles_closed, vals_closed, "-o", markersize=5,
                color="steelblue", linewidth=2)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title(title, pad=20, fontsize=13)

    if isinstance(monthly_values, dict) and len(monthly_values) <= 8:
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_budget_polar_seasonal(model, budget_type, location,
                                begin_date, end_date,
                                components=None, ax=None,
                                figsize=(8, 8), save_path=None):
    """Polar seasonal plot from budget monthly averages.

    Parameters
    ----------
    components : list of str, optional
        Component names to include. If None, uses the top 5 by magnitude.
    """
    result = model.get_budget_monthly_average(
        budget_type, location, begin_date, end_date,
    )
    names = result["names"]
    flows = result["flows"]  # (n_flows, 12)

    if components is None:
        # Pick top 5 by average absolute magnitude
        avg_mag = np.abs(flows).mean(axis=1)
        top_idx = np.argsort(avg_mag)[-5:][::-1]
    else:
        top_idx = [i for i, n in enumerate(names) if n in components]

    monthly_dict = {names[i]: np.abs(flows[i]) for i in top_idx}

    return plot_polar_seasonal(
        monthly_dict,
        title=f"Seasonal Budget Pattern — Location {location}",
        ax=ax, figsize=figsize, save_path=save_path,
    )


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
            plot_budget_polar_seasonal(m, bt, 1, bd, ed,
                                       save_path="polar_seasonal.png")
    plt.show()
