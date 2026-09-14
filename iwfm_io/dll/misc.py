"""IWFM miscellaneous exports: version info, type ID enums, and time utilities."""

from ctypes import c_int, c_char, byref

from ._base import call_dll as _call
from ._proxy import _DLL_LOCK
from ._validate import check_date, check_int, check_interval, check_window


def _get_string(dll, name, buf_len=512):
    """Fetch a fixed-length character out-parameter: ``name(len, buf)``."""
    buf = (c_char * buf_len)()
    _call(dll, name, c_int(buf_len), buf)
    return bytes(buf).decode("ascii").rstrip("\x00 ")


def _get_ints(dll, name, count):
    """Fetch *count* integer out-parameters (the type-ID exports):
    ``name(byref(id_1), .., byref(id_count))``."""
    ids = [c_int(0) for _ in range(count)]
    _call(dll, name, *(byref(v) for v in ids))
    return [v.value for v in ids]


# ---------------------------------------------------------------------------
# Version functions
# ---------------------------------------------------------------------------

def get_version(dll):
    """Return the IWFM application version string."""
    return _get_string(dll, "IW_GetVersion")


def get_kernel_version(dll):
    """Return the IWFM kernel version string."""
    return _get_string(dll, "IW_IWFMKernel_GetVersion")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def set_log_file(dll, path):
    """Set the DLL log file path."""
    encoded = path.encode("ascii")
    c_len = c_int(len(encoded))
    buf = (c_char * len(encoded))(*encoded)
    _call(dll, "IW_SetLogFile", c_len, buf)


def close_log_file(dll):
    """Close the DLL log file."""
    _call(dll, "IW_CloseLogFile")


def get_last_message(dll):
    """Return the last DLL error/status message."""
    buf_len = 4096
    c_len = c_int(buf_len)
    buf = (c_char * buf_len)()
    iStat = c_int(0)
    dll.IW_GetLastMessage(c_len, buf, byref(iStat))
    return bytes(buf).decode("ascii", errors="replace").rstrip("\x00 ")


def log_last_message(dll):
    """Write the last message to the log file."""
    _call(dll, "IW_LogLastMessage")


# ---------------------------------------------------------------------------
# Type ID enum classes — populated from DLL constants
# ---------------------------------------------------------------------------

class BudgetTypeID:
    """Budget type identifiers."""

    GW = None
    RootZone = None
    LWU = None
    NonPondedCrop_RZ = None
    NonPondedCrop_LWU = None
    PondedCrop_RZ = None
    PondedCrop_LWU = None
    UnsatZone = None
    StrmNode = None
    StrmReach = None
    DiverDetail = None
    SWShed = None
    Lake = None

    @classmethod
    def _load(cls, dll):
        (cls.GW, cls.RootZone, cls.LWU, cls.NonPondedCrop_RZ,
         cls.NonPondedCrop_LWU, cls.PondedCrop_RZ, cls.PondedCrop_LWU,
         cls.UnsatZone, cls.StrmNode, cls.StrmReach, cls.DiverDetail,
         cls.SWShed, cls.Lake) = _get_ints(dll, "IW_GetBudgetTypeIDs", 13)


class ZBudgetTypeID:
    """Zone-budget type identifiers."""

    GW = None
    RootZone = None
    LWU = None
    UnsatZone = None

    @classmethod
    def _load(cls, dll):
        (cls.GW, cls.RootZone, cls.LWU,
         cls.UnsatZone) = _get_ints(dll, "IW_GetZBudgetTypeIDs", 4)


class LandUseTypeID:
    """Land use type identifiers (v2 — most complete)."""

    GenAg = None
    Urb = None
    NonPondedAg = None
    PondedAg = None
    Rice = None
    Refuge = None
    UrbIn = None
    UrbOut = None
    NVRV = None

    @classmethod
    def _load(cls, dll):
        (cls.GenAg, cls.Urb, cls.NonPondedAg, cls.PondedAg, cls.Rice,
         cls.Refuge, cls.UrbIn, cls.UrbOut,
         cls.NVRV) = _get_ints(dll, "IW_GetLandUseTypeIDs_2", 9)


class LocationTypeID:
    """Location type identifiers (v1 — includes Diversion and Bypass)."""

    Node = None
    Element = None
    Subregion = None
    Zone = None
    Lake = None
    StrmNode = None
    StrmReach = None
    TileDrainObs = None
    SmallWatershed = None
    GWHeadObs = None
    StrmHydObs = None
    SubsidenceObs = None
    StrmNodeBud = None
    Diversion = None
    Bypass = None

    @classmethod
    def _load(cls, dll):
        (cls.Node, cls.Element, cls.Subregion, cls.Zone, cls.Lake,
         cls.StrmNode, cls.StrmReach, cls.TileDrainObs, cls.SmallWatershed,
         cls.GWHeadObs, cls.StrmHydObs, cls.SubsidenceObs, cls.StrmNodeBud,
         cls.Diversion, cls.Bypass) = _get_ints(dll, "IW_GetLocationTypeIDs_1", 15)


class FlowDestTypeID:
    """Flow destination type identifiers."""

    Outside = None
    StrmNode = None
    Element = None
    Lake = None
    Subregion = None
    GWElement = None
    ElementSet = None

    @classmethod
    def _load(cls, dll):
        (cls.Outside, cls.StrmNode, cls.Element, cls.Lake,
         cls.Subregion, cls.GWElement,
         cls.ElementSet) = _get_ints(dll, "IW_GetFlowDestTypeIDs", 7)


class SupplyTypeID:
    """Supply type identifiers."""

    Diversion = None
    Well = None
    ElemPump = None

    @classmethod
    def _load(cls, dll):
        cls.Diversion = _get_ints(dll, "IW_GetSupplyTypeID_Diversion", 1)[0]
        cls.Well = _get_ints(dll, "IW_GetSupplyTypeID_Well", 1)[0]
        cls.ElemPump = _get_ints(dll, "IW_GetSupplyTypeID_ElemPump", 1)[0]


class ZoneExtentID:
    """Zone extent identifiers."""

    Horizontal = None
    Vertical = None

    @classmethod
    def _load(cls, dll):
        cls.Horizontal, cls.Vertical = _get_ints(dll, "IW_GetZoneExtentIDs", 2)


class DataUnitTypeID:
    """Data unit type identifiers."""

    Length = None
    Area = None
    Volume = None

    @classmethod
    def _load(cls, dll):
        cls.Length, cls.Area, cls.Volume = _get_ints(dll, "IW_GetDataUnitTypeIDs", 3)


def load_all_type_ids(dll):
    """Populate all enum classes from the DLL. Called once at import/init."""
    BudgetTypeID._load(dll)
    ZBudgetTypeID._load(dll)
    LandUseTypeID._load(dll)
    LocationTypeID._load(dll)
    FlowDestTypeID._load(dll)
    SupplyTypeID._load(dll)
    ZoneExtentID._load(dll)
    DataUnitTypeID._load(dll)


# ---------------------------------------------------------------------------
# Time utilities
# ---------------------------------------------------------------------------

def get_n_intervals(dll, begin_date, end_date, interval):
    """Return the number of time intervals between two dates.

    Parameters
    ----------
    begin_date, end_date : str
        Date-time strings (e.g. ``"10/01/1990_24:00"``).
    interval : str
        Time step string (e.g. ``"1MON"``).
    """
    begin_date, end_date = check_window(begin_date, end_date)
    interval = check_interval(interval)
    b_enc = begin_date.encode("ascii")
    e_enc = end_date.encode("ascii")
    i_enc = interval.encode("ascii")
    # both dates are validated MM/DD/YYYY_HH:MM, hence the same length
    c_len_date = c_int(len(b_enc))
    c_len_intv = c_int(len(i_enc))
    c_begin = (c_char * len(b_enc))(*b_enc)
    c_end = (c_char * len(e_enc))(*e_enc)
    c_intv = (c_char * len(i_enc))(*i_enc)
    n = c_int(0)
    with _DLL_LOCK:
        _call(dll, "IW_GetNIntervals",
              c_begin, c_end, c_len_date, c_intv, c_len_intv, byref(n))
    return n.value


def increment_time(dll, date_time, interval, count=1):
    """Increment a date-time string by *count* intervals.

    Returns the new date-time string.
    """
    date_time = check_date("date_time", date_time)
    interval = check_interval(interval)
    count = check_int("count", count)
    dt_enc = date_time.encode("ascii")
    iv_enc = interval.encode("ascii")
    c_len_dt = c_int(len(dt_enc))
    c_len_iv = c_int(len(iv_enc))
    # date-time is INOUT: keep headroom beyond the 16-character stamp
    dt_buf = (c_char * 32)(*dt_enc)
    iv_buf = (c_char * len(iv_enc))(*iv_enc)
    with _DLL_LOCK:
        _call(dll, "IW_IncrementTime",
              c_len_dt, dt_buf, c_len_iv, iv_buf, c_int(count))
    return bytes(dt_buf).decode("ascii").rstrip("\x00 ")


def is_time_greater_than(dll, dt1, dt2):
    """Return True if *dt1* is later than *dt2*."""
    dt1 = check_date("dt1", dt1)
    dt2 = check_date("dt2", dt2)
    enc1 = dt1.encode("ascii")
    enc2 = dt2.encode("ascii")
    length = max(len(enc1), len(enc2))
    c_len = c_int(length)
    buf1 = (c_char * length)(*enc1.ljust(length))
    buf2 = (c_char * length)(*enc2.ljust(length))
    result = c_int(0)
    with _DLL_LOCK:
        _call(dll, "IW_IsTimeGreaterThan", c_len, buf1, buf2, byref(result))
    return result.value == 1
