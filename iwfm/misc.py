"""IWFM miscellaneous exports: version info, type ID enums, and time utilities."""

from ctypes import c_int, c_char, c_double, byref

from ._errors import _check_status


# ---------------------------------------------------------------------------
# Version functions
# ---------------------------------------------------------------------------

def get_version(dll):
    """Return the IWFM application version string."""
    buf_len = 512
    c_len = c_int(buf_len)
    buf = (c_char * buf_len)()
    iStat = c_int(0)
    dll.IW_GetVersion(c_len, buf, byref(iStat))
    _check_status(iStat, dll)
    return bytes(buf).decode("ascii").rstrip("\x00 ")


def get_kernel_version(dll):
    """Return the IWFM kernel version string."""
    buf_len = 512
    c_len = c_int(buf_len)
    buf = (c_char * buf_len)()
    iStat = c_int(0)
    dll.IW_IWFMKernel_GetVersion(c_len, buf, byref(iStat))
    _check_status(iStat, dll)
    return bytes(buf).decode("ascii").rstrip("\x00 ")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def set_log_file(dll, path):
    """Set the DLL log file path."""
    encoded = path.encode("ascii")
    c_len = c_int(len(encoded))
    buf = (c_char * len(encoded))(*encoded)
    iStat = c_int(0)
    dll.IW_SetLogFile(c_len, buf, byref(iStat))
    _check_status(iStat, dll)


def close_log_file(dll):
    """Close the DLL log file."""
    iStat = c_int(0)
    dll.IW_CloseLogFile(byref(iStat))
    _check_status(iStat, dll)


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
    iStat = c_int(0)
    dll.IW_LogLastMessage(byref(iStat))
    _check_status(iStat, dll)


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
        ids = [c_int(0) for _ in range(13)]
        iStat = c_int(0)
        dll.IW_GetBudgetTypeIDs(
            byref(ids[0]),   # GW
            byref(ids[1]),   # RootZone
            byref(ids[2]),   # LWU
            byref(ids[3]),   # NonPondedCrop_RZ
            byref(ids[4]),   # NonPondedCrop_LWU
            byref(ids[5]),   # PondedCrop_RZ
            byref(ids[6]),   # PondedCrop_LWU
            byref(ids[7]),   # UnsatZone
            byref(ids[8]),   # StrmNode
            byref(ids[9]),   # StrmReach
            byref(ids[10]),  # DiverDetail
            byref(ids[11]),  # SWShed
            byref(ids[12]),  # Lake
            byref(iStat),
        )
        _check_status(iStat, dll)
        (cls.GW, cls.RootZone, cls.LWU, cls.NonPondedCrop_RZ,
         cls.NonPondedCrop_LWU, cls.PondedCrop_RZ, cls.PondedCrop_LWU,
         cls.UnsatZone, cls.StrmNode, cls.StrmReach, cls.DiverDetail,
         cls.SWShed, cls.Lake) = [v.value for v in ids]


class ZBudgetTypeID:
    """Zone-budget type identifiers."""

    GW = None
    RootZone = None
    LWU = None
    UnsatZone = None

    @classmethod
    def _load(cls, dll):
        ids = [c_int(0) for _ in range(4)]
        iStat = c_int(0)
        dll.IW_GetZBudgetTypeIDs(
            byref(ids[0]), byref(ids[1]), byref(ids[2]), byref(ids[3]),
            byref(iStat),
        )
        _check_status(iStat, dll)
        cls.GW, cls.RootZone, cls.LWU, cls.UnsatZone = [v.value for v in ids]


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
        ids = [c_int(0) for _ in range(9)]
        iStat = c_int(0)
        dll.IW_GetLandUseTypeIDs_2(
            byref(ids[0]),  # GenAg
            byref(ids[1]),  # Urb
            byref(ids[2]),  # NonPondedAg
            byref(ids[3]),  # PondedAg
            byref(ids[4]),  # Rice
            byref(ids[5]),  # Refuge
            byref(ids[6]),  # UrbIn
            byref(ids[7]),  # UrbOut
            byref(ids[8]),  # NVRV
            byref(iStat),
        )
        _check_status(iStat, dll)
        (cls.GenAg, cls.Urb, cls.NonPondedAg, cls.PondedAg, cls.Rice,
         cls.Refuge, cls.UrbIn, cls.UrbOut, cls.NVRV) = [v.value for v in ids]


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
        ids = [c_int(0) for _ in range(15)]
        iStat = c_int(0)
        dll.IW_GetLocationTypeIDs_1(
            byref(ids[0]),   # Node
            byref(ids[1]),   # Element
            byref(ids[2]),   # Subregion
            byref(ids[3]),   # Zone
            byref(ids[4]),   # Lake
            byref(ids[5]),   # StrmNode
            byref(ids[6]),   # StrmReach
            byref(ids[7]),   # TileDrainObs
            byref(ids[8]),   # SmallWatershed
            byref(ids[9]),   # GWHeadObs
            byref(ids[10]),  # StrmHydObs
            byref(ids[11]),  # SubsidenceObs
            byref(ids[12]),  # StrmNodeBud
            byref(ids[13]),  # Diversion
            byref(ids[14]),  # Bypass
            byref(iStat),
        )
        _check_status(iStat, dll)
        (cls.Node, cls.Element, cls.Subregion, cls.Zone, cls.Lake,
         cls.StrmNode, cls.StrmReach, cls.TileDrainObs, cls.SmallWatershed,
         cls.GWHeadObs, cls.StrmHydObs, cls.SubsidenceObs, cls.StrmNodeBud,
         cls.Diversion, cls.Bypass) = [v.value for v in ids]


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
        ids = [c_int(0) for _ in range(7)]
        iStat = c_int(0)
        dll.IW_GetFlowDestTypeIDs(
            byref(ids[0]), byref(ids[1]), byref(ids[2]), byref(ids[3]),
            byref(ids[4]), byref(ids[5]), byref(ids[6]), byref(iStat),
        )
        _check_status(iStat, dll)
        (cls.Outside, cls.StrmNode, cls.Element, cls.Lake,
         cls.Subregion, cls.GWElement, cls.ElementSet) = [v.value for v in ids]


class SupplyTypeID:
    """Supply type identifiers."""

    Diversion = None
    Well = None
    ElemPump = None

    @classmethod
    def _load(cls, dll):
        vals = [c_int(0) for _ in range(3)]
        iStat = c_int(0)
        dll.IW_GetSupplyTypeID_Diversion(byref(vals[0]), byref(iStat))
        _check_status(iStat, dll)
        dll.IW_GetSupplyTypeID_Well(byref(vals[1]), byref(iStat))
        _check_status(iStat, dll)
        dll.IW_GetSupplyTypeID_ElemPump(byref(vals[2]), byref(iStat))
        _check_status(iStat, dll)
        cls.Diversion, cls.Well, cls.ElemPump = [v.value for v in vals]


class ZoneExtentID:
    """Zone extent identifiers."""

    Horizontal = None
    Vertical = None

    @classmethod
    def _load(cls, dll):
        h = c_int(0)
        v = c_int(0)
        iStat = c_int(0)
        dll.IW_GetZoneExtentIDs(byref(h), byref(v), byref(iStat))
        _check_status(iStat, dll)
        cls.Horizontal = h.value
        cls.Vertical = v.value


class DataUnitTypeID:
    """Data unit type identifiers."""

    Length = None
    Area = None
    Volume = None

    @classmethod
    def _load(cls, dll):
        ids = [c_int(0) for _ in range(3)]
        iStat = c_int(0)
        dll.IW_GetDataUnitTypeIDs(
            byref(ids[0]), byref(ids[1]), byref(ids[2]), byref(iStat),
        )
        _check_status(iStat, dll)
        cls.Length, cls.Area, cls.Volume = [v.value for v in ids]


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
    b_enc = begin_date.encode("ascii")
    e_enc = end_date.encode("ascii")
    i_enc = interval.encode("ascii")
    c_len_date = c_int(len(b_enc))
    c_len_intv = c_int(len(i_enc))
    c_begin = (c_char * len(b_enc))(*b_enc)
    c_end = (c_char * len(e_enc))(*e_enc)
    c_intv = (c_char * len(i_enc))(*i_enc)
    n = c_int(0)
    iStat = c_int(0)
    dll.IW_GetNIntervals(
        c_begin, c_end, c_len_date, c_intv, c_len_intv, byref(n), byref(iStat),
    )
    _check_status(iStat, dll)
    return n.value


def increment_time(dll, date_time, interval, count=1):
    """Increment a date-time string by *count* intervals.

    Returns the new date-time string.
    """
    dt_enc = date_time.encode("ascii")
    iv_enc = interval.encode("ascii")
    c_len_dt = c_int(len(dt_enc))
    c_len_iv = c_int(len(iv_enc))
    # date-time is INOUT — needs mutable buffer
    dt_buf = (c_char * len(dt_enc))(*dt_enc)
    iv_buf = (c_char * len(iv_enc))(*iv_enc)
    c_count = c_int(count)
    iStat = c_int(0)
    dll.IW_IncrementTime(
        c_len_dt, dt_buf, c_len_iv, iv_buf, c_count, byref(iStat),
    )
    _check_status(iStat, dll)
    return bytes(dt_buf).decode("ascii").rstrip("\x00 ")


def is_time_greater_than(dll, dt1, dt2):
    """Return True if *dt1* is later than *dt2*."""
    enc1 = dt1.encode("ascii")
    enc2 = dt2.encode("ascii")
    length = max(len(enc1), len(enc2))
    c_len = c_int(length)
    buf1 = (c_char * length)(*enc1.ljust(length))
    buf2 = (c_char * length)(*enc2.ljust(length))
    result = c_int(0)
    iStat = c_int(0)
    dll.IW_IsTimeGreaterThan(c_len, buf1, buf2, byref(result), byref(iStat))
    _check_status(iStat, dll)
    return result.value == 1
