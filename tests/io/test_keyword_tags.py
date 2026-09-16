"""Keyword tags spelled with a trailing slash (issue #37).

IWFM reads a ``VALUE / KEYWORD`` line list-directed and stops at the first
``/``, so the tag is a comment to the executable and real decks spell it
``/ KEYWORD/`` as happily as ``/ KEYWORD``.  Readers that dispatch on the tag
used to take the raw first word -- ``ZRZBUDFL/`` -- which matched nothing,
ended the keyword block early, and handed the line to whatever table came
next (the root-zone soil table, in the report).

Each main file below is parsed twice from the same folder, clean and with a
trailing slash on every keyword tag, and the results must be identical.
"""

import dataclasses
import math
import re
import shutil

import numpy as np
import pandas as pd
import pytest

from tests.io.conftest import SIMULATION_DIR

# keyed-line shape: at most one value token, then " / TAG"
_TAG = re.compile(r"^(?P<head>(?:\S+\s+)?\s*/\s*)(?P<kw>[A-Z][A-Z0-9_]*)(?=\s|$)")


def _slash_every_tag(text):
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        if line[:1] not in ("C", "c", "*", "#") and (m := _TAG.match(line.lstrip())):
            indent = line[: len(line) - len(line.lstrip())]
            body = line.lstrip()
            line = indent + body[: m.end("kw")] + "/" + body[m.end("kw"):]
            n += 1
        out.append(line)
    return "".join(out), n


def _same(a, b, path="root"):
    if isinstance(a, pd.DataFrame):
        assert isinstance(b, pd.DataFrame) and a.equals(b), path
    elif isinstance(a, pd.Series):
        assert isinstance(b, pd.Series) and a.equals(b), path
    elif isinstance(a, np.ndarray):
        np.testing.assert_array_equal(a, b, err_msg=path)
    elif dataclasses.is_dataclass(a) and not isinstance(a, type):
        assert type(a) is type(b), path
        for f in dataclasses.fields(a):
            _same(getattr(a, f.name), getattr(b, f.name), f"{path}.{f.name}")
    elif isinstance(a, dict):
        assert a.keys() == b.keys(), path
        for k in a:
            _same(a[k], b[k], f"{path}[{k!r}]")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and math.isnan(a):
        assert isinstance(b, float) and math.isnan(b), path
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


MAINS = [
    ("read_rootzone_main", "RootZone/RootZone_MAIN.dat"),
    ("read_gw_main", "GW/GW_MAIN.dat"),
    ("read_stream_main", "Stream/Stream_MAIN.dat"),
    ("read_simulation", "Simulation_MAIN.IN"),
]


@pytest.mark.parametrize("reader,rel", MAINS, ids=[r for r, _ in MAINS])
def test_trailing_slash_on_every_tag_parses_identically(reader, rel, tmp_path):
    import iwfm_io

    src = SIMULATION_DIR / rel
    if not src.is_file():
        pytest.skip(f"{rel} not present")
    # same folder for both copies, so relative references resolve alike
    folder = tmp_path / src.parent.name
    folder.mkdir()
    clean = folder / f"clean{src.suffix}"
    slashed = folder / f"slashed{src.suffix}"
    shutil.copy(src, clean)
    text, n_tags = _slash_every_tag(src.read_text(encoding="utf-8", errors="replace"))
    slashed.write_text(text, encoding="utf-8")
    assert n_tags >= 3, f"too few tags decorated in {rel}: {n_tags}"

    fn = getattr(iwfm_io, reader)
    _same(fn(clean), fn(slashed))


class TestKeywordName:
    @pytest.mark.parametrize("tag,name", [
        ("ZRZBUDFL", "ZRZBUDFL"),
        ("ZRZBUDFL/", "ZRZBUDFL"),          # the YGM spelling in #37
        ("ZRZBUDFL//", "ZRZBUDFL"),
        ("zrzbudfl", "ZRZBUDFL"),
        ("FACTK   (cm -> ft)", "FACTK"),
        ("FACTK/ (cm -> ft)", "FACTK"),
        ("TUNITK/description", "TUNITK"),
        ("", ""),
        ("   ", ""),
        ("/", ""),
    ])
    def test_name(self, tag, name):
        from iwfm_io._tokens import keyword_name
        assert keyword_name(tag) == name


class TestRootZoneSoilTableBounds:
    """IWFM reads exactly NE soil-parameter rows and nothing after them."""

    def _deck(self, tmp_path, extra=""):
        src = SIMULATION_DIR / "RootZone" / "RootZone_MAIN.dat"
        if not src.is_file():
            pytest.skip("RootZone_MAIN.dat not present")
        folder = tmp_path / "RootZone"
        folder.mkdir()
        p = folder / "RootZone_MAIN.dat"
        text = src.read_text(encoding="utf-8")
        if extra and not text.endswith("\n"):
            text += "\n"          # appended lines must be lines of their own
        p.write_text(text + extra, encoding="utf-8")
        return p

    def test_count_bounds_the_table_and_ignores_what_follows(self, tmp_path):
        from iwfm_io import read_rootzone_main
        ref = read_rootzone_main(self._deck(tmp_path))
        n = len(ref.element_params)
        p = tmp_path / "junk"
        p.mkdir()
        junk = self._deck(p, "   ..\\Results\\extra.hdf     / ZRZBUDFL/\n"
                             "   1  2  3\n")
        got = read_rootzone_main(junk, n_elements=n)
        assert got.element_params.equals(ref.element_params)

    def test_short_table_raises_when_the_count_is_known(self, tmp_path):
        from iwfm_io import IWFMParseError, read_rootzone_main
        n = len(read_rootzone_main(self._deck(tmp_path)).element_params)
        p = tmp_path / "short"
        p.mkdir()
        with pytest.raises(IWFMParseError, match=f"has {n} rows but the model has {n + 1}"):
            read_rootzone_main(self._deck(p), n_elements=n + 1)

    def test_keyed_line_ends_the_table_without_a_count(self, tmp_path):
        from iwfm_io import read_rootzone_main
        ref = read_rootzone_main(self._deck(tmp_path))
        p = tmp_path / "keyed"
        p.mkdir()
        got = read_rootzone_main(
            self._deck(p, "   ..\\Results\\extra.hdf     / ZRZBUDFL/\n"))
        assert got.element_params.equals(ref.element_params)

    def test_open_model_passes_the_element_count(self, monkeypatch):
        import iwfm_io
        import iwfm_io._links as links
        from tests.io.conftest import SAMPLE_MODEL

        seen = []
        real = links._reader

        def spy_reader(name):
            fn = real(name)
            if name != "read_rootzone_main":
                return fn

            def spy(path, n_elements=None):
                seen.append(n_elements)
                return fn(path, n_elements=n_elements)
            return spy

        monkeypatch.setattr(links, "_reader", spy_reader)
        m = iwfm_io.open_model(SAMPLE_MODEL)
        m.component("rootzone")
        assert seen == [len(m.elements_df())]
