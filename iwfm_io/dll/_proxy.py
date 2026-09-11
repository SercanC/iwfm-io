"""A guard around every DLL call.

The IWFM DLL keeps process-global state (one current model, one open
budget file, files opened relative to the process working directory)
and its Fortran routines are not reentrant. Wrapper objects therefore
never hold the raw ``ctypes`` library: they hold a :class:`GuardedDLL`
whose attribute access returns callables that

1. take the process-wide re-entrant lock (ctypes releases the GIL, so
   two Python threads could otherwise run Fortran concurrently),
2. run the owner's ``before`` hook (model activation / budget-file
   ownership / closed-object checks),
3. anchor the working directory to the model's run directory for the
   duration of the call (the DLL opens result files lazily, relative
   to the CWD at call time),

and then call the real export. Non-callable attributes (registration
flags) pass straight through.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager

_DLL_LOCK = threading.RLock()


@contextmanager
def _cwd(path):
    if path is None:
        yield
        return
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


class GuardedDLL:
    """Proxy over the raw DLL applying the lock/hook/cwd guard."""

    def __init__(self, dll, before=None, run_dir=None):
        object.__setattr__(self, "_raw", dll)
        object.__setattr__(self, "_before", before)
        object.__setattr__(self, "_run_dir", run_dir)

    @property
    def raw(self):
        """The underlying ``ctypes`` library (no guard)."""
        return self._raw

    def __getattr__(self, name):
        attr = getattr(self._raw, name)
        if not callable(attr):
            return attr
        before, run_dir = self._before, self._run_dir

        def call(*args):
            with _DLL_LOCK:
                if before is not None:
                    before(name)
                with _cwd(run_dir):
                    return attr(*args)
        call.__name__ = name
        return call

    def __setattr__(self, name, value):
        setattr(self._raw, name, value)
