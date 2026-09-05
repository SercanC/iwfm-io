"""Stream main files that end at the stream-bed table (no INTRCTYPE /
evaporation section) — the C2VSimCG v4.2 layout — must read and
round-trip; and peeking past the last data line must not raise."""

import pandas as pd

from iwfm_io._parser import IWFMFileReader as IWFMReader
from iwfm_io.readers.stream import read_stream_main
from iwfm_io.writers.stream import write_stream_main

_FILE = """#4.2
C *** DO NOT DELETE ABOVE LINE ***
                                                / INFLOWFL
                                                / DIVSPECFL
                                                / BYPSPECFL
                                                / DIVFL
    Results\\STR_Budget.hdf                     / STRMRCHBUDFL
                                                / DIVDTLBUDFL
       0                                        / NOUTR
       2                                        / IHSQR
       0.000022957                              / FACTVROU
       AC-FT/MON                                / UNITVROU
       1                                        / FACTLTOU
       FEET                                     / UNITLTOU
                                                / STHYDOUTFL
    2                                           / NBUDR
    Results\\STR_Node.hdf                       / STNDBUDFL
1
2
    1.0                   / FACTK           1.0
    1mon                  / TUNITSK
    1.0                   / FACTL
  1  700 1304  0.513342 46.263756      /Reach1
  2  900 1315  0.418678 46.263756      /Reach1
C trailing comment, no INTRCTYPE line
"""


def test_reads_file_ending_at_bed_table(tmp_path):
    p = tmp_path / "Streams_MAIN.dat"
    p.write_text(_FILE)
    sm = read_stream_main(p)
    assert sm.config["intrctype"] is None
    assert sm.config["starfl"] is None
    assert sm.evaporation is None
    assert sm.reach_params.shape[0] == 2
    assert sm.reach_params["conductance"].tolist() == [0.513342, 0.418678]
    assert sm.reach_params["notes"].tolist() == ["Reach1", "Reach1"]


def test_round_trip_keeps_layout(tmp_path):
    p = tmp_path / "Streams_MAIN.dat"
    p.write_text(_FILE)
    sm = read_stream_main(p)
    out = tmp_path / "out.dat"
    write_stream_main(sm, out, base_dir=tmp_path)
    text = out.read_text()
    assert "INTRCTYPE" not in text
    sm2 = read_stream_main(out)
    pd.testing.assert_frame_equal(sm.reach_params, sm2.reach_params)
    assert sm2.config["intrctype"] is None


def test_peek_past_last_data_line_returns_none(tmp_path):
    p = tmp_path / "f.dat"
    p.write_text("1 / A\nC only a comment after this\n\n")
    r = IWFMReader(p)
    assert r.next_data_line().startswith("1")
    assert r.peek_data_line() is None
    assert r.peek_data_line() is None  # repeatable, position unchanged
