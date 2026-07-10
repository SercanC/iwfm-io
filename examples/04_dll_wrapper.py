"""
Example 4: DLL Wrapper
======================

Demonstrates the iwfm DLL wrapper: IWFMModel, IWFMBudget, IWFMZBudget.

Requires:  Windows x64  +  IWFM_C_x64.dll  +  a compiled sample model.

Covers:
  - DLL version info
  - IWFMModel: grid, stratigraphy, aquifer parameters
  - IWFMModel: GW head time series and depth-to-water
  - IWFMModel: stream network
  - IWFMModel: hydrograph extraction
  - IWFMModel: budget queries
  - IWFMBudget: standalone HDF5 budget reader
  - IWFMZBudget: standalone zone-budget reader
  - Type-ID enums (BudgetTypeID, LocationTypeID, …)

Usage:
    python examples/04_dll_wrapper.py
"""

import sys
from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"
SIM_DIR      = SAMPLE_MODEL / "Simulation"
RESULTS_DIR  = SAMPLE_MODEL / "Results"
BUDGET_DIR   = SAMPLE_MODEL / "Budget"
ZBUDGET_DIR  = SAMPLE_MODEL / "ZBudget"
# IWFMModel wants the preprocessor MAIN input file (.IN), not the .bin
PREPROC_MAIN = SAMPLE_MODEL / "Preprocessor" / "PreProcessor_MAIN.IN"
SIM_IN       = SIM_DIR / "Simulation_MAIN.IN"

BEGIN = "10/01/1990_24:00"
END   = "09/30/2000_24:00"


def check_environment():
    if sys.platform != "win32":
        raise SystemExit("The DLL wrapper requires Windows x64.")
    if not PREPROC_MAIN.exists():
        raise SystemExit(
            f"Preprocessor main not found: {PREPROC_MAIN}\n"
            "Restore .assets/sample_model/ to run this example."
        )
    # The DLL resolves the model's relative paths (e.g.
    # ..\Results\GWHeadAll.hdf) against the process working directory,
    # so run from the Simulation folder like IWFM itself does.
    import os
    os.chdir(SIM_DIR)


# ── 1. DLL version ────────────────────────────────────────────────────────────

def demo_version():
    import iwfm_io
    print("=== DLL version ===")
    print(f"  Installed versions: {iwfm_io.dll.list_dll_versions()}")
    dll = iwfm_io.dll.load_dll()                      # uses default_version.txt / auto-discover
    print(f"  IWFM version:       {iwfm_io.dll.get_version(dll)}")
    print(f"  Kernel version:     {iwfm_io.dll.get_kernel_version(dll)}")


# ── 2. Grid and aquifer parameters ───────────────────────────────────────────

def demo_grid():
    import iwfm_io

    print("\n=== Grid and stratigraphy ===")
    # dll_version is optional — omit to use default_version.txt or auto-discover
    # with iwfm_io.dll.IWFMModel(..., dll_version="2015.0.1248") as m:
    with iwfm_io.dll.IWFMModel(
        preprocessor_file=str(PREPROC_MAIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        print(f"  Nodes:      {m.n_nodes}")
        print(f"  Elements:   {m.n_elements}")
        print(f"  Layers:     {m.n_layers}")
        print(f"  Subregions: {m.n_subregions}")

        x, y = m.get_node_coordinates()
        print(f"\n  Extent: X [{x.min():.0f}, {x.max():.0f}]  "
              f"Y [{y.min():.0f}, {y.max():.0f}]")

        for sid in m.get_subregion_ids():
            print(f"  Subregion {sid}: {m.get_subregion_name(sid)}")

        gse = m.get_ground_surface_elevation()
        print(f"\n  GSE (ft): min={gse.min():.1f}  max={gse.max():.1f}  "
              f"mean={gse.mean():.1f}")

        # Aquifer parameter getters return (n_nodes, n_layers) arrays.
        # On some models the DLL's inquiry-mode re-read of the aquifer
        # parameters fails (see docs/DLL_INQUIRY_MODE_LIMITS.md) — the
        # DLL-free adapter (example 01) always works instead.
        try:
            kh = m.get_aquifer_horizontal_k()
            sy = m.get_aquifer_specific_yield()
            for lyr in range(m.n_layers):
                print(f"  Layer {lyr + 1} "
                      f"Kh: [{kh[:, lyr].min():.3f}, {kh[:, lyr].max():.3f}]  "
                      f"Sy: [{sy[:, lyr].min():.3f}, {sy[:, lyr].max():.3f}]")
        except Exception as exc:
            print(f"  Aquifer parameters unavailable in inquiry mode "
                  f"(known DLL limitation): {str(exc)[:80]}")


# ── 3. GW head time series ────────────────────────────────────────────────────

def demo_heads():
    import iwfm_io
    import numpy as np

    print("\n=== GW head time series ===")
    with iwfm_io.dll.IWFMModel(
        preprocessor_file=str(PREPROC_MAIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        for lyr in range(1, m.n_layers + 1):
            # heads has shape (n_nodes, n_times)
            dates, heads = m.get_gw_heads_for_layer(
                layer=lyr, begin_date=BEGIN, end_date=END,
            )
            print(f"  Layer {lyr}: {len(dates)} timesteps × {heads.shape[0]} nodes  "
                  f"head=[{heads.min():.1f}, {heads.max():.1f}] ft")

        # Depth to water at final timestep
        gse   = m.get_ground_surface_elevation()
        _, h1 = m.get_gw_heads_for_layer(layer=1, begin_date=BEGIN, end_date=END)
        dtw   = gse - h1[:, -1]
        print(f"\n  DTW (layer 1, last step): "
              f"min={dtw.min():.1f}  max={dtw.max():.1f}  mean={dtw.mean():.1f} ft")


# ── 4. Stream network ─────────────────────────────────────────────────────────

def demo_streams():
    import iwfm_io

    print("\n=== Stream network ===")
    with iwfm_io.dll.IWFMModel(
        preprocessor_file=str(PREPROC_MAIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        print(f"  Stream nodes: {m.n_stream_nodes}")
        print(f"  Reaches:      {m.n_reaches}")

        # Bottom elevations are returned for all stream nodes at once
        elevs = m.get_stream_bottom_elevations()
        print(f"  Bottom elev: [{elevs.min():.1f}, {elevs.max():.1f}] ft")

        for rid in m.get_reach_ids():
            nodes = m.get_reach_stream_nodes(rid)
            print(f"  Reach {rid}: {len(nodes)} nodes "
                  f"({nodes.min()}–{nodes.max()})")


# ── 5. Hydrograph extraction ─────────────────────────────────────────────────

def demo_hydrographs():
    import iwfm_io

    print("\n=== Hydrograph extraction ===")
    with iwfm_io.dll.IWFMModel(
        preprocessor_file=str(PREPROC_MAIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        hyd_types = m.get_hydrograph_type_list()
        print(f"  Hydrograph types: {[t['name'] for t in hyd_types]}")

        for ht in hyd_types[:2]:
            loc_type = ht["location_type"]
            n = m.get_n_hydrographs(loc_type)
            if n <= 0:  # -1 = not queryable for this location type
                continue
            ids = m.get_hydrograph_ids(loc_type)
            dates, vals = m.get_hydrograph(
                hyd_type=loc_type,
                index=int(ids[0]),
                layer=1,
                begin_date=BEGIN,
                end_date=END,
                interval="1MON",
            )
            # Filter uninitialized entries — IW_Model_GetHydrograph reports
            # the full buffer size, leaving trailing dates uninitialized
            # (see docs/TEST_PLOTS_RESULTS.md)
            valid = dates > 0
            print(f"  {ht['name']}[{ids[0]}]: {valid.sum()} valid steps  "
                  f"val=[{vals[valid].min():.2f}, {vals[valid].max():.2f}]")


# ── 6. Budget queries ─────────────────────────────────────────────────────────

def demo_budget():
    import iwfm_io

    print("\n=== Budget queries ===")
    with iwfm_io.dll.IWFMModel(
        preprocessor_file=str(PREPROC_MAIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        budgets = m.get_budget_list()
        print(f"  Available budgets: {[b['name'] for b in budgets]}")

        for b in budgets[:2]:
            bt = b["budget_type"]
            cols = m.get_budget_column_titles(bt, location=1)
            print(f"\n  {b['name']} columns: {cols[:3]} ...")
            result = m.get_budget_timeseries(
                budget_type=bt,
                location=1,
                columns=list(range(1, min(4, len(cols)) + 1)),
                begin_date=BEGIN,
                end_date=END,
                interval="1MON",
            )
            values = result["values"]
            print(f"    {len(result['dates'])} timesteps × "
                  f"{values.shape[1]} cols  values[0]={values[0].tolist()}")


# ── 7. IWFMBudget standalone reader ──────────────────────────────────────────

def demo_iwfm_budget():
    import iwfm_io

    print("\n=== IWFMBudget (standalone HDF reader) ===")
    path = RESULTS_DIR / "GW.hdf"
    if not path.exists():
        print("  GW.hdf not found — skipping.")
        return

    with iwfm_io.dll.IWFMBudget(str(path)) as bud:
        print(f"  Locations:  {bud.n_locations}")
        print(f"  Timesteps:  {bud.n_timesteps}")
        locs = bud.get_location_names()
        print(f"  Names: {locs}")

        cols = bud.get_column_headers(1)
        print(f"  Columns (loc 1): {cols[:5]} ...")

        # Returns (n_times, n_columns+1) — first column is time
        values = bud.get_values(
            location=1, columns=list(range(1, 4)),
            begin_date=BEGIN, end_date=END, interval="1MON",
        )
        print(f"  Values shape: {values.shape}")


# ── 8. IWFMZBudget standalone reader ─────────────────────────────────────────

def demo_iwfm_zbudget():
    import iwfm_io

    print("\n=== IWFMZBudget (standalone zone-budget reader) ===")
    # IWFMZBudget opens the zone-budget HDF5 file (not ZBudget.in)
    zhdf = RESULTS_DIR / "GW_ZBud.hdf"

    if not zhdf.exists():
        print("  GW_ZBud.hdf not found — skipping.")
        return

    with iwfm_io.dll.IWFMZBudget(str(zhdf)) as zbud:
        print(f"  Zones: {zbud.n_zones}")
        zones = zbud.get_zone_list()
        if zones is None or len(zones) == 0:
            # Known limitation: the sample model publishes no zone
            # list through the DLL (see CLAUDE.md Known Issues)
            print("  No zone list published by the DLL for this model.")
        else:
            print(f"  Zone IDs: {zones}")
            print(f"  Zone names: {zbud.get_zone_names()}")


# ── 9. Type-ID enums ──────────────────────────────────────────────────────────

def demo_type_ids():
    import iwfm_io

    print("\n=== Type-ID enums ===")
    dll = iwfm_io.dll.load_dll()
    iwfm_io.dll.load_all_type_ids(dll)

    for cls_name in ("BudgetTypeID", "LocationTypeID", "SupplyTypeID",
                     "DataUnitTypeID"):
        cls = getattr(iwfm_io.dll, cls_name, None)
        if cls is None:
            continue
        members = {k: v for k, v in vars(cls).items() if not k.startswith("_")}
        print(f"  {cls_name}: {list(members.items())[:4]} ...")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # arrows in redirected output
    check_environment()
    demo_version()
    demo_grid()
    demo_heads()
    demo_streams()
    demo_hydrographs()
    demo_budget()
    demo_iwfm_budget()
    demo_iwfm_zbudget()
    demo_type_ids()
    print("\nDone.")
