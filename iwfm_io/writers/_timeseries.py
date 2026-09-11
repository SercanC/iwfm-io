"""Shared body writer for IWFM time-series input files.

Every time-series writer (precipitation, ET, pumping, diversions,
inflows, boundary conditions, irrigation fractions, ...) has the same
shape: a keyed specification block, the load-bearing comment that
terminates it, an optional file-specific block, then either DSS
pathname assignments or inline data rows. :func:`write_ts_body` is the
one implementation; the per-file writers only supply the keywords.
"""

from __future__ import annotations

from typing import Callable, Iterable

import pandas as pd

from iwfm_io._writer import IWFMFileWriter

#: The comment that terminates a time-series specification block.
#: IWFM's file reader otherwise consumes the first data/pathname line
#: while resolving the (possibly blank) DSS filename, shifting the
#: whole time-series read (verified against the executables: without
#: this line a recurring-year ET file fails with "End-of-file
#: reached"). Load-bearing, not decoration.
END_OF_SPEC = "C  end of specification"


def write_ts_body(
    w: IWFMFileWriter,
    fields: Iterable[tuple[object, str]],
    data: pd.DataFrame | None,
    dss_pathnames: list[tuple[int, str]] | None,
    *,
    n_columns: int,
    between: Callable[[IWFMFileWriter], None] | None = None,
) -> None:
    """Write a time-series file body: spec fields, terminator, data.

    Parameters
    ----------
    w : IWFMFileWriter
    fields : iterable of (value, keyword)
        The keyed specification lines, in file order (``NCOL``,
        ``FACT``, ``NSP``, ``NFQ``, ``DSSFL`` or the file's variants;
        a ``None`` value writes a blank entry).
    data : pandas.DataFrame or None
        Inline data rows (``date`` column or DatetimeIndex + value
        columns), written when *dss_pathnames* is empty.
    dss_pathnames : list of (column, pathname) or None
        DSS pathname assignments; when non-empty they are written
        instead of *data*.
    n_columns : int
        The declared NCOL. Both the pathname count and the data width
        are checked against it (IWFM reads exactly NCOL of either).
    between : callable, optional
        Writes a file-specific block between the terminating comment
        and the data (the stream-inflow node assignments).
    """
    for value, keyword in fields:
        w.write_keyed_value(value, keyword)
    w.write_comment(END_OF_SPEC)
    if between is not None:
        between(w)
    w._last_spec_ncol = int(n_columns)
    if dss_pathnames:
        w.write_dss_pathnames(list(dss_pathnames))
    elif data is not None:
        w.write_timeseries_data(data)
