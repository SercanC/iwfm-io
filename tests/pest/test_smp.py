"""Tests for the SMP bore-sample file reader/writer (iwfm_io.pest.smp)."""

import numpy as np
import pandas as pd
import pytest


def _sample_df():
    return pd.DataFrame({
        "site": ["w1", "w1", "gage_a"],
        "datetime": pd.to_datetime(
            ["2000-10-31", "2000-11-30", "2000-10-31"]),
        "value": [386.69, 385.59, 1234.5],
    })


class TestRoundTrip:
    def test_write_then_read(self, tmp_path):
        from iwfm_io.pest import read_smp, write_smp

        f = tmp_path / "obs.smp"
        write_smp(_sample_df(), f)
        back = read_smp(f)
        expected = _sample_df().sort_values(
            ["site", "datetime"]).reset_index(drop=True)
        expected["excluded"] = False
        pd.testing.assert_frame_equal(back, expected)

    def test_round_trip_mm_dd_yyyy(self, tmp_path):
        from iwfm_io.pest import read_smp, write_smp

        f = tmp_path / "obs.smp"
        write_smp(_sample_df(), f, date_format="mm/dd/yyyy")
        # 10/31, 11/30 -> second component > 12 -> auto-detects month-first
        back = read_smp(f)
        assert back["datetime"].dt.month.tolist() == [10, 10, 11]

    def test_written_layout(self, tmp_path):
        from iwfm_io.pest import write_smp

        f = tmp_path / "obs.smp"
        write_smp(_sample_df(), f)
        line = f.read_text().splitlines()[0]
        # site, dd/mm/yyyy, hh:mm:ss, value — whitespace-delimited
        parts = line.split()
        assert parts[0] == "gage_a"          # sorted: gage_a first
        assert parts[1] == "31/10/2000"
        assert parts[2] == "00:00:00"
        assert float(parts[3]) == pytest.approx(1234.5)

    def test_unsorted_preserved_when_sort_false(self, tmp_path):
        from iwfm_io.pest import read_smp, write_smp

        f = tmp_path / "obs.smp"
        write_smp(_sample_df(), f, sort=False)
        assert read_smp(f)["site"].tolist() == ["w1", "w1", "gage_a"]


class TestDateDetection:
    def test_day_first_detected(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  1.0\n")
        assert read_smp(f)["datetime"].iloc[0] == pd.Timestamp("2000-10-31")

    def test_month_first_detected(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  10/31/2000  00:00:00  1.0\n")
        assert read_smp(f)["datetime"].iloc[0] == pd.Timestamp("2000-10-31")

    def test_ambiguous_raises_without_explicit_format(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  03/04/2000  00:00:00  1.0\n")
        with pytest.raises(ValueError, match="auto-detect"):
            read_smp(f)
        # explicit format resolves it
        d = read_smp(f, date_format="mm/dd/yyyy")["datetime"].iloc[0]
        assert d == pd.Timestamp("2000-03-04")

    def test_bad_format_argument(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  1.0\n")
        with pytest.raises(ValueError, match="date_format"):
            read_smp(f, date_format="yyyy-mm-dd")


class TestValidation:
    def test_long_site_name_raises_and_can_be_allowed(self, tmp_path):
        from iwfm_io.pest import read_smp, write_smp

        df = _sample_df()
        df.loc[0, "site"] = "a_site_name_longer_than_ten"
        f = tmp_path / "obs.smp"
        with pytest.raises(ValueError, match="10 chars"):
            write_smp(df, f)
        write_smp(df, f, max_site_len=None)
        assert "a_site_name_longer_than_ten" in read_smp(f)["site"].tolist()

    def test_whitespace_site_raises(self, tmp_path):
        from iwfm_io.pest import write_smp

        df = _sample_df()
        df.loc[0, "site"] = "bad name"
        with pytest.raises(ValueError, match="whitespace"):
            write_smp(df, tmp_path / "obs.smp")

    def test_nan_values_dropped_on_write(self, tmp_path, caplog):
        from iwfm_io.pest import read_smp, write_smp

        df = _sample_df()
        df.loc[1, "value"] = np.nan
        f = tmp_path / "obs.smp"
        with caplog.at_level("WARNING"):
            write_smp(df, f)
        assert "dropping 1" in caplog.text
        assert len(read_smp(f)) == 2

    def test_non_numeric_value_read_as_nan(self, tmp_path, caplog):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  dry\n"
                     "w1  30/11/2000  00:00:00  2.5\n")
        with caplog.at_level("WARNING"):
            df = read_smp(f)
        assert np.isnan(df["value"].iloc[0])
        assert df["value"].iloc[1] == pytest.approx(2.5)
        assert "non-numeric" in caplog.text

    def test_malformed_line_raises(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  1.0\nw2  31/10/2000\n")
        with pytest.raises(ValueError, match="malformed"):
            read_smp(f)


class TestExclusionFlag:
    def test_flag_read(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  1.0  x\n"
                     "w1  30/11/2000  00:00:00  2.0\n"
                     "w1  31/12/2000  00:00:00  3.0  X\n")
        df = read_smp(f)
        assert df["excluded"].tolist() == [True, False, True]
        assert df["value"].tolist() == [1.0, 2.0, 3.0]

    def test_flag_round_trip(self, tmp_path):
        from iwfm_io.pest import read_smp, write_smp

        df = _sample_df()
        df["excluded"] = [True, False, False]
        f = tmp_path / "obs.smp"
        write_smp(df, f, sort=False)
        first = f.read_text().splitlines()[0]
        assert first.split()[-1] == "x"
        back = read_smp(f)
        assert back["excluded"].tolist() == [True, False, False]
        assert back["value"].tolist() == df["value"].tolist()

    def test_unknown_trailing_field_raises(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text("w1  31/10/2000  00:00:00  1.0  q\n")
        with pytest.raises(ValueError, match="trailing"):
            read_smp(f)


class TestFixedWidth:
    @staticmethod
    def _line(site, date, time, value, flag=""):
        return f"{site:<25}{date:<12}{time:<12}{value:>11.3f}{flag}\n"

    def test_site_names_with_spaces(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text(
            self._line("STATE WELL 12N03E22Q001M", "31/10/2000",
                       "00:00:00", 386.69)
            + self._line("STATE WELL 12N03E22Q001M", "30/11/2000",
                         "00:00:00", 385.59, "x"))
        df = read_smp(f, fixed_width=True)
        assert df["site"].tolist() == ["STATE WELL 12N03E22Q001M"] * 2
        assert df["value"].tolist() == [386.69, 385.59]
        assert df["excluded"].tolist() == [False, True]
        assert df["datetime"].iloc[0] == pd.Timestamp("2000-10-31")

    def test_month_first_explicit(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text(self._line("w1", "03/04/2000", "12:30:00", 1.0))
        df = read_smp(f, fixed_width=True, date_format="mm/dd/yyyy")
        assert df["datetime"].iloc[0] == pd.Timestamp("2000-03-04 12:30")

    def test_missing_field_raises(self, tmp_path):
        from iwfm_io.pest import read_smp

        f = tmp_path / "a.smp"
        f.write_text(self._line("w1", "31/10/2000", "00:00:00", 1.0)
                     + f"{'w2':<25}{'31/10/2000':<12}\n")
        with pytest.raises(ValueError, match="malformed"):
            read_smp(f, fixed_width=True)
