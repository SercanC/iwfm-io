"""Tests for the GW initial-conditions (restart) writer and the
HeadAll -> initial-heads helper (issue #35)."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from iwfm_io.readers.text_output import read_final_state_out, read_head_all_out
from iwfm_io.writers.groundwater import (
    initial_heads_from_head_all,
    write_gw_initial_conditions,
)
from tests.io.conftest import RESULTS_DIR


def _heads(n_nodes=3, n_layers=2):
    data = {"node_id": list(range(1, n_nodes + 1))}
    for lay in range(1, n_layers + 1):
        data[f"head_layer_{lay}"] = [100.0 * lay + i + 0.25 for i in range(n_nodes)]
    return pd.DataFrame(data)


def _head_all(n_nodes=3, n_layers=2, n_steps=2, generic=False):
    cols = {"date": [f"09/30/{2000 + t}_24:00" for t in range(n_steps)]}
    k = 0
    for lay in range(1, n_layers + 1):
        for nid in range(1, n_nodes + 1):
            k += 1
            name = f"col_{k}" if generic else f"node_{nid}_layer_{lay}"
            cols[name] = [1000.0 * t + 100.0 * lay + nid for t in range(n_steps)]
    return pd.DataFrame(cols)


class TestWriteInitialConditions:
    def test_round_trip_through_final_state_reader(self, tmp_output):
        heads = _heads(n_nodes=4, n_layers=3)
        out = tmp_output / "Restart.dat"
        write_gw_initial_conditions(out, heads, facthp=1.0)

        back = read_final_state_out(out)
        assert list(back.iloc[:, 0]) == [1, 2, 3, 4]
        assert back.shape == (4, 4)
        for lay in range(1, 4):
            assert back.iloc[:, lay].tolist() == pytest.approx(
                heads[f"head_layer_{lay}"].tolist())

    def test_layout_matches_iwfm_final_state_file(self, tmp_output):
        out = tmp_output / "Restart.dat"
        write_gw_initial_conditions(out, _heads(), facthp=1.0,
                                    header=["heads from init run"])
        text = out.read_text().splitlines()
        # banner + comment lines first, then FACTHP, then data
        assert text[0].startswith("C")
        assert any("heads from init run" in ln for ln in text[:4])
        fact = [ln for ln in text if "FACTHP" in ln]
        assert len(fact) == 1
        assert fact[0].split("/")[0].strip() == "1"
        # three dashed separators (what read_final_state_out keys on)
        assert sum(1 for ln in text if ln.startswith("C---")) == 3
        assert any("HP[1]" in ln and "HP[2]" in ln for ln in text)
        data = [ln for ln in text if ln.strip() and not ln.startswith("C")
                and "FACTHP" not in ln]
        assert len(data) == 3
        assert data[0].split()[0] == "1"

    def test_facthp_written_verbatim_values_not_rescaled(self, tmp_output):
        out = tmp_output / "Restart.dat"
        write_gw_initial_conditions(out, _heads(), facthp=0.3048)
        text = out.read_text()
        assert "0.3048" in text
        # raw values in the file are unscaled
        raw = [ln for ln in text.splitlines() if ln.strip().startswith("1 ")
               or ln.split()[:1] == ["1"]]
        assert "100.25" in raw[0]

    def test_accepts_final_state_reader_frame(self, tmp_output):
        src = RESULTS_DIR / "FinalGWHeads.out"
        if not src.exists():
            pytest.skip("sample model not available")
        final = read_final_state_out(src)
        out = tmp_output / "Restart.dat"
        write_gw_initial_conditions(out, final)
        back = read_final_state_out(out)
        pd.testing.assert_frame_equal(
            back.reset_index(drop=True).astype(float),
            final.reset_index(drop=True).astype(float),
            check_names=False, check_column_type=False, atol=1e-9)

    def test_rejects_nan_and_duplicates_and_empty(self, tmp_output):
        out = tmp_output / "Restart.dat"
        bad = _heads()
        bad.loc[1, "head_layer_2"] = float("nan")
        with pytest.raises(ValueError, match="NaN"):
            write_gw_initial_conditions(out, bad)
        dup = _heads()
        dup.loc[2, "node_id"] = 1
        with pytest.raises(ValueError, match="duplicate"):
            write_gw_initial_conditions(out, dup)
        with pytest.raises(ValueError, match="empty"):
            write_gw_initial_conditions(out, _heads().iloc[0:0])
        with pytest.raises(ValueError, match="layer"):
            write_gw_initial_conditions(out, _heads()[["node_id"]])
        assert not out.exists()


class TestReadHandWrittenRestart:
    """Restart files people write by hand (or older tools produce) have
    no dashed separators and a bare factor line — IWFM reads them fine,
    so the reader must too."""

    def test_bare_factor_no_dashes(self, tmp_output):
        text = (
            "C\n"
            "C ***** GROUNDWATER HEAD VALUES\n"
            "C*****************************************************\n"
            "C spun up from a 5-yr run\n"
            "C\n"
            " 1.00000000000000\n"
            "1\t495.5\t481.6\t427.6\t427.6\n"
            "2\t471.0\t497.0\t430.6\t430.6\n"
            "3\t456.6\t490.0\t427.0\t427.0\n"
        )
        p = tmp_output / "CVInitial_Restart.dat"
        p.write_text(text)
        df = read_final_state_out(p)
        assert df.shape == (3, 5)
        assert df.iloc[:, 0].tolist() == [1, 2, 3]
        assert df.iloc[0, 1:].tolist() == pytest.approx([495.5, 481.6, 427.6, 427.6])

    def test_bare_factor_is_applied(self, tmp_output):
        p = tmp_output / "r.dat"
        p.write_text("C x\n 2.0\n1 10.0 20.0\n2 30.0 40.0\n")
        df = read_final_state_out(p)
        assert df.iloc[:, 1].tolist() == [20.0, 60.0]

    def test_star_comments_and_keyword_factor(self, tmp_output):
        p = tmp_output / "r.dat"
        p.write_text("* banner\n     1.0     / FACTHP\n1 10.0\n2 30.0\n")
        df = read_final_state_out(p)
        assert df.shape == (2, 2)
        assert df.iloc[:, 1].tolist() == [10.0, 30.0]

    def test_writer_output_and_hand_written_agree(self, tmp_output):
        heads = _heads(n_nodes=3, n_layers=4)
        a = tmp_output / "a.dat"
        write_gw_initial_conditions(a, heads)
        b = tmp_output / "b.dat"
        rows = "\n".join(
            "%d\t%s" % (r.node_id, "\t".join(str(r[f"head_layer_{l}"])
                                             for l in range(1, 5)))
            for _, r in heads.iterrows())
        b.write_text("C hand written\n 1.0\n" + rows + "\n")
        da, db = read_final_state_out(a), read_final_state_out(b)
        assert da.shape == db.shape
        assert np.allclose(da.astype(float).values, db.astype(float).values)


class TestInitialHeadsFromHeadAll:
    def test_last_timestep_by_default(self):
        ic = initial_heads_from_head_all(_head_all(n_nodes=3, n_layers=2,
                                                   n_steps=3))
        assert list(ic.columns) == ["node_id", "head_layer_1", "head_layer_2"]
        assert ic["node_id"].tolist() == [1, 2, 3]
        # t=2 -> 2000 + 100*lay + nid
        assert ic["head_layer_1"].tolist() == [2101.0, 2102.0, 2103.0]
        assert ic["head_layer_2"].tolist() == [2201.0, 2202.0, 2203.0]

    def test_select_by_string_and_datetime(self):
        ha = _head_all(n_steps=3)
        by_str = initial_heads_from_head_all(ha, date="09/30/2001_24:00")
        assert by_str["head_layer_1"].tolist() == [1101.0, 1102.0, 1103.0]
        # 09/30/2001 24:00 == 10/01/2001 00:00 in IWFM's convention
        by_dt = initial_heads_from_head_all(ha, date=datetime(2001, 10, 1))
        pd.testing.assert_frame_equal(by_str, by_dt)
        by_ts = initial_heads_from_head_all(ha, date=pd.Timestamp("2001-10-01"))
        pd.testing.assert_frame_equal(by_str, by_ts)

    def test_missing_date_raises(self):
        with pytest.raises(ValueError, match="no HeadAll record"):
            initial_heads_from_head_all(_head_all(), date="01/31/1900_24:00")

    def test_generic_columns_raise(self):
        with pytest.raises(ValueError, match="node_<id>_layer_<L>"):
            initial_heads_from_head_all(_head_all(generic=True))

    def test_truncated_last_record_raises(self):
        ha = _head_all(n_steps=2)
        ha.loc[1, "node_3_layer_2"] = float("nan")
        with pytest.raises(ValueError, match="truncated"):
            initial_heads_from_head_all(ha)
        # an earlier, complete record is still usable
        ok = initial_heads_from_head_all(ha, date="09/30/2000_24:00")
        assert len(ok) == 3

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            initial_heads_from_head_all(pd.DataFrame())

    def test_sample_model_end_to_end(self, tmp_output):
        """Spin-up pattern: last HeadAll timestep -> restart file ->
        read back, and it agrees with IWFM's own FinalGWHeads.out."""
        ha_path = RESULTS_DIR / "GWHeadAll.out"
        fin_path = RESULTS_DIR / "FinalGWHeads.out"
        if not (ha_path.exists() and fin_path.exists()):
            pytest.skip("sample model not available")
        ha = read_head_all_out(ha_path)
        ic = initial_heads_from_head_all(ha)
        out = tmp_output / "Restart.dat"
        write_gw_initial_conditions(out, ic)
        back = read_final_state_out(out)
        final = read_final_state_out(fin_path)
        assert back.shape == final.shape
        assert back.iloc[:, 0].tolist() == final.iloc[:, 0].tolist()
        for j in range(1, back.shape[1]):
            # HeadAll prints 4 decimals; FinalGWHeads prints 6
            assert back.iloc[:, j].tolist() == pytest.approx(
                final.iloc[:, j].tolist(), abs=1e-3)
