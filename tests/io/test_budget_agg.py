"""Tests for the 24:00-aware date helpers and component-aware budget
aggregation (iwfm_io._tokens.iwfm_day/water_year, collect.aggregate_budget)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"


class TestIwfmDay:
    def test_midnight_stamp_belongs_to_previous_day(self):
        from iwfm_io import iwfm_day

        assert iwfm_day("09/30/2024_24:00") == pd.Timestamp("2024-09-30")
        assert iwfm_day(pd.Timestamp("2024-10-01")) == \
            pd.Timestamp("2024-09-30")

    def test_intraday_stamp_belongs_to_its_own_day(self):
        from iwfm_io import iwfm_day

        assert iwfm_day("09/30/2024_12:00") == pd.Timestamp("2024-09-30")
        assert iwfm_day("09/30/2024_00:30") == pd.Timestamp("2024-09-30")

    def test_vector_inputs(self):
        from iwfm_io import iwfm_day

        idx = pd.DatetimeIndex(["2024-10-01", "2024-10-01 12:00"])
        out = iwfm_day(idx)
        assert isinstance(out, pd.DatetimeIndex)
        assert out.tolist() == [pd.Timestamp("2024-09-30"),
                                pd.Timestamp("2024-10-01")]
        s_out = iwfm_day(pd.Series(idx))
        assert isinstance(s_out, pd.Series)
        assert s_out.tolist() == out.tolist()


class TestWaterYear:
    def test_boundary_stamps(self):
        from iwfm_io import water_year

        # 9/30 24:00 closes the WY; 10/1 24:00 opens the next one
        assert water_year("09/30/2024_24:00") == 2024
        assert water_year("10/01/2024_24:00") == 2025
        assert water_year("01/15/2024_24:00") == 2024

    def test_vector_and_series(self):
        from iwfm_io import water_year

        idx = pd.DatetimeIndex(["2024-10-01", "2024-10-02", "2025-04-01"])
        assert water_year(idx).tolist() == [2024, 2025, 2025]
        assert water_year(pd.Series(idx)).tolist() == [2024, 2025, 2025]


class TestComponentAgg:
    def test_rules(self):
        from iwfm_io import budget_component_agg

        assert budget_component_agg("Beginning Storage (+)") == "first"
        assert budget_component_agg("Ending Storage (-)") == "last"
        assert budget_component_agg("Cumulative Subsidence") == "last"
        assert budget_component_agg("Deep Percolation (+)") == "sum"
        assert budget_component_agg("Pumping (-)") == "sum"
        assert budget_component_agg("Discrepancy (=)") == "sum"


def _toy_wide():
    """Two water years of monthly stamps (24:00 → first-of-next-month)."""
    idx = pd.date_range("2000-11-01", periods=24, freq="MS")  # WY2001+2002
    n = len(idx)
    return pd.DataFrame({
        "Beginning Storage (+)": 1000.0 + np.arange(n),
        "Ending Storage (-)": 1001.0 + np.arange(n),
        "Deep Percolation (+)": np.full(n, 2.0),
        "Cumulative Subsidence": np.linspace(0.1, 2.4, n),
    }, index=idx)


class TestAggregateBudgetWide:
    def test_stocks_and_flows(self):
        from iwfm_io import aggregate_budget

        wide = _toy_wide()
        out = aggregate_budget(wide, period="WY")
        assert out.index.tolist() == [2001, 2002]
        # flows sum: 12 months x 2.0
        assert out.loc[2001, "Deep Percolation (+)"] == pytest.approx(24.0)
        # stocks: first/last of the period, not sums
        assert out.loc[2001, "Beginning Storage (+)"] == 1000.0
        assert out.loc[2001, "Ending Storage (-)"] == 1012.0
        assert out.loc[2002, "Beginning Storage (+)"] == 1012.0
        # cumulative: last value
        assert out.loc[2002, "Cumulative Subsidence"] == \
            pytest.approx(wide["Cumulative Subsidence"].iloc[-1])

    def test_unsorted_input(self):
        from iwfm_io import aggregate_budget

        wide = _toy_wide().iloc[::-1]
        out = aggregate_budget(wide, period="WY")
        assert out.loc[2001, "Beginning Storage (+)"] == 1000.0
        assert out.loc[2001, "Ending Storage (-)"] == 1012.0

    def test_calendar_year_and_month(self):
        from iwfm_io import aggregate_budget

        wide = _toy_wide()
        cy = aggregate_budget(wide, period="CY")
        # stamps 2000-11-01..2002-10-01 → owning days 2000-10-31..2002-09-30
        assert cy.index.tolist() == [2000, 2001, 2002]
        mon = aggregate_budget(wide, period="MON")
        assert str(mon.index[0]) == "2000-10"
        assert mon["Deep Percolation (+)"].iloc[0] == pytest.approx(2.0)

    def test_bad_inputs(self):
        from iwfm_io import aggregate_budget

        with pytest.raises(ValueError, match="period"):
            aggregate_budget(_toy_wide(), period="QTR")
        with pytest.raises(ValueError, match="DatetimeIndex"):
            aggregate_budget(pd.DataFrame({"a": [1.0]}))


class TestAggregateBudgetLong:
    def test_long_form(self):
        from iwfm_io import aggregate_budget

        wide = _toy_wide()
        long_df = (wide.reset_index(names="datetime")
                   .melt(id_vars="datetime", var_name="component",
                         value_name="value"))
        long_df["run"] = "baseline"
        long_df["location"] = "ENTIRE MODEL AREA"

        out = aggregate_budget(long_df, period="WY")
        assert set(out.columns) == {"run", "location", "water_year",
                                    "component", "value"}
        piv = out.pivot_table(index="water_year", columns="component",
                              values="value")
        ref = aggregate_budget(wide, period="WY")
        for col in ref.columns:
            assert piv[col].values == pytest.approx(ref[col].values)


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestDayIndex:
    @pytest.fixture(scope="class")
    def model(self):
        from iwfm_io import open_model

        return open_model(SAMPLE_MODEL)

    def test_budget_df_day_index(self, model):
        from iwfm_io import iwfm_day

        raw = model.budget_df("GW", location=1)
        owned = model.budget_df("GW", location=1, day_index=True)
        assert (owned.index == iwfm_day(raw.index)).all()
        # first daily value belongs to 10/01/1990, not 10/02
        assert owned.index[0] == pd.Timestamp("1990-10-01")
        assert (owned.values == raw.values).all()

    def test_day_index_unlocks_ye_sep(self, model):
        from iwfm_io import aggregate_budget

        owned = model.budget_df("GW", location=1, day_index=True)
        flows = owned[["Deep Percolation (+)"]]
        by_resample = flows.resample("YE-SEP").sum()
        ref = aggregate_budget(
            model.budget_df("GW", location=1), period="WY")
        assert by_resample.index[0] == pd.Timestamp("1991-09-30")
        assert by_resample["Deep Percolation (+)"].values == pytest.approx(
            ref["Deep Percolation (+)"].values)

    def test_heads_and_hydrograph_day_index(self, model):
        from iwfm_io import iwfm_day

        raw = model.heads_df(layer=1)
        owned = model.heads_df(layer=1, day_index=True)
        assert (owned.index == iwfm_day(raw.index)).all()

        raw_h = model.hydrograph_df("GWHyd")
        owned_h = model.hydrograph_df("GWHyd", day_index=True)
        assert (owned_h.index == iwfm_day(raw_h.index)).all()

    def test_default_unchanged(self, model):
        a = model.budget_df("GW", location=1)
        b = model.budget_df("GW", location=1, day_index=False)
        assert (a.index == b.index).all()


# ---------------------------------------------------------------------------
# DLL-faithful aggregation engine (iwfm_io._budget_agg) — issues #33/#34
# ---------------------------------------------------------------------------

def _dll_lwu_reference(labels, req, short, pump, div, other, potcuaw):
    """Straight transcription of the Fortran accumulation loop
    (Class_Budget.f90 ReadData_SelectedColumns_FromHDFFile) as a slow
    reference: per window, prev shortage = previous step's RAW shortage,
    reset to 0 at each window start."""
    out_req, out_short, out_pot = {}, {}, {}
    prev_short = 0.0
    n_in_window = {}
    for t, lab in enumerate(labels):
        if lab not in out_req:
            out_req[lab] = out_short[lab] = out_pot[lab] = 0.0
            n_in_window[lab] = sum(1 for x in labels if x == lab)
            prev_short = 0.0
        if n_in_window[lab] == 1:
            out_req[lab] = req[t]
            out_short[lab] = short[t]
            out_pot[lab] = potcuaw[t]
        else:
            if prev_short <= 0.0:
                mod = req[t]
            elif req[t] > prev_short:
                mod = req[t] - prev_short
            else:
                mod = req[t]
            out_req[lab] += mod
            out_short[lab] += mod - pump[t] - div[t] - other[t]
            if req[t] != 0.0:
                out_pot[lab] += potcuaw[t] * mod / req[t]
        prev_short = short[t]
    keys = list(dict.fromkeys(labels))
    return (np.array([out_req[k] for k in keys]),
            np.array([out_short[k] for k in keys]),
            np.array([out_pot[k] for k in keys]))


class TestWindowEndLabels:
    def test_water_year_anchoring(self):
        from iwfm_io._budget_agg import window_end_labels

        # Monthly stamps Oct 1990 .. Sep 1992 (24:00 -> next-month-first)
        idx = pd.date_range("1990-11-01", periods=24, freq="MS")
        labels, complete = window_end_labels(idx, "1YEAR",
                                             native_unit="1MON")
        assert complete.all()
        assert labels[0] == pd.Timestamp("1991-10-01")   # 09/30/1991_24:00
        assert labels[11] == pd.Timestamp("1991-10-01")
        assert labels[12] == pd.Timestamp("1992-10-01")
        assert labels[-1] == pd.Timestamp("1992-10-01")

    def test_trailing_partial_window_dropped(self):
        from iwfm_io._budget_agg import window_end_labels

        # 30 months: WY1991, WY1992 complete + 6 months of WY1993
        idx = pd.date_range("1990-11-01", periods=30, freq="MS")
        labels, complete = window_end_labels(idx, "1YEAR",
                                             native_unit="1MON")
        assert complete[:24].all()
        assert not complete[24:].any()

    def test_monthly_identity_on_monthly_data(self):
        from iwfm_io._budget_agg import window_end_labels

        idx = pd.date_range("1990-11-01", periods=6, freq="MS")
        labels, complete = window_end_labels(idx, "1MON",
                                             native_unit="1MON")
        assert complete.all()
        assert list(labels) == list(idx)

    def test_daily_owning_month(self):
        from iwfm_io._budget_agg import window_end_labels

        # Daily stamps for Oct 1990 (10/01_24:00 -> Oct 2 .. Nov 1)
        idx = pd.date_range("1990-10-02", periods=31, freq="D")
        labels, complete = window_end_labels(idx, "1MON",
                                             delta_minutes=1440)
        # every October day belongs to the window stamped 10/31_24:00
        assert (labels == pd.Timestamp("1990-11-01")).all()
        assert complete.all()

    def test_calendar_year_keeps_partials(self):
        from iwfm_io._budget_agg import window_end_labels

        idx = pd.date_range("1990-11-01", periods=24, freq="MS")
        labels, complete = window_end_labels(idx, "1CALYEAR",
                                             native_unit="1MON")
        assert complete.all()
        # Oct-Dec 1990 -> label Jan 1 1991 (12/31/1990_24:00)
        assert labels[0] == pd.Timestamp("1991-01-01")
        assert labels[2] == pd.Timestamp("1991-01-01")
        assert labels[3] == pd.Timestamp("1992-01-01")

    def test_bad_interval(self):
        from iwfm_io._budget_agg import window_end_labels

        with pytest.raises(ValueError, match="Unsupported interval"):
            window_end_labels(pd.DatetimeIndex([]), "1WEEK")


class TestLwuCarryOver:
    def _frame(self, seed=0, n=48):
        rng = np.random.default_rng(seed)
        req = rng.uniform(0, 100, n)
        req[5] = 0.0  # exercise the PotCUAW zero-req skip
        pump = rng.uniform(0, 40, n)
        div = rng.uniform(0, 40, n)
        other = rng.uniform(0, 5, n)
        # native shortage as the model writes it (signed, can go negative)
        short = req - pump - div - other
        pot = rng.uniform(0, 80, n)
        idx = pd.date_range("2000-11-01", periods=n, freq="MS")
        df = pd.DataFrame({
            "Ag. Area": rng.uniform(500, 600, n),
            "Potential CUAW": pot,
            "Ag. Supply Requirement (+)": req,
            "Ag. Pumping (-)": pump,
            "Ag. Deliveries (-)": div,
            "Ag. Other Inflow (-)": other,
            "Ag. Shortage (=)": short,
        }, index=idx)
        types = {"Ag. Area": 4, "Potential CUAW": 6,
                 "Ag. Supply Requirement (+)": 7, "Ag. Pumping (-)": 9,
                 "Ag. Deliveries (-)": 10, "Ag. Other Inflow (-)": 11,
                 "Ag. Shortage (=)": 8}
        return df, types

    def test_matches_fortran_reference(self):
        from iwfm_io._budget_agg import aggregate_frame, window_end_labels

        df, types = self._frame()
        labels, complete = window_end_labels(df.index, "1YEAR",
                                             native_unit="1MON")
        out = aggregate_frame(df, types, labels, complete)

        ref_req, ref_short, ref_pot = _dll_lwu_reference(
            list(np.asarray(labels)),
            df["Ag. Supply Requirement (+)"].to_numpy(),
            df["Ag. Shortage (=)"].to_numpy(),
            df["Ag. Pumping (-)"].to_numpy(),
            df["Ag. Deliveries (-)"].to_numpy(),
            df["Ag. Other Inflow (-)"].to_numpy(),
            df["Potential CUAW"].to_numpy(),
        )
        np.testing.assert_allclose(
            out["Ag. Supply Requirement (+)"].to_numpy(), ref_req)
        np.testing.assert_allclose(
            out["Ag. Shortage (=)"].to_numpy(), ref_short)
        np.testing.assert_allclose(out["Potential CUAW"].to_numpy(), ref_pot)
        # sums and last-value columns
        np.testing.assert_allclose(
            out["Ag. Pumping (-)"].to_numpy(),
            df["Ag. Pumping (-)"].groupby(np.asarray(labels)).sum().values)
        assert out["Ag. Area"].iloc[0] == df["Ag. Area"].iloc[11]

    def test_shortage_stays_signed(self):
        """Shortage aggregates signed — supply-adjustment overshoot makes
        monthly shortages negative and they must not be clipped."""
        from iwfm_io._budget_agg import aggregate_frame, window_end_labels

        idx = pd.date_range("2000-11-01", periods=12, freq="MS")
        req = np.full(12, 10.0)
        pump = np.full(12, 12.0)   # oversupplied -> negative shortage
        div = np.zeros(12)
        short = req - pump
        df = pd.DataFrame({"req": req, "pump": pump, "div": div,
                           "short": short}, index=idx)
        types = {"req": 7, "pump": 9, "div": 10, "short": 8}
        labels, complete = window_end_labels(df.index, "1YEAR",
                                             native_unit="1MON")
        out = aggregate_frame(df, types, labels, complete)
        # prev shortage always <= 0 -> no clipping; plain sums
        assert out["short"].iloc[0] == pytest.approx(-24.0)
        assert out["req"].iloc[0] == pytest.approx(120.0)

    def test_carry_over_reduces_requirement(self):
        """A positive previous shortage reduces the next step's modified
        requirement (the DLL clipping rule)."""
        from iwfm_io._budget_agg import aggregate_frame, window_end_labels

        idx = pd.date_range("2000-11-01", periods=12, freq="MS")
        req = np.r_[10.0, 10.0, np.zeros(10)]
        pump = np.r_[4.0, 10.0, np.zeros(10)]
        div = np.zeros(12)
        short = req - pump  # [6, 0, 0, ...]
        df = pd.DataFrame({"req": req, "pump": pump, "div": div,
                           "short": short}, index=idx)
        types = {"req": 7, "pump": 9, "div": 10, "short": 8}
        labels, complete = window_end_labels(df.index, "1YEAR",
                                             native_unit="1MON")
        out = aggregate_frame(df, types, labels, complete)
        # t=0: mod=10; t=1: prev raw short 6 > 0, req 10 > 6 -> mod=4
        assert out["req"].iloc[0] == pytest.approx(14.0)
        # shortage: (10-4) + (4-10) = 0
        assert out["short"].iloc[0] == pytest.approx(0.0)

    def test_single_step_windows_take_raw_values(self):
        from iwfm_io._budget_agg import aggregate_frame, window_end_labels

        df, types = self._frame(n=12)
        labels, complete = window_end_labels(df.index, "1MON",
                                             native_unit="1MON")
        out = aggregate_frame(df, types, labels, complete)
        # 1MON on monthly data is the identity — including PotCUAW at the
        # zero-req step (the Fortran single-step branch takes raw values)
        np.testing.assert_allclose(out.to_numpy(), df.to_numpy())


class TestAggregateBudgetDataTypes:
    def _frame(self):
        idx = pd.date_range("2000-11-01", periods=24, freq="MS")
        n = len(idx)
        rng = np.random.default_rng(1)
        req = rng.uniform(0, 100, n)
        pump = rng.uniform(0, 60, n)
        div = rng.uniform(0, 60, n)
        short = req - pump - div
        df = pd.DataFrame({
            "Ag. Area": np.full(n, 555.0),
            "Ag. Supply Requirement (+)": req,
            "Ag. Pumping (-)": pump,
            "Ag. Deliveries (-)": div,
            "Ag. Shortage (=)": short,
        }, index=idx)
        types = {"Ag. Area": 4, "Ag. Supply Requirement (+)": 7,
                 "Ag. Pumping (-)": 9, "Ag. Deliveries (-)": 10,
                 "Ag. Shortage (=)": 8}
        return df, types

    def test_area_last_not_sum(self):
        from iwfm_io import aggregate_budget

        df, types = self._frame()
        naive = aggregate_budget(df, period="WY")
        typed = aggregate_budget(df, period="WY", data_types=types)
        # name heuristic sums Area to ~12x; the type rule takes the last
        assert naive.loc[2001, "Ag. Area"] == pytest.approx(12 * 555.0)
        assert typed.loc[2001, "Ag. Area"] == pytest.approx(555.0)

    def test_lwu_carry_over_matches_engine(self):
        from iwfm_io import aggregate_budget
        from iwfm_io._budget_agg import aggregate_frame
        from iwfm_io._tokens import water_year

        df, types = self._frame()
        typed = aggregate_budget(df, period="WY", data_types=types)
        ref = aggregate_frame(df, types,
                              np.asarray(water_year(df.index)))
        np.testing.assert_allclose(typed.to_numpy(), ref.to_numpy())
        assert typed.index.name == "water_year"

    def test_missing_types_fall_back_to_heuristic(self):
        from iwfm_io import aggregate_budget

        df, _ = self._frame()
        df["Beginning Storage (+)"] = 100.0 + np.arange(len(df))
        # only Area typed; storage column falls back to first-of-period
        out = aggregate_budget(df, period="WY",
                               data_types={"Ag. Area": 4})
        assert out.loc[2001, "Ag. Area"] == pytest.approx(555.0)
        assert out.loc[2001, "Beginning Storage (+)"] == pytest.approx(100.0)

    def test_long_form_with_types(self):
        from iwfm_io import aggregate_budget

        df, types = self._frame()
        long_df = (df.reset_index(names="datetime")
                   .melt(id_vars="datetime", var_name="component",
                         value_name="value"))
        long_df["run"] = "baseline"
        long_df["location"] = "R1"

        out = aggregate_budget(long_df, period="WY", data_types=types)
        assert set(out.columns) == {"run", "location", "water_year",
                                    "component", "value"}
        piv = out.pivot_table(index="water_year", columns="component",
                              values="value")
        ref = aggregate_budget(df, period="WY", data_types=types)
        for col in ref.columns:
            assert piv[col].values == pytest.approx(ref[col].values)


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestSampleModel:
    def test_gw_budget_water_years(self):
        from iwfm_io import aggregate_budget, open_model, water_year

        gw = open_model(SAMPLE_MODEL).budget_df(
            "GW", location="ENTIRE MODEL AREA")
        ann = aggregate_budget(gw, period="WY")
        assert ann.index.tolist() == list(range(1991, 2001))

        wy91 = gw[water_year(gw.index) == 1991]
        assert len(wy91) == 365
        assert ann.loc[1991, "Beginning Storage (+)"] == \
            wy91["Beginning Storage (+)"].iloc[0]
        assert ann.loc[1991, "Deep Percolation (+)"] == pytest.approx(
            wy91["Deep Percolation (+)"].sum())
        # stock continuity across water years — only holds when storage
        # is first/last, never summed
        for wy in range(1992, 2001):
            assert ann.loc[wy, "Beginning Storage (+)"] == \
                ann.loc[wy - 1, "Ending Storage (-)"]
