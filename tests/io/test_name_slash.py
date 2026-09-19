"""NAME fields are cut at the first ``/``, glued or not (issue #39).

IWFM reads name-bearing rows with
``StripTextUntilCharacter(ALine, '/')`` (``Class_Diversion.f90:220``),
which cuts the line at the first ``/`` whatever precedes it.  The
readers' keyword separator needs whitespace (or a digit) in front, so a
name like ``N/A`` used to survive as ``N/A`` where IWFM reads ``N`` --
and since the writers refuse a ``/`` inside a NAME (it would be
truncated on the next read), a plain read -> write of an untouched deck
raised.  DWR ships one: diversion 498 of C2VSimFG v1.5 is named ``N/A``.
"""

import pytest

from iwfm_io import read_diver_specs, write_diver_specs
from iwfm_io._tokens import split_name_notes

DIVER_SPECS = """C  diversion specs
        2   / NRDV
1  0  0  0.0  1  0.03  1  0.54  6  1  1  0.43  2  2  N/A
2  0  0  0.0  1  0.03  1  0.54  6  1  1  0.43  2  2  DIV_002 / a user comment
        0   / NGRP
"""


@pytest.mark.parametrize("text,note,expected", [
    ("N/A", "", ("N", "A")),
    ("N", "", ("N", "")),
    ("DIV_001", "a comment", ("DIV_001", "a comment")),
    ("N/A", "hello", ("N", "A / hello")),
    ("a/b/c", "", ("a", "b/c")),
    ("", "", ("", "")),
    (None, "", ("", "")),
])
def test_split_name_notes(text, note, expected):
    assert split_name_notes(text, note) == expected


@pytest.fixture
def spec_file(tmp_path):
    path = tmp_path / "DiverSpecs.dat"
    path.write_text(DIVER_SPECS)
    return path


def test_glued_slash_name_is_cut_like_iwfm(spec_file):
    ds = read_diver_specs(spec_file)
    assert ds.data["name"].tolist() == ["N", "DIV_002"]
    assert ds.data["notes"].tolist() == ["A", "a user comment"]


def test_glued_slash_name_round_trips(spec_file, tmp_path):
    ds = read_diver_specs(spec_file)
    out = tmp_path / "out.dat"
    write_diver_specs(ds, out)          # used to raise ValueError
    again = read_diver_specs(out)
    assert again.data["name"].tolist() == ds.data["name"].tolist()
    assert again.data["notes"].tolist() == ds.data["notes"].tolist()


def test_notes_may_contain_a_slash(spec_file, tmp_path):
    """A ``/`` in an annotation is invisible to IWFM, so it is allowed."""
    ds = read_diver_specs(spec_file)
    ds.data.loc[0, "notes"] = "see sheet 3 / rev B"
    out = tmp_path / "out.dat"
    write_diver_specs(ds, out)
    assert read_diver_specs(out).data.loc[0, "notes"] == "see sheet 3 / rev B"


def test_name_with_a_slash_still_refused(spec_file, tmp_path):
    """The writer guard stays: a NAME the model would truncate raises."""
    ds = read_diver_specs(spec_file)
    ds.data.loc[0, "name"] = "North/South"
    with pytest.raises(ValueError, match="contains '/'"):
        write_diver_specs(ds, tmp_path / "out.dat")
