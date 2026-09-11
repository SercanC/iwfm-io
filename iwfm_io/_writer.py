"""
Writer for IWFM text files.

Builds lines in memory and writes them out on :meth:`flush`.

Every cell that reaches the file goes through :func:`format_cell`, the
single formatting policy: missing values, non-finite numbers, embedded
newlines and non-integral IDs are refused with a ``ValueError`` instead
of being written as tokens IWFM would silently mis-read.
"""

from __future__ import annotations

import math
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from iwfm_io._tokens import format_iwfm_date, is_comment, is_iwfm_date
from iwfm_io.models.base import FileHeader, TimeSeriesSpec

_NUMBERED_RE_CACHE: dict[str, re.Pattern] = {}


def _is_missing(value) -> bool:
    """True for the scalar "missing" sentinels: None, pd.NA, NaT, NaN."""
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, (float, np.floating)):
        return math.isnan(value)
    if isinstance(value, (np.datetime64, np.timedelta64)):
        return bool(np.isnat(value))
    return False


def _check_newline(text: str, what: str) -> None:
    if "\n" in text or "\r" in text:
        raise ValueError(
            f"{what or 'cell'}: text contains a line break "
            f"({text!r}) -- it would inject extra lines IWFM reads as data")


_NUMERIC_WITH_COMMA_RE = re.compile(r"[+\-]?[0-9.,]+(?:[eEdD][+\-]?\d+)?")


def format_cell(value, *, what: str = "", allow_blank: bool = False,
                integer: bool = False, exact_float: bool = False) -> str:
    """Render one value as an IWFM file token.

    Policy (the only one writers use):

    * ``str`` -- passed through; a line break raises; an empty string
      raises unless *allow_blank*.
    * ``None`` / ``pd.NA`` / ``NaT`` / ``NaN`` -- raise unless
      *allow_blank* (then ``""``): a missing value would write a short
      row IWFM mis-reads.
    * ``bool`` -> ``"1"`` / ``"0"``; ``int`` / ``numpy`` integers ->
      decimal text.
    * ``float`` / ``numpy`` floats -- ``inf`` raises; integral values
      below ``1e15`` are written without a decimal point (unless
      *exact_float*); anything else is Python's shortest round-tripping
      ``repr``.
    * ``integer=True`` rejects non-integral floats (an ID like ``2.9``
      must not be truncated to ``2``).
    * Any other type raises ``TypeError`` (a ``datetime`` must be
      formatted with :func:`~iwfm_io.format_iwfm_date` first).

    Parameters
    ----------
    value : object
    what : str
        Name of the field for error messages (``"GW hydrograph layer"``).
    allow_blank : bool
        Accept missing values / empty strings and render them as ``""``
        (only for fields where IWFM tolerates a blank, e.g. names).
    integer : bool
        The field is an ID / count / flag: non-integral floats raise.
    exact_float : bool
        Keep a float's own ``repr`` even when integral (``1.0`` stays
        ``1.0``). Used for keyed scalars, whose Python type is what the
        reader stored, so a regenerated file matches the original.
    """
    label = what or "cell"
    if isinstance(value, str):
        _check_newline(value, label)
        if not value.strip():
            if allow_blank:
                return value
            raise ValueError(
                f"{label}: empty value would write a short row IWFM "
                "mis-reads")
        return value
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    if _is_missing(value):
        if allow_blank:
            return ""
        raise ValueError(
            f"{label}: missing value would write a short row IWFM "
            "mis-reads; fill or drop the value first")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        f = float(value)
        if math.isinf(f):
            raise ValueError(f"{label}: non-finite value {f!r}")
        if f.is_integer() and abs(f) < 1e15:
            return repr(f) if exact_float and not integer else str(int(f))
        if integer:
            raise ValueError(
                f"{label}: {f!r} is not an integer (IDs, counts and "
                "flags must be integral)")
        return repr(f)
    raise TypeError(
        f"{label}: cannot write a {type(value).__name__} "
        f"({value!r}) -- format it as text first")


def numbered_columns(df: pd.DataFrame, prefix: str,
                     n: int | None = None) -> list[str]:
    """Columns named ``<prefix><N>`` ordered by their numeric suffix.

    Positional IWFM tables must never take their order from the
    DataFrame's column order (a reordered frame would silently permute
    layers / crops). When *n* is given the suffixes must be exactly
    ``1..n`` or a ``ValueError`` names the mismatch.
    """
    pat = _NUMBERED_RE_CACHE.get(prefix)
    if pat is None:
        pat = _NUMBERED_RE_CACHE[prefix] = re.compile(
            re.escape(prefix) + r"(\d+)$")
    found: list[tuple[int, str]] = []
    for c in df.columns:
        m = pat.fullmatch(str(c))
        if m:
            found.append((int(m.group(1)), str(c)))
    found.sort()
    if n is not None:
        have = [k for k, _ in found]
        if have != list(range(1, n + 1)):
            raise ValueError(
                f"expected columns {prefix}1..{prefix}{n}, found "
                f"{[c for _, c in found]}")
    return [c for _, c in found]


def format_date_cell(value, what: str = "date") -> str:
    """An IWFM date token from a string (validated) or a datetime.

    Strings must be complete ``MM/DD/YYYY_HH:MM`` dates (sentinel years
    like 4000 included); ``datetime`` / ``pd.Timestamp`` values are
    formatted with the ``24:00`` convention; missing values raise.
    """
    if isinstance(value, str):
        text = value.strip()
        if not is_iwfm_date(text):
            raise ValueError(
                f"{what}: {value!r} is not an IWFM date "
                "(MM/DD/YYYY_HH:MM)")
        return text
    if _is_missing(value):
        raise ValueError(f"{what}: missing date")
    if isinstance(value, (datetime, np.datetime64)):
        return format_iwfm_date(pd.Timestamp(value).to_pydatetime())
    raise TypeError(
        f"{what}: cannot write a {type(value).__name__} as a date -- "
        "pass an IWFM date string or a datetime")


def replace_file_text(path: str | Path, text: str,
                      encoding: str | None = "utf-8",
                      newline: str | None = None,
                      errors: str | None = None) -> None:
    """Atomically replace *path*'s contents (write temp + rename).

    Never truncates the target in place, so if *path* is a hardlink
    (``create_scenario(..., link_unchanged=True)``) the linked sibling
    in the base model is left untouched and *path* becomes an
    independent file. On POSIX the existing file's permission bits are
    carried over to the replacement.
    """
    path = Path(path)
    mode = None
    if os.name != "nt":
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = None
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline,
                       errors=errors) as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


class IWFMFileWriter:
    """Sequential writer for IWFM text files.

    Parameters
    ----------
    path : str or Path, optional
        Output file path. If None, lines accumulate in memory only.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._lines: list[str] = []

    @property
    def lines(self) -> list[str]:
        """The accumulated output lines."""
        return self._lines

    # ------------------------------------------------------------------
    # Comment and header writing
    # ------------------------------------------------------------------

    def write_comment(self, text: str) -> None:
        """Write a single comment line.

        IWFM's comment characters are ``C``, ``c`` and ``*`` in column
        1 only; any other text (including a leading ``/``, which IWFM
        reads as a blank data value) gets ``C `` prepended.
        """
        _check_newline(text, "comment")
        if text and text[0] in "Cc*":
            self._lines.append(text)
        else:
            self._lines.append(f"C {text}")

    def write_comments(self, lines: list[str]) -> None:
        """Write multiple comment lines (each through :meth:`write_comment`)."""
        for line in lines:
            self.write_comment(line)

    def write_version_header(self, version: str) -> None:
        """Write a version header like ``#4.0``."""
        self._lines.append(f"#{version}")

    def write_header(self, header: FileHeader) -> None:
        """Write a :class:`FileHeader` (version + comment lines).

        ``header.version`` is the source of truth: when set, the
        ``#<version>`` line is written from it -- replacing the version
        line kept in ``comment_lines`` (in place, so files that already
        carry ``#4.0`` round-trip byte-for-byte) or, when none is kept,
        ahead of the comments. Comment lines that are not IWFM
        comments (no ``C``/``c``/``*`` in column 1) are prefixed so
        they can never be read as data.
        """
        version_line = (f"#{header.version}"
                        if header.version not in (None, "") else None)
        lines = list(header.comment_lines)
        has_version_line = any(ln.lstrip().startswith("#") for ln in lines)
        if version_line is not None and not has_version_line:
            self._lines.append(version_line)
        for line in lines:
            if line.lstrip().startswith("#"):
                if version_line is not None:
                    self._lines.append(version_line)
                    version_line = None  # emit once
                else:
                    _check_newline(line, "header line")
                    self._lines.append(line)
            elif is_comment(line):
                _check_newline(line, "header line")
                self._lines.append(line)
            else:
                self.write_comment(line)

    # ------------------------------------------------------------------
    # Key-value writing
    # ------------------------------------------------------------------

    def write_keyed_value(
        self,
        value: object,
        keyword: str,
        width: int = 50,
        comment: str = "",
    ) -> None:
        """Write a ``VALUE / KEYWORD comment`` line.

        Parameters
        ----------
        value : object
            The value to write, rendered by :func:`format_cell` with
            ``exact_float=True`` (a float value keeps its float text,
            ``1.0``; pass an ``int`` -- or pre-format with
            ``format_cell(..., integer=True)`` -- for integer fields).
            ``None`` writes a blank value (an optional entry); NaN, inf,
            embedded newlines and unsupported types raise.
        keyword : str
            The keyword label after the ``/``.
        width : int
            Width of the value field for alignment.
        comment : str
            Optional trailing comment.
        """
        if value is None:
            val_str = ""
        else:
            val_str = format_cell(value, what=keyword, allow_blank=True,
                                  exact_float=True)
        _check_newline(keyword, "keyword")
        _check_newline(comment, "comment")
        padded = val_str.rjust(width) if len(val_str) < width else f"    {val_str}"
        suffix = f"/{keyword}"
        if comment:
            suffix += f"    {comment}"
        self._lines.append(f"{padded} {suffix}")

    def write_keyed_path(
        self,
        path: str | None,
        keyword: str,
        base_dir: str | Path | None = None,
        width: int = 50,
    ) -> None:
        """Write a file-path keyed value.

        If *path* is None, writes a blank value (optional file).  An
        absolute path is written relative to *base_dir* -- or, when
        *base_dir* is not given, relative to the folder of the file
        being written (a relative one is passed through unchanged) -- pass
        the simulation working directory (the folder of the simulation
        main file), which is what IWFM resolves referenced paths
        against.  ``..`` traversals are supported (``..\\Results\\...``).
        """
        if path is None:
            val_str = ""
        elif os.path.isabs(str(path)):
            # anchor: base_dir, else the folder of the file being written
            # (right for the main files, whose folder IS the working dir)
            anchor = base_dir if base_dir is not None else (
                self.path.parent if self.path is not None else None)
            val_str = str(path)
            if anchor is not None:
                try:
                    val_str = os.path.relpath(path, anchor)
                except ValueError:  # e.g. different drive on Windows
                    pass
            if val_str.startswith("/"):
                # a leading '/' reads back as a BLANK value (list-directed
                # read stops at the slash) -- never write a POSIX absolute
                raise ValueError(
                    f"{keyword}: absolute path {path!r} cannot be written "
                    "into an IWFM deck (a leading '/' reads as a blank "
                    "value); pass base_dir so it can be relativised")
        else:
            # a relative reference is already deck-relative (the reader
            # keeps unresolvable ones as written) -- never relpath it
            # against the CWD
            val_str = str(path)
        self.write_keyed_value(val_str, keyword, width=width)

    # ------------------------------------------------------------------
    # Tabular data writing
    # ------------------------------------------------------------------

    def write_data_line(self, tokens: list[object], widths: list[int] | None = None,
                        note: str = "") -> None:
        """Write a single row of whitespace-delimited data.

        Parameters
        ----------
        tokens : list
            Values for each column. Strings are written as given
            (pre-formatted by the caller; an empty string is a blank
            continuation field); everything else goes through
            :func:`format_cell`, so missing / non-finite values raise.
        widths : list[int], optional
            Column widths for right-alignment, one per token. If None,
            uses 12 per column.
        note : str, optional
            End-of-line annotation, emitted as ``/ note`` -- transparent
            to IWFM (list-directed reads stop at the slash) but kept by
            the readers' notes/name capture.
        """
        if widths is None:
            widths = [12] * len(tokens)
        if len(widths) != len(tokens):
            raise ValueError(
                f"write_data_line: {len(tokens)} tokens but {len(widths)} "
                "column widths")
        parts = []
        for i, (tok, w) in enumerate(zip(tokens, widths), start=1):
            s = format_cell(tok, what=f"column {i}",
                            allow_blank=isinstance(tok, str))
            if "," in s and _NUMERIC_WITH_COMMA_RE.fullmatch(s):
                # "1,000": a comma is a Fortran list-directed separator,
                # so IWFM would read two fields and shift the row
                raise ValueError(
                    f"column {i}: {s!r} looks numeric but contains a "
                    "comma (a list-directed separator) -- pass a number")
            # a token at/over its column width would fuse with the
            # previous field -- force at least one separating space
            parts.append(s.rjust(w) if len(s) < w else " " + s)
        line = "".join(parts)
        if note:
            _check_newline(note, "note")
            line += f"    / {note}"
        self._lines.append(line)

    def write_data_table(
        self,
        df: pd.DataFrame,
        widths: list[int] | None = None,
        include_index: bool = True,
    ) -> None:
        """Write a DataFrame as whitespace-delimited rows.

        Parameters
        ----------
        df : pd.DataFrame
            Data to write.
        widths : list[int], optional
            Per-column widths.
        include_index : bool
            If True, the DataFrame index is written as the first column.
        """
        n_total = (1 if include_index else 0) + len(df.columns)
        if widths is None:
            widths = [12] * n_total

        for idx, row in df.iterrows():
            tokens: list[object] = []
            if include_index:
                tokens.append(idx)
            tokens.extend(row.tolist())
            self.write_data_line(tokens, widths)

    # ------------------------------------------------------------------
    # Time-series writing
    # ------------------------------------------------------------------

    def write_timeseries_spec(self, spec: TimeSeriesSpec, keywords: list[str] | None = None) -> None:
        """Write a 5-parameter time-series header.

        Parameters
        ----------
        spec : TimeSeriesSpec
        keywords : list[str], optional
            Keywords for each parameter. Defaults to generic names.
        """
        from iwfm_io.writers._timeseries import write_ts_body

        if keywords is None:
            keywords = ["NCOL", "FACT", "NSP", "NFQ", "DSSFL"]
        fields = list(zip(
            [spec.n_columns, spec.factor, spec.n_steps_update,
             spec.repeat_freq, spec.dss_file],
            keywords))
        write_ts_body(self, fields, None, None, n_columns=spec.n_columns)

    def write_timeseries_data(self, df: pd.DataFrame, col_width: int = 18) -> None:
        """Write time-series data rows.

        Supports two DataFrame formats:
        1. DataFrame with a ``date`` column (IWFM date strings or
           datetimes).
        2. DataFrame with a DatetimeIndex.

        Value columns named ``col_N`` are written in numeric order of
        *N* (never in DataFrame column order); a frame mixing ``col_N``
        names with other names is refused. Every value must be finite
        and every date a valid IWFM date, else ``ValueError`` names the
        offending row and column.

        Parameters
        ----------
        df : pd.DataFrame
        col_width : int
            Width for value columns.
        """
        if "date" in df.columns:
            dates = df["date"].tolist()
            value_cols = [c for c in df.columns if c != "date"]
        else:
            dates = list(df.index)
            value_cols = list(df.columns)
        expected = getattr(self, "_last_spec_ncol", None)
        if expected is not None and expected != len(value_cols):
            raise ValueError(
                f"time-series spec declares {expected} data columns but "
                f"the DataFrame has {len(value_cols)} -- update NCOL or "
                "the data")
        numbered = numbered_columns(df[value_cols], "col_")
        if numbered:
            if len(numbered) != len(value_cols):
                extra = [c for c in value_cols if c not in numbered]
                raise ValueError(
                    "time-series data mixes col_N columns with "
                    f"{extra} -- the column order would be ambiguous")
            value_cols = numbered

        n = len(df)
        if n == 0:
            return
        try:
            vals = df[value_cols].to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"time-series data has a non-numeric value: {exc}") from None
        finite = np.isfinite(vals)
        if not finite.all():
            r, c = np.argwhere(~finite)[0]
            raise ValueError(
                f"time-series data: non-finite value {vals[r, c]!r} at "
                f"row {r} (date {dates[r]!r}), column {value_cols[c]!r} -- "
                "fill or drop it first")

        # %.10g keeps full practical precision (%.6g measurably
        # truncated values like 7-digit pumping rates on round-trip).
        fmt = f"%{col_width}.10g"
        text = np.full(n, "", dtype=object)
        for j in range(vals.shape[1]):
            text = text + np.char.mod(fmt, vals[:, j]).astype(object)
        date_strs = [format_date_cell(d, f"time-series row {i} date")
                     for i, d in enumerate(dates)]
        self._lines.extend(
            f"  {d}{v}" for d, v in zip(date_strs, text))

    def write_dss_pathnames(self, pathnames: list[tuple[int, str]]) -> None:
        """Write DSS pathname assignments (validated against the spec's
        NCOL when a spec was written first -- IWFM reads exactly NCOL
        pathname rows)."""
        expected = getattr(self, "_last_spec_ncol", None)
        if expected is not None and expected != len(pathnames):
            raise ValueError(
                f"time-series spec declares {expected} columns but "
                f"{len(pathnames)} DSS pathnames were provided")
        for col_id, pathname in pathnames:
            col = format_cell(col_id, what="DSS pathname column",
                              integer=True)
            path = format_cell(pathname, what="DSS pathname")
            self._lines.append(f"     {col}    {path}")

    # ------------------------------------------------------------------
    # Raw line writing
    # ------------------------------------------------------------------

    def write_raw(self, line: str) -> None:
        """Write a raw line as-is (a line break inside it raises)."""
        _check_newline(line, "raw line")
        self._lines.append(line)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def flush(self, path: str | Path | None = None) -> None:
        """Write all accumulated lines to the output file.

        Parameters
        ----------
        path : str or Path, optional
            Override the path set in the constructor.
        """
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("No output path specified")
        target.parent.mkdir(parents=True, exist_ok=True)
        replace_file_text(target, "".join(line + "\n" for line in self._lines),
                          encoding="utf-8", newline="\n")

    def to_string(self) -> str:
        """Return all lines joined as a single string."""
        return "\n".join(self._lines) + "\n"
