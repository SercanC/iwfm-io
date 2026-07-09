"""Shared plotly builders for the optional ``engine="plotly"`` renders.

plotly is an optional dependency (``pip install iwfm-io[viz]``); every
function here imports it lazily. All builders share one visual theme —
the validated categorical palette and chart chrome used across the
library — and one save convention: ``save_path`` ending in ``.html``
writes an interactive page, any other extension goes through plotly's
static export (requires *kaleido*).

Plotly-engine plot functions return ``(fig, None)`` where ``fig`` is a
``plotly.graph_objects.Figure`` (there is no matplotlib Axes).
"""

from __future__ import annotations

CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
               "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
               # overflow slots for >8 series (budget tables can have
               # 9-12 balance components); order is CVD-validated —
               # don't rearrange without re-running the palette checks
               "#00a3c7", "#6d8f00", "#a4459f", "#b06a1f"]
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"


def _go():
    try:
        import plotly.graph_objects as go
        return go
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            'engine="plotly" needs plotly (and kaleido for PNG export): '
            "pip install iwfm-io[viz]") from exc


def rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    return (f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},"
            f"{int(h[4:6], 16)},{alpha})")


def color(i):
    """Categorical slot for series *i* (fixed order, folds after 8)."""
    return CATEGORICAL[i % len(CATEGORICAL)]


def apply_layout(fig, title, figsize=(12, 6), xaxis_title=None,
                 yaxis_title=None, show_range_slider=False):
    """Shared chrome: surface, ink, hairline grid, left-aligned title."""
    fig.update_layout(
        title=dict(text=title, font=dict(color=INK, size=18), x=0.02),
        font=dict(family='"Segoe UI", system-ui, sans-serif',
                  color=INK_2, size=13),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        width=int(figsize[0] * 100),
        height=int(figsize[1] * 100),
        margin=dict(l=60, r=30, t=60, b=50),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
    )
    fig.update_xaxes(title=xaxis_title, gridcolor=GRID, linecolor=GRID,
                     tickfont=dict(color=MUTED), zeroline=False)
    fig.update_yaxes(title=yaxis_title, gridcolor=GRID, linecolor=GRID,
                     tickfont=dict(color=MUTED),
                     zerolinecolor=GRID, zerolinewidth=1)
    if show_range_slider:
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
    return fig


def finish(fig, save_path):
    """Write HTML or (via kaleido) a static image; return (fig, None)."""
    if save_path:
        sp = str(save_path)
        if sp.lower().endswith(".html"):
            fig.write_html(sp, include_plotlyjs="cdn")
        else:
            fig.write_image(sp, scale=2)
        print(f"Saved: {sp}")
    return fig, None


def line_chart(x, series, title, ylabel, save_path, figsize=(12, 5),
               range_slider=True):
    """Multi-line time series. *series* = list of (name, values)."""
    go = _go()
    fig = go.Figure()
    for i, (name, values) in enumerate(series):
        fig.add_trace(go.Scatter(
            x=x, y=values, name=str(name), mode="lines",
            line=dict(color=color(i), width=2),
        ))
    apply_layout(fig, title, figsize, yaxis_title=ylabel,
                 show_range_slider=range_slider)
    return finish(fig, save_path)


def stacked_area(x, series, title, ylabel, save_path, figsize=(12, 6)):
    """Sign-split stacked areas: positive series stack up, negative down."""
    go = _go()
    import numpy as np
    fig = go.Figure()
    n_visible = 0
    for name, values in series:
        v = np.asarray(values, dtype=float)
        pos = np.clip(v, 0, None)
        neg = np.clip(v, None, 0)
        if not (pos.any() or neg.any()):
            continue  # all-zero series: no trace, don't burn a color slot
        c = color(n_visible)
        n_visible += 1
        common = dict(x=x, name=str(name), mode="lines",
                      line=dict(width=0.5, color=c),
                      fillcolor=rgba(c, 0.55), legendgroup=str(name))
        if pos.any():
            fig.add_trace(go.Scatter(y=pos, stackgroup="pos", **common))
        if neg.any():
            fig.add_trace(go.Scatter(y=neg, stackgroup="neg",
                                     showlegend=not pos.any(), **common))
    apply_layout(fig, title, figsize, yaxis_title=ylabel)
    return finish(fig, save_path)


def grouped_bars(x, series, title, ylabel, save_path, figsize=(14, 6),
                 error_bars=None, barmode="group"):
    """Grouped/stacked bars. *series* = list of (name, values)."""
    go = _go()
    fig = go.Figure()
    for i, (name, values) in enumerate(series):
        err = None
        if error_bars is not None:
            err = dict(type="data", array=error_bars[i], visible=True,
                       color=rgba(INK, 0.3), thickness=1)
        fig.add_trace(go.Bar(x=x, y=values, name=str(name),
                             marker=dict(color=color(i)), error_y=err))
    fig.update_layout(barmode=barmode, bargap=0.25)
    apply_layout(fig, title, figsize, yaxis_title=ylabel)
    return finish(fig, save_path)


def donut(labels, values, title, save_path, figsize=(8, 8)):
    """Donut chart with percentage + label."""
    go = _go()
    fig = go.Figure(go.Pie(
        labels=list(labels), values=list(values), hole=0.45,
        marker=dict(colors=[color(i) for i in range(len(labels))],
                    line=dict(color=SURFACE, width=2)),
        textinfo="label+percent", textfont=dict(size=12),
        sort=False,
    ))
    fig.update_layout(showlegend=False)
    apply_layout(fig, title, figsize)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return finish(fig, save_path)


def diverging_bars(names, values, title, xlabel, save_path,
                   figsize=(10, 8)):
    """Horizontal diverging bars: positive right (blue), negative left (red)."""
    go = _go()
    order = sorted(range(len(values)), key=lambda i: values[i])
    fig = go.Figure(go.Bar(
        x=[values[i] for i in order],
        y=[str(names[i]) for i in order],
        orientation="h",
        marker=dict(color=[CATEGORICAL[0] if values[i] >= 0
                           else CATEGORICAL[5] for i in order]),
        text=[f"{abs(values[i]):,.0f}" for i in order],
        textposition="outside",
    ))
    fig.update_layout(showlegend=False)
    apply_layout(fig, title, figsize, xaxis_title=xlabel)
    return finish(fig, save_path)
