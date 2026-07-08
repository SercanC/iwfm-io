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
PREPROC_BIN  = SIM_DIR / "PreProcessor.bin"
SIM_IN       = SIM_DIR / "Simulation_MAIN.IN"

BEGIN = "10/01/1990_24:00"
END   = "09/30/2000_24:00"


def check_environment():
    if sys.platform != "win32":
        raise SystemExit("The DLL wrapper requires Windows x64.")
    if not PREPROC_BIN.exists():
        raise SystemExit(
            f"PreProcessor.bin not found: {PREPROC_BIN}\n"
            "Run the IWFM preprocessor first."
        )


# ── 1. DLL version ────────────────────────────────────────────────────────────

def demo_version():
    import iwfm
    print("=== DLL version ===")
    print(f"  Installed versions: {iwfm.list_dll_versions()}")
    dll = iwfm.load_dll()                      # uses default_version.txt / auto-discover
    print(f"  IWFM version:       {iwfm.get_version(dll)}")
    print(f"  Kernel version:     {iwfm.get_kernel_version(dll)}")


# ── 2. Grid and aquifer parameters ───────────────────────────────────────────

def demo_grid():
    import iwfm

    print("\n=== Grid and stratigraphy ===")
    # dll_version is optional — omit to use default_version.txt or auto-discover
    # with iwfm.IWFMModel(..., dll_version="2015.0.1248") as m:
    with iwfm.IWFMModel(
        preprocessor_file=str(PREPROC_BIN),
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

        for lyr in range(1, m.n_layers + 1):
            kh = m.get_aquifer_horizontal_k(layer=lyr)
            sy = m.get_aquifer_specific_yield(layer=lyr)
            print(f"  Layer {lyr} Kh: [{kh.min():.3f}, {kh.max():.3f}]  "
                  f"Sy: [{sy.min():.3f}, {sy.max():.3f}]")


# ── 3. GW head time series ────────────────────────────────────────────────────

def demo_heads():
    import iwfm
    import numpy as np

    print("\n=== GW head time series ===")
    with iwfm.IWFMModel(
        preprocessor_file=str(PREPROC_BIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        for lyr in range(1, m.n_layers + 1):
            dates, heads = m.get_gw_heads_for_layer(
                layer=lyr, begin_date=BEGIN, end_date=END,
            )
            print(f"  Layer {lyr}: {len(dates)} timesteps × {heads.shape[1]} nodes  "
                  f"head=[{heads.min():.1f}, {heads.max():.1f}] ft")

        # Depth to water at final timestep
        gse   = m.get_ground_surface_elevation()
        _, h1 = m.get_gw_heads_for_layer(layer=1, begin_date=BEGIN, end_date=END)
        dtw   = gse - h1[-1]
        print(f"\n  DTW (layer 1, last step): "
              f"min={dtw.min():.1f}  max={dtw.max():.1f}  mean={dtw.mean():.1f} ft")


# ── 4. Stream network ─────────────────────────────────────────────────────────

def demo_streams():
    import iwfm

    print("\n=== Stream network ===")
    with iwfm.IWFMModel(
        preprocessor_file=str(PREPROC_BIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        print(f"  Stream nodes: {m.n_stream_nodes}")
        print(f"  Reaches:      {m.n_reaches}")

        for rid in m.get_reach_ids():
            nodes = m.get_reach_stream_nodes(rid)
            elev  = m.get_stream_bottom_elevations(rid)
            print(f"  Reach {rid}: {len(nodes)} nodes  "
                  f"elev=[{elev.min():.1f}, {elev.max():.1f}] ft")


# ── 5. Hydrograph extraction ─────────────────────────────────────────────────

def demo_hydrographs():
    import iwfm

    print("\n=== Hydrograph extraction ===")
    with iwfm.IWFMModel(
        preprocessor_file=str(PREPROC_BIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        hyd_types = m.get_hydrograph_type_list()
        print(f"  Hydrograph types: {hyd_types}")

        for ht in hyd_types[:2]:
            n = m.get_n_hydrographs(ht)
            if n == 0:
                continue
            ids = m.get_hydrograph_ids(ht)
            dates, vals = m.get_hydrograph(
                hydrograph_type=ht,
                hydrograph_id=ids[0],
                layer=1,
                begin_date=BEGIN,
                end_date=END,
            )
            # Filter uninitialized entries — IW_Model_GetHydrograph reports
            # the full buffer size, leaving trailing dates uninitialized
            # (see docs/TEST_PLOTS_RESULTS.md)
            valid = dates > 0
            print(f"  {ht}[{ids[0]}]: {valid.sum()} valid steps  "
                  f"val=[{vals[valid].min():.2f}, {vals[valid].max():.2f}]")


# ── 6. Budget queries ─────────────────────────────────────────────────────────

def demo_budget():
    import iwfm

    print("\n=== Budget queries ===")
    with iwfm.IWFMModel(
        preprocessor_file=str(PREPROC_BIN),
        simulation_file=str(SIM_IN),
        is_for_inquiry=True,
    ) as m:
        budgets = m.get_budget_list()
        print(f"  Available budgets: {budgets}")

        for bt in budgets[:2]:
            cols = m.get_budget_column_titles(bt)
            print(f"\n  {bt} columns: {cols[:4]} ...")
            dates, values = m.get_budget_timeseries(
                budget_type=bt,
                location_index=1,
                columns=list(range(1, min(4, len(cols)) + 1)),
                begin_date=BEGIN,
                end_date=END,
            )
            print(f"    {len(dates)} timesteps × {values.shape[1]} cols  "
                  f"values[0]={values[0].tolist()}")


# ── 7. IWFMBudget standalone reader ──────────────────────────────────────────

def demo_iwfm_budget():
    import iwfm

    print("\n=== IWFMBudget (standalone HDF reader) ===")
    path = RESULTS_DIR / "GW.hdf"
    if not path.exists():
        print("  GW.hdf not found — skipping.")
        return

    with iwfm.IWFMBudget(str(path)) as bud:
        print(f"  Locations:  {bud.n_locations}")
        print(f"  Timesteps:  {bud.n_timesteps}")
        locs = bud.get_location_names()
        print(f"  Names: {locs}")

        cols = bud.get_column_headers(1)
        print(f"  Columns (loc 1): {cols[:5]} ...")

        times, values = bud.get_values(location=1, columns=list(range(1, 4)))
        print(f"  Values shape: {values.shape}")


# ── 8. IWFMZBudget standalone reader ─────────────────────────────────────────

def demo_iwfm_zbudget():
    import iwfm

    print("\n=== IWFMZBudget (standalone zone-budget reader) ===")
    zin  = ZBUDGET_DIR / "ZBudget.in"
    zhdf = RESULTS_DIR / "GW_ZBud.hdf"

    if not zin.exists() or not zhdf.exists():
        print("  ZBudget files not found — skipping.")
        return

    with iwfm.IWFMZBudget(str(zin)) as zbud:
        print(f"  Zones: {zbud.n_zones}")
        zones = zbud.get_zone_list()
        names = zbud.get_zone_names()
        print(f"  Zone IDs: {zones}")
        print(f"  Zone names: {names}")
        cols = zbud.get_column_headers_general()
        print(f"  General columns: {cols[:4]} ...")


# ── 9. Type-ID enums ──────────────────────────────────────────────────────────

def demo_type_ids():
    import iwfm

    print("\n=== Type-ID enums ===")
    dll = iwfm.load_dll()
    iwfm.load_all_type_ids(dll)

    for cls_name in ("BudgetTypeID", "LocationTypeID", "SupplyTypeID",
                     "DataUnitTypeID"):
        cls = getattr(iwfm, cls_name, None)
        if cls is None:
            continue
        members = {k: v for k, v in vars(cls).items() if not k.startswith("_")}
        print(f"  {cls_name}: {list(members.items())[:4]} ...")


if __name__ == "__main__":
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
