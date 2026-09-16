"""Standalone zone-budget file attacks (scripts a10, a10b, a09).

``IWFMZBudget`` needs the optional 100 MB ``UnsatZone_ZBud.hdf``; every
case returns ``skipped`` when the copy does not carry it. Reproduces the
``generate_zone_list`` default (``nZonesWithNames=0``) out-of-bounds read,
garbage from unknown zone numbers, and the ``get_column_headers_for_zone``
out-of-bounds read (its default column list ran past the general headers).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import B, E, N_ELEMENTS, attempt, main, paths, skipped, stats, zbudget_file  # noqa: E402

HORIZONTAL = 1          # ZoneExtentID.Horizontal in every published build
ALL_ELEMENTS = list(range(1, N_ELEMENTS + 1))
TWO_ZONES = [1] * 200 + [2] * 200


def _open(model_dir):
    from iwfm_io.dll import IWFMZBudget
    zb = zbudget_file(model_dir)
    if zb is None:
        return None
    return IWFMZBudget(zb)


def _named(z, extent=HORIZONTAL, elements=None, layers=None, zones=None, ids=None, names=None):
    """generate_zone_list with names supplied (the DLL-safe form)."""
    elements = ALL_ELEMENTS if elements is None else elements
    layers = [1] * len(elements) if layers is None else layers
    zones = TWO_ZONES[:len(elements)] if zones is None else zones
    if ids is None:
        ids = sorted(set(zones))
        names = [f"Z{i}" for i in ids]
    z.generate_zone_list(extent, elements, layers, zones, ids, names)
    return {"n_zones": z.n_zones, "zone_list": z.get_zone_list().tolist()[:10],
            "names": z.get_zone_names()[:5]}


def _with_zones(model_dir, fn, named=True):
    z = _open(model_dir)
    if z is None:
        return skipped("UnsatZone_ZBud.hdf not present")
    if named:
        _named(z)
    return attempt(lambda: fn(z))


def _vals(z, zone=1, cols=(1, 2, 3), interval="1MON", b=B, e=E, **kw):
    return stats(z.get_values_for_zone(zone, list(cols), b, e, interval, **kw))


# -- bad files ------------------------------------------------------------------

def _open_path(model_dir, path):
    from iwfm_io.dll import IWFMZBudget

    def go():
        z = IWFMZBudget(path)
        r = {"n_ts": z.n_timesteps, "n_titles": z.n_title_lines}
        z.close()
        return r
    return attempt(go)


def case_open_missing(model_dir):
    return _open_path(model_dir, str(paths(model_dir)["results"] / "nope.hdf"))


def case_open_budget_file_as_zbudget(model_dir):
    return _open_path(model_dir, str(paths(model_dir)["results"] / "GW.hdf"))


def case_open_heads_file_as_zbudget(model_dir):
    return _open_path(model_dir, str(paths(model_dir)["results"] / "GWHeadAll.hdf"))


def case_open_text_file_as_zbudget(model_dir):
    return _open_path(model_dir, paths(model_dir)["sim"])


def case_open_zero_byte(model_dir):
    p = Path(model_dir).parent / "zero.hdf"
    p.write_bytes(b"")
    return _open_path(model_dir, str(p))


# -- zone list generation ---------------------------------------------------------

def case_gen_default_unnamed(model_dir):
    """Wrapper default: no zone names -> the DLL reads past a 0-length name
    array (nZonesWithNames=0)."""
    def go(z):
        z.generate_zone_list(HORIZONTAL, ALL_ELEMENTS, [1] * N_ELEMENTS, TWO_ZONES)
        return {"n_zones": z.n_zones, "zone_list": z.get_zone_list().tolist(),
                "names": z.get_zone_names(), "values": _vals(z)}
    return _with_zones(model_dir, go, named=False)


def case_gen_named_control(model_dir):
    return _with_zones(model_dir, lambda z: _named(z), named=False)


def case_no_zone_list_n_zones(model_dir):
    return _with_zones(model_dir, lambda z: z.n_zones, named=False)


def case_no_zone_list_values(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z), named=False)


def case_no_zone_list_headers_general(model_dir):
    return _with_zones(model_dir, lambda z: z.get_column_headers_general()[:3], named=False)


def case_gen_elements_empty(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, elements=[], zones=[], ids=[1], names=["A"]), named=False)


def case_gen_element_0(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, elements=[0], zones=[1]), named=False)


def case_gen_element_999(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, elements=[999], zones=[1]), named=False)


def case_gen_element_neg1(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, elements=[-1], zones=[1]), named=False)


def case_gen_zones_all_0(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, zones=[0] * N_ELEMENTS, ids=[0], names=["Zero"]), named=False)


def case_gen_zones_all_neg1(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, zones=[-1] * N_ELEMENTS, ids=[-1], names=["Neg"]), named=False)


def case_gen_layer_0(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, layers=[0] * N_ELEMENTS), named=False)


def case_gen_layer_99(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, layers=[99] * N_ELEMENTS), named=False)


def case_gen_extent_99(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, extent=99), named=False)


def case_gen_duplicate_elements(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, elements=[1, 1, 1], zones=[1, 1, 1]), named=False)


def case_gen_names_mismatch_2_ids_1_name(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, ids=[1, 2], names=["A"]), named=False)


def case_gen_names_mismatch_1_id_2_names(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, ids=[1], names=["A", "B"]), named=False)


def case_gen_name_for_unknown_zone(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, ids=[99], names=["Ghost"]), named=False)


def case_gen_name_300_chars(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, ids=[1, 2], names=["N" * 300, "B"]), named=False)


def case_gen_name_non_ascii(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, ids=[1, 2], names=["Zoné", "B"]), named=False)


def case_gen_zone_id_int32_max(model_dir):
    big = 2**31 - 1
    return _with_zones(model_dir, lambda z: _named(z, zones=[big] * N_ELEMENTS, ids=[big], names=["Big"]), named=False)


def case_gen_zone_id_int32_overflow(model_dir):
    return _with_zones(model_dir, lambda z: _named(z, zones=[2**31] * N_ELEMENTS, ids=[2**31], names=["Over"]), named=False)


def case_gen_twice(model_dir):
    def go(z):
        first = _named(z)
        second = _named(z, zones=[1] * 100 + [2] * 100 + [3] * 200, ids=[1, 2, 3], names=["a", "b", "c"])
        return {"first": first, "second": second}
    return _with_zones(model_dir, go, named=False)


def case_gen_from_file_missing(model_dir):
    return _with_zones(model_dir, lambda z: z.generate_zone_list_from_file(str(Path(model_dir) / "nope.dat")), named=False)


def case_gen_from_file_sim_main(model_dir):
    return _with_zones(model_dir, lambda z: z.generate_zone_list_from_file(paths(model_dir)["sim"]), named=False)


def case_gen_from_file_vs_arrays(model_dir):
    """The shipped ZoneDef_SRs.dat and the equivalent arrays must agree."""
    import numpy as np
    zdef = str(Path(model_dir) / "ZBudget" / "ZoneDef_SRs.dat")
    if not Path(zdef).is_file():
        return skipped("ZoneDef_SRs.dat not present")

    def go(z):
        z.generate_zone_list_from_file(zdef)
        zl = z.get_zone_list().tolist()
        names = z.get_zone_names()
        a = z.get_values_for_zone(1, [1, 2, 3], B, E, "1MON")
        z.close()
        z2 = _open(model_dir)
        _named(z2)
        b = z2.get_values_for_zone(1, [1, 2, 3], B, E, "1MON")
        return {"file_zones": zl, "file_names": names, "shape_file": list(a.shape),
                "shape_arrays": list(b.shape), "close": bool(a.shape == b.shape and np.allclose(a, b))}
    return _with_zones(model_dir, go, named=False)


# -- values -----------------------------------------------------------------------

def case_values_control(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z))


def case_values_zone_not_in_list(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, zone=3))


def case_values_zone_0(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, zone=0))


def case_values_zone_neg1(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, zone=-1))


def case_values_zone_999(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, zone=999))


def case_values_cols_empty(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=()))


def case_values_cols_999(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=(1, 999)))


def case_values_cols_0(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=(1, 0)))


def case_values_cols_neg1(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=(1, -1)))


def case_values_cols_no_time(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=(2, 3)))


def case_values_cols_duplicate(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, cols=(1, 2, 2)))


def case_values_interval_3mon(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, interval="3MON"))


def case_values_interval_empty(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, interval=""))


def case_values_interval_trailing_space(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, interval="1YEAR "))


def case_values_interval_1year_control(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, interval="1YEAR"))


def case_values_begin_after_end(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, b=E, e=B))


def case_values_window_before_sim(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, b="10/01/1980_24:00", e="10/31/1980_24:00"))


def case_values_fact_nan(model_dir):
    return _with_zones(model_dir, lambda z: _vals(z, fact_vl=float("nan")))


def case_headers_general(model_dir):
    return _with_zones(model_dir, lambda z: z.get_column_headers_general()[:5])


def case_headers_general_max_columns_1(model_dir):
    return _with_zones(model_dir, lambda z: z.get_column_headers_general(max_columns=1))


def case_headers_general_max_columns_0(model_dir):
    return _with_zones(model_dir, lambda z: z.get_column_headers_general(max_columns=0))


def case_headers_for_zone(model_dir):
    """Default column list: once 1..500, an out-of-bounds read of the
    general headers that crashed or hung 2025.0.1747; now every general
    column."""
    return _with_zones(model_dir, lambda z: z.get_column_headers_for_zone(1)[0][:3])


def case_title_lines_zone_999(model_dir):
    return _with_zones(model_dir, lambda z: z.get_title_lines(999))


def case_title_lines_zone_1(model_dir):
    return _with_zones(model_dir, lambda z: z.get_title_lines(1))


def case_zones_interval_control(model_dir):
    import numpy as np
    return _with_zones(model_dir, lambda z: stats(
        z.get_values_for_zones_interval([1, 2], np.array([[1, 1], [2, 2], [3, 3]]), B, "1MON")))


def case_zones_interval_zone_999(model_dir):
    import numpy as np
    return _with_zones(model_dir, lambda z: stats(
        z.get_values_for_zones_interval([999], np.array([[1], [2]]), B, "1MON")))


def case_zones_interval_date_outside(model_dir):
    import numpy as np
    return _with_zones(model_dir, lambda z: stats(
        z.get_values_for_zones_interval([1], np.array([[1], [2]]), "10/01/1980_24:00", "1MON")))


def case_zones_interval_zones_empty(model_dir):
    import numpy as np
    return _with_zones(model_dir, lambda z: stats(
        z.get_values_for_zones_interval([], np.zeros((2, 0), dtype=int), B, "1MON")))


# -- lifecycle of the standalone readers ---------------------------------------------

def case_after_close_n_zones(model_dir):
    z = _open(model_dir)
    if z is None:
        return skipped("UnsatZone_ZBud.hdf not present")
    z.close()
    return attempt(lambda: z.n_zones)


def case_close_twice(model_dir):
    z = _open(model_dir)
    if z is None:
        return skipped("UnsatZone_ZBud.hdf not present")
    z.close()
    return attempt(lambda: (z.close(), "ok")[1])


def case_budget_and_zbudget_together(model_dir):
    """A standalone IWFMBudget must survive a zbudget open + close."""
    from iwfm_io.dll import IWFMBudget
    z = _open(model_dir)
    if z is None:
        return skipped("UnsatZone_ZBud.hdf not present")

    def go():
        b = IWFMBudget(str(paths(model_dir)["results"] / "GW.hdf"))
        r = {"b_nloc": b.n_locations, "z_nts": z.n_timesteps}
        z.close()
        r["b_nloc_after_zclose"] = b.n_locations
        r["b_values_after_zclose"] = stats(b.get_values(1, [1], B, E, "1MON"))
        b.close()
        return r
    return attempt(go)


def case_budget_reader_on_zbudget_file(model_dir):
    """IWFMBudget opened on a zone-budget HDF."""
    from iwfm_io.dll import IWFMBudget
    zb = zbudget_file(model_dir)
    if zb is None:
        return skipped("UnsatZone_ZBud.hdf not present")

    def go():
        b = IWFMBudget(zb)
        r = {"n_loc": b.n_locations, "n_ts": b.n_timesteps}
        b.close()
        return r
    return attempt(go)


if __name__ == "__main__":
    main(globals())
