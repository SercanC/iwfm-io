"""Strict / lenient reader mode.

Every file reader in ``iwfm_io`` snapshots the current mode when it is
created.  In **strict** mode (the default) malformed input — truncated
sections, short rows, non-numeric values where numbers are expected,
unrecognized content — raises :class:`~iwfm_io._parser.IWFMParseError`
naming the file, line and section.  In **lenient** mode the reader
keeps what it could parse and emits an
:class:`~iwfm_io._parser.IWFMReadWarning` instead.

Only *recoverable* situations are governed by the mode: section-level
recovery, time-series rows with too few values, and the heuristics that
decide where a table ends.  Tables whose length is declared by a count
variable (ND, NE, NRDV, ...) always raise on a shortfall — a wrong count
is never something to keep going from.

The mode is a :class:`contextvars.ContextVar`, so it is safe across
threads and ``asyncio`` tasks and is scoped by :func:`strict_mode`::

    with iwfm_io.strict_mode(False):
        model = iwfm_io.open_model(path)   # lenient for this call only
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_STRICT: ContextVar[bool] = ContextVar("iwfm_io_strict", default=True)


def current_strict() -> bool:
    """The reader mode in effect: ``True`` = strict (raise), ``False`` =
    lenient (warn and keep what parsed)."""
    return _STRICT.get()


@contextmanager
def strict_mode(enabled: bool = True):
    """Context manager setting the reader mode for the enclosed block.

    Parameters
    ----------
    enabled : bool
        ``True`` (default) makes readers raise ``IWFMParseError`` on
        malformed input; ``False`` makes them warn (``IWFMReadWarning``)
        and keep what they could parse.

    Readers created inside the block snapshot the mode, so an object
    that keeps parsing lazily after the block ends still uses the mode
    it was created under.
    """
    token = _STRICT.set(bool(enabled))
    try:
        yield
    finally:
        _STRICT.reset(token)
