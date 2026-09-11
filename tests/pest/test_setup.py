"""Tests for the PestSetup capstone builder (iwfm_io.pest.setup).

The end-to-end class runs a toy two-parameter problem through the real
pestpp-ies executable when one is available locally (skipped otherwise
— e.g. in CI).
"""

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PESTPP_IES = Path(r"C:\Projects\Calsim_PEST28_new\pestpp-ies.exe")


def _toy_setup():
    from iwfm_io.pest import ObsFileSpec, ParamSpec, PestSetup, build_parameters

    bundle = build_parameters([
        ParamSpec(name="slope", values_file="mult_a.csv",
                  keys=pd.DataFrame({"id": [1]}), transform="none",
                  lower=0.1, upper=10.0, initial=1.0),
        ParamSpec(name="intercept", values_file="mult_b.csv",
                  keys=pd.DataFrame({"id": [1]}), transform="none",
                  lower=0.1, upper=10.0, initial=1.0),
    ])
    names = ["toy_p1", "toy_p2", "toy_p3"]
    spec = ObsFileSpec(names)
    obs = spec.obs_data(values=[3.0, 5.0, 7.0], weight=1.0, group="toy")

    s = PestSetup("toycase")
    s.add_parameters(bundle)
    s.add_observations(obs, spec, output_file="toy_out.dat")
    s.add_run_step("toy model", f'"{sys.executable}" toy_model.py')
    return s, spec


_TOY_MODEL = '''\
import pandas as pd
from iwfm_io.pest import ObsFileSpec
a = pd.read_csv("mult_a.csv")["value"].iloc[0]
b = pd.read_csv("mult_b.csv")["value"].iloc[0]
spec = ObsFileSpec(["toy_p1", "toy_p2", "toy_p3"])
spec.write_output([a * x + b for x in (1.0, 2.0, 3.0)], "toy_out.dat")
'''


class TestWrite:
    def test_template_structure(self, tmp_path):
        s, spec = _toy_setup()
        dest = s.write(tmp_path / "t")
        for f in ["toycase.pst", "toycase_par_data.csv",
                  "toycase_pargp_data.csv", "toycase_obs_data.csv",
                  "mult_a.csv", "mult_a.csv.tpl", "mult_b.csv",
                  "mult_b.csv.tpl", "toy_out.dat.ins", "forward_run.py"]:
            assert (dest / f).is_file(), f
        pst = (dest / "toycase.pst").read_text()
        assert "pcf version=2" in pst
        assert "mult_a.csv.tpl  mult_a.csv" in pst
        assert "toy_out.dat.ins  toy_out.dat" in pst
        par = pd.read_csv(dest / "toycase_par_data.csv")
        assert par["parnme"].tolist() == ["slope", "intercept"]

    def test_forward_run_produces_matching_output(self, tmp_path):
        s, spec = _toy_setup()
        dest = s.write(tmp_path / "t")
        (dest / "toy_model.py").write_text(_TOY_MODEL)
        r = subprocess.run([sys.executable, "forward_run.py"], cwd=dest,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        # initial parameters are 1.0 -> y = x + 1
        out = spec.read_output(dest / "toy_out.dat")
        assert out.values == pytest.approx([2.0, 3.0, 4.0])

    def test_validation_errors(self, tmp_path):
        from iwfm_io.pest import PestSetup

        s, spec = _toy_setup()
        with pytest.raises(ValueError, match="mismatch"):
            s.add_observations(
                spec.obs_data().assign(obsnme=["a_1", "a_2", "a_3"]),
                spec, "o.dat")
        empty = PestSetup("x")
        with pytest.raises(ValueError, match="no parameters"):
            empty.write(tmp_path / "e")

    def test_duplicate_obs_rejected(self, tmp_path):
        s, spec = _toy_setup()
        s.add_observations(spec.obs_data(group="again"), spec, "o2.dat")
        with pytest.raises(ValueError, match="duplicate observation"):
            s.write(tmp_path / "d")


@pytest.mark.skipif(not PESTPP_IES.is_file(),
                    reason="pestpp-ies.exe not available locally")
class TestEndToEndPestpp:
    def test_base_run_through_real_pestpp(self, tmp_path):
        from iwfm_io.pest import load_ies_ensembles, rei_stats

        s, spec = _toy_setup()
        s.control_data["noptmax"] = 0
        dest = s.write(tmp_path / "run")
        (dest / "toy_model.py").write_text(_TOY_MODEL)

        r = subprocess.run([str(PESTPP_IES), "toycase.pst"], cwd=dest,
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, (r.stdout[-2000:] + r.stderr[-2000:])
        rei_files = list(dest.glob("*.rei"))
        assert rei_files, "pestpp-ies wrote no residual file"

        results = load_ies_ensembles(dest / "toycase.pst")
        rei = results.base_rei() if results.rei_files else None
        if rei is None:
            from iwfm_io.pest import read_rei
            rei = read_rei(rei_files[0])
        rei = rei.set_index("name")
        # initial run: y = x + 1 -> 2, 3, 4 vs obs 3, 5, 7
        assert rei.loc["toy_p1", "modelled"] == pytest.approx(2.0)
        assert rei.loc["toy_p3", "residual"] == pytest.approx(3.0)
        st = rei_stats(rei.reset_index())
        assert st.iloc[0]["n"] == 3
