"""Shared fixtures for iwfm_io.pest tests."""

import pandas as pd
import pytest

CASE = "demo_ies"


@pytest.fixture
def ies_dir(tmp_path):
    """Synthesize a small but complete PESTPP-IES output set.

    Mirrors real PESTPP-IES formats: realization columns in phi CSVs
    (with NaN holes for dropped realizations and a trailing comma),
    real_name-indexed ensemble CSVs (fewer rows in later iterations),
    a group-phi CSV, pdc, obs+noise, and a CRLF .base.rei.
    """
    d = tmp_path / "master"
    d.mkdir()
    (d / f"{CASE}.pst").write_text("pcf\n")

    # parameter ensembles: iterations 0..2; real 7 dropped after iter 0
    for it, reals in [(0, ["0", "7", "base"]), (1, ["0", "base"]),
                      (2, ["0", "base"])]:
        rows = [f"{r},{1.0 + it + i},{10.0 * (i + 1)}"
                for i, r in enumerate(reals)]
        (d / f"{CASE}.{it}.par.csv").write_text(
            "real_name,par1,par2\n" + "\n".join(rows) + "\n")

    # observation ensembles: iteration 1 missing (partial run)
    for it, reals in [(0, ["0", "7", "base"]), (2, ["0", "base"])]:
        rows = [f"{r},{100.0 + it + i},{200.0 + i},{300.0 + i}"
                for i, r in enumerate(reals)]
        (d / f"{CASE}.{it}.obs.csv").write_text(
            "real_name,gwh_w1_20001031,gwh_w2_20001031,bud_sr01\n"
            + "\n".join(rows) + "\n")

    # phi CSVs: trailing comma, hole for dropped real 7 after iter 0
    (d / f"{CASE}.phi.composite.csv").write_text(
        "iteration,total_runs,mean,standard_deviation,min,max,0,7,base,\n"
        "0,3,55,5,50,60,60,55,50,\n"
        "1,2,30,5,25,35,35,,25,\n"
        "2,2,20,5,15,25,15,,25,\n")
    (d / f"{CASE}.phi.actual.csv").write_text(
        "iteration,total_runs,mean,standard_deviation,min,max,0,7,base,\n"
        "0,3,155,5,150,160,160,155,150,\n"
        "2,2,120,5,115,125,115,,125,\n")

    (d / f"{CASE}.phi.group.csv").write_text(
        "iteration,total_runs,obs_realization,par_realization,gwh01,bud\n"
        "0,3,0,0,40,20\n"
        "0,3,base,base,30,20\n"
        "2,2,base,base,10,15\n")

    (d / f"{CASE}.pdc.csv").write_text(
        "name,obs_mean,obs_std,sim_mean,sim_std,distance\n"
        "gwh_w1_20001031,386.7,0.0,409.5,0.6,20.2\n")

    (d / f"{CASE}.obs+noise.csv").write_text(
        "real_name,gwh_w1_20001031,gwh_w2_20001031,bud_sr01\n"
        "0,101.0,201.0,301.0\nbase,100.0,200.0,300.0\n")

    (d / f"{CASE}.2.base.rei").write_text(
        " MODEL OUTPUTS AT END OF OPTIMISATION ITERATION NO. 2:-\r\n"
        "\r\n\r\n"
        " Name  Group  Measured  Modelled  Residual  Weight\r\n"
        " gwh_w1_20001031 gwh01 386.69 409.36 -22.67 0.0034\r\n"
        " bud_sr01 bud 300.0 301.0 -1.0 1.0\r\n")
    return d
