"""
Writer for IWFM text files.

Builds lines in memory and writes them out on :meth:`flush`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm.io._tokens import format_iwfm_date
from iwfm.io.models.base import FileHeader, TimeSeriesSpec


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

        If *text* does not already start with a comment character, ``C``
        is prepended.
        """
        stripped = text.lstrip()
        if stripped and stripped[0] in "Cc*/":
            self._lines.append(text)
        else:
            self._lines.append(f"C {text}")

    def write_comments(self, lines: list[str]) -> None:
        """Write multiple comment lines verbatim."""
        self._lines.extend(lines)

    def write_version_header(self, version: str) -> None:
        """Write a version header like ``#4.0``."""
        self._lines.append(f"#{version}")

    def write_header(self, header: FileHeader) -> None:
        """Write a :class:`FileHeader` (version + comment lines)."""
        for line in header.comment_lines:
            self._lines.append(line)

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
            The value to write (will be converted via str()).
        keyword : str
            The keyword label after the ``/``.
        width : int
            Width of the value field for alignment.
        comment : str
            Optional trailing comment.
        """
        val_str = str(value)
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

        If *path* is None, writes a blank value (optional file).
        """
        if path is None:
            val_str = ""
        elif base_dir is not None:
            try:
                val_str = str(Path(path).relative_to(Path(base_dir)))
            except ValueError:
                val_str = str(path)
        else:
            val_str = str(path)
        self.write_keyed_value(val_str, keyword, width=width)

    # ------------------------------------------------------------------
    # Tabular data writing
    # ------------------------------------------------------------------

    def write_data_line(self, tokens: list[object], widths: list[int] | None = None) -> None:
        """Write a single row of whitespace-delimited data.

        Parameters
        ----------
        tokens : list
            Values for each column.
        widths : list[int], optional
            Column widths for right-alignment. If None, uses 12 per column.
        """
        if widths is None:
            widths = [12] * len(tokens)
        parts = []
        for tok, w in zip(tokens, widths):
            s = str(tok)
            parts.append(s.rjust(w))
        self._lines.append("".join(parts))

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
        if keywords is None:
            keywords = ["NCOL", "FACT", "NSP", "NFQ", "DSSFL"]
        self.write_keyed_value(spec.n_columns, keywords[0])
        self.write_keyed_value(spec.factor, keywords[1])
        self.write_keyed_value(spec.n_steps_update, keywords[2])
        self.write_keyed_value(spec.repeat_freq, keywords[3])
        self.write_keyed_value(spec.dss_file, keywords[4])

    def write_timeseries_data(self, df: pd.DataFrame, col_width: int = 14) -> None:
        """Write time-series data rows.

        Supports two DataFrame formats:
        1. DataFrame with a ``date`` column (IWFM date strings).
        2. DataFrame with a DatetimeIndex.

        Parameters
        ----------
        df : pd.DataFrame
        col_width : int
            Width for value columns.
        """
        if "date" in df.columns:
            # Date is a column, value columns follow
            value_cols = [c for c in df.columns if c != "date"]
            for _, row in df.iterrows():
                date_str = row["date"]
                vals = "".join(f"{float(row[c]):>{col_width}.6g}" for c in value_cols)
                self._lines.append(f"  {date_str}{vals}")
        else:
            # DatetimeIndex format
            for dt, row in df.iterrows():
                date_str = format_iwfm_date(dt)
                vals = "".join(f"{v:>{col_width}.6g}" for v in row)
                self._lines.append(f"  {date_str}{vals}")

    def write_dss_pathnames(self, pathnames: list[tuple[int, str]]) -> None:
        """Write DSS pathname assignments."""
        for col_id, pathname in pathnames:
            self._lines.append(f"     {col_id}    {pathname}")

    # ------------------------------------------------------------------
    # Raw line writing
    # ------------------------------------------------------------------

    def write_raw(self, line: str) -> None:
        """Write a raw line as-is."""
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
        with open(target, "w", encoding="utf-8", newline="\n") as fh:
            for line in self._lines:
                fh.write(line + "\n")

    def to_string(self) -> str:
        """Return all lines joined as a single string."""
        return "\n".join(self._lines) + "\n"
