"""
Example 1: Reading IWFM Model Input Files
==========================================

Demonstrates iwfm.io readers for IWFM text input files.
No DLL required — runs on any platform.

Covers:
  - Date utilities (parse/format IWFM dates)
  - Preprocessor files (nodes, elements, stratigraphy, stream geom, lakes)
  - Simulation main file
  - Groundwater files (GW main, boundary conditions, tile drains)
  - Stream files (stream main, diversions, bypasses)
  - Time-series input files (precip, ET)
  - IOModelAdapter — unified DataFrame interface
  - Cross-file validation

Usage:
    python examples/01_read_inputs.py
"""

from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"
PP_DIR       = SAMPLE_MODEL / "Preprocessor"
SIM_DIR      = SAMPLE_MODEL / "Simulation"
GW_DIR       = SIM_DIR / "GW"
STRM_DIR     = SIM_DIR / "Stream"


def check_sample_model():
    if not PP_DIR.exists():
        raise SystemExit(
            f"Sample model not found at {SAMPLE_MODEL}\n"
            "Restore .assets/sample_model/ to run this example."
        )


# ── 1. Date utilities ─────────────────────────────────────────────────────────

def demo_dates():
    from iwfm.io import parse_iwfm_date, format_iwfm_date
    from datetime import datetime

    print("=== Date utilities ===")
    # Hour 24:00 means end of day (midnight next day)
    dt = parse_iwfm_date("09/30/1990_24:00")
    print(f"  parse '09/30/1990_24:00'  →  {dt}")

    s = format_iwfm_date(datetime(1990, 10, 1))
    print(f"  format datetime(1990,10,1) →  '{s}'")


# ── 2. Preprocessor files ─────────────────────────────────────────────────────

def demo_preprocessor():
    from iwfm.io import read_nodes, read_elements, read_strata, read_preprocessor

    print("\n=== Preprocessor files ===")

    # Individual file readers
    nodes = read_nodes(PP_DIR / "NodeXY.dat")
    print(f"  Nodes: {len(nodes.data)} rows  "
          f"columns={nodes.data.columns.tolist()}")
    print(f"    X [{nodes.data['x'].min():.0f}, {nodes.data['x'].max():.0f}]  "
          f"Y [{nodes.data['y'].min():.0f}, {nodes.data['y'].max():.0f}]")

    elements = read_elements(PP_DIR / "Element.dat")
    print(f"  Elements: {len(elements.data)} rows, "
          f"{elements.data['subregion'].nunique()} subregions")

    strata = read_strata(PP_DIR / "Strata.dat")
    print(f"  Stratigraphy: {len(strata.data)} nodes, "
          f"{strata.n_layers} aquifer layers")
    print(f"    Columns: {strata.data.columns.tolist()}")

    # Full preprocessor reader — follows file references automatically
    pp = read_preprocessor(PP_DIR / "PreProcessor_MAIN.IN")
    print(f"\n  Preprocessor main → children: {list(pp.children.keys())}")
    return pp


# ── 3. Simulation main file ───────────────────────────────────────────────────

def demo_simulation():
    from iwfm.io import read_simulation

    print("\n=== Simulation main ===")
    sim = read_simulation(SIM_DIR / "Simulation_MAIN.IN")
    print(f"  Period:    {sim.sim_begin}  →  {sim.sim_end}")
    print(f"  Time step: {sim.time_step}")
    print(f"  File refs: {len(sim.file_paths)}")
    return sim


# ── 4. Groundwater files ──────────────────────────────────────────────────────

def demo_groundwater():
    from iwfm.io import read_gw_main, read_bc_main, read_tile_drain

    print("\n=== Groundwater files ===")

    gw = read_gw_main(GW_DIR / "GW_MAIN.dat")
    print(f"  GW main:       {gw.n_hydrographs} hydrograph sites")

    bc = read_bc_main(GW_DIR / "BC_MAIN.dat")
    print(f"  BC main:       {bc.n_nodes} boundary nodes")

    td = read_tile_drain(GW_DIR / "TileDrain.dat")
    print(f"  Tile drains:   {len(td.data)} nodes  "
          f"columns={td.data.columns.tolist()}")


# ── 5. Stream files ───────────────────────────────────────────────────────────

def demo_stream():
    from iwfm.io import read_stream_main, read_diver_specs, read_bypass_specs

    print("\n=== Stream files ===")

    sm = read_stream_main(STRM_DIR / "Stream_MAIN.dat")
    print(f"  Stream main:   {sm.reach_params.shape[0]} reaches, "
          f"{sm.config['n_hydrographs']} hydrograph sites")

    divers = read_diver_specs(STRM_DIR / "DiverSpecs.dat")
    print(f"  Diver specs:   loaded (version={divers.header.version})")

    bypass = read_bypass_specs(STRM_DIR / "BypassSpecs.dat")
    n = len(bypass.bypass_data["bypass_id"]) if bypass.bypass_data else 0
    print(f"  Bypass specs:  {n} bypasses")


# ── 6. Time-series input files ────────────────────────────────────────────────

def demo_timeseries():
    from iwfm.io import read_precip, read_et

    print("\n=== Time-series inputs ===")

    precip = read_precip(SIM_DIR / "Precip.dat")
    print(f"  Precip: {len(precip.data)} timesteps × {precip.spec.n_columns} cols  "
          f"({precip.data.index[0].date()} → {precip.data.index[-1].date()})")
    print(f"  First 3 rows:\n{precip.data.head(3)}")

    et = read_et(SIM_DIR / "ET.dat")
    print(f"\n  ET:     {len(et.data)} timesteps × {et.spec.n_columns} cols")


# ── 7. IOModelAdapter ─────────────────────────────────────────────────────────

def demo_adapter(pp):
    from iwfm.io import IOModelAdapter, validate_preprocessor

    print("\n=== IOModelAdapter ===")
    results_dir = SAMPLE_MODEL / "Results"

    budget_hdfs = {}
    for name, fname in [("GW", "GW.hdf"), ("Stream", "StrmBud.hdf")]:
        p = results_dir / fname
        if p.exists():
            budget_hdfs[name] = str(p)

    heads_hdf = results_dir / "GWHeadAll.hdf"
    adapter = IOModelAdapter(
        preprocessor=pp,
        heads_hdf=str(heads_hdf) if heads_hdf.exists() else None,
        budget_hdfs=budget_hdfs,
    )

    print(f"  n_nodes={adapter.n_nodes}, n_elements={adapter.n_elements}, "
          f"n_layers={adapter.n_layers}, n_subregions={adapter.n_subregions}")
    print(f"  n_reaches={adapter.n_reaches}, n_stream_nodes={adapter.n_stream_nodes}")

    nodes_gdf = adapter.nodes_df()
    geo_col = nodes_gdf.dtypes.get("geometry", None)
    print(f"\n  nodes_df():        {nodes_gdf.shape}  geometry={geo_col is not None}")
    print(f"  elements_df():     {adapter.elements_df().shape}")
    print(f"  stratigraphy_df(): {adapter.stratigraphy_df().shape}")
    print(f"  reaches_df():      {adapter.reaches_df().shape}")
    print(f"  stream_nodes_df(): {adapter.stream_nodes_df().shape}")
    print(f"  lakes_df():        {adapter.lakes_df().shape}")
    print(f"  bypasses_df():     {adapter.bypasses_df().shape}")
    print(f"  tile_drains_df():  {adapter.tile_drains_df().shape}")

    # Time-series results (requires HDF files)
    if adapter._heads_hdf:
        heads = adapter.heads_df(layer=1,
                                 begin_date="10/01/1990_24:00",
                                 end_date="09/30/1995_24:00")
        print(f"\n  heads_df(layer=1): {heads.shape}")

    if "GW" in budget_hdfs:
        bud = adapter.budget_df("GW", location=1)
        print(f"  budget_df('GW',1): {bud.shape}  cols={bud.columns.tolist()[:3]} ...")

    # Validation
    errors = validate_preprocessor(pp)
    print(f"\n  validate_preprocessor(): {errors if errors else 'no errors'}")

    return adapter


if __name__ == "__main__":
    check_sample_model()
    demo_dates()
    pp = demo_preprocessor()
    demo_simulation()
    demo_groundwater()
    demo_stream()
    demo_timeseries()
    demo_adapter(pp)
    print("\nDone.")
