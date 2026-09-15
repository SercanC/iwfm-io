"""Exercise the plots the DLL cannot serve in inquiry mode, DLL-free.

These plot functions fail through the DLL wrapper in inquiry mode (see
docs/TEST_PLOTS_RESULTS.md); IOModelAdapter serves the same data from
the model's input and budget-output files on any OS.

Usage:  python examples/test_plots_dllfree.py [model_root]
        (default model_root: .assets/sample_model)
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from iwfm_io import open_model

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_REPO, ".assets", "sample_model")
OUT = os.path.join(_REPO, "test_output", "dllfree_" + os.path.basename(os.path.normpath(ROOT)))
os.makedirs(OUT, exist_ok=True)

m = open_model(ROOT)
n_sub = len(m.subregions_df())
_n = m.nodes_df()
_p1 = (float(_n["x"].min()), float(_n["y"].mean()))
_p2 = (float(_n["x"].max()), float(_n["y"].mean()))
_sim = m.describe()["simulation"]
_bd, _ed = _sim["begins"], _sim["ends"]

results = []

def run(tag, fn):
    try:
        out = fn()
        fig = out[0] if isinstance(out, tuple) else out
        # animations return a FuncAnimation, not a Figure
        plt.close(getattr(fig, "_fig", fig) if not hasattr(fig, "savefig")
                  else fig)
        results.append((tag, "OK"))
        print(f"[OK]   {tag}")
    except Exception as e:
        results.append((tag, f"FAIL: {type(e).__name__}: {e}"))
        print(f"[FAIL] {tag}: {type(e).__name__}: {str(e)[:130]}")

from iwfm_io.plots.maps import plot_aquifer_parameter, plot_tile_drain_locations
from iwfm_io.plots.summary import plot_aquifer_parameter_histograms, plot_supply_vs_demand
from iwfm_io.plots.timeseries import plot_land_use_area_timeseries
from iwfm_io.plots.stream_analysis import (plot_stream_gain_loss_profile,
                                        plot_stream_aquifer_exchange_map)
from iwfm_io.plots.supply_demand import plot_subregion_depth_vs_shortage
from iwfm_io.plots.connectivity import plot_bypass_flow_diagram

run("08 aquifer parameter (Kh)", lambda: plot_aquifer_parameter(
    m, parameter="Kh", layer=1, log_scale=True,
    save_path=os.path.join(OUT, "08_aquifer_kh.png")))
run("11 tile drain locations", lambda: plot_tile_drain_locations(
    m, save_path=os.path.join(OUT, "11_tile_drains.png")))
run("20 land use area timeseries", lambda: plot_land_use_area_timeseries(
    m, save_path=os.path.join(OUT, "20_land_use.png")))
run("33 aquifer parameter histograms", lambda: plot_aquifer_parameter_histograms(
    m, layer=1, save_path=os.path.join(OUT, "33_param_hist.png")))
run("38 supply vs demand", lambda: plot_supply_vs_demand(
    m, 1, list(range(1, n_sub + 1)), 1, list(range(1, n_sub + 1)),
    save_path=os.path.join(OUT, "38_supply_demand.png")))
run("39 stream gain/loss profile", lambda: plot_stream_gain_loss_profile(
    m, save_path=os.path.join(OUT, "39_gain_loss.png")))
run("40 stream-aquifer exchange map", lambda: plot_stream_aquifer_exchange_map(
    m, save_path=os.path.join(OUT, "40_exchange_map.png")))
run("54 subregion depth vs shortage", lambda: plot_subregion_depth_vs_shortage(
    m, 1, save_path=os.path.join(OUT, "54_depth_shortage.png")))
run("58 bypass flow diagram", lambda: plot_bypass_flow_diagram(
    m, save_path=os.path.join(OUT, "58_bypass.png")))

from iwfm_io.plots.profiles import plot_stratigraphic_cross_section
run("12 stratigraphic cross-section", lambda: plot_stratigraphic_cross_section(
    m, [_p1, _p2], save_path=os.path.join(OUT, "12_xsec.png")))

from iwfm_io.plots.timeseries import plot_zbudget_timeseries
run("18 zbudget timeseries", lambda: plot_zbudget_timeseries(
    m, zbudget_type="GW_ZBud", zone_id=1, columns=[1, 2, 3],
    zone_extent="Zone", elements=None, layers=None, zone_ids=None,
    begin_date=_bd, end_date=_ed,
    save_path=os.path.join(OUT, "18_zbudget_ts.png")))

from iwfm_io.plots.cross_sections import plot_multi_layer_head_panel
run("55 multi-layer head panel", lambda: plot_multi_layer_head_panel(
    m, points=[_p1, _p2], begin_date=_bd, end_date=_ed, time_index=0,
    save_path=os.path.join(OUT, "55_multi_layer_panel.png")))

from iwfm_io.plots.cross_sections import animate_cross_section
run("56 animate cross-section", lambda: animate_cross_section(
    m, points=[_p1, _p2], layer=1, begin_date=_bd, end_date=_ed,
    interval_frames=6, save_path=os.path.join(OUT, "56_anim_xsec.gif")))

ok = sum(1 for _, st in results if st == "OK")
print(f"\n{ok}/{len(results)} passed  ({os.path.basename(ROOT)})")
