"""Fortran <-> Python data conversion helpers."""

import sys
from ctypes import c_int, c_double, c_char

import numpy as np


#: The DLL copies raw bytes and opens files through the ANSI code page.
_ENC = "mbcs" if sys.platform == "win32" else "utf-8"


def str_to_c(s):
    """Convert Python str to (c_int length, c_char_Array) for Fortran input."""
    if not isinstance(s, str):
        raise TypeError(f"expected a string for the DLL, got {type(s).__name__}")
    try:
        encoded = s.encode(_ENC)
    except UnicodeEncodeError as exc:
        from iwfm_io.dll._errors import IWFMError
        raise IWFMError(
            f"cannot pass {s!r} to the IWFM DLL: {exc.reason} (the DLL "
            f"accepts only {_ENC}-encodable text)", -1) from None
    length = c_int(len(encoded))
    buf = (c_char * len(encoded))(*encoded)
    return length, buf


def c_to_str(buf, length):
    """Convert c_char buffer to Python str, stripping null bytes and whitespace."""
    return bytes(buf[:length]).decode(_ENC, errors="replace").rstrip("\x00 ")


def c_to_str_list(buf, loc_array, count):
    """Convert packed Fortran char buffer + offset array into list of Python strings.

    The Fortran side packs multiple strings into a single char buffer and
    returns a 1-based offset array (iLocArray) indicating where each string
    starts in the buffer.
    """
    raw = bytes(buf)
    result = []
    for i in range(count):
        start = loc_array[i] - 1  # Fortran 1-based -> Python 0-based
        if i + 1 < count:
            end = loc_array[i + 1] - 1
        else:
            end = len(raw)
        s = raw[start:end].decode(_ENC, errors="replace").rstrip("\x00 ")
        result.append(s)
    return result


def alloc_int(n):
    """Allocate a ctypes int array of size n."""
    return (c_int * n)()


def alloc_double(n):
    """Allocate a ctypes double array of size n."""
    return (c_double * n)()


def alloc_char(n):
    """Allocate a ctypes char buffer of size n."""
    return (c_char * n)()


def c_to_np(buf, dtype=None):
    """Convert a ctypes array to a numpy array."""
    return np.array(buf, dtype=dtype, copy=True)
