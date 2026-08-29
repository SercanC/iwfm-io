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
