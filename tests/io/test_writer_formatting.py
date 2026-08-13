"""Regression tests for fixed-width token formatting in IWFMFileWriter.

A float whose repr exceeds its column width (e.g. 105.09150000000001,
the repr of 70.061 * 1.5) used to overflow the layout and fuse with the
neighboring field, silently corrupting any file whose values were
modified programmatically.
"""

import pandas as pd
import pytest


class TestFormatToken:
    def test_long_repr_float_compacted(self):
        from iwfm_io._writer import _format_token

        v = 70.061 * 1.5                      # repr: 105.09150000000001
        s = _format_token(v, 12)
        assert len(s) <= 12
        assert float(s) == pytest.approx(v, rel=1e-8)

    def test_short_reprs_unchanged(self):
        from iwfm_io._writer import _format_token

        for v, expect in [(6.2e-06, "6.2e-06"), (57.2623, "57.2623"),
                          (0.0, "0.0"), (13, "13"), ("txt", "txt")]:
            assert _format_token(v, 12) == expect

    def test_nan_and_inf_pass_through(self):
        from iwfm_io._writer import _format_token

        assert _format_token(float("nan"), 12) == "nan"
        assert _format_token(float("inf"), 12) == "inf"


class TestDataLineSeparation:
    def test_overflowing_token_keeps_separator(self):
        from iwfm_io._writer import IWFMFileWriter

        w = IWFMFileWriter.__new__(IWFMFileWriter)
        w._lines = []
        w.write_data_line([1, 105.09150000000001e10, 2.0], [10, 12, 12])
        line = w._lines[0]
        assert len(line.split()) == 3          # three separate tokens
        assert float(line.split()[1]) == pytest.approx(1.0509150000000001e12)

    def test_modified_table_round_trips(self, tmp_path):
        from iwfm_io._writer import IWFMFileWriter

        df = pd.DataFrame({
            "node_id": [1, 2], "kh": [70.061 * 1.5, 3.0e-6],
        }).set_index("node_id")
        w = IWFMFileWriter.__new__(IWFMFileWriter)
        w._lines = []
        w.write_data_table(df, widths=[10, 14])
        back = pd.read_csv(
            pd.io.common.StringIO("\n".join(w._lines)),
            sep=r"\s+", header=None, names=["node_id", "kh"])
        assert back["kh"].tolist() == pytest.approx(df["kh"].tolist(),
                                                    rel=1e-8)
