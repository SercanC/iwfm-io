"""Hostile-QA regressions: plots / text outputs / land use / tokens / DSS / initial conditions.

Imported from the 2026-09-09 hostile-QA pass. Every test asserts the
EXPECTED behaviour; ``xfail(strict=True)`` marks the ones that still
reproduce a defect on the current code.
"""
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

pytestmark = [pytest.mark.regression, pytest.mark.sample_model]


@pytest.fixture(scope="module")
def m(open_sample):
    return open_sample


@pytest.fixture(scope="module")
def RES(sample_model):
    return sample_model / "Results"


@pytest.fixture(autouse=True)
def _close():
    yield
    plt.close("all")


# ---------------------------------------------------------------- text outputs
def test_read_velocity_out_keeps_every_element(RES):
    from iwfm_io.readers.text_output import read_velocity_out
    p = RES / "GWVelocities.out"
    if not p.is_file():
        pytest.skip("GWVelocities.out not present (large, regenerable Results file)")
    df = read_velocity_out(p)
    # 400 elements x 3653 timesteps; today only the dated row (element 1) survives
    assert len(df) == 400 * 3653


def test_read_head_all_out_rejects_bogus_header_node_count(tmp_path, RES):
    from iwfm_io.readers.text_output import read_head_all_out
    lines = (RES / "GWHeadAll.out").read_text(encoding="utf-8").splitlines(keepends=True)
    h = next(i for i, ln in enumerate(lines) if ln.startswith("*") and "TIME" in ln)
    toks = lines[h].split()
    lines[h] = "   ".join(toks[:2] + toks[2:5]) + "\n"        # header lists only nodes 1..3
    p = tmp_path / "x.out"
    p.write_text("".join(lines[:h + 9]))
    df = read_head_all_out(p)
    # 882 data columns / 3 header ids -> silently labelled node_1..3 x layer_1..294
    assert not any(c.endswith("_layer_294") for c in df.columns)


def test_read_head_all_out_tolerates_overflow_stars_like_hydrograph_reader(tmp_path, RES):
    from iwfm_io.readers.text_output import read_head_all_out
    lines = (RES / "GWHeadAll.out").read_text(encoding="utf-8").splitlines(keepends=True)
    h = next(i for i, ln in enumerate(lines) if ln.startswith("*") and "TIME" in ln) + 1
    row = lines[h].split()
    row[5] = "*******"
    p = tmp_path / "x.out"
    p.write_text("".join(lines[:h] + ["  ".join(row) + "\n"] + lines[h + 1:h + 8]))
    df = read_head_all_out(p)                      # today: ValueError could not convert '*******'
    assert np.isnan(df.iloc[0, 5])


def test_hydrograph_metadata_nodes_label_not_split_as_node_S(RES):
    from iwfm_io.readers.text_output import read_hydrograph_out_with_metadata
    md = read_hydrograph_out_with_metadata(RES / "StrmHyd.out")["metadata"]
    assert "S" not in md.get("node", []) and "S" not in md.get("nodes", [])


def test_read_budget_text_column_names_align_with_data(sample_model):
    from iwfm_io.readers.text_output import read_budget_text
    secs = read_budget_text(sample_model / "Budget" / "DiverDetail.bud")
    df = next(iter(secs.values()))
    assert df.columns.is_unique                     # today: 'Loss', 'Loss' + truncated 'Subreg.'


# ---------------------------------------------------------------- adapter / plots
@pytest.mark.parametrize("layer", [0, -1, 3, 99, 1.0])
def test_heads_df_invalid_layer_raises(m, layer):
    with pytest.raises((ValueError, IndexError, KeyError, TypeError)):
        m.heads_df(layer)                           # today: silently empty (3654, 0) frame


def test_heads_df_negative_layer_text_path_does_not_return_layer1(sample_model, RES):
    from iwfm_io.model_adapter import IOModelAdapter
    from iwfm_io.readers.preprocessor import read_preprocessor_main
    from iwfm_io.readers.simulation import read_simulation_main
    a = IOModelAdapter(preprocessor=read_preprocessor_main(sample_model / "Preprocessor" / "PreProcessor_MAIN.IN"),
                       simulation=read_simulation_main(sample_model / "Simulation" / "Simulation_MAIN.IN"),
                       heads_hdf=RES / "GWHeadAll.out")
    with pytest.raises(Exception):
        a.heads_df(-1)                              # today: returns layer-1 heads


def test_head_contour_time_index_not_silently_ignored(m):
    from iwfm_io.plots.maps import plot_gw_head_contour
    fig, ax = plot_gw_head_contour(m, layer=1, time_index=0)   # no dates
    first = m.heads_df(1).iloc[0].to_numpy()
    cs = [c for c in ax.collections if hasattr(c, "levels")][0]
    lo, hi = cs.get_clim()
    assert lo <= first.min() and hi >= first.max() and "last output" not in ax.get_title()


def test_head_contour_factor_applied_without_dates(m):
    from iwfm_io.plots.maps import plot_gw_head_contour
    fig, ax = plot_gw_head_contour(m, layer=1, factor=0.3048)
    cs = [c for c in ax.collections if hasattr(c, "levels")][0]
    assert cs.get_clim()[1] < 200                   # metres, not feet (today ~540)


def test_head_vs_gse_scatter_aquifer_top_is_an_elevation(m):
    from iwfm_io.plots.spatial_patterns import plot_head_vs_gse_scatter
    fig, ax = plot_head_vs_gse_scatter(m, layer=1)
    top = [c for c in ax.collections if c.get_label() == "Aquifer top"][0].get_offsets()[:, 1]
    gse = m.stratigraphy_df()["elevation"].to_numpy()
    assert np.all(top <= gse) and np.all(top > 0)   # today: aquitard_1 THICKNESS (all 0.0)


def test_trend_map_out_of_range_dates_raise_not_zero_map(m):
    from iwfm_io.plots.trends import plot_head_trend_map
    with pytest.raises(Exception):
        plot_head_trend_map(m, 1, "10/01/2050_24:00", "10/01/2051_24:00")   # today: silent all-zero map


def test_drought_drawdown_ignores_nan(m):
    from iwfm_io.plots.trends import plot_drought_drawdown_rate

    class NanModel:
        def __init__(s, b):
            s._b = b

        def __getattr__(s, k):
            return getattr(s._b, k)

        def heads_df(s, layer, *a, **k):
            df = s._b.heads_df(layer, *a, **k).copy()
            mask = np.random.default_rng(0).random(df.shape) < 0.1
            return pd.DataFrame(np.where(mask, np.nan, df.to_numpy()), index=df.index, columns=df.columns)

    fig, ax = plot_drought_drawdown_rate(NanModel(m), 1, "09/30/1990_24:00", "09/30/2000_24:00")
    cs = [c for c in ax.collections if hasattr(c, "levels")][0]
    assert cs.get_clim()[1] > 1.0                   # today: (-1e-14, 1e-14) -> blank map


def test_plot_element_map_rejects_wrong_length(m):
    from iwfm_io.plots import plot_element_map
    with pytest.raises(ValueError):
        plot_element_map(m, np.arange(10.0))        # today: 10 colours recycled over 400 elements


def test_animation_colorbar_matches_later_frames(m):
    from iwfm_io.plots.animations import animate_gw_heads
    an = animate_gw_heads(m, 1, "09/30/1990_24:00", "09/30/2000_24:00", interval_frames=1000)
    ax = an._fig.axes[0]
    lv0 = [c for c in ax.collections if hasattr(c, "levels")][0].levels.copy()
    an._func(3000)
    lv1 = [c for c in ax.collections if hasattr(c, "levels")][0].levels.copy()
    assert len(lv0) == len(lv1) and np.allclose(lv0, lv1)


def test_animate_fps_zero_gives_clean_error(m):
    from iwfm_io.plots.animations import animate_gw_heads
    with pytest.raises(ValueError):
        animate_gw_heads(m, 1, "09/30/1990_24:00", "10/03/1990_24:00", fps=0)   # today: ZeroDivisionError


def test_stream_exchange_map_without_streams(m):
    from iwfm_io.plots.stream_analysis import plot_stream_aquifer_exchange_map

    class NoStreams:
        def __init__(s, b):
            s._b = b

        def __getattr__(s, k):
            return getattr(s._b, k)

        def stream_nodes_df(s):
            return pd.DataFrame(columns=["stream_node_id", "reach_id", "gw_node_id"])

        def reaches_df(s):
            return pd.DataFrame(columns=["reach_id", "n_nodes", "outflow_dest", "name"])

    fig, ax = plot_stream_aquifer_exchange_map(NoStreams(m))   # today: IndexError boolean index mismatch


# ---------------------------------------------------------------- land use
HDR = ("C x\n        1.0        / FACTLNNP\n          1        / NSPLNNP\n"
       "          0        / NFQLNNP\n                   / DSSFL\nC  end\n")


def _block(date, n=5, off=0.0):
    return "".join(f"{(date if k == 0 else ''):>19}{e:7d}{10.0 + off + e:16.10g}{1.0:16.10g}\n"
                   for k, e in enumerate(range(1, n + 1)))


def test_land_use_block_missing_date_is_not_merged(tmp_path):
    from iwfm_io.readers.rootzone import read_land_use_area
    b2 = _block("09/30/1991_24:00", off=100)
    b2 = " " * 19 + b2[19:]     # drop block-2 date
    p = tmp_path / "lu.dat"
    p.write_text(HDR + _block("09/30/1990_24:00") + b2 + _block("09/30/1992_24:00", off=200))
    from iwfm_io import IWFMParseError
    with pytest.raises(IWFMParseError, match="appears twice"):
        read_land_use_area(p)                       # was: 5 dup pairs silently merged into 2 blocks


def test_write_land_use_area_rejects_non_block_major_frame(tmp_path):
    from iwfm_io.readers.rootzone import read_land_use_area
    from iwfm_io.writers.rootzone import write_land_use_area
    p = tmp_path / "lu.dat"
    p.write_text(HDR + _block("09/30/1990_24:00") + _block("09/30/1991_24:00", off=100))
    lu = read_land_use_area(p)
    lu.data = lu.data.sort_values(["element_id", "date"]).reset_index(drop=True)
    out = tmp_path / "out.dat"
    write_land_use_area(lu, out)
    from iwfm_io._tokens import is_iwfm_date
    dated = [ln for ln in out.read_text().splitlines() if ln.strip() and is_iwfm_date(ln.split()[0])]
    assert len(dated) == 2                          # was: 10 one-row "blocks" -> IWFM reads 10 timesteps
    assert read_land_use_area(out).data.equals(
        lu.data.sort_values(["date", "element_id"]).reset_index(drop=True))


def test_write_land_use_area_rejects_timestamp_dates(tmp_path):
    from iwfm_io.readers.rootzone import read_land_use_area
    from iwfm_io.writers.rootzone import write_land_use_area
    p = tmp_path / "lu.dat"
    p.write_text(HDR + _block("09/30/1990_24:00"))
    lu = read_land_use_area(p)
    lu.data["date"] = pd.Timestamp("1990-10-01")
    out = tmp_path / "out.dat"
    # decided: datetimes are formatted as IWFM stamps (midnight = 24:00
    # of the previous day); was: wrote '1990-10-01', unreadable by IWFM
    write_land_use_area(lu, out)
    back = read_land_use_area(out).data
    assert set(back["date"]) == {"09/30/1990_24:00"}
    lu.data["date"] = "1990-10-01"
    with pytest.raises(ValueError):
        write_land_use_area(lu, out)                # a non-IWFM date *string* is refused


def test_write_land_use_area_rejects_nan(tmp_path):
    from iwfm_io.readers.rootzone import read_land_use_area
    from iwfm_io.writers.rootzone import write_land_use_area
    p = tmp_path / "lu.dat"
    p.write_text(HDR + _block("09/30/1990_24:00"))
    lu = read_land_use_area(p)
    lu.data.loc[0, "area_1"] = np.nan
    with pytest.raises(ValueError):
        write_land_use_area(lu, tmp_path / "out.dat")   # today: literal 'nan' in the file


# ---------------------------------------------------------------- tokens
def test_expand_recurring_real_year_2100_not_treated_as_recurring():
    from iwfm_io._tokens import expand_recurring
    df = pd.DataFrame({"date": ["09/30/2098_24:00", "09/30/2099_24:00", "09/30/2100_24:00"], "v": [1, 2, 3]})
    out = expand_recurring(df, "10/01/2097_24:00", "09/30/2100_24:00")
    assert len(out) == 3                            # today: 9 rows, 3 values stacked on every stamp


def test_expand_recurring_keeps_value_in_effect_at_begin():
    from iwfm_io._tokens import expand_recurring
    df = pd.DataFrame({"date": ["01/31/4000_24:00", "06/30/4000_24:00"], "v": [1, 2]})
    out = expand_recurring(df, "03/01/1990_24:00", "05/31/1990_24:00")
    assert len(out) >= 1 and out["v"].iloc[0] == 1  # today: empty (step function loses the active value)


def test_parse_iwfm_date_rejects_minute_60():
    from iwfm_io._tokens import parse_iwfm_date
    with pytest.raises(ValueError):
        parse_iwfm_date("10/01/1990_24:60")         # today: -> 10/02 00:00


# ---------------------------------------------------------------- initial conditions
def test_write_gw_initial_conditions_honours_layer_number_not_column_order(tmp_path):
    from iwfm_io.writers.groundwater import write_gw_initial_conditions
    from iwfm_io.readers.text_output import read_final_state_out
    heads = pd.DataFrame({"node_id": [1, 2], "head_layer_2": [20.0, 21.0], "head_layer_1": [10.0, 11.0]})
    p = tmp_path / "ic.dat"
    write_gw_initial_conditions(p, heads)
    back = read_final_state_out(p)
    assert list(back["HP[1]"]) == [10.0, 11.0]      # today: HP[1] = layer-2 values


def test_write_gw_initial_conditions_rejects_layer_gap(tmp_path):
    from iwfm_io.writers.groundwater import write_gw_initial_conditions
    heads = pd.DataFrame({"node_id": [1], "head_layer_1": [10.0], "head_layer_3": [30.0]})
    with pytest.raises(ValueError):
        write_gw_initial_conditions(tmp_path / "ic.dat", heads)   # today: layer 3 written as HP[2]


def test_write_gw_initial_conditions_header_lines_are_comments(tmp_path):
    from iwfm_io.writers.groundwater import write_gw_initial_conditions
    from iwfm_io.readers.text_output import read_final_state_out
    heads = pd.DataFrame({"node_id": [1, 2], "head_layer_1": [10.0, 11.0]})
    p = tmp_path / "ic.dat"
    write_gw_initial_conditions(p, heads, header=["  indented banner", "two\nlines"])
    for ln in p.read_text().splitlines():
        if ln.strip() and not ln.lstrip()[0].isdigit():
            assert ln[0] in "Cc*", repr(ln)           # today: '  indented banner' and 'lines' are data lines
    back = read_final_state_out(p)
    assert list(back.columns) == ["ID", "HP[1]"]


def test_write_gw_initial_conditions_rejects_non_finite(tmp_path):
    from iwfm_io.writers.groundwater import write_gw_initial_conditions
    heads = pd.DataFrame({"node_id": [1], "head_layer_1": [np.inf]})
    with pytest.raises(ValueError):
        write_gw_initial_conditions(tmp_path / "ic.dat", heads)   # today: writes 'inf'


# ---------------------------------------------------------------- DSS
def test_dss_catalog_does_not_create_files(tmp_path):
    pytest.importorskip("pydsstools")
    from iwfm_io.dss import dss_catalog
    missing = tmp_path / "nope.dss"
    with pytest.raises(FileNotFoundError):
        dss_catalog(missing)
    assert not missing.exists()                     # today: empty catalog AND a 126 KB nope.dss is created


def test_read_dss_timeseries_handles_iwfm_year_4000_records(tmp_path, sample_model):
    pytest.importorskip("pydsstools")
    from iwfm_io.dss import dss_catalog, read_dss_timeseries
    src = sample_model / "Simulation" / "TSDATA_IN.DSS"
    if not src.is_file():
        pytest.skip("sample model has no TSDATA_IN.DSS")
    dss = tmp_path / "ts.dss"
    shutil.copy(src, dss)
    cat = dss_catalog(dss)
    df = read_dss_timeseries(dss, cat["condensed"].iloc[0])   # today: OutOfBoundsDatetime (4000-02-01)
    assert len(df)
