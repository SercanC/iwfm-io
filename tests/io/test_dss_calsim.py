"""Tests for HEC-DSS reading + CalSim channel linking (iwfm_io.dss)."""

import numpy as np
import pandas as pd
import pytest

AF_PER_CFS_DAY = 86400.0 / 43560.0


def _metadata(**kw):
    base = {
        "gauge_id": ["g1", "g2", "g3"],
        "calsim_bpart": ["C_SAC041", "c_amr004", "C_MOK022"],
    }
    base.update(kw)
    return pd.DataFrame(base)


def _catalog():
    """Synthetic dss_catalog frame: 2 arcs (one in 2 blocks), 1 non-arc."""
    from iwfm_io.dss import dss_catalog  # noqa: F401 (import check)

    rows = [
        ("/CALSIM/C_SAC041/CHANNEL/01Jan1920/1Month/L2020A/",),
        ("/CALSIM/C_SAC041/CHANNEL/01Jan1930/1Month/L2020A/",),
        ("/CALSIM/C_AMR004/CHANNEL/01Jan1920/1Month/L2020A/",),
        ("/CALSIM/D_SAC041/DIVERSION/01Jan1920/1Month/L2020A/",),
        ("/CALSIM/C_ORPHAN/CHANNEL/01Jan1920/1Month/L2020A/",),
    ]
    recs = []
    for (p,) in rows:
        _, a, b, c, d, e, f, _ = p.split("/")
        recs.append({"pathname": p, "a": a, "b": b, "c": c, "d": d,
                     "e": e, "f": f, "condensed": f"/{a}/{b}/{c}//{e}/{f}/"})
    return pd.DataFrame(recs)


class TestLinkCalsimChannels:
    def test_link_case_insensitive_and_blocks_collapse(self):
        from iwfm_io.dss import link_calsim_channels

        link = link_calsim_channels(_metadata(), _catalog())
        s = link.summary()
        assert s["n_gauges_linked"] == 2          # g3 has no record
        assert link.unmatched_gauges == ["g3"]
        assert link.orphan_arcs == ["C_ORPHAN"]   # D_SAC041 not an arc
        row = link.links.set_index("gauge_id")
        assert row.loc["g1", "pathname"] == \
            "/CALSIM/C_SAC041/CHANNEL//1Month/L2020A/"
        assert row.loc["g2", "bpart"] == "C_AMR004"

    def test_dss_path_override(self):
        from iwfm_io.dss import link_calsim_channels

        md = _metadata(dss_path=[None, None,
                                 "/CALSIM/X_SPECIAL/FLOW//1Month/L2020A/"])
        link = link_calsim_channels(md, _catalog())
        row = link.links.set_index("gauge_id")
        assert row.loc["g3", "bpart"] == "X_SPECIAL"
        assert link.unmatched_gauges == []

    def test_ambiguous_bpart_and_fpart_filter(self):
        from iwfm_io.dss import link_calsim_channels

        cat = _catalog()
        extra = cat.iloc[[0]].copy()
        extra["f"] = "L2035A"
        extra["pathname"] = extra["condensed"] = \
            "/CALSIM/C_SAC041/CHANNEL//1Month/L2035A/"
        cat2 = pd.concat([cat, extra], ignore_index=True)
        with pytest.raises(ValueError, match="cpart=/epart=/fpart="):
            link_calsim_channels(_metadata(), cat2)
        link = link_calsim_channels(_metadata(), cat2, fpart="l2020a")
        assert link.summary()["n_gauges_linked"] == 2

    def test_bad_metadata_raises(self):
        from iwfm_io.dss import link_calsim_channels

        with pytest.raises(ValueError, match="no column"):
            link_calsim_channels(pd.DataFrame({"gauge_id": ["g1"]}),
                                 _catalog())
        md = _metadata(calsim_bpart=["C_SAC041", "C_SAC041", "x"])
        with pytest.raises(ValueError, match="duplicate value"):
            link_calsim_channels(md, _catalog())

    def test_overfiltered_catalog_raises(self):
        from iwfm_io.dss import link_calsim_channels

        with pytest.raises(ValueError, match="filters"):
            link_calsim_channels(_metadata(), _catalog(), cpart="STORAGE")


class TestCfsToTaf:
    def test_known_months(self):
        from iwfm_io.dss import cfs_to_taf

        # end-of-period stamps: Feb 1 covers January (31 d), Mar 1
        # covers February 1921 (28 d)
        idx = pd.to_datetime(["1921-02-01", "1921-03-01"])
        out = cfs_to_taf(pd.DataFrame({"q": [1.0, 100.0]}, index=idx))
        assert out["q"].iloc[0] == pytest.approx(31 * AF_PER_CFS_DAY / 1000)
        assert out["q"].iloc[1] == pytest.approx(
            100 * 28 * AF_PER_CFS_DAY / 1000)


# ---------------------------------------------------------------------------
# Round-trip through a real DSS file (needs the optional pydsstools)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dss_file(tmp_path_factory):
    """Synthetic CalSim-style DV file: 2 channel arcs, 24 months."""
    pytest.importorskip("pydsstools")
    from pydsstools.heclib.dss.HecDss import Open
    from pydsstools.core import TimeSeriesContainer

    path = tmp_path_factory.mktemp("dss") / "DV.dss"
    with Open(str(path)) as fid:
        for bpart, scale in (("C_SAC041", 1.0), ("C_AMR004", 10.0)):
            vals = [scale * (i + 1) for i in range(24)]
            tsc = TimeSeriesContainer(
                f"/CALSIM/{bpart}/CHANNEL//1MON/L2020A/",
                len(vals), 1, values=vals,
                start_time="31JAN1921 2400",
                data_units="CFS", data_type="PER-AVER")
            fid.put_ts(tsc)
    return path


class TestDssRoundtrip:
    def test_catalog(self, dss_file):
        from iwfm_io.dss import dss_catalog

        cat = dss_catalog(dss_file)
        assert set(cat["b"]) == {"C_SAC041", "C_AMR004"}
        assert (cat["c"] == "CHANNEL").all()
        sac = cat[cat["b"] == "C_SAC041"]
        assert (sac["condensed"] ==
                "/CALSIM/C_SAC041/CHANNEL//1Month/L2020A/").all()

    def test_read_timeseries(self, dss_file):
        from iwfm_io.dss import dss_catalog, read_dss_timeseries

        cat = dss_catalog(dss_file)
        paths = sorted(cat["condensed"].unique())
        frame = read_dss_timeseries(dss_file, paths)
        assert frame.shape == (24, 2)
        # end-of-period convention: Jan 1921 value stamped Feb 1 1921
        assert frame.index[0] == pd.Timestamp("1921-02-01")
        assert frame.index[-1] == pd.Timestamp("1923-01-01")
        sac = frame["/CALSIM/C_SAC041/CHANNEL//1Month/L2020A/"]
        assert np.allclose(sac.values, np.arange(1.0, 25.0))
        assert frame.attrs["units"][paths[0]] == "CFS"
        assert frame.attrs["data_type"][paths[0]] == "PER-AVER"

    def test_link_and_extract(self, dss_file):
        from iwfm_io.dss import (link_calsim_channels,
                                 calsim_streamflow_series)

        link = link_calsim_channels(_metadata(), dss_file)
        assert link.summary()["n_gauges_linked"] == 2
        assert link.unmatched_gauges == ["g3"]

        cfs = calsim_streamflow_series(link, dss_file)
        assert list(cfs.columns) == ["g1", "g2"]
        assert cfs["g2"].iloc[0] == pytest.approx(10.0)

        taf = calsim_streamflow_series(link, dss_file, units="taf")
        # Jan 1921: 1 cfs avg over 31 days
        assert taf["g1"].iloc[0] == pytest.approx(
            31 * AF_PER_CFS_DAY / 1000)
        # Feb 1921 (28 days), stamped Mar 1
        assert taf.index[1] == pd.Timestamp("1921-03-01")
        assert taf["g1"].iloc[1] == pytest.approx(
            2 * 28 * AF_PER_CFS_DAY / 1000)

    def test_units_guard(self, dss_file):
        from pydsstools.heclib.dss.HecDss import Open
        from pydsstools.core import TimeSeriesContainer
        from iwfm_io.dss import (link_calsim_channels,
                                 calsim_streamflow_series)

        with Open(str(dss_file)) as fid:
            tsc = TimeSeriesContainer(
                "/CALSIM/C_STAGE01/CHANNEL//1MON/L2020A/",
                3, 1, values=[1.0, 2.0, 3.0],
                start_time="31JAN1921 2400",
                data_units="FEET", data_type="PER-AVER")
            fid.put_ts(tsc)
        md = pd.DataFrame({"gauge_id": ["s1"],
                           "calsim_bpart": ["C_STAGE01"]})
        link = link_calsim_channels(md, dss_file)
        with pytest.raises(ValueError, match="expects CFS"):
            calsim_streamflow_series(link, dss_file, units="taf")
