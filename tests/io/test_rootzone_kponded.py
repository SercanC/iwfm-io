"""v4.1/v4.11 soil tables may omit the trailing KPonded column (issue #37).

IWFM decides the width of the root-zone soil table from its FIRST row: it
tries to read 14 reals out of that line and, when that fails, reads the
whole table 13 columns wide (``RootZone_v411.f90``, "Backward
compatibility: Check if the user entered KPonded values at all"; the same
block is in ``RootZone_v41.f90``, and both are unchanged between the
2015.3.1443 and 2025.0.1747 sources).  A 13-column deck is therefore
first-class v4.11 input, not a legacy accident -- the reporter's YGM
model (v10.001.003, 2026-01) is one, and it runs under IWFM 2015.3.1443.

An absent KPonded means "same as K", exactly as the ``-1.0`` sentinel does
in the 14-column form::

    IF (nDataCols .EQ. 13) THEN
        RootZone%HydCondPonded(iElem) = pSoilsData(iElem)%HydCond
    ELSE
        IF (DummyRealArray(indxElem,14) .EQ. -1.0) THEN
            RootZone%HydCondPonded(iElem) = pSoilsData(iElem)%HydCond
        ...

Before the fix a 13-column deck raised ``IWFMParseError`` at the first
soil row in strict mode, and in lenient mode warned once per element and
returned ``k_ponded`` all-NaN.
"""
from __future__ import annotations

import math

import pytest

import iwfm_io
from iwfm_io import IWFMParseError, read_rootzone_main, write_rootzone_main

# Keyword order of a v4.11 root-zone main (as in C2VSimFG v1.5).
_KEYWORDS = [
    ("0.00000001", "RZCONV"), ("2000", "RZITERMX"),
    ("0.083333", "FACTCN"), ("1", "GWUPTK"),
    ("", "AGNPFL"), ("", "PFL"), ("", "URBFL"), ("", "NVRVFL"),
    ("", "RFFL"), ("", "RUFL"), ("", "IPFL"), ("", "MSRCFL"),
    ("", "AGWDFL"), ("", "LWUBUDFL"), ("", "RZBUDFL"),
    ("", "ZLWUBUDFL"), ("", "ZRZBUDFL"), ("", "FNSMFL"),
    ("1.0", "FACTK"), ("1.0", "FACTCPRISE"), ("1DAY", "TUNITK"),
]

# element_id wp fc tn lambda k rhc cap_rise irne frne imsrc typdest dest
_SOIL_13 = [
    "1   0.1518  0.2537  0.3356  0.3506  0.0165  1  0.0  1  1.0  0  0  0",
    "2   0.1625  0.2641  0.3372  0.3309  0.0087  1  0.0  1  1.0  0  1  7",
    "3   0.1049  0.3150  0.3393  0.4042  0.0213  1  0.0  1  1.0  0  2  3",
]
# ... the same rows with a 14th value (KPonded); -1.0 means "same as K"
_KPONDED = ["0.0055", "-1.0", "0.0100"]


def _deck(rows: list[str]) -> str:
    lines = ["#4.11", "C*** DO NOT DELETE ABOVE LINE ***", "C"]
    lines += [f"     {value:<40s} / {kw}" for value, kw in _KEYWORDS]
    lines.append("C  Soil, Precipitation and Runoff Destination Parameters")
    lines += [f"     {row}" for row in rows]
    return "\n".join(lines) + "\n"


def _write(tmp_path, rows, name="RootZone_MAIN.dat"):
    path = tmp_path / name
    path.write_text(_deck(rows), encoding="utf-8")
    return path


@pytest.fixture
def deck_13(tmp_path):
    return _write(tmp_path, _SOIL_13)


@pytest.fixture
def deck_14(tmp_path):
    rows = [f"{row}  {kp}" for row, kp in zip(_SOIL_13, _KPONDED)]
    return _write(tmp_path, rows, name="RootZone_MAIN_14.dat")


# --------------------------------------------------------------- reading
def test_13_column_deck_reads_strictly(deck_13, recwarn):
    """The reported failure: strict mode must accept a 13-column table."""
    rz = read_rootzone_main(deck_13)

    assert len(rz.element_params) == 3
    # The column is absent in the file, so it is absent here too.
    assert "k_ponded" not in rz.element_params.columns
    assert list(rz.element_params.columns)[-1] == "dest"
    assert rz.element_params["dest"].tolist() == [0, 7, 3]
    assert [w for w in recwarn.list
            if issubclass(w.category, iwfm_io.IWFMReadWarning)] == []


def test_13_column_deck_keeps_the_rest_of_the_file(deck_13):
    """The probe must not disturb anything before the soil table."""
    rz = read_rootzone_main(deck_13)
    assert rz.config == {"factk": 1.0, "factcprise": 1.0, "tunitk": "1DAY"}
    assert rz.max_iterations == 2000
    assert rz.gw_uptake == 1


def test_14_column_deck_still_reads(deck_14):
    rz = read_rootzone_main(deck_14)
    assert "k_ponded" in rz.element_params.columns
    # Read faithfully: the -1.0 sentinel is preserved, not resolved.
    assert rz.element_params["k_ponded"].tolist() == [0.0055, -1.0, 0.01]


def test_a_short_row_after_a_14_column_first_row_still_degrades(tmp_path):
    """The width comes from the first row, as in IWFM -- later short
    rows are a real defect and must not pass silently."""
    rows = [f"{_SOIL_13[0]}  0.0055", _SOIL_13[1], _SOIL_13[2]]
    path = _write(tmp_path, rows, name="RootZone_MAIN_ragged.dat")
    with pytest.raises(IWFMParseError):
        read_rootzone_main(path)


# ------------------------------------------------------------- semantics
def test_k_ponded_defaults_to_k_when_the_column_is_absent(deck_13):
    rz = read_rootzone_main(deck_13)
    assert rz.k_ponded().tolist() == rz.element_params["k"].tolist()


def test_k_ponded_resolves_the_minus_one_sentinel(deck_14):
    rz = read_rootzone_main(deck_14)
    k = rz.element_params["k"]
    assert rz.k_ponded().tolist() == [0.0055, k.iloc[1], 0.01]


def test_k_ponded_is_none_without_a_soil_table():
    from iwfm_io.models.rootzone import RootZoneMain
    assert RootZoneMain().k_ponded() is None


# ------------------------------------------------------------ round trip
def test_13_column_deck_round_trips_at_13_columns(deck_13, tmp_path):
    """Writing must not invent a KPonded column the deck never had."""
    rz = read_rootzone_main(deck_13)
    out = tmp_path / "out.dat"
    write_rootzone_main(rz, out)

    again = read_rootzone_main(out)
    assert "k_ponded" not in again.element_params.columns
    assert list(again.element_params.columns) == \
        list(rz.element_params.columns)
    for column in rz.element_params.columns:
        assert again.element_params[column].tolist() == \
            rz.element_params[column].tolist()


def test_14_column_deck_round_trips_at_14_columns(deck_14, tmp_path):
    rz = read_rootzone_main(deck_14)
    out = tmp_path / "out14.dat"
    write_rootzone_main(rz, out)

    again = read_rootzone_main(out)
    assert again.element_params["k_ponded"].tolist() == \
        rz.element_params["k_ponded"].tolist()
    assert not any(math.isnan(v)
                   for v in again.element_params["k_ponded"].tolist())
