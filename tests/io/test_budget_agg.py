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
