"""Zone-budget reads by diversified column (issue #36).

The general Z-Budget column list carries one lumped pair, "Inflow from" /
"Outflow to adjacent zones".  For a given zone that pair is replaced by one
inflow/outflow pair per adjacent zone, so a zone with k neighbours has
``len(general) - 2 + 2k`` columns, and the zone reads take indices into that
diversified list.  2.14.0 validated them against the general count, which
rejected every column past it for any zone with more than one neighbour.

A 3x3 grid of zones on the sample model gives corner zones two
neighbours, edge zones three and the centre four, so the diversified lists
run past the general count -- inter-zone columns included -- and differ in
width.  Uses the default DLL build (2025.0.1747), where the per-zone header
export was long believed to hang; it only did with the wrapper's old default
column list, 1..500.

Runs only where the IWFM DLL loads (Windows x64 with an installed build).
"""

import re

import numpy as np
import pytest

from tests.io.conftest import RESULTS_DIR, SAMPLE_MODEL

_dll_ok = False
try:  # pragma: no cover - environment dependent
    from iwfm_io.dll import load_dll

    load_dll()
    _dll_ok = True
except Exception:
    pass

pytestmark = pytest.mark.skipif(not _dll_ok, reason="IWFM DLL not available")

HORIZONTAL = 1   # ZoneExtentID.Horizontal in every published build
_INFLOW = re.compile(r"Inflow from zone (\d+) ")
_OUTFLOW = re.compile(r"Outflow to zone (\d+) ")


def _grid_zones(n=3):
    """Zone 1..n*n per element by which cell of an n x n grid (split at
    centroid quantiles) its centroid falls in."""
    from iwfm_io import read_preprocessor

    pp = read_preprocessor(SAMPLE_MODEL / "Preprocessor" / "PreProcessor_MAIN.IN")
    xy = pp.nodes.set_index("node_id")[["x", "y"]]
    el = pp.elements
    nodes = el[["node1", "node2", "node3", "node4"]].to_numpy()
    cx = np.array([xy.loc[[n for n in row if n], "x"].mean() for row in nodes])
    cy = np.array([xy.loc[[n for n in row if n], "y"].mean() for row in nodes])
    col = np.digitize(cx, np.quantile(cx, np.linspace(0, 1, n + 1)[1:-1]))
    row = np.digitize(cy, np.quantile(cy, np.linspace(0, 1, n + 1)[1:-1]))
    zones = 1 + col + n * row
    return el["element_id"].astype(int).tolist(), zones.tolist()


@pytest.fixture(scope="module")
def zbud():
    from iwfm_io.dll import IWFMZBudget

    hdf = RESULTS_DIR / "GW_ZBud.hdf"
    if not hdf.is_file():
        pytest.skip("GW_ZBud.hdf not present")
    elements, zones = _grid_zones()
    ids = sorted(set(zones))
    with IWFMZBudget(str(hdf)) as z:
        z.generate_zone_list(HORIZONTAL, elements, [1] * len(elements), zones,
                             ids, [f"Cell {i}" for i in ids])
        yield z


@pytest.fixture(scope="module")
def layout(zbud):
    """general headers, and per zone: (headers, neighbour ids)."""
    general = zbud.get_column_headers_general()
    zones = {}
    for zone in zbud.get_zone_list().tolist():
        headers, _ = zbud.get_column_headers_for_zone(zone)
        neighbours = [int(m.group(1)) for h in headers if (m := _INFLOW.match(h))]
        zones[zone] = (headers, neighbours)
    return general, zones


@pytest.fixture(scope="module")
def window(zbud):
    dates = zbud.get_time_specs()["dates"]
    return dates[0], dates[min(29, len(dates) - 1)]


def test_diversified_count_follows_the_adjacency_rule(layout):
    general, zones = layout
    for zone, (headers, neighbours) in zones.items():
        assert len(headers) == len(general) - 2 + 2 * len(neighbours), zone
    # the case issue #36 is about: more columns than the general list
    assert any(len(h) > len(general) for h, _ in zones.values())


def test_get_values_for_zone_reads_every_diversified_column(zbud, layout, window):
    general, zones = layout
    for zone, (headers, _) in zones.items():
        vals = zbud.get_values_for_zone(
            zone, list(range(1, len(headers) + 1)), *window, "1DAY")
        assert vals.shape[1] == len(headers)
        assert np.isfinite(vals).all()


def test_interzone_columns_past_the_general_count_hold_the_right_flows(
        zbud, layout, window):
    """A's inflow from B is B's outflow to A (both stored as magnitudes).
    Checked on columns whose diversified index exceeds the general count,
    which is exactly what 2.14.0 refused to read."""
    general, zones = layout
    data = {z: zbud.get_values_for_zone(z, list(range(1, len(h) + 1)), *window, "1DAY")
            for z, (h, _) in zones.items()}
    checked = beyond = 0
    for a, (ha, _) in zones.items():
        for i, h in enumerate(ha):
            m = _INFLOW.match(h)
            if not m:
                continue
            b = int(m.group(1))
            hb = zones[b][0]
            j = next(k for k, x in enumerate(hb)
                     if (mo := _OUTFLOW.match(x)) and int(mo.group(1)) == a)
            np.testing.assert_allclose(data[a][:, i], data[b][:, j], rtol=1e-9)
            checked += 1
            beyond += (i + 1 > len(general)) or (j + 1 > len(general))
    assert checked >= 4 and beyond >= 1, (checked, beyond)


def test_column_past_the_zone_count_is_still_refused(zbud, layout, window):
    """The single-zone read sizes the zone's flow array exactly and indexes
    it unchecked: one past the zone's own count must never reach it."""
    _, zones = layout
    zone, (headers, _) = next(iter(zones.items()))
    with pytest.raises(ValueError, match=f"zone {zone}"):
        zbud.get_values_for_zone(
            zone, list(range(1, len(headers) + 2)), *window, "1DAY")


def test_default_column_list_is_every_general_column(zbud, layout):
    """The old default (1..500) crashed the 2025.0.1747 build."""
    general, zones = layout
    zone = next(iter(zones))
    default, _ = zbud.get_column_headers_for_zone(zone)
    explicit, _ = zbud.get_column_headers_for_zone(
        zone, list(range(1, len(general) + 1)))
    assert default == explicit


def test_general_index_past_the_general_count_is_refused(zbud, layout):
    general, zones = layout
    with pytest.raises(ValueError, match="general column indices"):
        zbud.get_column_headers_for_zone(
            next(iter(zones)), list(range(1, len(general) + 2)))


def test_zones_interval_reads_zones_of_different_widths_padded_with_zero(
        zbud, layout, window):
    general, zones = layout
    order = sorted(zones, key=lambda z: len(zones[z][0]))
    widths = [len(zones[z][0]) for z in order]
    n_max = max(widths)
    cols = np.zeros((n_max, len(order)), dtype=np.int32)
    for j, w in enumerate(widths):
        cols[:w, j] = np.arange(1, w + 1)          # shorter zones padded with 0
    got = zbud.get_values_for_zones_interval(order, cols, window[0], "1DAY")
    for j, (zone, w) in enumerate(zip(order, widths)):
        single = zbud.get_values_for_zone(
            zone, list(range(1, w + 1)), window[0], window[0], "1DAY")
        np.testing.assert_allclose(got[1:w, j], single[0, 1:], rtol=1e-9)


def test_zones_interval_refuses_a_column_past_that_zones_count(zbud, layout, window):
    _, zones = layout
    zone, (headers, _) = next(iter(zones.items()))
    cols = np.arange(1, len(headers) + 2, dtype=np.int32).reshape(-1, 1)
    with pytest.raises(ValueError, match=f"zone {zone}"):
        zbud.get_values_for_zones_interval([zone], cols, window[0], "1DAY")
