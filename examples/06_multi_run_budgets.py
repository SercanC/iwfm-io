"""
Example 6: Unified Budget DataFrame from Multiple Model Runs
=============================================================

Shows how to read budget HDF5 output files of various types from one or
more IWFM model runs and combine them into a single long-form pandas
DataFrame suitable for comparison, aggregation, and export.

Output shape (long form):

    run  budget_type  location  datetime  component  value
    ─────────────────────────────────────────────────────
    baseline  GW  Subregion_1  1990-10-02  Beginning Storage  1.23e8
    baseline  GW  Subregion_1  1990-11-01  Beginning Storage  1.21e8
    ...

Usage:
    python examples/06_multi_run_budgets.py

No DLL required — uses iwfm.io HDF5 readers only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from iwfm.io import collect_budgets as _collect_budgets

REPO_ROOT    = Path(__file__).resolve().parent.parent
SAMPLE_MODEL = REPO_ROOT / ".assets" / "sample_model"

# ── Run registry ──────────────────────────────────────────────────────────────
#
# Map a short run label to the Results/ directory for that run.
# Add as many entries as you have model runs.

RUNS: Dict[str, Path] = {
    "baseline": SAMPLE_MODEL / "Results",
    # "drought":  Path("runs/drought/Results"),
    # "wet":      Path("runs/wet/Results"),
}

# ── Budget file registry ──────────────────────────────────────────────────────
#
# Map a short type label to the HDF5 filename produced by IWFM.
# Remove entries for budget types your runs don't produce.

BUDGET_FILES: Dict[str, str] = {
    "GW":        "GW.hdf",
    "Stream":    "StrmBud.hdf",
    "RootZone":  "RootZone.hdf",
    "LWU":       "LWU.hdf",
    "Lake":      "LakeBud.hdf",
    "UnsatZone": "UnsatZoneBud.hdf",
    "SWShed":    "SWShed.hdf",
}


# ─────────────────────────────────────────────────────────────────────────────
# Core collector
# ─────────────────────────────────────────────────────────────────────────────

# collect_budgets is provided by iwfm.io — imported above as _collect_budgets.
# A thin wrapper is kept here to add console progress output for the demo.

def collect_budgets(
    runs: Dict[str, Path],
    budget_files: Dict[str, str],
    locations: Optional[List[str]] = None,
    budget_types: Optional[List[str]] = None,
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Thin demo wrapper around ``iwfm.io.collect_budgets`` with console output."""
    from iwfm.io import read_budget_hdf

    active_types = budget_types or list(budget_files.keys())
    for run_label, results_dir in runs.items():
        results_dir = Path(results_dir)
        for btype in active_types:
            fname = budget_files.get(btype)
            if fname is None:
                continue
            path = results_dir / fname
            if not path.exists():
                print(f"  [skip] {run_label}/{btype}: {fname} not found")
                continue
            result = read_budget_hdf(path)
            loc_names = result["locations"]
            if locations is not None:
                loc_names = [loc for loc in loc_names if loc in locations]
            print(f"  [ok]   {run_label}/{btype}: "
                  f"{len(loc_names)} location(s), "
                  f"{len(result['data'][result['locations'][0]])} timesteps")

    return _collect_budgets(
        runs=runs,
        budget_files=budget_files,
        locations=locations,
        budget_types=budget_types,
        begin_date=begin_date,
        end_date=end_date,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Wide-form pivot
# ─────────────────────────────────────────────────────────────────────────────

def to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot a long-form budget DataFrame to wide form.

    Returns a DataFrame with a DatetimeIndex and MultiIndex columns:
    ``(run, budget_type, location, component)``.
    """
    return df.pivot_table(
        index="datetime",
        columns=["run", "budget_type", "location", "component"],
        values="value",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers
# ─────────────────────────────────────────────────────────────────────────────

def annual_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Sum volumetric components by calendar year.

    Returns a DataFrame grouped by ``(year, run, budget_type, location, component)``.
    """
    out = df.copy()
    out["year"] = out["datetime"].dt.year
    return (
        out.groupby(["year", "run", "budget_type", "location", "component"],
                    observed=True)["value"]
           .sum()
           .reset_index()
           .rename(columns={"value": "annual_total"})
    )


def monthly_means(df: pd.DataFrame) -> pd.DataFrame:
    """Average each component by calendar month (1–12) across all years.

    Returns a DataFrame grouped by ``(month, run, budget_type, location, component)``.
    """
    out = df.copy()
    out["month"] = out["datetime"].dt.month
    return (
        out.groupby(["month", "run", "budget_type", "location", "component"],
                    observed=True)["value"]
           .mean()
           .reset_index()
           .rename(columns={"value": "monthly_mean"})
    )


def run_delta(df: pd.DataFrame, base_run: str, compare_run: str) -> pd.DataFrame:
    """Compute the difference (compare_run − base_run) for each component.

    Returns a DataFrame with column ``delta`` alongside the original identifiers.
    Rows present in one run but not the other are dropped.
    """
    base    = df[df["run"] == base_run].drop(columns="run")
    compare = df[df["run"] == compare_run].drop(columns="run")

    keys = ["budget_type", "location", "datetime", "component"]
    merged = base.merge(compare, on=keys, suffixes=("_base", "_compare"))
    merged["delta"] = merged["value_compare"] - merged["value_base"]
    return merged[keys + ["value_base", "value_compare", "delta"]]


# ─────────────────────────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── 1. Collect all budgets ─────────────────────────────────────────────

    print("Collecting budget outputs ...")
    df = collect_budgets(RUNS, BUDGET_FILES)

    if df.empty:
        raise SystemExit(
            "No budget files found. Restore .assets/sample_model/Results/ and retry."
        )

    print(f"\nUnified DataFrame: {len(df):,} rows × {df.shape[1]} columns")
    print(df.dtypes)
    print(df.head(8).to_string())

    # ── 2. Summary of what was loaded ──────────────────────────────────────

    print("\n─── Coverage ───")
    summary = (
        df.groupby(["run", "budget_type", "location"], observed=True)["datetime"]
          .agg(["min", "max", "count"])
          .rename(columns={"min": "start", "max": "end", "count": "n_rows"})
    )
    print(summary.to_string())

    print("\n─── Budget types and component counts ───")
    comp_counts = (
        df.groupby(["budget_type", "component"], observed=True)
          .size()
          .reset_index(name="n_rows")
          .groupby("budget_type", observed=True)["component"]
          .apply(list)
    )
    for btype, comps in comp_counts.items():
        print(f"  {btype}: {comps}")

    # ── 3. GW budget — entire model only ──────────────────────────────────

    print("\n─── GW budget (Entire Model) — first 5 timesteps ───")
    gw_entire = df[
        (df["budget_type"] == "GW") &
        (df["location"].str.contains("Entire", case=False))
    ]
    if not gw_entire.empty:
        pivot = gw_entire.pivot_table(
            index="datetime", columns="component", values="value"
        )
        print(pivot.head(5).to_string())

    # ── 4. Annual totals ───────────────────────────────────────────────────

    print("\n─── Annual totals (GW, Entire Model) ───")
    ann = annual_totals(
        df[(df["budget_type"] == "GW") &
           (df["location"].str.contains("Entire", case=False))]
    )
    if not ann.empty:
        # Show one component as illustration
        component = ann["component"].iloc[0]
        print(f"  Component: '{component}'")
        print(
            ann[ann["component"] == component]
            .drop(columns=["run", "budget_type", "location", "component"])
            .to_string(index=False)
        )

    # ── 5. Monthly seasonal means ─────────────────────────────────────────

    print("\n─── Monthly seasonal means (GW, Entire Model) ───")
    seas = monthly_means(
        df[(df["budget_type"] == "GW") &
           (df["location"].str.contains("Entire", case=False))]
    )
    if not seas.empty:
        component = seas["component"].iloc[0]
        print(f"  Component: '{component}'")
        print(
            seas[seas["component"] == component]
            .drop(columns=["run", "budget_type", "location", "component"])
            .to_string(index=False)
        )

    # ── 6. Run comparison (when multiple runs are available) ───────────────

    runs_present = df["run"].unique().tolist()
    if len(runs_present) >= 2:
        base, compare = runs_present[0], runs_present[1]
        print(f"\n─── Run delta: {compare} − {base} (GW, Entire Model) ───")
        delta = run_delta(
            df[(df["budget_type"] == "GW") &
               (df["location"].str.contains("Entire", case=False))],
            base_run=base,
            compare_run=compare,
        )
        print(delta.head(10).to_string(index=False))
    else:
        print(f"\n─── Only one run loaded ('{runs_present[0]}') ───")
        print("    Add more entries to RUNS to enable run comparison.")

    # ── 7. Wide-form pivot ────────────────────────────────────────────────

    print("\n─── Wide-form pivot (GW only) ───")
    wide = to_wide(df[df["budget_type"] == "GW"])
    print(f"  Shape: {wide.shape}")
    print(f"  Column levels: {wide.columns.names}")
    print(wide.iloc[:3, :4].to_string())

    # ── 8. Export ─────────────────────────────────────────────────────────

    out_csv = REPO_ROOT / "test_output" / "budgets_combined.csv"
    out_csv.parent.mkdir(exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"\nLong-form CSV saved to: {out_csv}")

    # Parquet preserves dtypes and is much faster for large datasets
    try:
        out_parquet = out_csv.with_suffix(".parquet")
        df.to_parquet(out_parquet, index=False)
        print(f"Parquet saved to:       {out_parquet}")
    except ImportError:
        print("(Install pyarrow or fastparquet to enable Parquet export)")

    # ── 9. Targeted re-load (subset of runs / types / locations) ──────────

    print("\n─── Targeted subset load ───")
    gw_sub1 = _collect_budgets(
        runs=RUNS,
        budget_files=BUDGET_FILES,
        budget_types=["GW"],
        locations=["Subregion_1"],
        begin_date="1995-01-01",
        end_date="2000-12-31",
    )
    print(f"  GW/Subregion_1/1995-2000: {len(gw_sub1):,} rows")
    if not gw_sub1.empty:
        print(f"  Date range: {gw_sub1['datetime'].min()} → "
              f"{gw_sub1['datetime'].max()}")


if __name__ == "__main__":
    main()
