"""IWFM DLL error handling."""

from ctypes import c_int, c_char, byref


class IWFMError(Exception):
    """Exception raised when an IWFM DLL function returns a non-zero status."""

    def __init__(self, message, status_code=-1):
        self.status_code = status_code
        self.message = message
        super().__init__(f"IWFM error ({status_code}): {message}")


def _check_status(iStat, dll):
    """Check iStat and raise IWFMError with the DLL's last message on failure."""
    if iStat.value != 0:
        buf_len = 4096
        c_len = c_int(buf_len)
        msg_buf = (c_char * buf_len)()
        msg_stat = c_int(0)
        dll.IW_GetLastMessage(c_len, msg_buf, byref(msg_stat))
        message = bytes(msg_buf).decode("ascii", errors="replace").rstrip("\x00 ")
        raise IWFMError(message, iStat.value)
