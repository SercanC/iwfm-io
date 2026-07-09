"""Water balance storytelling visualizations.

37. Sankey diagram — full system water balance
38. Butterfly chart — inflows vs outflows mirrored bar chart
39. Cumulative departure plot — running sum of (inflow − outflow)
"""

import numpy as np
import matplotlib.pyplot as plt
from . import CUFT_TO_AF, excel_date_to_datetime, savefig


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

    inflows = sorted([(n, v) for n, v in filtered if v > 0],
                     key=lambda x: x[1], reverse=True)
    outflows = sorted([(n, -v) for n, v in filtered if v < 0],
                      key=lambda x: x[1], reverse=True)

    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch, Rectangle

    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    total = max(sum(v for _, v in inflows), sum(v for _, v in outflows), 1e-30)
    gap = 0.018            # vertical gap between bands (axis units)
    x_edge_l, x_node_l = 0.16, 0.475   # left band edge -> center node
    x_node_r, x_edge_r = 0.525, 0.84   # center node -> right band edge
    bar_w = 0.012

    def _stack(entries):
        """Return [(name, v, y_bottom, y_top)] centered vertically."""
        h_total = sum(v for _, v in entries) / total * 0.82
        h_total += gap * max(len(entries) - 1, 0)
        y = 0.5 + h_total / 2
        out = []
        for n, v in entries:
            h = v / total * 0.82
            out.append((n, v, y - h, y))
            y -= h + gap
        return out

    def _ribbon(x0, y0b, y0t, x1, y1b, y1t, color):
        xm = (x0 + x1) / 2
        verts = [(x0, y0b), (xm, y0b), (xm, y1b), (x1, y1b), (x1, y1t),
                 (xm, y1t), (xm, y0t), (x0, y0t), (x0, y0b)]
        codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4,
                 MplPath.CURVE4, MplPath.LINETO, MplPath.CURVE4,
                 MplPath.CURVE4, MplPath.CURVE4, MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=color,
                               edgecolor=_SURFACE, linewidth=1.2, alpha=0.55,
                               zorder=2))

    left = _stack(inflows)
    right = _stack(outflows)

    # Where each ribbon meets the center node (contiguous stacks)
    def _node_stack(entries, side_total):
        h_total = side_total / total * 0.82
        y = 0.5 + h_total / 2
        out = []
        for n, v, *_ in entries:
            h = v / total * 0.82
            out.append((y - h, y))
            y -= h
        return out

    node_l = _node_stack(left, sum(v for _, v in inflows))
    node_r = _node_stack(right, sum(v for _, v in outflows))

    def _spread_labels(bands, min_gap=0.055):
        """Nudge label centers apart so small-band labels don't collide."""
        ys = [(yb + yt) / 2 for _, _, yb, yt in bands]
        for k in range(1, len(ys)):
            if ys[k - 1] - ys[k] < min_gap:
                ys[k] = ys[k - 1] - min_gap
        return ys

    label_l = _spread_labels(left)
    label_r = _spread_labels(right)

    for i, ((name, v, yb, yt), (nyb, nyt)) in enumerate(zip(left, node_l)):
        c = _SANKEY_COLORS[i % 8]
        _ribbon(x_edge_l, yb, yt, x_node_l, nyb, nyt, c)
        ax.add_patch(Rectangle((x_edge_l - bar_w, yb), bar_w, yt - yb,
                               facecolor=c, edgecolor="none", zorder=3))
        ax.text(x_edge_l - bar_w - 0.012, label_l[i],
                f"{name}\n{v:,.0f}", ha="right", va="center",
                fontsize=9.5, color=_INK, linespacing=1.4)

    for j, ((name, v, yb, yt), (nyb, nyt)) in enumerate(zip(right, node_r)):
        c = _SANKEY_COLORS[(len(left) + j) % 8]
        _ribbon(x_node_r, nyb, nyt, x_edge_r, yb, yt, c)
        ax.add_patch(Rectangle((x_edge_r, yb), bar_w, yt - yb,
                               facecolor=c, edgecolor="none", zorder=3))
        ax.text(x_edge_r + bar_w + 0.012, label_r[j],
                f"{name}\n{v:,.0f}", ha="left", va="center",
                fontsize=9.5, color=_INK, linespacing=1.4)

    # Center node spanning the taller of the two stacks
    all_y = [y for s in (node_l, node_r) for pair in s for y in pair] or [0.5]
    ax.add_patch(Rectangle((x_node_l, min(all_y)), x_node_r - x_node_l,
                           max(all_y) - min(all_y), facecolor=_NODE_GRAY,
                           edgecolor="none", zorder=4))
    ax.text(0.5, max(all_y) + 0.03, "Balance", ha="center", va="bottom",
            fontsize=10, color=_INK_2)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_title(title, fontsize=14, color=_INK, loc="left")
    ax.axis("off")

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# Validated categorical palette + chart chrome (see dataviz reference)
_SANKEY_COLORS = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
                  "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
_INK = "#0b0b0b"
_INK_2 = "#52514e"
_SURFACE = "#fcfcfb"
_NODE_GRAY = "#c3c2b7"


def _hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _plotly_sankey(names, values, title, save_path, figsize=(14, 8)):
    """Render the signed in/out flows as a plotly Sankey.

    Returns ``(fig, None)`` — a plotly Figure, not matplotlib axes.
    ``save_path`` ending in ``.html`` writes an interactive page; other
    extensions use plotly's static export (requires *kaleido*).
    """
    import plotly.graph_objects as go

    inflows = [(n, v) for n, v in zip(names, values) if v > 0]
    outflows = [(n, -v) for n, v in zip(names, values) if v < 0]
    inflows.sort(key=lambda x: x[1], reverse=True)
    outflows.sort(key=lambda x: x[1], reverse=True)

    center = len(inflows)
    node_labels = ([f"{n}  {v:,.0f}" for n, v in inflows]
                   + ["Balance"]
                   + [f"{n}  {v:,.0f}" for n, v in outflows])
    node_colors = ([_SANKEY_COLORS[i % 8] for i in range(len(inflows))]
                   + [_NODE_GRAY]
                   + [_SANKEY_COLORS[(len(inflows) + i) % 8]
                      for i in range(len(outflows))])

    sources, targets, link_vals, link_colors = [], [], [], []
    for i, (_, v) in enumerate(inflows):
        sources.append(i)
        targets.append(center)
        link_vals.append(v)
        link_colors.append(_hex_to_rgba(node_colors[i], 0.35))
    for j, (_, v) in enumerate(outflows):
        sources.append(center)
        targets.append(center + 1 + j)
        link_vals.append(v)
        link_colors.append(_hex_to_rgba(node_colors[center + 1 + j], 0.35))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(
            label=node_labels,
            color=node_colors,
            pad=18,
            thickness=16,
            line=dict(color="rgba(11,11,11,0.10)", width=1),
        ),
        link=dict(source=sources, target=targets, value=link_vals,
                  color=link_colors),
        valueformat=",.0f",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color=_INK, size=18), x=0.02),
        font=dict(family='"Segoe UI", system-ui, sans-serif',
                  color=_INK_2, size=13),
        paper_bgcolor=_SURFACE,
        width=int(figsize[0] * 100),
        height=int(figsize[1] * 100),
        margin=dict(l=30, r=30, t=60, b=30),
    )

    if save_path:
        sp = str(save_path)
        if sp.lower().endswith(".html"):
            fig.write_html(sp, include_plotlyjs="cdn")
        else:
            fig.write_image(sp, scale=2)  # needs kaleido
        print(f"Saved: {sp}")
    return fig, None


def plot_budget_sankey(model, budget_type, location, begin_date, end_date,
                       interval="1MON", fact_vl=CUFT_TO_AF,
                       combine_storage=True, engine="auto",
                       ax=None, figsize=(14, 8),
                       save_path=None):
    """Sankey from model budget time-series averages.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    fact_vl : float
        Volume conversion; the default converts cubic-feet model units
        to acre-feet for display (pass 1.0 for raw model units).
    combine_storage : bool
        Replace Beginning/Ending Storage with a flux-scale
        "Change in Storage" component (default True).
    engine : str
        ``"plotly"`` uses plotly's Sankey (interactive HTML, or PNG via
        the *kaleido* package), ``"matplotlib"`` the built-in flow
        diagram, ``"auto"`` (default) plotly when it is installed.
    """
    titles = model.get_budget_column_titles(budget_type, location)
    n_cols = len(titles)
    ts = model.get_budget_timeseries(
        budget_type, location, list(range(1, n_cols + 1)),
        begin_date, end_date, interval, fact_vl=fact_vl,
    )
    values = np.asarray(ts["values"])
    if combine_storage:
        from . import combine_storage_terms
        titles, values = combine_storage_terms(titles, values)

    # IWFM budget values are magnitudes; direction is in the labels.
    # Sign them so outflows actually leave the diagram.
    from . import sign_budget_components
    titles, signed = sign_budget_components(titles, values.mean(axis=0))

    # Group minor flows so labels stay readable
    mags = np.abs(signed)
    thresh = 0.02 * mags.max() if len(mags) else 0.0
    keep = mags >= thresh
    names_f = [t for t, k in zip(titles, keep) if k]
    vals_f = [float(v) for v, k in zip(signed, keep) if k]
    other_in = float(sum(v for v, k in zip(signed, keep) if not k and v > 0))
    other_out = float(sum(v for v, k in zip(signed, keep) if not k and v < 0))
    if other_in > 0:
        names_f.append("Other inflows")
        vals_f.append(other_in)
    if other_out < 0:
        names_f.append("Other outflows")
        vals_f.append(other_out)

    title = f"Water Balance — Location {location} (mean monthly, AF)"

    if engine == "auto":
        try:
            import plotly.graph_objects  # noqa: F401
            engine = "plotly"
        except ImportError:
            engine = "matplotlib"
    if engine == "plotly":
        return _plotly_sankey(names_f, vals_f, title, save_path,
                              figsize=figsize)

    return plot_water_balance_sankey(
        names_f, vals_f,
        title=title,
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
    ax.set_xlabel("Mean flow (AF)")
    ax.set_title(title, fontsize=14)
    ax.legend(loc="lower right")
    ax.grid(True, axis="x", alpha=0.3)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


def plot_budget_butterfly(model, budget_type, location, begin_date, end_date,
                           interval="1MON", fact_vl=CUFT_TO_AF,
                           combine_storage=True,
                           ax=None, figsize=(10, 8),
                           save_path=None):
    """Butterfly chart from model budget time-series averages.

    Values display in acre-feet by default (``fact_vl=CUFT_TO_AF``,
    assuming cubic-feet model units); pass ``fact_vl=1.0`` for raw units.
    """
    titles = model.get_budget_column_titles(budget_type, location)
    n_cols = len(titles)
    ts = model.get_budget_timeseries(
        budget_type, location, list(range(1, n_cols + 1)),
        begin_date, end_date, interval, fact_vl=fact_vl,
    )
    values = np.asarray(ts["values"])
    if combine_storage:
        from . import combine_storage_terms
        titles, values = combine_storage_terms(titles, values)

    # Sign magnitudes by their label direction so outflows go left
    from . import sign_budget_components
    titles, signed = sign_budget_components(titles, values.mean(axis=0))

    return plot_butterfly_chart(
        titles, signed.tolist(),
        title=f"Butterfly Chart — Location {location}",
        ax=ax, figsize=figsize, save_path=save_path,
    )


# ──────────────────────────────────────────────────────────────────
# 39. Cumulative departure plot
# ──────────────────────────────────────────────────────────────────

def plot_cumulative_departure(model, budget_type, location,
                               begin_date, end_date, interval="1MON",
                               inflow_cols=None, outflow_cols=None,
                               fact_vl=CUFT_TO_AF,
                               combine_storage=True,
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
        begin_date, end_date, interval, fact_vl=fact_vl,
    )
    dates = excel_date_to_datetime(ts["dates"])
    values = np.asarray(ts["values"])

    # Only transform when columns are auto-classified — explicit indices
    # refer to the original column layout
    if inflow_cols is None and outflow_cols is None:
        if combine_storage:
            from . import combine_storage_terms
            titles, values = combine_storage_terms(titles, values)
        # Sign magnitudes by their label direction before classifying
        from . import sign_budget_components
        titles, values = sign_budget_components(titles, values)
        n_cols = len(titles)

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
    ax.set_ylabel("Cumulative departure (AF)")
    ax.set_title("Cumulative Departure — Net Water Balance")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()

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
        budgets = m.get_budget_list()
        if budgets:
            bt = budgets[0]["budget_type"]
            bd, ed = "10/01/1990_24:00", "09/30/2000_24:00"
            plot_budget_sankey(m, bt, 1, bd, ed, save_path="sankey.png")
            plot_budget_butterfly(m, bt, 1, bd, ed, save_path="butterfly.png")
            plot_cumulative_departure(m, bt, 1, bd, ed, save_path="cum_dep.png")
    plt.show()
