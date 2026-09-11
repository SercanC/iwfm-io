"""Tests for parameter write-back (iwfm_io.pest.apply)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SAMPLE_MODEL = Path(__file__).resolve().parents[2] / ".assets" / "sample_model"


class TestApplyAction:
    def test_validation(self):
        from iwfm_io.pest import ApplyAction

        with pytest.raises(ValueError, match="op"):
            ApplyAction("gw_main", "x", "t", "c", "v.csv", op="divide")
        with pytest.raises(ValueError, match="reader"):
            ApplyAction("rootzone", "x", "t", "c", "v.csv")


class TestApplyOne:
    def _df(self):
        return pd.DataFrame({
            "node_id": [1, 1, 2, 2], "layer": [1, 2, 1, 2],
            "kh": [10.0, 20.0, 30.0, 40.0]})

    def test_multiply_with_keys(self):
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        a = ApplyAction("gw_main", "f", "aquifer_params", "kh", "v.csv",
                        key_cols=("node_id", "layer"))
        vals = pd.DataFrame({"node_id": [1, 2], "layer": [1, 1],
                             "value": [2.0, 0.5]})
        out, n = _apply_one(self._df(), a, vals)
        assert n == 2
        assert out["kh"].tolist() == [20.0, 20.0, 15.0, 40.0]

    def test_replace_add_and_bounds(self):
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        vals = pd.DataFrame({"node_id": [1], "layer": [2], "value": [99.0]})
        a = ApplyAction("gw_main", "f", "t", "kh", "v.csv",
                        key_cols=("node_id", "layer"), op="replace",
                        upper=50.0)
        out, _ = _apply_one(self._df(), a, vals)
        assert out["kh"].tolist() == [10.0, 50.0, 30.0, 40.0]
        a2 = ApplyAction("gw_main", "f", "t", "kh", "v.csv",
                         key_cols=("node_id", "layer"), op="add")
        out2, _ = _apply_one(self._df(), a2, vals)
        assert out2["kh"].tolist()[1] == pytest.approx(119.0)

    def test_keyless_applies_to_all(self):
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        a = ApplyAction("gw_main", "f", "t", "kh", "v.csv", op="multiply")
        out, n = _apply_one(self._df(), a,
                            pd.DataFrame({"value": [10.0]}))
        assert n == 4
        assert out["kh"].tolist() == [100.0, 200.0, 300.0, 400.0]

    def test_unmatched_value_row_raises(self):
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        a = ApplyAction("gw_main", "f", "t", "kh", "v.csv",
                        key_cols=("node_id", "layer"))
        vals = pd.DataFrame({"node_id": [9], "layer": [1], "value": [2.0]})
        with pytest.raises(KeyError, match="match no"):
            _apply_one(self._df(), a, vals)

    def test_missing_column_raises(self):
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        a = ApplyAction("gw_main", "f", "t", "nope", "v.csv")
        with pytest.raises(KeyError, match="nope"):
            _apply_one(self._df(), a, pd.DataFrame({"value": [1.0]}))


class TestOverwriteFile:
    def test_round_trip(self, tmp_path):
        from iwfm_io.pest import read_gw_overwrite, write_gw_overwrite

        df = pd.DataFrame({
            "node": [1, 1, 2], "layer": [1, 2, 1],
            "pkh": [12.5, 3.75, 100.0], "ps": [1e-5, np.nan, 2e-4],
            "sy": [0.1, 0.2, 0.3],  # ignored (not an overwrite column)
        })
        f = tmp_path / "overwrite.dat"
        write_gw_overwrite(f, df, factors=[1, 1, 1, 1, 1, 2.0, 2.0],
                           time_unit="1DAY")
        back = read_gw_overwrite(f)
        assert len(back) == 3
        assert back.loc[0, "pkh"] == pytest.approx(12.5)
        assert back.loc[1, "ps"] == -1.0          # NaN -> keep original
        assert (back["pn"] == -1.0).all()          # column never given
        assert back.attrs["factors"][5] == pytest.approx(2.0)
        assert back.attrs["time_unit"] == "1DAY"

    def test_validation(self, tmp_path):
        from iwfm_io.pest import write_gw_overwrite

        with pytest.raises(ValueError, match="node"):
            write_gw_overwrite(tmp_path / "o.dat",
                               pd.DataFrame({"layer": [1]}))
        with pytest.raises(ValueError, match="7"):
            write_gw_overwrite(
                tmp_path / "o.dat",
                pd.DataFrame({"node": [1], "layer": [1]}), factors=[1, 2])


@pytest.mark.skipif(not SAMPLE_MODEL.is_dir(),
                    reason="sample model not available")
class TestApplyParametersEndToEnd:
    def test_multiply_stream_conductance_round_trip(self, tmp_path):
        import shutil

        from iwfm_io import read_stream_main
        from iwfm_io.pest import ApplyAction, apply_parameters

        src = SAMPLE_MODEL / "Simulation" / "Stream"
        run = tmp_path / "run"
        shutil.copytree(src, run / "Stream")
        sm_path = run / "Stream" / "Stream_MAIN.dat"

        before = read_stream_main(sm_path).reach_params
        pd.DataFrame({
            "stream_node_id": before["stream_node_id"].iloc[:4],
            "value": [2.0, 0.5, 3.0, 1.0],
        }).to_csv(run / "mult_cond.csv", index=False)

        log = apply_parameters(run, [ApplyAction(
            reader="stream_main",
            path=str(sm_path.relative_to(run)),
            table="reach_params", column="conductance",
            values_file="mult_cond.csv", key_cols=("stream_node_id",),
            lower=1e-6, base_dir=".")])
        assert log.iloc[0]["n_applied"] == 4
        assert (run / "apply_parameters_log.csv").exists()

        after = read_stream_main(sm_path).reach_params
        merged = before.merge(after, on="stream_node_id",
                              suffixes=("_b", "_a"))
        assert merged["conductance_a"].iloc[:4].values == pytest.approx(
            [2.0, 0.5, 3.0, 1.0] * merged["conductance_b"].iloc[:4].values,
            rel=1e-6)
        assert merged["conductance_a"].iloc[4:].values == pytest.approx(
            merged["conductance_b"].iloc[4:].values)
        # other columns untouched
        assert merged["bed_thickness_a"].values == pytest.approx(
            merged["bed_thickness_b"].values)
