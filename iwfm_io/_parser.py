"""
Stateful line-iterator for reading IWFM text files.

Reads an entire file into memory, then provides methods to walk
through data lines (skipping comments), parse key-value pairs,
read tabular data, and extract time-series sections.

Every reader raises :class:`IWFMParseError` — naming the file, the line
and the section being read — on malformed input.  Recoverable problems
go through :meth:`IWFMFileReader.degrade`, which raises in strict mode
and warns (:class:`IWFMReadWarning`) in lenient mode; see
:mod:`iwfm_io._strict`.
"""

from __future__ import annotations

import os
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from iwfm_io._strict import current_strict
from iwfm_io._tokens import (
    is_comment,
    is_iwfm_date,
    is_version_header,
    parse_version_header,
    split_keyed_line,
    tokenize_data_line,
)
from iwfm_io.models.base import FileHeader, TimeSeriesSpec


def resolve_child_path(value: str, base_dir: str | Path) -> str:
    """Resolve a child-file reference from an IWFM input file.

    IWFM resolves referenced paths against the simulation working
    directory, which for component mains in a subfolder is the parent
    of the file's own folder — but a file opened standalone can't know
    the working directory, so candidates are ranked by evidence:

    1. the candidate that exists as a file (inputs),
    2. the candidate whose parent directory exists (outputs that the
       run has not created yet, e.g. ``..\\Results\\*.hdf`` in a fresh
       scenario copy),
    3. otherwise the reference is kept exactly as written (relative):
       guessing a folder would let a later write re-relativise a wrong
       absolute path and drift the deck (a ``../Results/x`` reference
       becoming ``Results/x``); writers pass relative references
       through untouched.
    """
    rel = value.replace("\\", "/")
    base = Path(base_dir)
    candidates = [base / rel, base.parent / rel]
    # resolved references are absolute: a relative one would be relative
    # to the CWD at read time and be written verbatim into a deck that
    # lives elsewhere (the writers relativise absolute paths against the
    # deck's own folder / base_dir)
    for cand in candidates:
        if cand.exists():
            return os.path.abspath(cand)
    for cand in candidates:
        if cand.parent.exists():
            return os.path.abspath(cand)
    return value.strip()


class IWFMReadWarning(UserWarning):
    """A reader kept going past malformed input (lenient mode only).

    Emitted by :meth:`IWFMFileReader.degrade` when strict mode is off,
    and for harmless irregularities (e.g. extra values on a time-series
    row, which IWFM ignores) in either mode.
    """


class IWFMParseError(ValueError):
    """Malformed content or unexpected end of data in an IWFM file.

    Attributes
    ----------
    path : str or None
        The file being read.
    lineno : int or None
        1-based line number of the offending line.
    section : str
        The section being read when the error occurred (nested
        sections joined with ``" > "``); empty when unknown.
    msg : str
        The bare message without the location prefix.

    The string form is ``"{path}:{lineno} [{section}]: {msg}"`` with
    absent parts omitted.
    """

    def __init__(self, msg: str, *, path=None, lineno: int | None = None,
                 section: str = "") -> None:
        self.msg = msg
        self.path = str(path) if path is not None else None
        self.lineno = lineno
        self.section = section or ""
        loc = self.path or ""
        if lineno is not None:
            loc = f"{loc}:{lineno}" if loc else f"line {lineno}"
        sec = f" [{self.section}]" if self.section else ""
        full = f"{loc}{sec}: {msg}" if (loc or sec) else msg
        super().__init__(full)


class IWFMFileReader:
    """Sequential reader for IWFM text files.

    Parameters
    ----------
    path : str or Path
        Path to the IWFM text file.
    strict : bool, optional
        Reader mode for this file.  ``None`` (default) snapshots the
        mode in effect (see :func:`iwfm_io.strict_mode`); ``True``
        raises :class:`IWFMParseError` on recoverable problems, ``False``
        warns and keeps what parsed.
    """

    def __init__(self, path: str | Path, strict: bool | None = None) -> None:
        self.path = Path(path)
        self.strict = current_strict() if strict is None else bool(strict)
        self._lines: list[str] = []
        self._pos: int = 0
        self._comment_buffer: list[str] = []
        self._sections: list[str] = []
        self._warned: set[str] = set()
        self._read_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self) -> None:
        """Load all lines from the file (a UTF-8 BOM is dropped).

        Decks are UTF-8 (or ASCII) normally; a file with legacy Windows
        bytes in its comments (``cp1252``, e.g. ``\xe9``) is decoded as
        cp1252 so the text survives a round-trip instead of turning
        into U+FFFD replacement characters.
        """
        raw = Path(self.path).read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
        self._lines = text.splitlines()

    @property
    def eof(self) -> bool:
        """True when all lines have been consumed."""
        return self._pos >= len(self._lines)

    @property
    def lineno(self) -> int:
        """1-based number of the most recently consumed line (0 before
        any line was read)."""
        return self._pos

    @property
    def n_lines(self) -> int:
        """Total number of lines in the file."""
        return len(self._lines)

    # ------------------------------------------------------------------
    # Context, errors and degradation
    # ------------------------------------------------------------------

    @property
    def section_name(self) -> str:
        """The current section context (nested names joined by ``" > "``)."""
        return " > ".join(self._sections)

    @contextmanager
    def section(self, name: str):
        """Name the section being read, for error messages.

        Nested sections are joined with ``" > "``::

            with reader.section("hydrograph table"):
                ...
        """
        self._sections.append(name)
        try:
            yield self
        finally:
            self._sections.pop()

    def error(self, msg: str, lineno: int | None = None) -> IWFMParseError:
        """Build an :class:`IWFMParseError` carrying file, line and section.

        The line defaults to the most recently consumed one; pass
        *lineno* to point at another line.  Use as ``raise
        reader.error("...")``.
        """
        if lineno is None:
            lineno = self.lineno if self.lineno else None
        return IWFMParseError(msg, path=self.path, lineno=lineno,
                              section=self.section_name)

    def degrade(self, msg: str, lineno: int | None = None) -> None:
        """Report a recoverable problem.

        Raises :meth:`error` in strict mode; in lenient mode emits an
        :class:`IWFMReadWarning` with the same file/line/section prefix
        and returns so the caller can keep what it parsed.
        """
        err = self.error(msg, lineno)
        if self.strict:
            raise err
        warnings.warn(str(err), IWFMReadWarning, stacklevel=2)

    def warn_once(self, key: str, msg: str) -> None:
        """Emit an :class:`IWFMReadWarning` once per file per *key*."""
        if key in self._warned:
            return
        self._warned.add(key)
        warnings.warn(f"{self.path}: {msg}", IWFMReadWarning, stacklevel=2)

    # ------------------------------------------------------------------
    # Core iteration
    # ------------------------------------------------------------------

    def next_line(self) -> str:
        """Return the next raw line (comment or data) and advance."""
        if self.eof:
            raise self.error("end of file reached while reading data",
                             lineno=self.n_lines or None)
        line = self._lines[self._pos]
        self._pos += 1
        return line

    def next_data_line(self) -> str:
        """Return the next non-comment line, accumulating skipped comments.

        Comments encountered while scanning are stored in the internal
        comment buffer and can be retrieved with :meth:`drain_comments`.
        """
        while not self.eof:
            line = self._lines[self._pos]
            self._pos += 1
            if is_comment(line):
                self._comment_buffer.append(line)
                continue
            return line
        raise self.error(
            "end of file reached while a data line was still expected — "
            "the file may be truncated or a section is missing",
            lineno=self.n_lines or None)

    def peek_data_line(self) -> str | None:
        """Peek at the next non-comment line without consuming it."""
        pos = self._pos
        lines = self._lines
        n = len(lines)
        while pos < n:
            line = lines[pos]
            if not is_comment(line):
                return line
            pos += 1
        return None

    def drain_comments(self) -> list[str]:
        """Return and clear accumulated comment lines."""
        comments = self._comment_buffer
        self._comment_buffer = []
        return comments

    # ------------------------------------------------------------------
    # Header reading
    # ------------------------------------------------------------------

    def read_header(self) -> FileHeader:
        """Read the file header: optional version line + leading comments.

        Returns a :class:`FileHeader` and positions the cursor at the
        first data line.
        """
        version = None
        comments: list[str] = []

        # Scan through leading comments/version headers
        while not self.eof:
            line = self._lines[self._pos]
            if is_version_header(line):
                version = parse_version_header(line)
                comments.append(line)
                self._pos += 1
            elif is_comment(line):
                comments.append(line)
                self._pos += 1
            else:
                break

        self._comment_buffer = []
        return FileHeader(version=version, comment_lines=comments)

    # ------------------------------------------------------------------
    # Key-value reading
    # ------------------------------------------------------------------

    def read_keyed_value(self) -> tuple[str, str]:
        """Read a ``VALUE / KEYWORD`` line.

        Returns ``(value_str, keyword_str)``.
        """
        line = self.next_data_line()
        return split_keyed_line(line)

    def read_keyed_int(self) -> tuple[int, str]:
        """Read a keyed integer value. Returns ``(int_value, keyword)``."""
        value_str, keyword = self.read_keyed_value()
        try:
            return int(value_str), keyword
        except ValueError:
            what = keyword.split()[0] if keyword else "value"
            raise self.error(
                f"expected an integer for {what} but found {value_str!r}"
            ) from None

    def read_keyed_float(self) -> tuple[float, str]:
        """Read a keyed float value. Returns ``(float_value, keyword)``."""
        value_str, keyword = self.read_keyed_value()
        try:
            return float(value_str), keyword
        except ValueError:
            what = keyword.split()[0] if keyword else "value"
            raise self.error(
                f"expected a number for {what} but found {value_str!r}"
            ) from None

    def read_keyed_path(self, base_dir: str | Path | None = None) -> tuple[str | None, str]:
        """Read a keyed file path, resolving relative to *base_dir*.

        Returns ``(resolved_path_or_None, keyword)``.  A blank value
        means no file is specified (returns None).
        """
        value_str, keyword = self.read_keyed_value()
        if not value_str or value_str == "*":
            return None, keyword
        if base_dir is not None:
            return resolve_child_path(value_str, base_dir), keyword
        return value_str.replace("\\", "/"), keyword

    # ------------------------------------------------------------------
    # Row primitives
    # ------------------------------------------------------------------

    def read_row(self, n_cols: int, what: str = "row", *,
                 min_cols: int | None = None) -> list[str]:
        """Read one data line as tokens, requiring at least *min_cols*
        (default *n_cols*) of them.

        A short row raises :class:`IWFMParseError` naming *what*, the
        line and the section.  Extra tokens are returned too (IWFM
        ignores them; callers slice what they need).
        """
        line = self.next_data_line()
        tokens = tokenize_data_line(line)
        need = n_cols if min_cols is None else min_cols
        if len(tokens) < need:
            raise self.error(
                f"{what}: expected {need} values but found {len(tokens)}: "
                f"{line.strip()!r}")
        return tokens

    def read_data_table(self, n_rows: int, n_cols: int | None = None,
                        what: str = "table row") -> list[list[str]]:
        """Read *n_rows* of whitespace-delimited data.

        Parameters
        ----------
        n_rows : int
            Number of data rows to read.
        n_cols : int, optional
            Minimum number of columns.  If given, each row is validated.
        what : str
            Name used in error messages.

        Returns
        -------
        list[list[str]]
            Each inner list contains the string tokens for one row.
        """
        return [self.read_row(n_cols or 0, what) for _ in range(n_rows)]

    def to_floats(self, tokens: list[str], what: str = "value",
                  lineno: int | None = None) -> list[float]:
        """Convert *tokens* to floats, naming line and column on failure."""
        out: list[float] = []
        for i, tok in enumerate(tokens, start=1):
            try:
                out.append(float(tok))
            except ValueError:
                raise self.error(
                    f"{what}: column {i} is not a number: {tok!r}",
                    lineno) from None
        return out

    def to_ints(self, tokens: list[str], what: str = "value",
                lineno: int | None = None) -> list[int]:
        """Convert *tokens* to integers, naming line and column on failure.

        Integral floats (``3.0``) are accepted; ``3.5`` is not.
        """
        out: list[int] = []
        for i, tok in enumerate(tokens, start=1):
            try:
                out.append(int(tok))
                continue
            except ValueError:
                pass
            try:
                f = float(tok)
            except ValueError:
                raise self.error(
                    f"{what}: column {i} is not an integer: {tok!r}",
                    lineno) from None
            if f != int(f):
                raise self.error(
                    f"{what}: column {i} is not an integer: {tok!r}",
                    lineno)
            out.append(int(f))
        return out

    def read_ints(self, n: int, what: str = "values") -> list[int]:
        """Read one data line holding *n* integers."""
        tokens = self.read_row(n, what)
        return self.to_ints(tokens[:n], what)

    def read_floats(self, n: int, what: str = "values") -> list[float]:
        """Read one data line holding *n* numbers."""
        tokens = self.read_row(n, what)
        return self.to_floats(tokens[:n], what)

    # ------------------------------------------------------------------
    # Time-series reading
    # ------------------------------------------------------------------

    def read_timeseries_spec(self) -> TimeSeriesSpec:
        """Read a 5-parameter time-series header block.

        Expected order: NCOL, FACT, NSP, NFQ, DSSFL.
        """
        with self.section("time-series spec"):
            n_columns, _ = self.read_keyed_int()
            factor, _ = self.read_keyed_float()
            n_steps_update, _ = self.read_keyed_int()
            repeat_freq, _ = self.read_keyed_int()
            dss_file, _ = self.read_keyed_value()
        return TimeSeriesSpec(
            n_columns=n_columns,
            factor=factor,
            n_steps_update=n_steps_update,
            repeat_freq=repeat_freq,
            dss_file=dss_file,
        )

    def read_ts_rows(
        self,
        n_columns: int,
        col_names: list[str] | None = None,
        *,
        what: str = "time series",
    ) -> pd.DataFrame:
        """Read ``DATE  v1 .. vN`` time-series rows to the end of the file.

        Dates are kept as the raw IWFM strings in a ``date`` column
        (recurring data uses sentinel years 2500/4000 that pandas
        timestamps cannot hold); values become floats.

        Rules (matching IWFM's list-directed reads):

        - every data row must start with a complete IWFM date
          (``MM/DD/YYYY_HH:MM``); a row that does not is an error —
          strict mode raises, lenient mode warns and stops there;
        - a row with fewer than *n_columns* values is an error — strict
          mode raises, lenient mode warns and pads with NaN;
        - extra values beyond *n_columns* are ignored (IWFM reads only
          NCOL), with one warning per file;
        - a non-numeric value raises, naming the line and column.

        Returns
        -------
        pd.DataFrame
            Columns: ``date`` (str), then *col_names* (default
            ``col_1..col_N``).
        """
        if col_names is None:
            col_names = [f"col_{i + 1}" for i in range(n_columns)]
        if len(col_names) != n_columns:
            raise ValueError(
                f"{what}: {len(col_names)} column names given for "
                f"{n_columns} columns")

        date_strs: list[str] = []
        values: list[list[str]] = []
        linenos: list[int] = []
        padded = False

        with self.section(what):
            while True:
                line = self.peek_data_line()
                if line is None:
                    break
                tokens = tokenize_data_line(line)
                first = tokens[0] if tokens else ""
                if not is_iwfm_date(first):
                    self.next_data_line()  # position the error on it
                    self.degrade(
                        "expected a data row starting with an IWFM date "
                        f"(MM/DD/YYYY_HH:MM) but found {line.strip()[:60]!r}"
                        "; data after this line was not read")
                    break
                self.next_data_line()
                vals = tokens[1:]
                if len(vals) < n_columns:
                    self.degrade(
                        f"row {first} has {len(vals)} of {n_columns} "
                        "values (missing values read as NaN)")
                    vals = vals + [""] * (n_columns - len(vals))
                    padded = True
                elif len(vals) > n_columns:
                    self.warn_once(
                        "ts_extra",
                        f"{what}: rows carry more than {n_columns} "
                        "values; the extras are ignored (IWFM reads only "
                        "NCOL values per row)")
                    vals = vals[:n_columns]
                date_strs.append(first)
                values.append(vals)
                linenos.append(self.lineno)

        if not date_strs:
            return pd.DataFrame(columns=["date"] + col_names)

        raw = np.array(values, dtype=object)
        if padded:
            raw[raw == ""] = "nan"
        try:
            arr = raw.astype(float)
        except ValueError:
            # locate the offending token for a precise message
            for r, row in enumerate(values):
                for c, tok in enumerate(row, start=1):
                    if tok == "":
                        continue
                    try:
                        float(tok)
                    except ValueError:
                        raise IWFMParseError(
                            f"{what}: row {date_strs[r]} column {c} is "
                            f"not a number: {tok!r}",
                            path=self.path, lineno=linenos[r],
                            section=self.section_name) from None
            raise  # pragma: no cover - unreachable

        df = pd.DataFrame(arr, columns=col_names)
        df.insert(0, "date", date_strs)
        return df

    def read_dss_pathnames(self, spec: TimeSeriesSpec) -> list[tuple[int, str]]:
        """Read DSS pathname assignments (col_id, pathname) pairs.

        Used when spec.dss_file is non-empty. Each line has:
        ``COL_ID  /A/B/C//E/F/``
        """
        pathnames: list[tuple[int, str]] = []
        with self.section("DSS pathnames"):
            for i in range(spec.n_columns):
                try:
                    line = self.next_data_line()
                except IWFMParseError:
                    raise self.error(
                        f"DSS pathname block has only {i} of "
                        f"{spec.n_columns} expected rows") from None
                tokens = line.split(None, 1)
                try:
                    col_id = int(tokens[0])
                except ValueError:
                    raise self.error(
                        f"DSS pathname row must start with a column "
                        f"number: {line.strip()!r}") from None
                pathname = tokens[1].strip() if len(tokens) > 1 else ""
                pathnames.append((col_id, pathname))
        return pathnames

    # ------------------------------------------------------------------
    # Convenience: skip to end or consume remaining comments
    # ------------------------------------------------------------------

    def skip_to_end(self) -> list[str]:
        """Consume all remaining lines and return them."""
        remaining = self._lines[self._pos :]
        self._pos = len(self._lines)
        return remaining

    def tail_cursor(self):
        """Consume the rest of the file into a
        :class:`~iwfm_io.readers._param_blocks.LineCursor` that reports
        this file's path, real line numbers and reader mode."""
        from iwfm_io.readers._param_blocks import LineCursor
        lineno0 = self.lineno
        return LineCursor(self.skip_to_end(), path=self.path,
                          lineno0=lineno0, strict=self.strict)
