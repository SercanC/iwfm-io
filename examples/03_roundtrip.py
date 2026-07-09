"""
Example 3: Round-Trip Read → Modify → Write
============================================

Demonstrates reading IWFM input files, making data changes, and writing
modified files back.  No DLL required — runs on any platform.

Covers:
  - Node file round-trip (read → write → read back → verify)
  - Precipitation scaling (drought / climate-change scenario)
  - Full preprocessor tree copy
  - Stream inflow modification
  - Groundwater boundary-condition copy

Usage:
    python examples/03_roundtrip.py
"""

import tempfile
from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"
PP_DIR   = SAMPLE_MODEL / "Preprocessor"
SIM_DIR  = SAMPLE_MODEL / "Simulation"
GW_DIR   = SIM_DIR / "GW"
STRM_DIR = SIM_DIR / "Stream"


def check_sample_model():
    if not PP_DIR.exists():
        raise SystemExit(f"Sample model not found at {SAMPLE_MODEL}")


# ── 1. Node file round-trip ───────────────────────────────────────────────────

def demo_nodes(tmp: Path):
    from iwfm_io import read_nodes, write_nodes

    print("=== Node file round-trip ===")
    original = read_nodes(PP_DIR / "NodeXY.dat")
    print(f"  Read:  {len(original.data)} nodes")

    out_path = tmp / "NodeXY_copy.dat"
    write_nodes(original, out_path)

    copy = read_nodes(out_path)
    assert len(copy.data) == len(original.data), "row count mismatch"
    assert list(copy.data.columns) == list(original.data.columns), "column mismatch"
    print(f"  Write + read back: OK ({len(copy.data)} nodes match)")


# ── 2. Element file round-trip ────────────────────────────────────────────────

def demo_elements(tmp: Path):
    from iwfm_io import read_elements, write_elements

    print("\n=== Element file round-trip ===")
    original = read_elements(PP_DIR / "Element.dat")
    print(f"  Read:  {len(original.data)} elements")

    out_path = tmp / "Element_copy.dat"
    write_elements(original, out_path)

    copy = read_elements(out_path)
    assert len(copy.data) == len(original.data), "row count mismatch"
    print(f"  Write + read back: OK ({len(copy.data)} elements match)")


# ── 3. Precipitation scaling (climate scenario) ───────────────────────────────

def demo_precip_scale(tmp: Path):
    from iwfm_io import read_precip, write_precip
    import copy

    print("\n=== Precipitation scaling (drought scenario −20%) ===")
    original = read_precip(SIM_DIR / "Precip.dat")
    orig_mean = original.data.iloc[:, 0].mean()
    print(f"  Original mean col_1 = {orig_mean:.4f}")

    # Deep copy so original is unchanged
    modified = copy.deepcopy(original)
    modified.data = original.data * 0.80

    out_path = tmp / "Precip_drought.dat"
    write_precip(modified, out_path)

    verify = read_precip(out_path)
    ratio = verify.data.iloc[:, 0].mean() / orig_mean
    assert abs(ratio - 0.80) < 1e-5, f"Expected 0.80 ratio, got {ratio:.6f}"
    print(f"  Scaled mean = {verify.data.iloc[:, 0].mean():.4f}  "
          f"ratio = {ratio:.4f}  OK")


# ── 4. Full preprocessor tree copy ───────────────────────────────────────────

def demo_preprocessor_copy(tmp: Path):
    from iwfm_io import read_preprocessor, write_preprocessor, read_nodes, read_elements

    print("\n=== Full preprocessor tree copy ===")
    pp = read_preprocessor(PP_DIR / "PreProcessor_MAIN.IN")
    orig_nodes = len(pp.children["node"].data)
    orig_elems = len(pp.children["element"].data)
    print(f"  Loaded: {orig_nodes} nodes, {orig_elems} elements")

    out_dir = tmp / "preprocessor_copy"
    out_dir.mkdir()
    write_preprocessor(pp, out_dir / "PreProcessor_MAIN_copy.IN")

    node_copy = read_nodes(out_dir / "NodeXY.dat")
    elem_copy = read_elements(out_dir / "Element.dat")
    assert len(node_copy.data) == orig_nodes
    assert len(elem_copy.data) == orig_elems
    print(f"  Round-trip OK: {orig_nodes} nodes, {orig_elems} elements")


# ── 5. Stream inflow modification ────────────────────────────────────────────

def demo_stream_inflow(tmp: Path):
    from iwfm_io import read_stream_inflow, write_stream_inflow
    import copy

    print("\n=== Stream inflow modification (+10% wet scenario) ===")
    path = STRM_DIR / "StreamInflow.dat"
    if not path.exists():
        print("  StreamInflow.dat not found — skipping.")
        return

    original = read_stream_inflow(path)
    print(f"  Read: {len(original.data)} timesteps × {len(original.data.columns)} cols")

    modified = copy.deepcopy(original)
    modified.data = original.data * 1.10

    out_path = tmp / "StreamInflow_wet.dat"
    write_stream_inflow(modified, out_path)

    verify = read_stream_inflow(out_path)
    ratio = verify.data.sum().sum() / original.data.sum().sum()
    assert abs(ratio - 1.10) < 1e-4, f"Expected 1.10, got {ratio:.6f}"
    print(f"  Wet scenario written, total ratio = {ratio:.4f}  OK")


# ── 6. GW boundary conditions round-trip ─────────────────────────────────────

def demo_gw_bc(tmp: Path):
    from iwfm_io import read_bc_main, write_bc_main

    print("\n=== GW boundary conditions round-trip ===")
    path = GW_DIR / "BC_MAIN.dat"
    if not path.exists():
        print("  BC_MAIN.dat not found — skipping.")
        return

    bc = read_bc_main(path)
    out_path = tmp / "BC_MAIN_copy.dat"
    write_bc_main(bc, out_path)

    bc2 = read_bc_main(out_path)
    assert bc2.n_nodes == bc.n_nodes, "node count mismatch"
    print(f"  Round-trip OK: {bc.n_nodes} boundary nodes")


# ── 7. Stratigraphy round-trip ────────────────────────────────────────────────

def demo_strata(tmp: Path):
    from iwfm_io import read_strata, write_strata
    import numpy as np

    print("\n=== Stratigraphy round-trip ===")
    original = read_strata(PP_DIR / "Strata.dat")
    print(f"  Read: {len(original.data)} nodes, {original.n_layers} layers")

    out_path = tmp / "Strata_copy.dat"
    write_strata(original, out_path)

    copy = read_strata(out_path)
    assert len(copy.data) == len(original.data)
    assert copy.n_layers == original.n_layers

    # Verify numerical values are preserved
    numeric_cols = original.data.select_dtypes("number").columns
    max_diff = (original.data[numeric_cols].values
                - copy.data[numeric_cols].values).__abs__().max()
    assert max_diff < 1e-3, f"Numerical drift: {max_diff}"
    print(f"  Round-trip OK: {len(copy.data)} nodes, max numeric diff = {max_diff:.2e}")


if __name__ == "__main__":
    check_sample_model()
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        demo_nodes(tmp)
        demo_elements(tmp)
        demo_precip_scale(tmp)
        demo_preprocessor_copy(tmp)
        demo_stream_inflow(tmp)
        demo_gw_bc(tmp)
        demo_strata(tmp)
    print("\nAll round-trip tests passed.")
