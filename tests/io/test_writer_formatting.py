"""Regression tests for token formatting in IWFMFileWriter.

Cells are rendered by ``format_cell`` with the exact ``repr`` of a
float (no shrinking): a value whose text fills its column can never
fuse with the neighbouring field because ``write_data_line`` forces a
separating space instead.
"""

import pandas as pd
import pytest


class TestFormatCell:
    def test_long_repr_float_kept_exact(self):
        from iwfm_io._writer import format_cell

        v = 70.061 * 1.5                      # repr: 105.09150000000001
        assert format_cell(v) == repr(v)
        assert float(format_cell(v)) == v

    def test_short_reprs_unchanged(self):
        from iwfm_io._writer import format_cell

        for v, expect in [(6.2e-06, "6.2e-06"), (57.2623, "57.2623"),
                          (0.0, "0"), (13, "13"), ("txt", "txt")]:
            assert format_cell(v) == expect

    def test_nan_and_inf_raise(self):
        from iwfm_io._writer import format_cell

        with pytest.raises(ValueError, match="missing"):
            format_cell(float("nan"), what="kh")
        with pytest.raises(ValueError, match="non-finite"):
            format_cell(float("inf"), what="kh")
        assert format_cell(float("nan"), allow_blank=True) == ""


class TestTimeSeriesSpecTerminator:
    """The comment terminating the 5-parameter time-series spec block is
    load-bearing: without it the IWFM executables consume the first
    data/pathname line while resolving the (possibly blank) DSS
    filename, shifting the whole read (a recurring-year ET file then
    fails with "End-of-file reached")."""

    def _spec(self, dss_file=""):
        from iwfm_io.models.base import TimeSeriesSpec

        return TimeSeriesSpec(n_columns=3, factor=1.0, n_steps_update=1,
                              repeat_freq=0, dss_file=dss_file)

    def test_comment_follows_dssfl(self):
        from iwfm_io._tokens import is_comment
        from iwfm_io._writer import IWFMFileWriter

        for dss in ("", "TSDATA_IN.DSS"):
            w = IWFMFileWriter.__new__(IWFMFileWriter)
            w._lines = []
            w.write_timeseries_spec(self._spec(dss))
            dssfl_at = next(i for i, l in enumerate(w._lines)
                            if "DSSFL" in l)
            assert is_comment(w._lines[dssfl_at + 1]), \
                "spec block must end with a comment line"

    def test_written_et_file_keeps_terminator(self, tmp_path):
        from pathlib import Path

        from iwfm_io._tokens import is_comment

        sample = (Path(__file__).resolve().parents[2] / ".assets"
                  / "sample_model" / "Simulation" / "ET.dat")
        if not sample.is_file():
            pytest.skip("sample model not available")
        from iwfm_io import read_et, write_et

        out = tmp_path / "ET.dat"
        write_et(read_et(sample), out)
        lines = out.read_text().splitlines()
        dssfl_at = next(i for i, l in enumerate(lines)
                        if not is_comment(l) and "DSSFL" in l)
        assert is_comment(lines[dssfl_at + 1])


class TestDataLineSeparation:
    def test_overflowing_token_keeps_separator(self):
        from iwfm_io._writer import IWFMFileWriter

        w = IWFMFileWriter.__new__(IWFMFileWriter)
        w._lines = []
        w.write_data_line([1, 105.09150000000001e10, 2.0], [10, 12, 12])
        line = w._lines[0]
        assert len(line.split()) == 3          # three separate tokens
        assert float(line.split()[1]) == 1.0509150000000001e12

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
            sep=r"\s+", header=None, names=["node_id", "kh"],
            float_precision="round_trip")
        assert back["kh"].tolist() == df["kh"].tolist()   # exact repr
