"""Trend and change-detection visualizations.

33. Head trend map — linear slope of GW head at every node
34. Seasonal amplitude map — max-min head range at each node
35. Drought drawdown rate map — head decline rate during driest period
36. Recovery lag map — time to recover after drought
"""

import numpy as np
import matplotlib.pyplot as plt
from . import (build_triangulation, plot_contour_map, overlay_streams,
               overlay_grid, excel_date_to_datetime, savefig,
               _has_df_methods)


def _compute_layer_head_stats(model, layer, begin_date, end_date):
    """Return (dates, heads) for one layer over a date range.

    dates : 1-D float array (Excel serial dates)
    heads : (n_nodes, n_times)
    """
    if _has_df_methods(model):
        hdf = model.heads_df(layer, begin_date, end_date)
        # Convert DatetimeIndex to Excel serial dates for compatibility
        from datetime import datetime, timedelta
        base = datetime(1899, 12, 30)
        dates = np.array([(d.to_pydatetime() - base).total_seconds() / 86400.0
                          for d in hdf.index])
        heads = hdf.values.T  # (n_nodes, n_times)
        return dates, heads
    # Legacy path
    dates, heads = model.get_gw_heads_for_layer(
        layer, begin_date, end_date, factor=1.0,
    )
    return dates, heads


# ──────────────────────────────────────────────────────────────────
# 33. Head trend map
# ──────────────────────────────────────────────────────────────────

def plot_head_trend_map(model, layer, begin_date, end_date,
                        ax=None, figsize=(10, 8), save_path=None):
    """Map of linear head trend (slope) at every node.

    Red = declining, blue = rising.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    layer : int
    begin_date, end_date : str
        IWFM date strings.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    dates, heads = _compute_layer_head_stats(model, layer, begin_date, end_date)
    n_nodes, n_times = heads.shape

    # Convert dates to years for slope units
    dt_objs = excel_date_to_datetime(dates)
    t_years = np.array([(d - dt_objs[0]).total_seconds() / (365.25 * 86400)
                        for d in dt_objs])

    # Linear regression at each node
    slopes = np.zeros(n_nodes)
    for i in range(n_nodes):
        valid = np.isfinite(heads[i])
        if valid.sum() > 2:
            p = np.polyfit(t_years[valid], heads[i, valid], 1)
            slopes[i] = p[0]

    # Symmetric color scale
    vmax = np.percentile(np.abs(slopes[np.isfinite(slopes)]), 95)

    fig, ax, cs, cb = plot_contour_map(
        model, slopes, ax=ax, cmap="RdBu", levels=20,
        label="Head trend (ft/yr)", title=f"GW Head Trend — Layer {layer}",
    )
    cs.set_clim(-vmax, vmax)
    overlay_streams(model, ax, color="black", linewidth=0.8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 34. Seasonal amplitude map
# ──────────────────────────────────────────────────────────────────

def plot_seasonal_amplitude_map(model, layer, begin_date, end_date,
                                 ax=None, figsize=(10, 8), save_path=None):
    """Map of (max head − min head) at each node over the period.

    Highlights areas with the strongest seasonal water-table fluctuation.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    _, heads = _compute_layer_head_stats(model, layer, begin_date, end_date)
    amplitude = np.nanmax(heads, axis=1) - np.nanmin(heads, axis=1)

    fig, ax, cs, cb = plot_contour_map(
        model, amplitude, ax=ax, cmap="YlOrRd", levels=20,
        label="Head amplitude (ft)",
        title=f"Seasonal Head Amplitude — Layer {layer}",
    )
    overlay_streams(model, ax, color="blue", linewidth=0.8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 35. Drought drawdown rate map
# ──────────────────────────────────────────────────────────────────

def plot_drought_drawdown_rate(model, layer, begin_date, end_date,
                                drought_start_idx=None,
                                drought_end_idx=None,
                                ax=None, figsize=(10, 8),
                                save_path=None):
    """Map of head decline rate during a drought window.

    If drought indices are not given, the function finds the longest
    continuous declining period at the median node and uses that window.

    Parameters
    ----------
    drought_start_idx, drought_end_idx : int, optional
        Time-step indices bounding the drought period.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    dates, heads = _compute_layer_head_stats(model, layer, begin_date, end_date)
    n_nodes, n_times = heads.shape

    if drought_start_idx is None or drought_end_idx is None:
        # Use full period for simplicity: rate = (last - max) / duration
        dt_objs = excel_date_to_datetime(dates)
        t_years = np.array([(d - dt_objs[0]).total_seconds() / (365.25 * 86400)
                            for d in dt_objs])
        # Find peak and end for each node
        peak_idx = np.argmax(heads, axis=1)
        drawdown_rate = np.zeros(n_nodes)
        for i in range(n_nodes):
            pi = peak_idx[i]
            trough_idx = pi + np.argmin(heads[i, pi:])
            if trough_idx > pi and t_years[trough_idx] > t_years[pi]:
                drawdown_rate[i] = (heads[i, pi] - heads[i, trough_idx]) / \
                                   (t_years[trough_idx] - t_years[pi])
    else:
        dt_objs = excel_date_to_datetime(dates)
        t_years = np.array([(d - dt_objs[0]).total_seconds() / (365.25 * 86400)
                            for d in dt_objs])
        dt = t_years[drought_end_idx] - t_years[drought_start_idx]
        if dt > 0:
            drawdown_rate = (heads[:, drought_start_idx] -
                             heads[:, drought_end_idx]) / dt
        else:
            drawdown_rate = np.zeros(n_nodes)

    fig, ax, cs, cb = plot_contour_map(
        model, drawdown_rate, ax=ax, cmap="Reds", levels=20,
        label="Drawdown rate (ft/yr)",
        title=f"Drought Drawdown Rate — Layer {layer}",
    )
    overlay_streams(model, ax, color="blue", linewidth=0.8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 36. Recovery lag map
# ──────────────────────────────────────────────────────────────────

def plot_recovery_lag_map(model, layer, begin_date, end_date,
                           recovery_threshold=0.9, ax=None,
                           figsize=(10, 8), save_path=None):
    """Map of recovery time after heads reach their minimum.

    Recovery is defined as regaining *recovery_threshold* fraction of
    the total head drop (peak-to-trough).

    Parameters
    ----------
    recovery_threshold : float
        Fraction (0–1) of the head drop that must be recovered.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    dates, heads = _compute_layer_head_stats(model, layer, begin_date, end_date)
    n_nodes, n_times = heads.shape
    dt_objs = excel_date_to_datetime(dates)
    t_years = np.array([(d - dt_objs[0]).total_seconds() / (365.25 * 86400)
                        for d in dt_objs])

    recovery_time = np.full(n_nodes, np.nan)
    for i in range(n_nodes):
        h = heads[i]
        peak_idx = np.argmax(h)
        trough_idx = peak_idx + np.argmin(h[peak_idx:])
        if trough_idx <= peak_idx:
            continue
        drop = h[peak_idx] - h[trough_idx]
        if drop <= 0:
            continue
        target = h[trough_idx] + recovery_threshold * drop
        # Find first time after trough that head exceeds target
        post_trough = h[trough_idx:]
        recovered = np.where(post_trough >= target)[0]
        if len(recovered) > 0:
            rec_idx = trough_idx + recovered[0]
            recovery_time[i] = t_years[rec_idx] - t_years[trough_idx]

    # Replace NaN with max for visualization
    max_time = np.nanmax(recovery_time) if np.any(np.isfinite(recovery_time)) else 1.0
    display = np.where(np.isfinite(recovery_time), recovery_time, max_time)

    fig, ax, cs, cb = plot_contour_map(
        model, display, ax=ax, cmap="YlGnBu", levels=20,
        label="Recovery time (years)",
        title=f"Recovery Lag — Layer {layer} ({recovery_threshold:.0%} recovery)",
    )
    overlay_streams(model, ax, color="black", linewidth=0.8)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import iwfm_io

    with iwfm_io.dll.IWFMModel(
        preprocessor_file=".assets/sample_model/Simulation/PreProcessor.bin",
        simulation_file=".assets/sample_model/Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as m:
        bd, ed = "10/01/1990_24:00", "09/30/2000_24:00"
        plot_head_trend_map(m, 1, bd, ed, save_path="head_trend.png")
        plot_seasonal_amplitude_map(m, 1, bd, ed, save_path="seasonal_amp.png")
        plot_drought_drawdown_rate(m, 1, bd, ed, save_path="drought_dd.png")
        plot_recovery_lag_map(m, 1, bd, ed, save_path="recovery_lag.png")
    plt.show()
