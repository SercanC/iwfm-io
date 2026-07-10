"""System connectivity visualizations.

52. Diversion network diagram — which stream nodes supply which elements
53. Bypass flow diagram — bypass routing with loss fractions
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
from . import (get_stream_node_xy, get_element_centroids, overlay_grid,
               overlay_streams, _id_to_index_map, _has_df_methods, savefig,
               style_map_axes, map_legend_outside)


# ──────────────────────────────────────────────────────────────────
# 52. Diversion network diagram
# ──────────────────────────────────────────────────────────────────

def plot_diversion_network(model, ax=None, figsize=(12, 10),
                            save_path=None):
    """Graph visualization showing diversion flow paths.

    Stream export nodes are connected to their served elements via
    arrows. Arrow width is uniform (flow magnitude requires simulation).

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    overlay_grid(model, ax, alpha=0.15)
    overlay_streams(model, ax, color="dodgerblue", linewidth=1.5)

    # Get coordinates
    sx, sy = get_stream_node_xy(model)
    cx, cy = get_element_centroids(model)

    if _has_df_methods(model):
        sn_df = model.stream_nodes_df()
        sn_ids = sn_df["stream_node_id"].values
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        edf = model.elements_df()
        elem_ids = edf["element_id"].values
        elem_map = {int(eid): i for i, eid in enumerate(elem_ids)}

        dv_df = model.diversions_df()
        div_ids = dv_df["diversion_id"].values
        if len(div_ids) == 0:
            ax.text(0.5, 0.5, "No diversions in model", ha="center",
                    va="center", transform=ax.transAxes, fontsize=14)
            return fig, ax
        export_nodes = dv_df["export_node"].values
    else:
        sn_ids = model.get_stream_node_ids()
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}
        elem_ids = model.get_element_ids()
        elem_map = {int(eid): i for i, eid in enumerate(elem_ids)}

        div_ids = model.get_diversion_ids()
        if len(div_ids) == 0:
            ax.text(0.5, 0.5, "No diversions in model", ha="center",
                    va="center", transform=ax.transAxes, fontsize=14)
            return fig, ax
        export_nodes = model.get_diversion_export_nodes(list(range(1, len(div_ids) + 1)))

    colors = plt.cm.Set2(np.linspace(0, 1, min(len(div_ids), 8)))

    for i, did in enumerate(div_ids):
        color = colors[i % len(colors)]
        div_idx = i + 1  # 1-based

        # Export node position
        en = int(export_nodes[i])
        if en not in sn_map:
            continue
        ex, ey = sx[sn_map[en]], sy[sn_map[en]]

        # Elements served
        try:
            if _has_df_methods(model):
                row = dv_df[dv_df["diversion_id"] == int(did)].iloc[0]
                elems = row["elements"]
            else:
                elems = model.get_diversion_elements(div_idx)
        except Exception:
            continue

        # Draw export node
        ax.plot(ex, ey, "s", color=color, markersize=10, zorder=8,
                markeredgecolor="black", markeredgewidth=1)
        ax.annotate(f"D{int(did)}", (ex, ey), fontsize=7,
                    fontweight="bold", ha="center", va="bottom",
                    xytext=(0, 8), textcoords="offset points",
                    color=color, zorder=9)

        # Draw arrows to served elements
        for eid in elems:
            ei = elem_map.get(int(eid))
            if ei is not None:
                ax.annotate(
                    "", xy=(cx[ei], cy[ei]), xytext=(ex, ey),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                    lw=1.5, alpha=0.6),
                    zorder=7,
                )
                ax.plot(cx[ei], cy[ei], "o", color=color, markersize=4,
                        alpha=0.6, zorder=7)

    ax.set_aspect("equal")
    style_map_axes(ax)
    ax.set_title("Diversion Network")

    # Legend
    handles = [
        mpatches.Patch(color="dodgerblue", label="Stream network"),
        plt.Line2D([0], [0], marker="s", color="w", markerfacecolor="gray",
                   markersize=10, label="Export node"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
                   markersize=6, label="Served element"),
    ]
    map_legend_outside(ax, handles=handles)

    if save_path:
        savefig(fig, save_path)
    return fig, ax


# ──────────────────────────────────────────────────────────────────
# 53. Bypass flow diagram
# ──────────────────────────────────────────────────────────────────

def plot_bypass_flow_diagram(model, ax=None, figsize=(12, 10),
                              save_path=None):
    """Bypass routing diagram with loss fractions.

    Shows bypass export nodes, outflow destinations, and
    recoverable/non-recoverable loss percentages.

    Parameters
    ----------
    model : IWFMModel (inquiry mode)
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    overlay_grid(model, ax, alpha=0.15)
    overlay_streams(model, ax, color="dodgerblue", linewidth=1.5)

    sx, sy = get_stream_node_xy(model)

    if _has_df_methods(model):
        sn_df = model.stream_nodes_df()
        sn_ids = sn_df["stream_node_id"].values
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}

        bp_df = model.bypasses_df()
        bypass_ids = bp_df["bypass_id"].values
        if len(bypass_ids) == 0:
            ax.text(0.5, 0.5, "No bypasses in model", ha="center",
                    va="center", transform=ax.transAxes, fontsize=14)
            ax.set_aspect("equal")
            return fig, ax
        export_nodes = bp_df["export_node"].values
    else:
        sn_ids = model.get_stream_node_ids()
        sn_map = {int(sid): i for i, sid in enumerate(sn_ids)}

        bypass_ids = model.get_bypass_ids()
        if len(bypass_ids) == 0:
            ax.text(0.5, 0.5, "No bypasses in model", ha="center",
                    va="center", transform=ax.transAxes, fontsize=14)
            ax.set_aspect("equal")
            return fig, ax

        n_byp = len(bypass_ids)
        indices = list(range(1, n_byp + 1))
        export_nodes = model.get_bypass_export_nodes(indices)
        dest_data = model.get_bypass_export_dest_data(indices)
        bp_df = None

    n_byp = len(bypass_ids)
    colors = plt.cm.Set1(np.linspace(0, 1, min(n_byp, 9)))

    for i, bid in enumerate(bypass_ids):
        color = colors[i % len(colors)]
        byp_idx = i + 1

        en = int(export_nodes[i])
        if en not in sn_map:
            continue
        ex, ey = sx[sn_map[en]], sy[sn_map[en]]

        # Loss factors
        try:
            if _has_df_methods(model):
                row = bp_df[bp_df["bypass_id"] == int(bid)].iloc[0]
                rec_loss = row["rec_loss"]
                nonrec_loss = row["nonrec_loss"]
            else:
                rec_loss = model.get_bypass_recoverable_loss_factor(byp_idx)
                nonrec_loss = model.get_bypass_non_recoverable_loss_factor(byp_idx)
        except Exception:
            rec_loss, nonrec_loss = 0.0, 0.0

        # Export node marker
        ax.plot(ex, ey, "D", color=color, markersize=12, zorder=8,
                markeredgecolor="black", markeredgewidth=1.5)

        # Label with loss info
        label_text = (f"B{int(bid)}\n"
                      f"Rec: {rec_loss:.0%}\n"
                      f"Non-rec: {nonrec_loss:.0%}")
        ax.annotate(label_text, (ex, ey), fontsize=7, ha="left",
                    va="bottom", xytext=(12, 5),
                    textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.3", fc=color,
                              alpha=0.3, ec="gray"),
                    zorder=9)

        # Destination arrow
        if _has_df_methods(model):
            row = bp_df[bp_df["bypass_id"] == int(bid)].iloc[0]
            dest_node = int(row["dest"])
            dest_type = int(row["dest_type"])
        else:
            dest_node = int(dest_data["destinations"][i])
            dest_type = int(dest_data["dest_types"][i])

        if dest_node > 0 and dest_node in sn_map:
            dx, dy = sx[sn_map[dest_node]], sy[sn_map[dest_node]]
            ax.annotate(
                "", xy=(dx, dy), xytext=(ex, ey),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=2.5, alpha=0.7,
                                connectionstyle="arc3,rad=0.2"),
                zorder=7,
            )
            ax.plot(dx, dy, "v", color=color, markersize=10, zorder=8,
                    markeredgecolor="black")

    ax.set_aspect("equal")
    style_map_axes(ax)
    ax.set_title("Bypass Flow Diagram")

    handles = [
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="gray",
                   markersize=10, label="Bypass export"),
        plt.Line2D([0], [0], marker="v", color="w", markerfacecolor="gray",
                   markersize=10, label="Destination"),
    ]
    map_legend_outside(ax, handles=handles)

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
        plot_diversion_network(m, save_path="div_network.png")
        plot_bypass_flow_diagram(m, save_path="bypass_flow.png")
    plt.show()
