"""Tests for plot-layer budget post-processing."""

import numpy as np


def test_combine_storage_terms_columns():
    from iwfm_io.plots import combine_storage_terms

    names = ["Percolation", "Beginning Storage (+)", "Ending Storage (-)",
             "Gain from Stream (+)"]
    values = np.array([
        [10.0, 1000.0, 1005.0, 3.0],
        [20.0, 1005.0, 1002.0, 4.0],
    ])
    new_names, new_values = combine_storage_terms(names, values)
    assert new_names == ["Percolation", "Change in Storage",
                         "Gain from Stream (+)"]
    assert new_values.shape == (2, 3)
    # ending - beginning: +5 then -3
    np.testing.assert_allclose(new_values[:, 1], [5.0, -3.0])
    # other columns untouched
    np.testing.assert_allclose(new_values[:, 0], [10.0, 20.0])
    np.testing.assert_allclose(new_values[:, 2], [3.0, 4.0])


def test_combine_storage_terms_rows_with_extras():
    from iwfm_io.plots import combine_storage_terms

    names = ["Beginning Storage (+)", "Ending Storage (-)", "Recharge (+)"]
    flows = np.array([
        [100.0, 200.0],   # beginning
        [110.0, 190.0],   # ending
        [1.0, 2.0],       # recharge
    ])
    stds = np.array([[3.0, 4.0], [4.0, 3.0], [0.5, 0.5]])
    new_names, new_flows, new_stds = combine_storage_terms(
        names, flows, extras=stds, component_axis=0)
    assert new_names == ["Change in Storage", "Recharge (+)"]
    np.testing.assert_allclose(new_flows[0], [10.0, -10.0])
    np.testing.assert_allclose(new_stds[0], [5.0, 5.0])  # quadrature 3-4-5


def test_filter_balance_components():
    from iwfm_io.plots import filter_balance_components

    # Untagged 'Percolation' is reporting-only; '(=)' is closure —
    # both drop. Tagged components and Change in Storage stay.
    names = ["Percolation", "Change in Storage", "Deep Percolation (+)",
             "Pumping (-)", "Discrepancy (=)"]
    values = np.ones((3, 5)) * np.arange(5)
    out_names, out_vals = filter_balance_components(names, values)
    assert out_names == ["Change in Storage", "Deep Percolation (+)",
                         "Pumping (-)"]
    np.testing.assert_allclose(out_vals[0], [1, 2, 3])


def test_filter_balance_components_untagged_passthrough():
    from iwfm_io.plots import filter_balance_components

    # The monthly/annual flows API returns untagged, already
    # balance-only names — nothing may be dropped
    names = ["Change in Storage", "Deep Percolation", "Pumping"]
    values = np.ones((2, 3))
    out_names, out_vals = filter_balance_components(names, values)
    assert out_names == names
    assert out_vals.shape == (2, 3)


def test_water_year_totals():
    import pandas as pd
    from iwfm_io.plots import water_year_totals

    # Two water years of monthly ones: Oct 1990 .. Sep 1992
    months = pd.date_range("1990-10-31", periods=24, freq="ME")
    values = np.ones((24, 2))
    ends, totals = water_year_totals(months, values)
    assert totals.shape == (2, 2)
    np.testing.assert_allclose(totals, 12.0)
    assert [e.year for e in ends] == [1991, 1992]
    assert all(e.month == 9 and e.day == 30 for e in ends)


def test_sign_budget_components():
    from iwfm_io.plots import sign_budget_components

    names = ["Percolation", "Change in Storage", "Deep Percolation (+)",
             "Pumping (-)", "Discrepancy (=)"]
    means = np.array([10.0, 4.0, 20.0, 15.0, 0.1])
    out_names, signed = sign_budget_components(names, means)
    assert out_names == ["Percolation", "Change in Storage",
                         "Deep Percolation", "Pumping"]
    # storage gain -> negative (leaves the balance); pumping -> negative;
    # (+) and untagged stay positive; discrepancy dropped
    np.testing.assert_allclose(signed, [10.0, -4.0, 20.0, -15.0])


def test_sign_budget_components_2d():
    from iwfm_io.plots import sign_budget_components

    names = ["In (+)", "Out (-)"]
    series = np.array([[1.0, 2.0], [3.0, 4.0]])
    out_names, signed = sign_budget_components(names, series)
    assert out_names == ["In", "Out"]
    np.testing.assert_allclose(signed, [[1.0, -2.0], [3.0, -4.0]])


def test_combine_storage_terms_no_pair_passthrough():
    from iwfm_io.plots import combine_storage_terms

    names = ["Percolation", "Recharge"]
    values = np.ones((4, 2))
    new_names, new_values = combine_storage_terms(names, values)
    assert new_names == names
    assert new_values.shape == (4, 2)


def test_finish_saves_and_closes(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from iwfm_io.plots import _finish

    plt.close("all")
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    out = tmp_path / "fig.png"
    assert _finish(fig, str(out), close=True) is fig
    assert out.is_file() and out.stat().st_size > 0
    assert plt.get_fignums() == []

    # default keeps the figure open (callers get a live (fig, ax) back)
    fig2, _ = plt.subplots()
    _finish(fig2, None)
    assert plt.get_fignums() == [fig2.number]
    plt.close("all")


class _GridSource:
    """Minimal nodes_df()/stream_nodes_df()/reaches_df() source."""

    def __init__(self, nodes, stream_nodes, reaches):
        import pandas as pd
        self._n = pd.DataFrame(nodes)
        self._s = pd.DataFrame(stream_nodes)
        self._r = pd.DataFrame(reaches)

    def nodes_df(self):
        return self._n

    def elements_df(self):
        raise AssertionError("not needed")

    def stream_nodes_df(self):
        return self._s

    def reaches_df(self):
        return self._r


def _rowwise_stream_segments(source):
    """The pre-vectorisation implementation (iterrows), kept as the oracle."""
    ndf = source.nodes_df()
    coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
    sn_df = source.stream_nodes_df()
    reach_ids = source.reaches_df()["reach_id"].values
    segments = []
    for rid in reach_ids:
        gw_nodes = sn_df.loc[sn_df["reach_id"] == rid, "gw_node_id"].values
        pts = [coord[int(gn)] for gn in gw_nodes if int(gn) in coord]
        segments.append(np.array(pts) if len(pts) >= 2 else np.empty((0, 2)))
    return segments, reach_ids


def _rowwise_stream_node_xy(source):
    ndf = source.nodes_df()
    coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
    sn_df = source.stream_nodes_df()
    sx = np.zeros(len(sn_df))
    sy = np.zeros(len(sn_df))
    for i, (_, row) in enumerate(sn_df.iterrows()):
        gw_id = int(row["gw_node_id"])
        if gw_id in coord:
            sx[i], sy[i] = coord[gw_id]
    return sx, sy


def test_vectorised_stream_helpers_match_rowwise():
    from iwfm_io.plots import get_stream_segments, get_stream_node_xy

    # unsorted reach ids, a reach with one usable node, a stream node whose
    # GW node is missing, a duplicated node id (last row wins), and a
    # float-typed gw_node_id column
    src = _GridSource(
        nodes={"node_id": [1, 2, 3, 4, 5, 3],
               "x": [0.0, 1.0, 2.0, 3.0, 4.0, 2.5],
               "y": [0.0, 0.5, 1.0, 1.5, 2.0, 9.0]},
        stream_nodes={"stream_node_id": [1, 2, 3, 4, 5, 6, 7],
                      "reach_id": [3, 3, 1, 1, 1, 2, 2],
                      "gw_node_id": [5.0, 4.0, 1.0, 2.0, 3.0, 99.0, 1.0]},
        reaches={"reach_id": [1, 3, 2]},
    )
    segs, rids = get_stream_segments(src)
    ref_segs, ref_rids = _rowwise_stream_segments(src)
    np.testing.assert_array_equal(rids, ref_rids)
    assert len(segs) == len(ref_segs) == 3
    for got, ref in zip(segs, ref_segs):
        assert got.shape == ref.shape
        np.testing.assert_array_equal(got, ref)
    assert segs[2].shape == (0, 2)              # reach 2: only one node found
    np.testing.assert_array_equal(segs[0][-1], [2.5, 9.0])   # duplicate: last

    sx, sy = get_stream_node_xy(src)
    rx, ry = _rowwise_stream_node_xy(src)
    np.testing.assert_array_equal(sx, rx)
    np.testing.assert_array_equal(sy, ry)
    assert sx[5] == 0.0 and sy[5] == 0.0         # missing GW node stays 0


def test_element_configs_vectorised_ints():
    import pandas as pd
    from iwfm_io.plots import _get_element_configs

    class _Src:
        def nodes_df(self):
            return pd.DataFrame({"node_id": [1, 2, 3, 4], "x": [0, 1, 1, 0],
                                 "y": [0, 0, 1, 1]})

        def elements_df(self):
            return pd.DataFrame({"element_id": [7, 8],
                                 "node1": [1, 1], "node2": [2, 2],
                                 "node3": [3, 3], "node4": [4, 0]})

    eids, cfgs = _get_element_configs(_Src())
    np.testing.assert_array_equal(eids, [7, 8])
    assert cfgs == [[1, 2, 3, 4], [1, 2, 3, 0]]
    assert all(type(v) is int for cfg in cfgs for v in cfg)
