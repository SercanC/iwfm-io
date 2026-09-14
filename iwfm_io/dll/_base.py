"""Shared call boilerplate for the DLL wrapper classes.

Every IWFM export is a Fortran subroutine whose last argument is an
``iStat`` out-parameter; the wrappers used to spell the same three
lines at each of ~140 call sites (allocate ``iStat``, call, check).
:func:`call_dll` is that sequence once; :class:`_DllCallMixin` binds it
to an object's ``_dll`` handle and adds the recurring result shapes
(scalar out-parameter, ``n``-sized int/double buffers); and
:class:`_DllFileReader` is the lifecycle the two standalone file readers
(:class:`~iwfm_io.dll.budget.IWFMBudget`,
:class:`~iwfm_io.dll.zbudget.IWFMZBudget`) share.

Nothing here touches string marshalling (``str_to_c`` /
``c_to_str_list`` and their buffer sizes stay at the call sites) and
the guard around every call (lock, activation, working directory) is
still :class:`~iwfm_io.dll._proxy.GuardedDLL` -- the helpers only go
through ``self._dll``.
"""

import os
from ctypes import c_int, c_double, byref

import numpy as np

from ._dll import load_dll
from ._errors import IWFMError, _check_status
from ._marshal import str_to_c, alloc_int, alloc_double
from ._proxy import GuardedDLL


def call_dll(dll, name, *args):
    """Invoke ``dll.<name>(*args, byref(iStat))`` and raise
    :class:`IWFMError` on a non-zero status."""
    iStat = c_int(0)
    getattr(dll, name)(*args, byref(iStat))
    _check_status(iStat, dll)


def fortran_view(buf, shape):
    """A column-major ``(rows, cols)`` view of a ctypes double buffer
    (no copy -- ``.copy()`` before handing it out)."""
    return np.frombuffer(buf, dtype=np.float64).reshape(shape, order="F")


class _DllCallMixin:
    """Status-checked calls through ``self._dll`` (a ``GuardedDLL``)."""

    def _call(self, name, *args):
        """``self._dll.<name>(*args, byref(iStat))`` + status check."""
        call_dll(self._dll, name, *args)

    def _scalar_int(self, name, *lead_args):
        """``name(*lead_args, byref(n))`` -> ``int``."""
        n = c_int(0)
        self._call(name, *lead_args, byref(n))
        return n.value

    def _scalar_double(self, name, *lead_args):
        """``name(*lead_args, byref(v))`` -> ``float``."""
        v = c_double(0.0)
        self._call(name, *lead_args, byref(v))
        return v.value

    def _int_array(self, name, n, *lead_args, mid=()):
        """``name(*lead_args, n, *mid, buf)`` -> int32 array of *n*."""
        buf = alloc_int(n)
        self._call(name, *lead_args, c_int(n), *mid, buf)
        return np.array(buf, dtype=np.int32)

    def _double_array(self, name, n, *lead_args, mid=()):
        """``name(*lead_args, n, *mid, buf)`` -> float64 array of *n*."""
        buf = alloc_double(n)
        self._call(name, *lead_args, c_int(n), *mid, buf)
        return np.array(buf, dtype=np.float64)

    def _double_arrays(self, name, n, k, *lead_args):
        """``name(*lead_args, n, buf_1, .., buf_k)`` -> *k* float64 arrays
        of *n* (paired outputs such as x/y or top/bottom)."""
        bufs = [alloc_double(n) for _ in range(k)]
        self._call(name, *lead_args, c_int(n), *bufs)
        return tuple(np.array(b, dtype=np.float64) for b in bufs)


class _DllFileReader(_DllCallMixin):
    """Lifecycle of a standalone budget-type file opened in the DLL.

    The DLL holds a single open file per kind (``IW_Budget_*`` /
    ``IW_ZBudget_*``), so each concrete reader class tracks which path
    currently occupies its slot in ``_current_path`` and re-opens its
    own file transparently when another instance has taken the slot.
    Subclasses set ``_OPEN_FN`` / ``_CLOSE_FN`` and declare
    ``_current_path = None``.
    """

    _OPEN_FN = None
    _CLOSE_FN = None

    def __init__(self, hdf_file, dll_version=None, dll_path=None):
        self._open = False
        self._path = os.path.abspath(str(hdf_file))
        if not os.path.isfile(self._path):
            raise FileNotFoundError(f"budget file not found: {self._path}")
        raw = load_dll(version=dll_version, dll_path=dll_path)
        self._dll = GuardedDLL(raw, before=self._before_call)
        self._reopen()
        self._open = True

    @classmethod
    def _slot_owner(cls):
        """The class that declares ``_current_path`` -- the bookkeeping
        for the DLL's file slot (a user subclass shares its parent's)."""
        for klass in cls.__mro__:
            if "_current_path" in klass.__dict__:
                return klass
        return cls

    def _before_call(self, name):
        if name in (self._OPEN_FN, self._CLOSE_FN, "IW_GetLastMessage"):
            return
        if not self._open:
            raise IWFMError(f"{self._slot_owner().__name__} is closed", -1)
        if self._slot_owner()._current_path != self._path:
            # another instance took the DLL's single file slot: reopen
            # ours transparently (the DLL closes the other one)
            self._reopen()

    def _reopen(self):
        c_len, c_name = str_to_c(self._path)
        iStat = c_int(0)
        getattr(self._dll.raw, self._OPEN_FN)(c_name, c_len, byref(iStat))
        _check_status(iStat, self._dll.raw)
        self._slot_owner()._current_path = self._path

    def close(self):
        """Close the file (releases the DLL's file slot)."""
        if self._open:
            try:
                owner = self._slot_owner()
                if owner._current_path == self._path:
                    self._call(self._CLOSE_FN)
                    owner._current_path = None
            finally:
                self._open = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
