"""Tests for IWFM line classification and the slash conventions.

Ground truth is the IWFM Fortran source (Class_AsciiFileType.f90):
``f_cCommentIndicators = 'Cc*'`` — a ``/`` is NOT a comment marker.
A line whose first non-blank character is ``/`` is a data line with an
empty value (list-directed reads stop at the slash), which C2VSimFG
uses to disable optional entries: ``/  path  / HTPOUTFL``.
"""

from iwfm_io._tokens import is_comment, split_keyed_line, tokenize_data_line


class TestIsComment:
    def test_column1_comment_chars(self):
        assert is_comment("C  a comment")
        assert is_comment("c  a comment")
        assert is_comment("*  a comment")
        assert is_comment("")
        assert is_comment("   ")

    def test_slash_is_not_a_comment(self):
        # IWFM consumes these as (blank-value) data lines
        assert not is_comment("/  ..\\Results\\HeadTecPlot.out  / HTPOUTFL")
        assert not is_comment("/ DSSFL")

    def test_indented_lines_are_data(self):
        # comment test applies to raw column 1 only — crop codes like
        # CO/CN/CU/CS are data when indented
        assert not is_comment("    CO   / CCODE[ 2]  Cotton")
        assert not is_comment("    C2VSimFG value line")


class TestSplitKeyedLine:
    def test_normal_keyed_line(self):
        assert split_keyed_line("   441   / ND") == ("441", "ND")

    def test_date_slashes_preserved(self):
        v, k = split_keyed_line("  09/30/1990_24:00  / BDT")
        assert v == "09/30/1990_24:00"
        assert k == "BDT"

    def test_disabled_entry_with_old_value(self):
        # C2VSimFG style: leading slash blanks out the entry
        v, k = split_keyed_line(
            "/  ..\\Results\\C2VSimFG_GW_HeadTecPlot.out   / HTPOUTFL")
        assert v == ""
        assert k == "HTPOUTFL"

    def test_blank_entry_leading_slash(self):
        assert split_keyed_line("/ DSSFL") == ("", "DSSFL")

    def test_blank_entry_indented_slash(self):
        assert split_keyed_line("            / DSSFL") == ("", "DSSFL")


class TestTokenizeDataLine:
    def test_strips_trailing_comment(self):
        assert tokenize_data_line("  1  2.0  3  / note") == ["1", "2.0", "3"]

    def test_leading_slash_has_no_tokens(self):
        assert tokenize_data_line("/  1  2  3  / KEYWORD") == []
        assert tokenize_data_line("   / DSSFL") == []


class TestGluedSlashSeparator:
    """A ``/`` glued to a number is a separator (Fortran stops at it)."""

    def test_glued_keyword(self):
        assert split_keyed_line("441/ ND") == ("441", "ND")

    def test_glued_note_tokens(self):
        assert tokenize_data_line("1 2 3/ note") == ["1", "2", "3"]

    def test_date_slashes_untouched(self):
        assert split_keyed_line("09/30/1990_24:00 / BDT") == \
            ("09/30/1990_24:00", "BDT")

    def test_path_slashes_untouched(self):
        assert split_keyed_line("../Results/GW.hdf / GWBUDFL") == \
            ("../Results/GW.hdf", "GWBUDFL")
        assert split_keyed_line("v1.5/Simulation/x.dat / FL") == \
            ("v1.5/Simulation/x.dat", "FL")


class TestParseIwfmDate:
    def test_fullmatch_only(self):
        import pytest
        from iwfm_io._tokens import parse_iwfm_date
        for bad in ("xx10/01/1990_24:00", "10/01/1990_24:00zz",
                    "10/01/1990_24:00 10/02/1990_24:00", "10/01/1990",
                    "1990-10-01"):
            with pytest.raises(ValueError):
                parse_iwfm_date(bad)

    def test_surrounding_whitespace_ok(self):
        from datetime import datetime
        from iwfm_io._tokens import parse_iwfm_date
        assert parse_iwfm_date(" 10/01/1990_24:00 ") == datetime(1990, 10, 2)

    def test_24_with_minutes_rejected(self):
        import pytest
        from iwfm_io._tokens import parse_iwfm_date
        with pytest.raises(ValueError):
            parse_iwfm_date("10/01/1990_24:01")
        with pytest.raises(ValueError):
            parse_iwfm_date("10/01/1990_25:00")

    def test_is_iwfm_date(self):
        from iwfm_io._tokens import is_iwfm_date
        assert is_iwfm_date("09/30/4000_24:00")      # recurring sentinel
        assert is_iwfm_date("02/29/2000_12:30")
        assert not is_iwfm_date("02/30/1990_24:00")
        assert not is_iwfm_date("11/30/1990")
        assert not is_iwfm_date(19901001)


class TestRecurringYear:
    def test_threshold(self):
        from iwfm_io._tokens import is_recurring_year
        assert is_recurring_year(2500) and is_recurring_year(4000)
        assert not is_recurring_year(2100) and not is_recurring_year(2262)

    def test_year_2100_is_real_data(self):
        import pandas as pd
        from iwfm_io._tokens import expand_recurring
        df = pd.DataFrame({"date": ["09/30/2098_24:00", "09/30/2099_24:00",
                                    "09/30/2100_24:00"], "v": [1, 2, 3]})
        out = expand_recurring(df, "10/01/2097_24:00", "09/30/2100_24:00")
        assert len(out) == 3 and out["v"].tolist() == [1, 2, 3]

    def test_value_in_effect_at_begin_is_carried(self):
        import pandas as pd
        from iwfm_io._tokens import expand_recurring
        df = pd.DataFrame({"date": ["01/31/4000_24:00", "06/30/4000_24:00"],
                           "v": [10, 20]})
        out = expand_recurring(df, "03/01/1991_24:00", "05/31/1991_24:00")
        # begin is 03/02 00:00; the 01/31 value (10) is in effect then
        assert len(out) == 1
        assert out["date"].iloc[0] == pd.Timestamp(1991, 3, 2)
        assert out["v"].iloc[0] == 10
