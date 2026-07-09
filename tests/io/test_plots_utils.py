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
