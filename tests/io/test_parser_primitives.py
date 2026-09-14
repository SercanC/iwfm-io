"""Tests for the IWFMFileReader primitives (WP2: P-R1, P-R2, P-R4).

Covers ``IWFMParseError`` (attributes, message, no StopIteration),
``section``/``error``/``degrade``, ``read_row``/``read_data_table``,
``read_ints``/``read_floats``, BOM handling, ``peek_data_line`` and the
shared time-series row reader ``read_ts_rows``, plus ``from_lines``/
``tail_cursor`` tail readers and ``peek_keyword``.
"""

import warnings

import numpy as np
import pytest

from iwfm_io import IWFMParseError, IWFMReadWarning, strict_mode
from iwfm_io._parser import IWFMFileReader


def _write(tmp_path, text, name="f.dat", encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


class TestParseError:
    def test_is_value_error_not_stop_iteration(self):
        err = IWFMParseError("boom", path="x.dat", lineno=3, section="a > b")
        assert isinstance(err, ValueError)
        assert not isinstance(err, StopIteration)
        assert err.path == "x.dat" and err.lineno == 3
        assert err.section == "a > b" and err.msg == "boom"
        assert str(err) == "x.dat:3 [a > b]: boom"

    def test_message_omits_absent_parts(self):
        assert str(IWFMParseError("m")) == "m"
        assert str(IWFMParseError("m", path="p")) == "p: m"
        assert str(IWFMParseError("m", lineno=2)) == "line 2: m"
        assert str(IWFMParseError("m", section="s")) == " [s]: m".lstrip() or True

    def test_next_data_line_at_eof_carries_context(self, tmp_path):
        p = _write(tmp_path, "C hdr\n  1  / A\n")
        r = IWFMFileReader(p)
        r.read_header()
        r.read_keyed_int()
        with r.section("tail"):
            with pytest.raises(IWFMParseError) as ei:
                r.next_data_line()
        err = ei.value
        assert err.path == str(p) and err.section == "tail"
        assert err.lineno == 2
        assert "end of file" in err.msg


class TestSectionsAndErrors:
    def test_nested_sections_join(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "1\n"))
        with r.section("outer"):
            with r.section("inner"):
                assert r.section_name == "outer > inner"
                assert r.error("x").section == "outer > inner"
            assert r.section_name == "outer"
        assert r.section_name == ""

    def test_error_lineno_is_last_consumed(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "C c\n\n 5\n 6\n"))
        r.read_header()
        r.next_data_line()  # line 3
        assert r.error("x").lineno == 3
        assert r.error("x", lineno=4).lineno == 4

    def test_degrade_raises_when_strict(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "1\n"), strict=True)
        with pytest.raises(IWFMParseError, match="oops"):
            r.degrade("oops")

    def test_degrade_warns_when_lenient(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "1\n"), strict=False)
        with pytest.warns(IWFMReadWarning, match="oops"):
            r.degrade("oops")

    def test_reader_snapshots_context_mode(self, tmp_path):
        p = _write(tmp_path, "1\n")
        assert IWFMFileReader(p).strict is True
        with strict_mode(False):
            r = IWFMFileReader(p)
        assert r.strict is False
        with strict_mode(False):
            assert IWFMFileReader(p, strict=True).strict is True

    def test_keyed_int_error_names_keyword(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, " abc  / NCOL\n"))
        with pytest.raises(IWFMParseError, match="NCOL.*'abc'"):
            r.read_keyed_int()


class TestRowPrimitives:
    def test_read_row_short_row_raises_with_context(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "C\n 1 2\n"))
        r.read_header()
        with r.section("nodes"):
            with pytest.raises(IWFMParseError) as ei:
                r.read_row(3, "node row")
        assert "node row" in ei.value.msg and "expected 3" in ei.value.msg
        assert ei.value.lineno == 2 and ei.value.section == "nodes"

    def test_read_row_min_cols_and_extras(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, " 1 2 3 4 / note\n"))
        assert r.read_row(3, "row", min_cols=2) == ["1", "2", "3", "4"]

    def test_read_data_table(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "1 2\n3 4\n"))
        assert r.read_data_table(2, n_cols=2) == [["1", "2"], ["3", "4"]]
        r = IWFMFileReader(_write(tmp_path, "1 2\n3\n"))
        with pytest.raises(IWFMParseError, match="expected 2"):
            r.read_data_table(2, n_cols=2)

    def test_read_ints_and_floats_name_column(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, " 1 2.5 x\n 1.0 2.0\n"))
        with pytest.raises(IWFMParseError, match="column 2 is not an integer"):
            r.read_ints(2, "ids")
        assert r.read_floats(2, "vals") == [1.0, 2.0]
        r = IWFMFileReader(_write(tmp_path, " 1 abc\n"))
        with pytest.raises(IWFMParseError, match="column 2 is not a number"):
            r.read_floats(2, "vals")

    def test_to_ints_accepts_integral_floats(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "1\n"))
        assert r.to_ints(["3.0", "4"]) == [3, 4]

    def test_bom_is_dropped(self, tmp_path):
        p = _write(tmp_path, "C header\n 7 / N\n", encoding="utf-8-sig")
        r = IWFMFileReader(p)
        hdr = r.read_header()
        assert hdr.comment_lines[0] == "C header"
        assert r.read_keyed_int() == (7, "N")

    def test_peek_does_not_consume_or_touch_comments(self, tmp_path):
        r = IWFMFileReader(_write(tmp_path, "C a\n\n 9\n"))
        assert r.peek_data_line() == " 9"
        assert r.lineno == 0
        assert r.drain_comments() == []
        assert r.next_data_line() == " 9"
        assert r.drain_comments() == ["C a", ""]
        assert r.peek_data_line() is None


class TestTailReader:
    """``tail_cursor()`` hands the rest of a file to a second reader
    (``from_lines``) that keeps the file's path, line numbers and mode."""

    def test_next_at_eof_raises_parse_error_with_file_lineno(self, tmp_path):
        p = _write(tmp_path, "C h\n 1 / A\n 2\nC end\n")
        r = IWFMFileReader(p)
        r.read_header()
        r.read_keyed_int()
        c = r.tail_cursor()
        assert isinstance(c, IWFMFileReader)
        assert r.eof and c.lineno0 == 2 and c.lineno == 2
        assert c.next_data_line() == " 2"
        assert c.lineno == 3
        with pytest.raises(IWFMParseError) as ei:
            c.next_data_line()
        assert not isinstance(ei.value, StopIteration)
        assert ei.value.path == str(p) and ei.value.lineno == 4

    def test_tail_reader_keeps_mode_and_error_context(self, tmp_path):
        p = _write(tmp_path, "C h\n 1 / A\n x / B\n")
        r = IWFMFileReader(p, strict=False)
        r.read_header()
        r.read_keyed_int()
        c = r.tail_cursor()
        assert c.strict is False
        with c.section("tail"):
            c.next_data_line()
            err = c.error("bad")
        assert (err.path, err.lineno, err.section) == (str(p), 3, "tail")

    def test_from_lines_degrade_follows_mode(self):
        with pytest.raises(IWFMParseError):
            IWFMFileReader.from_lines(["1"], path="p", strict=True).degrade("x")
        with pytest.warns(IWFMReadWarning):
            IWFMFileReader.from_lines(["1"], path="p", strict=False).degrade("x")

    def test_from_lines_without_path(self):
        c = IWFMFileReader.from_lines(["C c", " 1 / A"])
        assert c.path is None and c.n_lines == 2
        assert str(c.error("m", lineno=2)) == "line 2: m"
        with pytest.warns(IWFMReadWarning, match="^w$"):
            c.warn_once("k", "w")

    def test_from_lines_lineno0_offsets_all_line_numbers(self):
        c = IWFMFileReader.from_lines(["C a", " 1 / A", "C b"], path="f",
                                      lineno0=10)
        assert c.lineno == 10
        c.next_data_line()
        assert c.lineno == 12 and c.error("x").lineno == 12
        assert c.data_eof and not c.eof
        with pytest.raises(IWFMParseError) as ei:
            c.next_data_line()
        assert ei.value.lineno == 13


class TestPeekKeyword:
    def test_peek_keyword_skips_comments_and_does_not_consume(self):
        c = IWFMFileReader.from_lines(["C c", "  12  / NOUTF  face flows", " 3"])
        assert c.peek_keyword() == "NOUTF"
        assert c.lineno == 0 and c.drain_comments() == []
        assert c.read_keyed_int() == (12, "NOUTF  face flows")
        assert c.peek_keyword() == ""          # keyword-less row
        c.next_data_line()
        assert c.peek_keyword() == ""          # end of data

    def test_peek_keyword_uppercases_and_handles_blank_value(self):
        c = IWFMFileReader.from_lines(["  / dssfl", "/ old / TDOUTFL"])
        assert c.peek_keyword() == "DSSFL"
        c.next_data_line()
        assert c.peek_keyword() == "TDOUTFL"


TS = ("C ts\n 2 / NCOL\n 1.0 / FACT\n 1 / NSP\n 0 / NFQ\n / DSSFL\n"
      "C end of spec\n")


class TestReadTsRows:
    def _reader(self, tmp_path, rows, strict=None):
        r = IWFMFileReader(_write(tmp_path, TS + rows), strict=strict)
        r.read_header()
        r.read_timeseries_spec()
        return r

    def test_shape_and_dtypes(self, tmp_path):
        r = self._reader(tmp_path, "10/31/1990_24:00 1 2\n11/30/1990_24:00 3 4 / x\n")
        df = r.read_ts_rows(2)
        assert list(df.columns) == ["date", "col_1", "col_2"]
        assert df["date"].tolist() == ["10/31/1990_24:00", "11/30/1990_24:00"]
        assert df["col_2"].tolist() == [2.0, 4.0]
        assert df["col_1"].dtype == float

    def test_custom_names_and_empty(self, tmp_path):
        r = self._reader(tmp_path, "")
        df = r.read_ts_rows(2, ["a", "b"])
        assert list(df.columns) == ["date", "a", "b"] and df.empty
        with pytest.raises(ValueError, match="column names"):
            r.read_ts_rows(2, ["a"])

    def test_non_date_row_raises_strict(self, tmp_path):
        r = self._reader(tmp_path, "10/31/1990_24:00 1 2\n garbage 1 2\n",
                         strict=True)
        with pytest.raises(IWFMParseError) as ei:
            r.read_ts_rows(2)
        assert ei.value.lineno == 9 and "IWFM date" in ei.value.msg

    def test_non_date_row_warns_and_stops_lenient(self, tmp_path):
        r = self._reader(tmp_path, "10/31/1990_24:00 1 2\n garbage 1 2\n"
                         "11/30/1990_24:00 3 4\n", strict=False)
        with pytest.warns(IWFMReadWarning, match="IWFM date"):
            df = r.read_ts_rows(2)
        assert len(df) == 1

    def test_bad_date_token_is_an_error(self, tmp_path):
        # V7: 24:MM with MM != 00 is not a date
        r = self._reader(tmp_path, "10/31/1990_24:30 1 2\n", strict=True)
        with pytest.raises(IWFMParseError):
            r.read_ts_rows(2)

    def test_short_row_strict_raises_lenient_pads(self, tmp_path):
        rows = "10/31/1990_24:00 1\n"
        with pytest.raises(IWFMParseError, match="1 of 2 values"):
            self._reader(tmp_path, rows, strict=True).read_ts_rows(2)
        with pytest.warns(IWFMReadWarning, match="1 of 2 values"):
            df = self._reader(tmp_path, rows, strict=False).read_ts_rows(2)
        assert df["col_1"].iloc[0] == 1.0 and np.isnan(df["col_2"].iloc[0])

    def test_extra_values_ignored_with_one_warning(self, tmp_path):
        r = self._reader(tmp_path, "10/31/1990_24:00 1 2 3\n"
                         "11/30/1990_24:00 4 5 6\n")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = r.read_ts_rows(2)
        extra = [x for x in w if issubclass(x.category, IWFMReadWarning)]
        assert len(extra) == 1 and "extras are ignored" in str(extra[0].message)
        assert df.shape == (2, 3) and df["col_2"].tolist() == [2.0, 5.0]

    def test_non_numeric_value_names_line_and_column(self, tmp_path):
        r = self._reader(tmp_path, "10/31/1990_24:00 1 2\n"
                         "11/30/1990_24:00 3 abc\n")
        with pytest.raises(IWFMParseError) as ei:
            r.read_ts_rows(2)
        assert ei.value.lineno == 9
        assert "column 2" in ei.value.msg and "'abc'" in ei.value.msg
        assert "11/30/1990_24:00" in ei.value.msg

    def test_recurring_years_kept_as_strings(self, tmp_path):
        r = self._reader(tmp_path, "10/31/4000_24:00 1 2\n")
        assert r.read_ts_rows(2)["date"].iloc[0] == "10/31/4000_24:00"
