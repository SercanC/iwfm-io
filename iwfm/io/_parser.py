"""
Stateful line-iterator for reading IWFM text files.

Reads an entire file into memory, then provides methods to walk
through data lines (skipping comments), parse key-value pairs,
read tabular data, and extract time-series sections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from iwfm.io._tokens import (
    is_comment,
    is_version_header,
    parse_version_header,
    split_keyed_line,
    tokenize_data_line,
    parse_iwfm_date,
)
from iwfm.io.models.base import FileHeader, TimeSeriesSpec


class IWFMFileReader:
    """Sequential reader for IWFM text files.

    Parameters
    ----------
    path : str or Path
        Path to the IWFM text file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lines: list[str] = []
        self._pos: int = 0
        self._comment_buffer: list[str] = []
        self._read_all()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self) -> None:
        """Load all lines from the file."""
        with open(self.path, "r", encoding="utf-8", errors="replace") as fh:
            self._lines = [line.rstrip("\n\r") for line in fh]

    @property
    def eof(self) -> bool:
        """True when all lines have been consumed."""
        return self._pos >= len(self._lines)

    # ------------------------------------------------------------------
    # Core iteration
    # ------------------------------------------------------------------

    def next_line(self) -> str:
        """Return the next raw line (comment or data) and advance."""
        if self.eof:
            raise StopIteration("End of file reached")
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
        raise StopIteration("End of file reached without finding data line")

    def peek_data_line(self) -> str | None:
        """Peek at the next non-comment line without consuming it."""
        saved_pos = self._pos
        saved_buf = list(self._comment_buffer)
        try:
            line = self.next_data_line()
            return line
        except StopIteration:
            return None
        finally:
            self._pos = saved_pos
            self._comment_buffer = saved_buf

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

        saved_pos = self._pos
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
        return int(value_str), keyword

    def read_keyed_float(self) -> tuple[float, str]:
        """Read a keyed float value. Returns ``(float_value, keyword)``."""
        value_str, keyword = self.read_keyed_value()
        return float(value_str), keyword

    def read_keyed_path(self, base_dir: str | Path | None = None) -> tuple[str | None, str]:
        """Read a keyed file path, resolving relative to *base_dir*.

        Returns ``(resolved_path_or_None, keyword)``.  A blank value
        means no file is specified (returns None).
        """
        value_str, keyword = self.read_keyed_value()
        if not value_str or value_str == "*":
            return None, keyword
        # Normalise backslash to forward slash
        value_str = value_str.replace("\\", "/")
        if base_dir is not None:
            resolved = Path(base_dir) / value_str
            return str(resolved), keyword
        return value_str, keyword

    # ------------------------------------------------------------------
    # Tabular data reading
    # ------------------------------------------------------------------

    def read_data_table(self, n_rows: int, n_cols: int | None = None) -> list[list[str]]:
        """Read *n_rows* of whitespace-delimited data.

        Parameters
        ----------
        n_rows : int
            Number of data rows to read.
        n_cols : int, optional
            Expected number of columns.  If given, each row is validated.

        Returns
        -------
        list[list[str]]
            Each inner list contains the string tokens for one row.
        """
        rows: list[list[str]] = []
        for _ in range(n_rows):
            line = self.next_data_line()
            tokens = tokenize_data_line(line)
            if n_cols is not None and len(tokens) < n_cols:
                raise ValueError(
                    f"Expected {n_cols} columns but got {len(tokens)}: {line!r}"
                )
            rows.append(tokens)
        return rows

    # ------------------------------------------------------------------
    # Time-series reading
    # ------------------------------------------------------------------

    def read_timeseries_spec(self) -> TimeSeriesSpec:
        """Read a 5-parameter time-series header block.

        Expected order: NCOL, FACT, NSP, NFQ, DSSFL.
        """
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

    def read_timeseries_data(
        self,
        spec: TimeSeriesSpec,
        col_names: list[str] | None = None,
        read_all: bool = True,
    ) -> pd.DataFrame:
        """Read inline time-series data rows.

        Each row is ``DATE  val1  val2  ...  valN`` where N = spec.n_columns.

        Parameters
        ----------
        spec : TimeSeriesSpec
            Spec with column count and conversion factor.
        col_names : list[str], optional
            Column names.  Defaults to ``col_1, col_2, ...``.
        read_all : bool
            If True, read until EOF or next non-date data line.

        Returns
        -------
        pd.DataFrame
            DataFrame with DatetimeIndex and one column per data column.
        """
        if col_names is None:
            col_names = [f"col_{i+1}" for i in range(spec.n_columns)]

        dates: list[Any] = []
        values: list[list[float]] = []

        while not self.eof:
            line = self.peek_data_line()
            if line is None:
                break
            tokens = tokenize_data_line(line)
            if not tokens:
                break
            # Check if first token looks like an IWFM date
            if "/" not in tokens[0] or "_" not in tokens[0]:
                break
            # Consume the line
            self.next_data_line()
            dt = parse_iwfm_date(tokens[0])
            row_vals = [float(v) for v in tokens[1 : spec.n_columns + 1]]
            dates.append(dt)
            values.append(row_vals)

        if not dates:
            return pd.DataFrame(columns=col_names)

        df = pd.DataFrame(values, columns=col_names, index=pd.DatetimeIndex(dates, name="datetime"))
        return df

    def read_dss_pathnames(self, spec: TimeSeriesSpec) -> list[tuple[int, str]]:
        """Read DSS pathname assignments (col_id, pathname) pairs.

        Used when spec.dss_file is non-empty. Each line has:
        ``COL_ID  /A/B/C//E/F/``
        """
        pathnames: list[tuple[int, str]] = []
        for _ in range(spec.n_columns):
            line = self.next_data_line()
            tokens = line.split(None, 1)
            col_id = int(tokens[0])
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
