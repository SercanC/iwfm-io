"""Tests for the zone/tpl parameterization builder (iwfm_io.pest.params)."""

import pandas as pd
import pytest


def _spec(**kw):
    from iwfm_io.pest import ParamSpec

    base = dict(
        name="strk", values_file="mult_strk.csv",
        keys=pd.DataFrame({"reach_id": [1, 2, 3, 4],
                           "zone": ["north", "north", "south", "south"]}),
        zone_col="zone", transform="log", lower=0.01, upper=100.0)
    base.update(kw)
    return ParamSpec(**base)


class TestBuild:
    def test_zoned_parameters(self):
        from iwfm_io.pest import build_parameters

        b = build_parameters([_spec()])
        assert b.par_data["parnme"].tolist() == ["strk_north", "strk_south"]
        assert (b.par_data["partrans"] == "log").all()
        assert b.pargp_data["pargpnme"].tolist() == ["strk"]
        tpl = b.tpl_texts["mult_strk.csv.tpl"].splitlines()
        assert tpl[0] == "ptf ~"
        assert tpl[1] == "reach_id,value"
        assert "~" in tpl[2] and "strk_north" in tpl[2]
        vals = b.value_texts["mult_strk.csv"].splitlines()
        assert vals[1] == "1,1"

    def test_global_parameter(self):
        from iwfm_io.pest import ParamSpec, build_parameters

        b = build_parameters([ParamSpec(
            name="etfact", values_file="et.csv",
            keys=pd.DataFrame({"wba": [1, 2, 3]}),
            transform="none", lower=0.8, upper=1.05, initial=1.0)])
        assert b.par_data["parnme"].tolist() == ["etfact"]
        # all three rows carry the same parameter
        assert b.tpl_texts["et.csv.tpl"].count("etfact") == 3

    def test_tied_zones(self):
        from iwfm_io.pest import build_parameters

        b = build_parameters([_spec(tied={"south": "north"})])
        pd_ = b.par_data.set_index("parnme")
        assert pd_.loc["strk_south", "partrans"] == "tied"
        assert pd_.loc["strk_south", "partied"] == "strk_north"
        assert pd_.loc["strk_north", "partrans"] == "log"

    def test_tie_to_unknown_zone_raises(self):
        from iwfm_io.pest import build_parameters

        with pytest.raises(ValueError, match="unknown zone"):
            build_parameters([_spec(tied={"south": "east"})])

    def test_duplicate_names_and_files_rejected(self):
        from iwfm_io.pest import build_parameters

        with pytest.raises(ValueError, match="duplicate values_file"):
            build_parameters([_spec(), _spec()])
        with pytest.raises(ValueError, match="duplicate parameter"):
            build_parameters([_spec(),
                              _spec(values_file="other.csv")])

    def test_pargp_overrides(self):
        from iwfm_io.pest import build_parameters

        b = build_parameters([_spec()],
                             pargp_overrides={"strk": {"derinc": 0.05}})
        assert b.pargp_data.iloc[0]["derinc"] == 0.05
        with pytest.raises(ValueError, match="unknown group"):
            build_parameters([_spec()],
                             pargp_overrides={"nope": {"derinc": 1}})

    def test_spec_validation(self):
        from iwfm_io.pest import ParamSpec

        with pytest.raises(ValueError, match="transform"):
            _spec(transform="sqrt")
        with pytest.raises(ValueError, match="outside bounds"):
            _spec(initial=1000.0)
        with pytest.raises(ValueError, match="log transform"):
            _spec(lower=0.0)
        with pytest.raises(ValueError, match="zone_col"):
            _spec(zone_col="nope")
        with pytest.raises(ValueError, match="empty"):
            ParamSpec(name="x", values_file="v.csv",
                      keys=pd.DataFrame({"a": []}))


class TestRoundTrip:
    def test_write_verify_and_apply_integration(self, tmp_path):
        from iwfm_io.pest import build_parameters
        from iwfm_io.pest.apply import ApplyAction, _apply_one

        b = build_parameters([_spec()])
        b.write(tmp_path)
        assert (tmp_path / "mult_strk.csv.tpl").exists()
        b.verify()

        # the initial value file feeds the apply step directly
        vals = pd.read_csv(tmp_path / "mult_strk.csv")
        table = pd.DataFrame({"reach_id": [1, 2, 3, 4],
                              "conductance": [10.0, 20.0, 30.0, 40.0]})
        a = ApplyAction("stream_main", "f", "reach_params", "conductance",
                        "mult_strk.csv", key_cols=("reach_id",))
        out, n = _apply_one(table, a, vals)
        assert n == 4
        # initial multipliers are 1.0 -> unchanged
        assert out["conductance"].tolist() == [10.0, 20.0, 30.0, 40.0]

    def test_verify_catches_corruption(self):
        from iwfm_io.pest import build_parameters

        b = build_parameters([_spec()])
        key = "mult_strk.csv"
        b.value_texts[key] = b.value_texts[key].replace("1,1", "1,2", 1)
        with pytest.raises(AssertionError, match="reproduce"):
            b.verify()
