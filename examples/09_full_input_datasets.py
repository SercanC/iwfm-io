"""
Example 9: Every Input Dataset as a DataFrame
=============================================

Every dataset in every IWFM input file is parsed into pandas
DataFrames — aquifer parameters, initial conditions, crop pointer
tables, small watersheds, and more. No DLL required.

Pointer columns (names starting with ``ic``/``irn``/``itscol``) are
1-based column numbers referencing data columns of OTHER files (ET,
Precipitation, return-flow fractions, time-series pumping, ...); each
dataclass docstring says which file every such column points at.

Writers regenerate the files entirely from the parsed DataFrames:
read → edit a DataFrame → write produces a valid IWFM input file
(verified against the IWFM executables — the sample model reproduces
baseline heads exactly after a full read/write round-trip).

Covers:
  - GW main: aquifer parameters, Kh anomalies, initial heads
  - Subsidence parameters
  - Tile drain hydrograph print control
  - Well specs: pumping configuration + delivery element groups
  - Diversion specs: full table, recharge zones, spill locations
  - Small watersheds: all five tables
  - Unsaturated zone: per-element parameters + initial moisture
  - Root zone main: per-element soil table
  - Root zone sub-components: crops, urban, native vegetation
  - Editing a DataFrame and writing the file back

Usage:
    python examples/09_full_input_datasets.py
"""

from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"
SIM_DIR      = SAMPLE_MODEL / "Simulation"
GW_DIR       = SIM_DIR / "GW"
RZ_DIR       = SIM_DIR / "RootZone"


def check_sample_model():
    if not SIM_DIR.exists():
        raise SystemExit(
            f"Sample model not found at {SAMPLE_MODEL}\n"
            "Restore .assets/sample_model/ to run this example."
        )


# ── 1. GW main: aquifer parameters and initial conditions ────────────────────

def demo_gw_main():
    from iwfm_io import read_gw_main

    print("=== GW main: aquifer parameters ===")
    gw = read_gw_main(GW_DIR / "GW_MAIN.dat")

    print(f"  NGROUP = {gw.ngroup} "
          f"({'parametric grid' if gw.ngroup else 'values at every node'})")
    print(f"  Conversion factors: {gw.param_factors}")

    if gw.ngroup:
        # Parametric grid: parameters at parametric nodes, interpolated
        # by IWFM onto the FE grid nodes listed in node_range
        grid = gw.parametric_grids[0]
        print(f"  Group 1 covers nodes {grid['node_range']} "
              f"({len(grid['nodes'])} nodes)")
        print(grid["params"].to_string(index=False))
    else:
        # Per-node long format: one row per (node, layer)
        print(gw.aquifer_params.head())

    print(f"\n  Kh anomalies: "
          f"{0 if gw.kh_anomalies is None else len(gw.kh_anomalies)} elements")
    print(f"  Return-flow section: IFLAGRF={gw.iflagrf}")

    print(f"\n  Initial heads ({len(gw.initial_heads)} nodes, "
          f"FACTHP={gw.facthp}):")
    print(gw.initial_heads.head(3).to_string(index=False))


# ── 2. Subsidence parameters ──────────────────────────────────────────────────

def demo_subsidence():
    from iwfm_io import read_subsidence

    print("\n=== Subsidence parameters ===")
    sub = read_subsidence(GW_DIR / "Subsidence.dat")
    print(f"  NGROUP = {sub.ngroup}, factors: {sub.param_factors}")
    params = (sub.parametric_grids[0]["params"] if sub.ngroup
              else sub.subsidence_params)
    # sce/sci = elastic/inelastic storage, dc = interbed thickness,
    # hc = pre-compaction head (99999 = use initial heads)
    print(params.head(4).to_string(index=False))


# ── 3. Tile drains: hydrograph print control ─────────────────────────────────

def demo_tile_drain():
    from iwfm_io import read_tile_drain

    print("\n=== Tile drain hydrograph print control ===")
    td = read_tile_drain(GW_DIR / "TileDrain.dat")
    print(f"  {td.n_tile_drains} tile drains; {td.n_hydrographs} hydrographs "
          f"→ {td.hyd_out_file}")
    print(td.hydrographs.to_string(index=False))


# ── 4. Element pumping: delivery element groups ──────────────────────────────

def demo_elem_pump():
    from iwfm_io import read_elem_pump

    print("\n=== Element pumping ===")
    ep = read_elem_pump(GW_DIR / "ElemPump.dat")
    # icolsk points at a column of the time-series pumping file;
    # icfirigsk at the irrigation fractions file; icadjsk at the
    # supply adjustment file
    print(f"  {ep.n_sinks} pumping elements, {ep.n_groups} element groups")
    print(ep.data.head(3).to_string(index=False))
    print(f"  element_groups_df: {ep.element_groups_df.shape} "
          "(long format: group_id, element_id)")


# ── 5. Diversion specs: table + recharge zones + spills ──────────────────────

def demo_diver_specs():
    from iwfm_io import read_diver_specs

    print("\n=== Diversion specifications ===")
    ds = read_diver_specs(SIM_DIR / "Stream" / "DiverSpecs.dat")
    print(f"  {ds.n_diversions} diversions")
    cols = ["diversion_id", "export_node", "dest_type", "dest_id",
            "delivery_frac", "name"]
    print(ds.data[cols].to_string(index=False))
    print(f"\n  Delivery groups: {ds.delivery_groups_df.shape}")
    print(f"  Recharge zones:  {ds.recharge_zones_df.shape}")
    print(f"  Spill locations: {ds.spill_locations_df.shape} "
          "(older stream-package formats only)")


# ── 6. Small watersheds ───────────────────────────────────────────────────────

def demo_swshed():
    from iwfm_io import read_swshed

    print("\n=== Small watersheds ===")
    sw = read_swshed(SIM_DIR / "SWShed.dat")
    print(f"  {sw.n_watersheds} watersheds")
    print(sw.watershed_data.to_string(index=False))
    print("\n  Receiving GW nodes (qmax < 0 encodes the layer):")
    print(sw.watershed_nodes.to_string(index=False))
    # irns/icets are lookup columns into the Precip and ET files
    print("\n  Root zone parameters:")
    print(sw.rootzone_params.to_string(index=False))
    print("\n  Aquifer parameters:")
    print(sw.aquifer_params.to_string(index=False))
    print("\n  Initial conditions:")
    print(sw.initial_conditions.to_string(index=False))


# ── 7. Unsaturated zone ───────────────────────────────────────────────────────

def demo_unsatzone():
    from iwfm_io import read_unsatzone

    print("\n=== Unsaturated zone ===")
    uz = read_unsatzone(SIM_DIR / "UnsatZone.dat")
    print(f"  {uz.n_unsat_layers} unsaturated layers, "
          f"{uz.element_params['element_id'].nunique()} elements")
    print(uz.element_params.head(4).to_string(index=False))
    print("\n  Initial moisture (element_id 0 = all elements):")
    print(uz.initial_moisture.to_string(index=False))


# ── 8. Root zone: soil table and sub-components ──────────────────────────────

def demo_rootzone():
    from iwfm_io import (read_rootzone_main, read_nonponded_ag_main,
                         read_ponded_ag_main, read_urban_main,
                         read_native_veg_main)

    print("\n=== Root zone: per-element soil table ===")
    rz = read_rootzone_main(RZ_DIR / "RootZone_MAIN.dat")
    # irne → Precip file column; icdst* → surface-flow destination
    # file columns (v4.12); older files have typdest/dest instead
    print(f"  {len(rz.element_params)} elements  "
          f"columns: {rz.element_params.columns.tolist()}")
    print(rz.element_params.head(3).to_string(index=False))

    print("\n=== Non-ponded crops ===")
    np_ = read_nonponded_ag_main(rz.file_paths["nonponded_ag"])
    print(f"  {np_.n_crops} crops: {np_.crop_codes}")
    print("  Root depths (icroot → root depth fractions file column):")
    print(np_.root_depths.to_string(index=False))
    print(f"  Curve numbers: {np_.curve_numbers.shape}")
    # element_id 0 = the row applies to every element
    print(f"  ET columns (→ ET file): "
          f"{np_.et_columns.to_dict('records')}")
    print(f"  Initial conditions: {np_.initial_conditions.shape}")

    print("\n=== Ponded crops (rice/refuge) ===")
    pa = read_ponded_ag_main(rz.file_paths["ponded_ag"])
    print(f"  Root depths: {pa.root_depths}")
    print(f"  Ponding depth columns (→ PNDTHFL): "
          f"{pa.ponding_depth_columns.to_dict('records')}")

    print("\n=== Urban lands ===")
    ur = read_urban_main(rz.file_paths["urban"])
    print(f"  Root depth {ur.root_depth}; params {ur.element_params.shape}")
    print(ur.element_params.head(2).to_string(index=False))

    print("\n=== Native and riparian vegetation ===")
    nv = read_native_veg_main(rz.file_paths["native_veg"])
    print(f"  Root depths: native={nv.root_depth_native}, "
          f"riparian={nv.root_depth_riparian}")
    print(nv.element_params.head(2).to_string(index=False))


# ── 9. Edit a DataFrame, write the file back ─────────────────────────────────

def demo_edit_and_write():
    import tempfile
    from iwfm_io import read_gw_main, write_gw_main

    print("\n=== Edit + write back (files regenerate from DataFrames) ===")
    gw = read_gw_main(GW_DIR / "GW_MAIN.dat")

    # Raise all layer-1 initial heads by 5 ft
    gw.initial_heads["head_layer_1"] += 5.0

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "GW_MAIN_modified.dat"
        # base_dir: IWFM resolves referenced paths against the
        # simulation working directory — pass it to keep paths relative
        write_gw_main(gw, out, base_dir=SIM_DIR)

        gw2 = read_gw_main(out)
        print(f"  Original layer-1 head at node 1: 280.0")
        print(f"  Modified layer-1 head at node 1: "
              f"{gw2.initial_heads['head_layer_1'].iloc[0]}")
        assert gw2.initial_heads["head_layer_1"].iloc[0] == 285.0
    print("  Round-trip OK — no raw text involved, DataFrames only.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # arrows in redirected output
    check_sample_model()
    demo_gw_main()
    demo_subsidence()
    demo_tile_drain()
    demo_elem_pump()
    demo_diver_specs()
    demo_swshed()
    demo_unsatzone()
    demo_rootzone()
    demo_edit_and_write()
    print("\nDone.")
