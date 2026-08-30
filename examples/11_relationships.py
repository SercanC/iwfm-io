"""
Example 11: Cross-File Relationships
====================================

IWFM input files reference each other constantly. A crop table doesn't
hold ET values — it holds a COLUMN NUMBER into the ET file. A well
doesn't hold its pumping — it holds a column number into the
time-series pumping file plus a share fraction. Boundary conditions
point at columns of the time-series BC file, lakes at the
maximum-elevation file, and destinations are (type, id) pairs whose
meaning depends on a per-file code table.

Since v2.11.0 the model object returned by ``open_model()`` knows every
such relationship. This example walks through the four capabilities:

  1. RESOLUTION      — series(role, column): the actual data a pointer
                       points at, factor-applied and calendar-expanded
  2. REVERSE LOOKUP  — column_usage(role): who uses each column of a
                       time-series file (recovers the meaning of the
                       otherwise anonymous col_1..col_N columns)
  3. VALIDATION      — validate_references(): every pointer, entity ID,
                       and destination pair checked model-wide
  4. ACCESSORS       — crop_series / urban_series / well_pumping /
                       element_pumping / bc_series / diversion_series /
                       lake_max_elevation: one-call answers

No DLL required — runs on any platform.

Usage:
    python examples/11_relationships.py
"""

from pathlib import Path

SAMPLE_MODEL = Path(__file__).resolve().parent.parent / ".assets" / "sample_model"


def check_sample_model():
    if not SAMPLE_MODEL.exists():
        raise SystemExit(
            f"Sample model not found at {SAMPLE_MODEL}\n"
            "Restore .assets/sample_model/ to run this example."
        )


# ── 1. The problem: pointers, not values ──────────────────────────────────────

def demo_the_problem(model):
    print("=== The problem: pointer columns ===")

    # Any component/sub-file is one lazy call away — the model walks the
    # main-file chain (simulation main → root zone main → crops main):
    np_ag = model.component("nonponded_ag")
    names = [np_ag.crop_names[c] for c in np_ag.crop_codes
             if np_ag.crop_names.get(c)]
    print(f"  non-ponded crops: {np_ag.crop_codes}"
          + (f"  ({names})" if names else ""))

    # The crop table holds COLUMN NUMBERS, not ET values.
    # element_id 0 is IWFM's "applies to all elements" sentinel.
    print("\n  et_columns — column numbers into the ET file:")
    print("  " + np_ag.et_columns.to_string(index=False).replace("\n", "\n  "))

    # The ET file itself has anonymous columns...
    et_file = model.timeseries("et")
    print(f"\n  ET file: {et_file.spec.n_columns} columns named "
          f"{list(et_file.data.columns[1:4])} ...  — which is which?")


# ── 2. Resolution: series() ───────────────────────────────────────────────────

def demo_resolution(model):
    print("\n=== 1. Resolution: series(role, column) ===")

    # Crop TO points at ET column 1. Resolve it three ways:

    # (a) raw pattern — exactly what the file stores (inches, year 4000
    #     = IWFM's "recurring every year" sentinel)
    raw = model.series("et", 1, raw=True, expand=False)
    print(f"  raw pattern:      {len(raw)} rows, first "
          f"{raw['date'].iloc[0]} = {raw['value'].iloc[0]} (file units)")

    # (b) factor applied (FACTET converts inches → feet here)
    factored = model.series("et", 1, expand=False)
    print(f"  factor applied:   first value {factored['value'].iloc[0]:.5f} "
          f"(x FACTET {model.timeseries('et').spec.factor})")

    # (c) the default: factor applied AND the recurring pattern expanded
    #     onto the simulation calendar (10/1990 – 9/2000)
    s = model.series("et", 1)
    print(f"  expanded:         {len(s)} monthly stamps from "
          f"{s['date'].iloc[0].date()} to {s['date'].iloc[-1].date()}")
    print("  (values are step functions: each applies from its stamp "
          "until the next)")

    # expand_recurring() is also available standalone for files you
    # read directly:
    from iwfm_io import expand_recurring, read_timeseries_file
    rf = read_timeseries_file(
        SAMPLE_MODEL / "Simulation" / "RootZone" / "ReturnFlowFrac.dat")
    expanded = expand_recurring(rf.data, "10/01/1990_00:00",
                                "09/30/2000_24:00")
    print(f"  expand_recurring on ReturnFlowFrac: {len(rf.data)} pattern "
          f"row(s) → {len(expanded)} stamp(s) on the sim calendar")


# ── 3. Reverse lookup: column_usage() ─────────────────────────────────────────

def demo_reverse_lookup(model):
    print("\n=== 2. Reverse lookup: column_usage(role) ===")
    print("  Who points at each ET column?  (This recovers the meaning")
    print("  of col_1..col_7 — information the file itself only carried")
    print("  in a comment line.)\n")

    usage = model.column_usage("et")
    print("  " + usage.to_string(index=False).replace("\n", "\n  "))

    print("\n  → col 1 = the tomato crop, col 3 = every ponded type,")
    print("    col 4 = urban, col 5 = native+riparian, col 6 = small")
    print("    watersheds, col 7 = the lake — matching the ET file's")
    print("    original column-label comment exactly.")


# ── 4. Validation: validate_references() ──────────────────────────────────────

def demo_validation(model):
    import iwfm_io

    print("\n=== 3. Validation: validate_references() ===")

    findings = model.validate_references()
    print(f"  this model: {len(findings)} findings "
          f"{'(every reference resolves)' if findings.empty else ''}")

    # Break a reference on a THROWAWAY copy of the model and watch the
    # validator catch it: point crop TO at ET column 99 (only 7 exist)
    # and send a diversion to subregion 99 (only 2 exist).
    broken = iwfm_io.open_model(SAMPLE_MODEL)
    broken.component("nonponded_ag").et_columns.loc[0, "TO"] = 99
    ds = broken.component("diver_specs")
    ds.data.loc[0, ["dest_type", "dest_id"]] = [4, 99]

    findings = broken.validate_references()
    print(f"\n  after breaking two references: {len(findings)} findings")
    show = findings[["severity", "source", "column", "issue", "examples"]]
    print("  " + show.to_string(index=False).replace("\n", "\n  "))


# ── 5. Accessors: one-call answers ────────────────────────────────────────────

def demo_accessors(model):
    print("\n=== 4. Convenience accessors ===")

    # -- crops: pointer lookup + element_id=0 sentinel handled for you
    et = model.crop_series("et", "TO", element=12)
    print(f"  crop_series('et', 'TO', element=12): {len(et)} stamps, "
          f"peak {et['value'].max():.3f}")

    ip = model.crop_series("irrigation_period", "AL", expand=False)
    months = [d[:2] for d, v in zip(ip['date'], ip['value']) if v == 1]
    print(f"  crop_series('irrigation_period', 'AL'): irrigable in "
          f"months {months}")

    rice = model.crop_series("et", "rice_fl", expand=False)
    rip = model.crop_series("et", "riparian", element=1, expand=False)
    print(f"  ponded ('rice_fl') and riparian ET resolve too: "
          f"{len(rice)}/{len(rip)} pattern rows")

    # a pointer of 0 means "none / computed internally" — the accessor
    # says so instead of failing cryptically:
    try:
        model.crop_series("supply_requirement", "TO")
    except ValueError as exc:
        print(f"  0-pointer → clear error: {exc}")

    # -- urban drivers
    pop = model.urban_series("population", element=5, expand=False)
    print(f"\n  urban_series('population', element=5): "
          f"{pop['value'].iloc[0]:.0f} people")

    # -- pumping: TSPumping column x that element's FRACSK share
    pump = model.element_pumping(73, expand=False)
    print(f"  element_pumping(73): {len(pump)} monthly values, "
          f"annual total {pump['value'].sum():,.0f} (model volume units)")

    # -- boundary conditions: searches all four BC files
    const = model.bc_series(1, layer=1)
    print(f"\n  bc_series(1, layer=1): constant head "
          f"{const['value'].iloc[0]} (ITSCOL=0 → one stamp at sim start)")
    sh = model.component("spec_head").data
    ts_node = int(sh.query("itscol > 0")["node_id"].iloc[0])
    driven = model.bc_series(ts_node, layer=1)
    print(f"  bc_series({ts_node}, layer=1): time-series driven, "
          f"{len(driven)} stamps from the boundary TS file")

    # -- diversions: column x delivery fraction
    dv = model.diversion_series(1)
    un = model.diversion_series(1, scaled=False)
    print(f"\n  diversion_series(1): delivery = column x frac "
          f"({dv['value'].iloc[-1]:,.0f} = {un['value'].iloc[-1]:,.0f} x 0.98)")

    # -- lakes
    lme = model.lake_max_elevation()
    print(f"  lake_max_elevation(): {lme['value'].iloc[0]} "
          f"(constant across the simulation)")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")  # arrows in redirected output
    check_sample_model()

    import iwfm_io
    model = iwfm_io.open_model(SAMPLE_MODEL)

    demo_the_problem(model)
    demo_resolution(model)
    demo_reverse_lookup(model)
    demo_validation(model)
    demo_accessors(model)
    print("\nDone.")
