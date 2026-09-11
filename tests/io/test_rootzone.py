"""Tests for root zone component readers and writers."""


from tests.io.conftest import SIMULATION_DIR

RZ_DIR = SIMULATION_DIR / "RootZone"


class TestRootZoneMain:
    def test_read_rootzone_main(self):
        from iwfm_io.readers.rootzone import read_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            assert rz.header is not None
            assert rz.convergence > 0
            assert rz.max_iterations > 0
            # 13 core roles + version-dependent extras (v4.12 sample
            # adds area_scale and surface_flow_dest)
            assert len(rz.file_paths) >= 14

    def test_rootzone_file_paths(self):
        from iwfm_io.readers.rootzone import read_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            assert "nonponded_ag" in rz.file_paths
            assert "urban" in rz.file_paths
            assert "native_veg" in rz.file_paths

    def test_rootzone_round_trip(self, tmp_output):
        from iwfm_io.readers.rootzone import read_rootzone_main
        from iwfm_io.writers.rootzone import write_rootzone_main

        path = RZ_DIR / "RootZone_MAIN.dat"
        if path.exists():
            rz = read_rootzone_main(path)
            out = tmp_output / "RootZone_MAIN.dat"
            write_rootzone_main(rz, out)
            assert out.exists()

            rz2 = read_rootzone_main(out)
            assert rz2.convergence == rz.convergence
            assert rz2.max_iterations == rz.max_iterations
            assert rz2.gw_uptake == rz.gw_uptake


class TestNonPondedCropNames:
    NP_MAIN = RZ_DIR / "NonPondedAg" / "NonPondedAg_MAIN.dat"

    def test_crop_names_on_sample_model(self):
        from iwfm_io.readers.rootzone import read_nonponded_ag_main

        if self.NP_MAIN.exists():
            np_ag = read_nonponded_ag_main(self.NP_MAIN)
            assert set(np_ag.crop_names) == set(np_ag.crop_codes)
            # sample deck carries bare CCODE[n] tags, no descriptions
            assert all(v == "" for v in np_ag.crop_names.values())

    def test_keyed_codes_formats(self, tmp_output):
        # Both in-the-wild comment formats (issue #28): C2VSimFG
        # repeats the CCODE[n] tag before the name; YGM-style decks
        # carry the bare name. Codes starting with C (CO, CN, ...) are
        # data because the comment test applies to column 1 of the raw
        # line only.
        from iwfm_io._parser import IWFMFileReader
        from iwfm_io.readers.rootzone import _read_keyed_codes

        path = tmp_output / "codes.dat"
        path.write_text(
            "C  test deck\n"
            "    GR         / CCODE[ 1]  Grain\n"
            "    CO         / CCODE[ 2]  Cotton\n"
            "    01         / Almonds\n"
            "    02         / CCODE[4]\n"
        )
        reader = IWFMFileReader(path)
        reader.read_header()
        codes, names = _read_keyed_codes(reader, 4)
        assert codes == ["GR", "CO", "01", "02"]
        assert names == ["Grain", "Cotton", "Almonds", ""]

    def test_crop_names_round_trip(self, tmp_output):
        from iwfm_io.readers.rootzone import read_nonponded_ag_main
        from iwfm_io.writers.rootzone import write_nonponded_ag_main

        if self.NP_MAIN.exists():
            np_ag = read_nonponded_ag_main(self.NP_MAIN)
            np_ag.crop_names = {
                c: f"Crop {c}" for c in np_ag.crop_codes}
            out = tmp_output / "NonPondedAg_MAIN.dat"
            write_nonponded_ag_main(np_ag, out)

            np_ag2 = read_nonponded_ag_main(out)
            assert np_ag2.crop_codes == np_ag.crop_codes
            assert np_ag2.crop_names == np_ag.crop_names


class TestIrrPeriod:
    IP_FILE = RZ_DIR / "IrigPeriod.dat"

    def test_read_irr_period(self):
        from iwfm_io import read_irr_period

        if self.IP_FILE.exists():
            ip = read_irr_period(self.IP_FILE)
            assert ip.n_columns == 4
            assert ip.data is not None
            assert list(ip.data.columns) == [
                "date", "col_1", "col_2", "col_3", "col_4"]
            assert len(ip.data) == 12  # recurring year-4000 pattern
            flags = ip.data[["col_1", "col_2", "col_3", "col_4"]]
            assert flags.isin([0, 1]).all().all()
            assert ip.data["date"].str.contains("4000").all()

    def test_irr_period_round_trip(self, tmp_output):
        import pandas as pd
        from iwfm_io import read_irr_period, write_irr_period

        if self.IP_FILE.exists():
            ip = read_irr_period(self.IP_FILE)
            out = tmp_output / "IrigPeriod.dat"
            write_irr_period(ip, out)

            ip2 = read_irr_period(out)
            assert ip2.n_columns == ip.n_columns
            assert ip2.n_steps_update == ip.n_steps_update
            assert ip2.repeat_freq == ip.repeat_freq
            pd.testing.assert_frame_equal(ip2.data, ip.data)
