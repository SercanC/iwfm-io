"""The shipped API index must match the code it indexes.

The index exists so that an agent (or a person) can ask "does iwfm-io
already do this?" in one command instead of reimplementing a reader.
That only works while it is complete and current, so these tests fail
when a public name is added without regenerating it::

    python -m iwfm_io._api_index --write
"""
from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

import iwfm_io
from iwfm_io import _api_index
from iwfm_io.cli import main


def _live_entries():
    """Introspect the package, skipping if a subpackage cannot import.

    Generating the index needs ``plots``, ``pest`` and ``dll`` (the
    ctypes layer imports fine without a DLL, on any OS). If one of them
    ever stops importing, skip rather than report drift that isn't.
    """
    for module in ("iwfm_io.plots", "iwfm_io.pest", "iwfm_io.dll"):
        pytest.importorskip(module)
    return _api_index.collect_entries()


def test_index_is_current():
    """The shipped file equals what the live package generates."""
    shipped = _api_index.index_path()
    assert shipped.exists(), (
        f"{shipped} is missing - regenerate it with "
        f"`python -m iwfm_io._api_index --write`")
    _live_entries()          # skips if a subpackage cannot import
    assert shipped.read_text(encoding="utf-8") == _api_index.build_index(), (
        "the API index has drifted from the code - regenerate it with "
        "`python -m iwfm_io._api_index --write`")


def test_docs_copy_matches():
    """docs/API_INDEX.md is the same file (it is the browsable copy)."""
    docs = (_api_index.index_path().resolve().parent.parent / "docs"
            / _api_index.INDEX_FILENAME)
    if not docs.parent.is_dir():           # installed wheel, no docs tree
        pytest.skip("no docs/ directory (running against an install)")
    assert docs.read_text(encoding="utf-8") == \
        _api_index.index_path().read_text(encoding="utf-8")


def test_every_entry_round_trips():
    """Nothing is lost between rendering the index and searching it.

    ``search()`` reads the rendered file back, so a line the parser
    cannot match is a name that silently cannot be found.
    """
    built = _live_entries()
    parsed = _api_index._index_entries()
    assert len(parsed) == len(built)
    assert {e.parent + e.qualname for e in parsed} == \
        {e.parent + e.qualname for e in built}


def test_all_is_complete():
    """Every public top-level attribute is exported in ``__all__``.

    ``open_model`` itself was missing from ``__all__`` when the API
    index was built, which hid the package's main entry point from
    ``import *`` and from every tool that introspects the namespace.
    """
    exported = set(iwfm_io.__all__)
    public = {name for name, obj in vars(iwfm_io).items()
              if not name.startswith("_") and not inspect.ismodule(obj)}
    assert public - exported == set()
    assert [n for n in iwfm_io.__all__ if not hasattr(iwfm_io, n)] == []
    assert len(iwfm_io.__all__) == len(set(iwfm_io.__all__))


def test_no_entry_falls_outside_a_group():
    """A new module must be given an intent group in ``GROUPS``."""
    stray = sorted(e.parent + e.qualname
                   for e in _live_entries()
                   if e.group == "Other")
    assert stray == [], (
        f"these names have no intent group - add their module to "
        f"iwfm_io._api_index.GROUPS: {stray}")


def test_index_is_ascii():
    """cp1252 consoles (a redirected stdout on Windows) must render it."""
    text = _api_index.index_path().read_text(encoding="utf-8")
    text.encode("ascii")


@pytest.mark.parametrize("query, expected", [
    ("water year", "water_year"),
    ("land use", "read_land_use_area"),
    ("depth to water", "plots.maps.plot_depth_to_water"),
    ("scenario", "create_scenario"),
    ("smp", "pest.read_smp"),
    ("recurring", "expand_recurring"),
])
def test_search_finds_the_obvious(query, expected):
    """The searches an agent would actually type reach the right name."""
    hits = {e.parent + e.qualname for e in _api_index.search(query)}
    assert expected in hits


def test_search_without_query_returns_everything():
    assert len(_api_index.search()) == len(_live_entries())


def test_cli_api_command(capsys):
    assert main(["api", "water", "year"]) == 0
    assert "water_year" in capsys.readouterr().out

    assert main(["api", "--path"]) == 0
    assert _api_index.INDEX_FILENAME in capsys.readouterr().out

    # A miss exits non-zero and says it is fine to write your own.
    assert main(["api", "notafunctionanywhere"]) == 1
    assert "no iwfm-io name matches" in capsys.readouterr().out


def test_cli_api_no_query_prints_index(capsys):
    assert main(["api"]) == 0
    out = capsys.readouterr().out
    assert "# iwfm-io API index" in out
    assert "open_model" in out


def test_find_is_importable_and_prints(capsys):
    hits = iwfm_io.find("water year")
    assert hits
    assert "water_year" in capsys.readouterr().out


def test_module_runs_as_a_script():
    """``python -m iwfm_io._api_index`` prints the index."""
    result = subprocess.run(
        [sys.executable, "-m", "iwfm_io._api_index"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr
    assert "# iwfm-io API index" in result.stdout


# ------------------------------------------------------- init-agent block
def test_agent_rules_block_ships_and_is_self_contained():
    from iwfm_io.cli import agent_rules_path

    text = agent_rules_path().read_text(encoding="utf-8")
    assert text.lstrip().startswith("<!-- iwfm-io:begin")
    assert text.rstrip().endswith("<!-- iwfm-io:end -->")
    # The commands it tells the reader to run must exist.
    for command in ("iwfm-io api", "open_model", "aggregate_budget"):
        assert command in text


def test_init_agent_creates_updates_and_is_idempotent(tmp_path, capsys):
    from iwfm_io.cli import agent_rules_path

    target = tmp_path / "CLAUDE.md"

    assert main(["init-agent", str(tmp_path)]) == 0
    assert "created" in capsys.readouterr().out
    assert "iwfm-io:begin" in target.read_text(encoding="utf-8")

    # Re-running an unchanged block changes nothing.
    before = target.read_text(encoding="utf-8")
    assert main(["init-agent", str(tmp_path)]) == 0
    assert "already up to date" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == before

    # An existing file keeps its own content; the block is appended once.
    target.write_text("# Project\n\nOur own rules.\n", encoding="utf-8")
    assert main(["init-agent", str(tmp_path)]) == 0
    assert main(["init-agent", str(tmp_path)]) == 0
    text = target.read_text(encoding="utf-8")
    assert text.count("iwfm-io:begin") == 1
    assert "Our own rules." in text

    # A stale block is replaced in place, not duplicated.
    target.write_text(
        "# Project\n\nOur own rules.\n\n<!-- iwfm-io:begin -->\nold\n"
        "<!-- iwfm-io:end -->\n\nTrailing notes.\n", encoding="utf-8")
    assert main(["init-agent", str(tmp_path)]) == 0
    assert "updated" in capsys.readouterr().out
    text = target.read_text(encoding="utf-8")
    assert "old" not in text
    assert text.count("iwfm-io:begin") == 1
    assert "Our own rules." in text and "Trailing notes." in text
    assert agent_rules_path().read_text(
        encoding="utf-8").strip() in text


def test_init_agent_honours_file_and_print(tmp_path, capsys):
    assert main(["init-agent", str(tmp_path), "--file", "AGENTS.md"]) == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()

    assert main(["init-agent", str(tmp_path), "--print"]) == 0
    assert "iwfm-io:begin" in capsys.readouterr().out


def test_init_agent_rejects_a_missing_directory(tmp_path, capsys):
    assert main(["init-agent", str(tmp_path / "nope")]) == 1
    assert "does not exist" in capsys.readouterr().err
