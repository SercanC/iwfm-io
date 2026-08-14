"""Tests for stream gauge metadata and linking (iwfm_io.gauges)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"


def _metadata(**kw):
    base = {
        "gauge_id": ["g1", "g2", "g3"],
        "group": [1, 1, 2],
        "site_code": ["11447650", "11303500", "BND"],
    }
    base.update(kw)
    return pd.DataFrame(base)


def _specs():
    return [{"node_id": 5, "name": "11447650"},
            {"node_id": 12, "name": "11303500"},
            {"node_id": 3, "name": "unlinked_gage"}]


class TestValidateAndLink:
    def test_validate(self):
        from iwfm_io.gauges import validate_gauge_metadata

        assert validate_gauge_metadata(_metadata()) == []
        bad = _metadata()
        bad.loc[1, "gauge_id"] = "g1"
        assert any("duplicate gauge_id" in p
                   for p in validate_gauge_metadata(bad))

    def test_link_by_site_code(self):
        from iwfm_io.gauges import link_stream_hydrographs

        link = link_stream_hydrographs(_metadata(), _specs())
        s = link.summary()
        assert s["n_gauges_linked"] == 2
        assert link.unmatched_gauges == ["g3"]
        assert link.orphan_names == ["unlinked_gage"]
        row = link.links.set_index("gauge_id")
        assert row.loc["g1", "hyd_id"] == 1        # spec order = column order
        assert row.loc["g2", "node_id"] == 12

    def test_stem_matching_with_sep(self):
        from iwfm_io.gauges import link_stream_hydrographs

        specs = [{"node_id": 1, "name": "11447650%Q"}]
        link = link_stream_hydrographs(_metadata(), specs, name_sep="%")
        assert link.links["gauge_id"].tolist() == ["g1"]

    def test_duplicate_link_values_raise(self):
        from iwfm_io.gauges import link_stream_hydrographs

        md = _metadata(site_code=["same", "same", "x"])
        with pytest.raises(ValueError, match="duplicate value"):
            link_stream_hydrographs(md, _specs())

    def test_empty_specs_raise(self):
        from iwfm_io.gauges import link_stream_hydrographs

        with pytest.raises(ValueError, match="NOUTR"):
            link_stream_hydrographs(_metadata(), [])


class TestSeries:
    def _link(self):
        from iwfm_io.gauges import link_stream_hydrographs

        return link_stream_hydrographs(_metadata(), _specs())

    def test_extract_and_rename(self):
        from iwfm_io.gauges import stream_hydrograph_series

        idx = pd.date_range("2000-01-31", periods=3, freq="ME")
        out_frame = pd.DataFrame(
            {"col_1": 10.0, "col_2": 20.0, "col_3": 30.0}, index=idx)
        out = stream_hydrograph_series(self._link(), out_frame)
        assert list(out.columns) == ["g1", "g2"]
        assert out["g2"].values == pytest.approx([20.0] * 3)

    def test_iwfm_date_column_handled(self):
        from iwfm_io.gauges import stream_hydrograph_series

        out_frame = pd.DataFrame({
            "date": ["09/30/2000_24:00", "10/31/2000_24:00"],
            "col_1": [1.0, 2.0], "col_2": [3.0, 4.0], "col_3": [0.0, 0.0]})
        out = stream_hydrograph_series(self._link(), out_frame)
        assert out.index[0] == pd.Timestamp("2000-10-01")

    def test_ihsqr_both_needs_quantity(self):
        from iwfm_io.gauges import stream_hydrograph_series

        with pytest.raises(ValueError, match="both quantities"):
            stream_hydrograph_series(self._link(), pd.DataFrame(), ihsqr=2)

    def test_ihsqr_both_block_layout(self):
        from iwfm_io.gauges import stream_hydrograph_series

        # 3 specs -> flows in col_1..3, stages in col_4..6
        idx = pd.date_range("2000-01-31", periods=2, freq="ME")
        frame = pd.DataFrame(
            {f"col_{i}": float(i) for i in range(1, 7)}, index=idx)
        link = self._link()
        flows = stream_hydrograph_series(link, frame, ihsqr=2,
                                         quantity="flow")
        stages = stream_hydrograph_series(link, frame, ihsqr=2,
                                          quantity="stage")
        assert list(flows.columns) == ["g1", "g2"]
        assert flows.iloc[0].tolist() == [1.0, 2.0]
        assert stages.iloc[0].tolist() == [4.0, 5.0]

    def test_quantity_mismatch_raises(self):
        from iwfm_io.gauges import stream_hydrograph_series

        idx = pd.date_range("2000-01-31", periods=1, freq="ME")
        frame = pd.DataFrame({f"col_{i}": [1.0] for i in range(1, 4)},
                             index=idx)
        with pytest.raises(ValueError, match="prints flow only"):
            stream_hydrograph_series(self._link(), frame, ihsqr=0,
                                     quantity="stage")
        with pytest.raises(ValueError, match="'flow' or 'stage'"):
            stream_hydrograph_series(self._link(), frame, quantity="depth")

    def test_ambiguous_gauge_raises(self):
        from iwfm_io.gauges import (link_stream_hydrographs,
                                    stream_hydrograph_series)

        specs = [{"node_id": 1, "name": "11447650"},
                 {"node_id": 2, "name": "11447650"}]
        link = link_stream_hydrographs(_metadata(), specs)
        idx = pd.date_range("2000-01-31", periods=1, freq="ME")
        frame = pd.DataFrame({"col_1": [1.0], "col_2": [2.0]}, index=idx)
        with pytest.raises(ValueError, match="multiple hydrograph"):
            stream_hydrograph_series(link, frame)

    def test_missing_columns_raise(self):
        from iwfm_io.gauges import stream_hydrograph_series

        idx = pd.date_range("2000-01-31", periods=1, freq="ME")
        with pytest.raises(KeyError, match="missing"):
            stream_hydrograph_series(
                self._link(), pd.DataFrame({"col_1": [1.0]}, index=idx))


class TestSequences:
    def test_stream_node_order(self):
        from iwfm_io.gauges import (assign_gauge_sequences,
                                    link_stream_hydrographs)

        link = link_stream_hydrographs(_metadata(group=[1, 1, 1]), _specs())
        out = assign_gauge_sequences(_metadata(group=[1, 1, 1]), link)
        s = out.set_index("gauge_id")["seq"]
        # g1 at node 5 before g2 at node 12; unlinked g3 appended last
        assert s["g1"] == 1 and s["g2"] == 2 and s["g3"] == 3

    def test_fill_only_ledger(self):
        from iwfm_io.gauges import (assign_gauge_sequences,
                                    link_stream_hydrographs)

        link = link_stream_hydrographs(_metadata(group=[1, 1, 1]), _specs())
        md = _metadata(group=[1, 1, 1],
                       seq=pd.array([pd.NA, 7, pd.NA], dtype="Int64"))
        out = assign_gauge_sequences(md, link)
        s = out.set_index("gauge_id")["seq"]
        assert s["g2"] == 7 and s["g1"] == 8 and s["g3"] == 9

    def test_spatial_order_and_errors(self):
        from iwfm_io.gauges import assign_gauge_sequences

        md = _metadata(group=[1, 1, 1], y=[10.0, 30.0, 20.0])
        out = assign_gauge_sequences(md, order="north_to_south")
        assert out.set_index("gauge_id")["seq"].tolist() == [3, 1, 2]
        with pytest.raises(ValueError, match="requires link"):
            assign_gauge_sequences(_metadata(group=[1, 1, 1]))
        with pytest.raises(ValueError, match="order"):
            assign_gauge_sequences(md, order="spiral")


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestSampleModel:
    def test_link_and_extract_real_output(self):
        from iwfm_io import read_stream_main
        from iwfm_io.readers.text_output import read_hydrograph_out
        from iwfm_io.gauges import (link_stream_hydrographs,
                                    stream_hydrograph_series)

        sm = read_stream_main(
            SAMPLE_MODEL / "Simulation" / "Stream" / "Stream_MAIN.dat")
        specs = pd.DataFrame(sm.hydrograph_specs)
        md = pd.DataFrame({
            "gauge_id": [f"g{i}" for i in range(len(specs))],
            "site_code": specs["name"],
        })
        link = link_stream_hydrographs(md, sm)
        s = link.summary()
        assert s["n_unmatched_gauges"] == 0 and s["n_orphan_names"] == 0
        assert s["ihsqr"] == 2               # sample prints flow + stage
        assert link.n_specs == len(specs)

        frame = read_hydrograph_out(SAMPLE_MODEL / "Results" / "StrmHyd.out")
        raw = frame.drop(columns=["date"])
        assert raw.shape[1] == 2 * len(specs)      # two blocks
        flows = stream_hydrograph_series(link, frame, quantity="flow")
        stages = stream_hydrograph_series(link, frame, quantity="stage")
        assert flows.shape[1] == stages.shape[1] == len(specs)
        # block layout: flows are raw columns 1..N, stages N+1..2N
        assert np.allclose(flows.values, raw.iloc[:, :len(specs)].values,
                           equal_nan=True)
        assert np.allclose(stages.values, raw.iloc[:, len(specs):].values,
                           equal_nan=True)
        # flows are water-scale, stages are ft-scale
        assert flows.values.max() > 100 * stages.values.max()
