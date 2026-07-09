"""
Example 2: Reading IWFM Model Output Files
==========================================

Demonstrates iwfm_io readers for HDF5 and text output files produced
by an IWFM simulation run.  No DLL required — runs on any platform.

Covers:
  - Budget HDF5 files (GW.hdf, StrmBud.hdf, …)
  - GW heads at all nodes (GWHeadAll.hdf)
  - Hydrograph HDF5 files (GWHyd.hdf, StrmHyd.hdf, …)
  - Zone budget HDF5 files (GW_ZBud.hdf)
  - Zone definition files (ZoneDef_*.dat)
  - Text hydrograph output (GWHyd.out)
  - Final state files (FinalGWHeads.out)
  - Budget text files (GW.bud)

Usage:
    python examples/02_read_outputs.py
"""

from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"
RESULTS_DIR  = SAMPLE_MODEL / "Results"
BUDGET_DIR   = SAMPLE_MODEL / "Budget"
ZBUDGET_DIR  = SAMPLE_MODEL / "ZBudget"


def check_results():
    if not RESULTS_DIR.exists():
        raise SystemExit(
            f"Results directory not found: {RESULTS_DIR}\n"
            "Run the IWFM simulation first, or restore .assets/sample_model/Results/."
        )


def _skip(name):
    print(f"  [{name}] not found — skipping.")


# ── 1. Budget HDF ─────────────────────────────────────────────────────────────

def demo_budget_hdf():
    from iwfm_io import read_budget_hdf

    print("=== Budget HDF (GW.hdf) ===")
    path = RESULTS_DIR / "GW.hdf"
    if not path.exists():
        return _skip("GW.hdf")

    result = read_budget_hdf(path)
    print(f"  Locations: {result['locations']}")

    for loc in result["locations"]:
        df = result["data"][loc]
        print(f"\n  [{loc}]  shape={df.shape}")
        print(f"    Columns:    {df.columns.tolist()[:4]} ...")
        print(f"    Date range: {df.index[0]}  →  {df.index[-1]}")
        print(df.head(2).to_string())

    # Stream budget
    strm_path = RESULTS_DIR / "StrmBud.hdf"
    if strm_path.exists():
        strm = read_budget_hdf(strm_path)
        print(f"\n  StrmBud locations: {strm['locations']}")


# ── 2. GW heads at all nodes ─────────────────────────────────────────────────

def demo_head_hdf():
    from iwfm_io import read_head_hdf

    print("\n=== GW Heads HDF (GWHeadAll.hdf) ===")
    path = RESULTS_DIR / "GWHeadAll.hdf"
    if not path.exists():
        return _skip("GWHeadAll.hdf")

    # Provide n_nodes and n_layers to get named columns: node_N_layer_M
    df = read_head_hdf(path, n_nodes=441, n_layers=2)
    print(f"  Shape:      {df.shape}")
    print(f"  Date range: {df.index[0]}  →  {df.index[-1]}")

    layer1 = [c for c in df.columns if c.endswith("_layer_1")]
    print(f"  Layer-1 cols: {len(layer1)}")
    print(df[layer1[:3]].head(3).to_string())


# ── 3. Hydrograph HDF ────────────────────────────────────────────────────────

def demo_hydrograph_hdf():
    from iwfm_io import read_hydrograph_hdf

    print("\n=== Hydrograph HDF files ===")

    for fname in ("GWHyd.hdf", "StrmHyd.hdf", "Subsidence.hdf"):
        path = RESULTS_DIR / fname
        if not path.exists():
            continue
        df = read_hydrograph_hdf(path)
        print(f"  {fname}: shape={df.shape}  "
              f"({df.index[0].date()} → {df.index[-1].date()})")
        print(df.iloc[:2, :3].to_string())


# ── 4. Zone budget HDF ───────────────────────────────────────────────────────

def demo_zbudget_hdf():
    from iwfm_io import read_zbudget_hdf, read_zone_def

    print("\n=== Zone Budget HDF (GW_ZBud.hdf) ===")
    path = RESULTS_DIR / "GW_ZBud.hdf"
    if not path.exists():
        return _skip("GW_ZBud.hdf")

    # Read without zone aggregation — returns raw layer datasets
    result = read_zbudget_hdf(path)
    print(f"  Top-level keys: {list(result.keys())[:6]}")

    # Read zone definition and aggregate by zone
    zone_def_path = ZBUDGET_DIR / "ZoneDef_E1_E10.dat"
    if zone_def_path.exists():
        zdef = read_zone_def(zone_def_path)
        print(f"  Zone definition: extent='{zdef.extent}', "
              f"{len(zdef.zones)} zones: {zdef.zones}")
        result_zoned = read_zbudget_hdf(path, zone_def=zdef)
        print(f"  Zoned result keys: {list(result_zoned.keys())[:6]}")


# ── 5. Text hydrograph output ─────────────────────────────────────────────────

def demo_hydrograph_out():
    from iwfm_io import read_hydrograph_out, read_hydrograph_out_with_metadata

    print("\n=== Hydrograph text output (GWHyd.out) ===")
    path = RESULTS_DIR / "GWHyd.out"
    if not path.exists():
        return _skip("GWHyd.out")

    df = read_hydrograph_out(path)
    print(f"  Shape:      {df.shape}")
    print(f"  Date range: {df.index[0]}  →  {df.index[-1]}")
    print(df.head(3).to_string())

    df2, meta = read_hydrograph_out_with_metadata(path)
    if meta:
        print(f"\n  Metadata keys: {list(meta.keys())}")


# ── 6. Final state output ─────────────────────────────────────────────────────

def demo_final_state():
    from iwfm_io import read_final_state_out

    print("\n=== Final state files ===")

    for fname in ("FinalGWHeads.out", "FinalSubsidence.out", "FinalLakeElev.out"):
        path = RESULTS_DIR / fname
        if not path.exists():
            continue
        df = read_final_state_out(path)
        print(f"  {fname}: {len(df)} rows  columns={df.columns.tolist()}")
        print(f"  {df.head(2).to_string()}")


# ── 7. Budget text files ──────────────────────────────────────────────────────

def demo_budget_text():
    from iwfm_io import read_budget_text

    print("\n=== Budget text files ===")

    for fname in ("GW.bud", "Strm.bud", "RootZone.bud"):
        path = BUDGET_DIR / fname
        if not path.exists():
            continue
        result = read_budget_text(path)
        print(f"  {fname}: {len(result)} sections")


# ── 8. Flow and velocity output ───────────────────────────────────────────────

def demo_flow_out():
    from iwfm_io import read_flow_out, read_velocity_out

    print("\n=== Flow and velocity output ===")

    face_path = RESULTS_DIR / "FaceFlow.out"
    if face_path.exists():
        df = read_flow_out(face_path)
        print(f"  FaceFlow.out:     {df.shape}")

    vel_path = RESULTS_DIR / "GWVelocities.out"
    if vel_path.exists():
        df = read_velocity_out(vel_path)
        print(f"  GWVelocities.out: {df.shape}")


if __name__ == "__main__":
    check_results()
    demo_budget_hdf()
    demo_head_hdf()
    demo_hydrograph_hdf()
    demo_zbudget_hdf()
    demo_hydrograph_out()
    demo_final_state()
    demo_budget_text()
    demo_flow_out()
    print("\nDone.")
