"""Tests for the scenario builder (cross-platform — no executables run)."""

import pytest

from iwfm.io import (
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
