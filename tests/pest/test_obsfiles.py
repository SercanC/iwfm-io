"""Tests for paired output/instruction writers (iwfm_io.pest.obsfiles)."""

import numpy as np
import pandas as pd
import pytest

NAMES = ["gwh_w1_20001031", "gwh_w1_20001130", "bud_dperc_sr01"]


class TestFixedLayout:
    def test_ins_and_output_agree_by_construction(self, tmp_path):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        spec.write_ins(tmp_path / "gw.ins")
        vals = pd.Series([386.69, -1.5e-3, 12345.678], index=NAMES)
        spec.write_output(vals, tmp_path / "gw.pout")

        ins = (tmp_path / "gw.ins").read_text().splitlines()
        assert ins[0] == "pif #"
        # column span in the ins matches where write_output puts values
        start, end = spec._value_span
        assert ins[1] == f"l1 [gwh_w1_20001031]{start}:{end}"
        line = (tmp_path / "gw.pout").read_text().splitlines()[0]
        assert float(line[start - 1:end]) == pytest.approx(386.69)

    def test_read_output_round_trip(self, tmp_path):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        vals = pd.Series([1.0, -2.5, 3.14159e10], index=NAMES)
        spec.write_output(vals, tmp_path / "o.pout")
        back = spec.read_output(tmp_path / "o.pout")
        assert back.values == pytest.approx(vals.values, rel=1e-7)

    def test_values_by_dict_and_order(self, tmp_path):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        spec.write_output({n: i for i, n in enumerate(NAMES)},
                          tmp_path / "a.pout")
        spec.write_output([0.0, 1.0, 2.0], tmp_path / "b.pout")
        assert ((tmp_path / "a.pout").read_text()
                == (tmp_path / "b.pout").read_text())

    def test_missing_value_raises(self):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        with pytest.raises(KeyError, match="missing"):
            spec._align(pd.Series({"gwh_w1_20001031": 1.0}))

    def test_nan_raises(self):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        with pytest.raises(ValueError, match="non-finite"):
            spec._align([1.0, np.nan, 2.0])

    def test_wrong_length_sequence_raises(self):
        from iwfm_io.pest import ObsFileSpec

        with pytest.raises(ValueError, match="expected 3"):
            ObsFileSpec(NAMES)._align([1.0, 2.0])

    def test_verify_round_trip_default_and_failure(self):
        from iwfm_io.pest import ObsFileSpec

        ObsFileSpec(NAMES).verify_round_trip()
        # a format too narrow to hold the value must be caught
        with pytest.raises(AssertionError, match="round-trip"):
            ObsFileSpec(NAMES, value_format="%6.1f").verify_round_trip(
                pd.Series([1e12, 1.0, 1.0], index=NAMES))


class TestCsvLayout:
    def test_csv_ins_and_round_trip(self, tmp_path):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES, layout="csv")
        spec.write_ins(tmp_path / "o.ins")
        ins = (tmp_path / "o.ins").read_text().splitlines()
        assert ins[1] == "l1 ~,~ !gwh_w1_20001031!"
        vals = pd.Series([1.5, -2.0, 3.0], index=NAMES)
        spec.write_output(vals, tmp_path / "o.csv")
        back = spec.read_output(tmp_path / "o.csv")
        assert back.values == pytest.approx(vals.values, rel=1e-7)
        spec.verify_round_trip(vals)


class TestValidationAndHelpers:
    def test_bad_names_rejected(self):
        from iwfm_io.pest import ObsFileSpec

        with pytest.raises(ValueError, match="invalid observation names"):
            ObsFileSpec(["ok_name", "bad name"])
        with pytest.raises(ValueError, match="non-empty"):
            ObsFileSpec([])
        with pytest.raises(ValueError, match="layout"):
            ObsFileSpec(NAMES, layout="tsv")

    def test_from_frame_and_obs_data(self):
        from iwfm_io.pest import ObsFileSpec

        df = pd.DataFrame({"obsnme": NAMES, "obsval": [1.0, 2.0, 3.0]})
        spec = ObsFileSpec.from_frame(df)
        od = spec.obs_data(values=df.set_index("obsnme")["obsval"],
                           weight=0.5, group="gwh01")
        assert list(od.columns) == ["obsnme", "obsval", "weight", "obgnme"]
        assert od["obsval"].tolist() == [1.0, 2.0, 3.0]
        assert (od["weight"] == 0.5).all()

    def test_wrong_line_count_on_read(self, tmp_path):
        from iwfm_io.pest import ObsFileSpec

        spec = ObsFileSpec(NAMES)
        (tmp_path / "o.pout").write_text("only_one_line 1.0\n")
        with pytest.raises(ValueError, match="expected 3"):
            spec.read_output(tmp_path / "o.pout")
