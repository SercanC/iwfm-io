"""Tests for the PEST observation-name codec (iwfm_io.pest.names)."""

import pandas as pd
import pytest


class TestEncodeDecode:
    def test_round_trip_dated(self):
        from iwfm_io.pest import encode_obs_name, decode_obs_name

        name = encode_obs_name("gwh", "w1234", "2000-10-31")
        assert name == "gwh_w1234_20001031"
        parts = decode_obs_name(name)
        assert parts.obs_type == "gwh"
        assert parts.location == "w1234"
        assert parts.time == pd.Timestamp("2000-10-31")

    def test_round_trip_dateless(self):
        from iwfm_io.pest import encode_obs_name, decode_obs_name

        name = encode_obs_name("bud", "dperc_sr01")
        assert name == "bud_dperc_sr01"
        parts = decode_obs_name(name)
        assert parts.obs_type == "bud"
        assert parts.location == "dperc_sr01"
        assert parts.time is None

    def test_location_with_separators(self):
        from iwfm_io.pest import encode_obs_name, decode_obs_name

        name = encode_obs_name("stf", "105_zcs014_13", "2000-10-31")
        parts = decode_obs_name(name)
        assert parts.location == "105_zcs014_13"
        assert parts.time == pd.Timestamp("2000-10-31")

    def test_lowercases(self):
        from iwfm_io.pest import encode_obs_name

        assert encode_obs_name("GWH", "W1234", "2000-10-31") == "gwh_w1234_20001031"

    def test_two_token_numeric_location_is_not_a_date(self):
        # "gwh_12345678": only one token after the type, so it is the
        # (mandatory) location, never a date.
        from iwfm_io.pest import decode_obs_name

        parts = decode_obs_name("gwh_12345678")
        assert parts.location == "12345678"
        assert parts.time is None

    def test_ambiguous_dateless_encode_raises(self):
        from iwfm_io.pest import encode_obs_name

        with pytest.raises(ValueError, match="ambiguous"):
            encode_obs_name("bud", "gage_20001031")

    def test_type_with_separator_raises(self):
        from iwfm_io.pest import encode_obs_name

        with pytest.raises(ValueError, match="separator"):
            encode_obs_name("gw_h", "w1", "2000-10-31")

    def test_empty_fields_raise(self):
        from iwfm_io.pest import encode_obs_name

        with pytest.raises(ValueError):
            encode_obs_name("", "w1")
        with pytest.raises(ValueError):
            encode_obs_name("gwh", "")

    def test_undecodable_raises(self):
        from iwfm_io.pest import decode_obs_name

        for bad in ("gwh", "", "gwh_", "_w1"):
            with pytest.raises(ValueError):
                decode_obs_name(bad)


class TestVectorized:
    def test_decode_many_matches_scalar(self):
        from iwfm_io.pest import decode_obs_name, decode_obs_names

        names = [
            "gwh_w1234_20001031",
            "stf_105_zcs014_13_20001031",
            "bud_dperc_sr01",
            "gwh_12345678",
        ]
        df = decode_obs_names(names)
        assert list(df.index) == names
        for name in names:
            scalar = decode_obs_name(name)
            row = df.loc[name]
            assert row["obs_type"] == scalar.obs_type
            assert row["location"] == scalar.location
            if scalar.time is None:
                assert pd.isnull(row["time"])
            else:
                assert row["time"] == scalar.time

    def test_decode_many_bad_name_raises(self):
        from iwfm_io.pest import decode_obs_names

        with pytest.raises(ValueError, match="cannot decode"):
            decode_obs_names(["gwh_w1_20001031", "nounderscore"])

    def test_encode_many_broadcasts(self):
        from iwfm_io.pest import encode_obs_names

        out = encode_obs_names(
            "gwh", ["w1", "w2"], ["2000-10-31", "2000-11-30"]
        )
        assert out.tolist() == ["gwh_w1_20001031", "gwh_w2_20001130"]

    def test_encode_many_dateless(self):
        from iwfm_io.pest import encode_obs_names

        out = encode_obs_names("bud", ["sr01", "sr02"])
        assert out.tolist() == ["bud_sr01", "bud_sr02"]

    def test_round_trip_scale(self):
        from iwfm_io.pest import decode_obs_names, encode_obs_names

        n = 5000
        locs = [f"w{i:04d}" for i in range(n)]
        dates = pd.date_range("1975-10-31", periods=1, freq="ME").repeat(n)
        names = encode_obs_names("gwh", locs, dates)
        df = decode_obs_names(names)
        assert (df["location"].values == locs).all()
        assert (df["obs_type"] == "gwh").all()


class TestSchemeRegistry:
    def test_register_and_use_custom_scheme(self):
        # A compact legacy scheme in the style of existing IWFM/CalSim IES
        # projects: "gwh010001_001031" = 3-char type + group/well digits +
        # 2-digit-year date, no separator between type and location.
        from iwfm_io.pest import (
            NameScheme,
            ObsName,
            decode_obs_name,
            encode_obs_name,
            register_scheme,
        )

        class LegacyHeadScheme(NameScheme):
            def encode(self, parts):
                stamp = parts.time.strftime("%y%m%d")
                return f"{parts.obs_type}{parts.location}_{stamp}".lower()

            def decode(self, name):
                head, stamp = name.lower().split("_")
                return ObsName(
                    head[:3], head[3:], pd.to_datetime(stamp, format="%y%m%d")
                )

        register_scheme("legacy-head", LegacyHeadScheme())
        name = encode_obs_name("GWH", "010001", "2000-10-31", scheme="legacy-head")
        assert name == "gwh010001_001031"
        parts = decode_obs_name(name, scheme="legacy-head")
        assert parts.obs_type == "gwh"
        assert parts.location == "010001"
        assert parts.time == pd.Timestamp("2000-10-31")

    def test_unknown_scheme_raises(self):
        from iwfm_io.pest import decode_obs_name

        with pytest.raises(KeyError, match="unknown name scheme"):
            decode_obs_name("gwh_w1_20001031", scheme="nope")

    def test_register_rejects_non_scheme(self):
        from iwfm_io.pest import register_scheme

        with pytest.raises(TypeError):
            register_scheme("bad", object())

    def test_scheme_instance_accepted_directly(self):
        from iwfm_io.pest import StandardScheme, decode_obs_name

        scheme = StandardScheme(date_format="%y%m%d")
        # 2-digit-year date tokens are only 6 digits -> tail reads as location
        parts = decode_obs_name("gwh_w1_001031_19", scheme=scheme)
        assert parts.time is None  # 8-digit rule not met
        assert parts.location == "w1_001031_19"


class TestValidation:
    def test_clean_names_pass(self):
        from iwfm_io.pest import validate_obs_names

        assert validate_obs_names(["gwh_w1_20001031", "bud_sr01"]) == []

    def test_case_insensitive_duplicates(self):
        from iwfm_io.pest import validate_obs_names

        problems = validate_obs_names(["gwh_w1", "GWH_W1"])
        assert len(problems) == 1
        assert "duplicate" in problems[0]

    def test_length_limit(self):
        from iwfm_io.pest import validate_obs_names

        long = "gwh_" + "x" * 30
        assert validate_obs_names([long], max_len=20)
        assert validate_obs_names([long], max_len=200) == []

    def test_invalid_characters(self):
        from iwfm_io.pest import validate_obs_names

        problems = validate_obs_names(["gwh w1", "gwh_w2"])
        assert len(problems) == 1
        assert "invalid characters" in problems[0]


class TestLazySubpackage:
    def test_top_level_lazy_import(self):
        import iwfm_io

        assert hasattr(iwfm_io.pest, "encode_obs_name")
