"""Tests for the scenario builder (cross-platform — no executables run)."""

import pytest

from iwfm_io import (
    create_scenario,
    read_simulation,
    replace_text,
    set_keyed_value,
)

from .conftest import SAMPLE_MODEL

pytestmark = pytest.mark.skipif(
    not SAMPLE_MODEL.is_dir(), reason="sample model not present (.assets/sample_model)")


def test_create_scenario_copies_inputs(tmp_path):
    out = create_scenario(SAMPLE_MODEL, tmp_path / "scen")
    assert (out / "Preprocessor" / "PreProcessor_MAIN.IN").is_file()
    assert (out / "Simulation" / "Simulation_MAIN.IN").is_file()
    assert (out / "Bin").is_dir()
    assert (out / "Results").is_dir()          # created empty for outputs
    assert not any((out / "Results").iterdir())


def test_create_scenario_refuses_existing(tmp_path):
    create_scenario(SAMPLE_MODEL, tmp_path / "scen", subdirs=("Preprocessor",))
    with pytest.raises(FileExistsError):
        create_scenario(SAMPLE_MODEL, tmp_path / "scen",
                        subdirs=("Preprocessor",))
    # overwrite=True replaces it
    out = create_scenario(SAMPLE_MODEL, tmp_path / "scen",
                          subdirs=("Preprocessor",), overwrite=True)
    assert (out / "Preprocessor").is_dir()


def test_set_keyed_value_changes_sim_end(tmp_path):
    out = create_scenario(
        SAMPLE_MODEL, tmp_path / "scen", subdirs=("Simulation",),
        changes=[set_keyed_value("Simulation/Simulation_MAIN.IN",
                                 "EDT", "09/30/1995_24:00")],
    )
    sim = read_simulation(out / "Simulation" / "Simulation_MAIN.IN")
    assert sim.sim_end == "09/30/1995_24:00"
    assert sim.sim_begin == "09/30/1990_24:00"  # untouched


def test_set_keyed_value_unknown_keyword(tmp_path):
    with pytest.raises(ValueError, match="NOSUCHKEY"):
        create_scenario(
            SAMPLE_MODEL, tmp_path / "scen", subdirs=("Simulation",),
            changes=[set_keyed_value("Simulation/Simulation_MAIN.IN",
                                     "NOSUCHKEY", "1")],
        )


def test_link_unchanged_hardlinks_and_copy_on_change(tmp_path):
    # Real-copied base inside tmp_path so base and scenario are
    # guaranteed to sit on the same filesystem (hardlinks possible).
    base = create_scenario(SAMPLE_MODEL, tmp_path / "base",
                           subdirs=("Simulation",))
    scen = create_scenario(
        base, tmp_path / "scen", subdirs=("Simulation",),
        link_unchanged=True,
        changes=[set_keyed_value("Simulation/Simulation_MAIN.IN",
                                 "EDT", "09/30/1995_24:00")],
    )
    # Untouched input files are hardlinks of the base's files
    linked = base / "Simulation" / "Groundwater" / "GW_MAIN.IN"
    if not linked.is_file():
        linked = next(p for p in (base / "Simulation").rglob("*.dat"))
    assert (scen / linked.relative_to(base)).samefile(linked)
    # The changed file is an independent copy; the base is untouched
    changed = "Simulation/Simulation_MAIN.IN"
    assert not (scen / changed).samefile(base / changed)
    assert read_simulation(scen / changed).sim_end == "09/30/1995_24:00"
    assert read_simulation(base / changed).sim_end != "09/30/1995_24:00"
    # Run-rewritten file types are never linked
    for p in (scen / "Simulation").rglob("*"):
        if p.is_file() and p.suffix.lower() in (".out", ".bin", ".bud",
                                                ".log", ".dss", ".hdf",
                                                ".h5"):
            assert not p.samefile(base / p.relative_to(scen))
    # Results is a real empty directory
    assert (scen / "Results").is_dir()
    assert not any((scen / "Results").iterdir())


def test_link_unchanged_falls_back_to_copy(tmp_path, monkeypatch, caplog):
    import os

    def _fail_link(src, dst):
        raise OSError("cross-device link")

    monkeypatch.setattr(os, "link", _fail_link)
    base = create_scenario(SAMPLE_MODEL, tmp_path / "base",
                           subdirs=("Simulation",))
    with caplog.at_level("WARNING", logger="iwfm_io.scenario"):
        scen = create_scenario(base, tmp_path / "scen",
                               subdirs=("Simulation",), link_unchanged=True)
    assert any("falling back to copying" in r.getMessage()
               for r in caplog.records)
    main = "Simulation/Simulation_MAIN.IN"
    assert not (scen / main).samefile(base / main)   # real copy, not link
    assert (scen / main).read_text() == (base / main).read_text()


def test_replace_text(tmp_path):
    out = create_scenario(
        SAMPLE_MODEL, tmp_path / "scen", subdirs=("Preprocessor",),
        changes=[replace_text("Preprocessor/PreProcessor_MAIN.IN",
                              "PreProcessor", "PreProcessor")],
    )
    assert out.is_dir()
    with pytest.raises(ValueError, match="not found"):
        create_scenario(
            SAMPLE_MODEL, tmp_path / "scen2", subdirs=("Preprocessor",),
            changes=[replace_text("Preprocessor/PreProcessor_MAIN.IN",
                                  "text-that-does-not-exist", "x")],
        )


# ---------------------------------------------------------------------------
# hardening (2.13.0): destructive-path guard, output skip, atomic cleanup,
# value-span replacement
# ---------------------------------------------------------------------------

def test_refuses_identical_and_nested_paths(tmp_path):
    base = create_scenario(SAMPLE_MODEL, tmp_path / "base",
                           subdirs=("Preprocessor", "Simulation"))
    with pytest.raises(ValueError, match="base model itself"):
        create_scenario(base, base, overwrite=True)
    with pytest.raises(ValueError, match="inside the base model"):
        create_scenario(base, base / "Simulation" / "scen")
    with pytest.raises(ValueError, match="contains the base model"):
        create_scenario(base, tmp_path, overwrite=True)
    # nothing was deleted
    assert (base / "Simulation").is_dir()


def test_baseline_outputs_not_copied_by_default(tmp_path):
    scen = create_scenario(SAMPLE_MODEL, tmp_path / "scen")
    assert (scen / "Budget" / "Budget.in").is_file()
    assert (scen / "ZBudget" / "ZBudget.in").is_file()
    assert not list((scen / "Budget").glob("*.bud"))
    assert not list((scen / "ZBudget").glob("*.bud"))
    assert not list((scen / "Budget").glob("*Messages.out"))
    from iwfm_io import open_model
    assert open_model(scen).describe()["results"]["budgets"] == {}
    scen2 = create_scenario(SAMPLE_MODEL, tmp_path / "scen2",
                            copy_outputs=True)
    assert list((scen2 / "Budget").glob("*.bud"))


def test_failed_change_removes_partial_scenario(tmp_path):
    def boom(root):
        raise RuntimeError("change failed")
    out = tmp_path / "scen"
    with pytest.raises(RuntimeError, match="change failed"):
        create_scenario(SAMPLE_MODEL, out, subdirs=("Preprocessor",),
                        changes=[boom])
    assert not out.exists()


def test_set_keyed_value_replaces_only_the_value(tmp_path):
    f = tmp_path / "x.dat"
    f.write_text("C header\n   1   / NOUTF   1 = on, 0 = off\n")
    set_keyed_value("x.dat", "NOUTF", 0)(tmp_path)
    assert f.read_text() == "C header\n   0   / NOUTF   1 = on, 0 = off\n"


def test_set_keyed_value_sets_blank_entry(tmp_path):
    f = tmp_path / "x.dat"
    f.write_text("C header\n/  HTPOUTFL\n")
    set_keyed_value("x.dat", "HTPOUTFL", "Results/htp.out")(tmp_path)
    from iwfm_io._tokens import split_keyed_line
    line = f.read_text().splitlines()[1]
    assert split_keyed_line(line) == ("Results/htp.out", "HTPOUTFL")


def test_set_keyed_value_rejects_newline_and_escape():
    with pytest.raises(ValueError, match="single line"):
        set_keyed_value("x.dat", "BDT", "10/01/1990_24:00\n 1 / RESTART")


def test_change_outside_scenario_rejected(tmp_path):
    (tmp_path / "scen").mkdir()
    with pytest.raises(ValueError, match="outside the scenario"):
        set_keyed_value("../other.dat", "BDT", "x")(tmp_path / "scen")


def test_legacy_bytes_survive_edit(tmp_path):
    f = tmp_path / "x.dat"
    f.write_bytes(b"C  Zone \xe9t\xe9\r\n   5   / ND\r\n")
    set_keyed_value("x.dat", "ND", 6)(tmp_path)
    assert f.read_bytes() == b"C  Zone \xe9t\xe9\r\n   6   / ND\r\n"
