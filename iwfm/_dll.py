"""IWFM DLL loading and function signature registration.

Loads the IWFM Fortran DLL (compiled with BIND(C) + STDCALL on Windows)
via ctypes.WinDLL and registers argtypes / restype for every exported
subroutine so that Python callers get automatic type-checking.

All Fortran subroutines are BIND(C) and return void, so every function
has ``restype = None``.  Because Fortran passes everything by reference,
scalar C_INT and C_DOUBLE parameters are declared as POINTER(c_int) and
POINTER(c_double) respectively; character buffers use c_char_p.
"""

import logging
import os
import ctypes
from ctypes import c_int, c_double, c_char_p, POINTER

logger = logging.getLogger(__name__)

# Shorthand aliases used in the signature tables below.
_P_INT = POINTER(c_int)
_P_DBL = POINTER(c_double)
_CHAR = c_char_p  # pointer-to-char buffer (works for C_CHAR arrays)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _safe_register(dll, name, argtypes):
    """Set *argtypes* and *restype* on *dll.name*, swallowing AttributeError.

    If the function is not exported by the DLL (e.g. a build that omits a
    module) a warning is logged and execution continues.
    """
    try:
        func = getattr(dll, name)
    except AttributeError:
        logger.warning("DLL does not export %s -- skipping registration", name)
        return
    func.argtypes = argtypes
    func.restype = None


# ---------------------------------------------------------------------------
# Internal helpers for version-based DLL discovery
# ---------------------------------------------------------------------------

_DLL_NAMES = ("IWFM_C_x64.dll", "IWFM_C_x64_D.dll")
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_DLLS = os.path.join(_REPO_ROOT, "dlls")
_USER_DLLS = os.path.join(os.path.expanduser("~"), ".iwfm", "dlls")


def _find_version(version):
    """Return the DLL path for *version*, searching project then user dirs.

    Returns None if the version is not found in either location.
    """
    for root in (_PROJECT_DLLS, _USER_DLLS):
        ver_dir = os.path.join(root, version)
        for name in _DLL_NAMES:
            candidate = os.path.join(ver_dir, name)
            if os.path.isfile(candidate):
                return candidate
    return None


def _read_default_version():
    """Return the version string from dlls/default_version.txt, or None."""
    txt = os.path.join(_PROJECT_DLLS, "default_version.txt")
    if os.path.isfile(txt):
        ver = open(txt).read().strip()
        return ver if ver else None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_dll_versions():
    """Return installed DLL version strings, sorted alphabetically.

    Scans ``dlls/`` in the project root and ``~/.iwfm/dlls/`` for
    subdirectories that contain ``IWFM_C_x64.dll``.

    Returns
    -------
    list of str
    """
    seen = set()
    versions = []
    for root in (_PROJECT_DLLS, _USER_DLLS):
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            ver_dir = os.path.join(root, entry)
            if not os.path.isdir(ver_dir):
                continue
            has_dll = any(
                os.path.isfile(os.path.join(ver_dir, n)) for n in _DLL_NAMES
            )
            if has_dll and entry not in seen:
                versions.append(entry)
                seen.add(entry)
    return versions


def load_dll(version=None, dll_path=None):
    """Load the IWFM DLL and register all function signatures.

    Parameters
    ----------
    version : str, optional
        DLL version string, e.g. ``"2015.0.1248"``.  The DLL is looked up
        in ``dlls/{version}/IWFM_C_x64.dll`` relative to the project root,
        then in ``~/.iwfm/dlls/{version}/IWFM_C_x64.dll``.
    dll_path : str or pathlib.Path, optional
        Explicit path to the DLL file.  Takes precedence over *version*.

    Resolution order
    ----------------
    1. *dll_path* — used directly when provided.
    2. *version* argument — searches ``dlls/{version}/``.
    3. ``IWFM_DLL_VERSION`` environment variable — same search as *version*.
    4. ``dlls/default_version.txt`` — project-level version config file.
    5. Legacy auto-discovery: project root, ``DLL/Bin/``, ``source_code/Bin/``.

    Returns
    -------
    ctypes.WinDLL
        The loaded DLL with every known function signature registered.

    Raises
    ------
    FileNotFoundError
        When no DLL can be located through any of the above methods.
    """
    resolved = None

    # 1. Explicit path
    if dll_path is not None:
        resolved = str(dll_path)

    # 2. Explicit version argument
    if resolved is None and version is not None:
        resolved = _find_version(version)
        if resolved is None:
            installed = list_dll_versions()
            raise FileNotFoundError(
                f"IWFM DLL version '{version}' not found.\n"
                f"  Searched: {os.path.join(_PROJECT_DLLS, version)}\n"
                f"       and: {os.path.join(_USER_DLLS, version)}\n"
                f"  Installed versions: {installed or '(none)'}\n"
                f"  Place IWFM_C_x64.dll in dlls/{version}/ to register it."
            )

    # 3. IWFM_DLL_VERSION environment variable
    if resolved is None:
        env_ver = os.environ.get("IWFM_DLL_VERSION")
        if env_ver:
            resolved = _find_version(env_ver)
            if resolved is None:
                logger.warning(
                    "IWFM_DLL_VERSION=%r is set but no DLL found in dlls/%s/ "
                    "— falling back to auto-discovery.", env_ver, env_ver
                )

    # 4. dlls/default_version.txt
    if resolved is None:
        default_ver = _read_default_version()
        if default_ver:
            resolved = _find_version(default_ver)
            if resolved is None:
                logger.warning(
                    "dlls/default_version.txt specifies %r but no DLL found "
                    "— falling back to auto-discovery.", default_ver
                )

    # 5. Legacy auto-discovery
    if resolved is None:
        search_dirs = [
            _REPO_ROOT,
            os.path.join(_REPO_ROOT, "DLL", "Bin"),
            os.path.join(_REPO_ROOT, "source_code", "Bin"),
        ]
        for bin_dir in search_dirs:
            for name in _DLL_NAMES:
                candidate = os.path.join(bin_dir, name)
                if os.path.isfile(candidate):
                    resolved = candidate
                    break
            if resolved is not None:
                break

    if resolved is None:
        installed = list_dll_versions()
        raise FileNotFoundError(
            "Could not find IWFM_C_x64.dll. To configure a version:\n"
            "  • Place DLL in:              dlls/<version>/IWFM_C_x64.dll\n"
            "  • Set env var:               IWFM_DLL_VERSION=<version>\n"
            "  • Edit project config:       dlls/default_version.txt\n"
            "  • Or pass explicitly:        load_dll(version='...') / "
            "load_dll(dll_path='...')\n"
            f"  Installed versions: {installed or '(none)'}"
        )

    logger.debug("Loading IWFM DLL: %s", resolved)
    dll = ctypes.WinDLL(resolved)
    _register_all(dll)
    return dll


# ---------------------------------------------------------------------------
# Top-level registration dispatcher
# ---------------------------------------------------------------------------

def _register_all(dll):
    """Register every known function signature on *dll*."""
    _register_misc(dll)
    _register_budget(dll)
    _register_zbudget(dll)
    _register_model(dll)


# ===================================================================
# MISC EXPORTS  (IWFM_Misc_Exports)
# ===================================================================

def _register_misc(dll):
    _sigs = [
        # --- Log / Version ------------------------------------------------
        ('IW_CloseLogFile', [_P_INT]),

        ('IW_GetVersion', [_P_INT, _CHAR, _P_INT]),

        ('IW_IWFMKernel_GetVersion', [_P_INT, _CHAR, _P_INT]),

        # --- Budget type IDs ----------------------------------------------
        # 13 type-ID outputs + iStat = 14 INT args
        ('IW_GetBudgetTypeIDs', [_P_INT] * 14),

        # 4 type-ID outputs + iStat = 5 INT args
        ('IW_GetZBudgetTypeIDs', [_P_INT] * 5),

        # 6 type-ID outputs + iStat = 7 INT args
        ('IW_GetLandUseTypeIDs', [_P_INT] * 7),

        # 8 type-ID outputs + iStat = 9 INT args
        ('IW_GetLandUseTypeIDs_1', [_P_INT] * 9),

        # 9 type-ID outputs + iStat = 10 INT args
        ('IW_GetLandUseTypeIDs_2', [_P_INT] * 10),

        ('IW_GetLandUseTypeID_GenAg', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_Urban', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_UrbIndoors', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_UrbOutdoors', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_NonPondedAg', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_PondedAg', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_Rice', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_Refuge', [_P_INT, _P_INT]),
        ('IW_GetLandUseTypeID_NVRV', [_P_INT, _P_INT]),

        # --- Data unit type IDs -------------------------------------------
        # 3 type-ID outputs + iStat = 4 INT args
        ('IW_GetDataUnitTypeIDs', [_P_INT] * 4),

        ('IW_GetDataUnitTypeID_Length', [_P_INT, _P_INT]),
        ('IW_GetDataUnitTypeID_Area', [_P_INT, _P_INT]),
        ('IW_GetDataUnitTypeID_Volume', [_P_INT, _P_INT]),

        # --- Location type IDs --------------------------------------------
        # 13 type-ID outputs + iStat = 14 INT args
        ('IW_GetLocationTypeIDs', [_P_INT] * 14),

        # 15 type-ID outputs + iStat = 16 INT args
        ('IW_GetLocationTypeIDs_1', [_P_INT] * 16),

        ('IW_GetLocationTypeID_Subregion', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Zone', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Node', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Lake', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_StrmReach', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_StrmNode', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_StrmHydObs', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_StrmNodeBud', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_GWHeadObs', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_SubsidenceObs', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_SmallWatershed', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_TileDrain', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_TileDrainObs', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Element', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Diversion', [_P_INT, _P_INT]),
        ('IW_GetLocationTypeID_Bypass', [_P_INT, _P_INT]),

        # --- Flow destination type IDs ------------------------------------
        # 7 type-ID outputs + iStat = 8 INT args
        ('IW_GetFlowDestTypeIDs', [_P_INT] * 8),

        ('IW_GetFlowDestTypeID_Outside', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_StrmNode', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_Element', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_Lake', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_Subregion', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_GWElement', [_P_INT, _P_INT]),
        ('IW_GetFlowDestTypeID_ElementSet', [_P_INT, _P_INT]),

        # --- Supply type IDs ----------------------------------------------
        ('IW_GetSupplyTypeID_Diversion', [_P_INT, _P_INT]),
        ('IW_GetSupplyTypeID_Well', [_P_INT, _P_INT]),
        ('IW_GetSupplyTypeID_ElemPump', [_P_INT, _P_INT]),

        # --- Zone extent IDs ----------------------------------------------
        ('IW_GetZoneExtentID_Horizontal', [_P_INT, _P_INT]),
        ('IW_GetZoneExtentID_Vertical', [_P_INT, _P_INT]),
        ('IW_GetZoneExtentIDs', [_P_INT, _P_INT, _P_INT]),

        # --- Time utilities -----------------------------------------------
        # (cBegin, cEnd, iLenDate, cInterval, iLenInterval, NIntervals, iStat)
        ('IW_GetNIntervals', [_CHAR, _CHAR, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT]),

        # --- Message utilities --------------------------------------------
        ('IW_GetLastMessage', [_P_INT, _CHAR, _P_INT]),
        ('IW_LogLastMessage', [_P_INT]),
        ('IW_SetLogFile', [_P_INT, _CHAR, _P_INT]),

        # --- Time manipulation --------------------------------------------
        # (iLenDate, cDateAndTime, iLenInterval, cInterval, iNCount, iStat)
        ('IW_IncrementTime', [_P_INT, _CHAR, _P_INT, _CHAR, _P_INT, _P_INT]),

        # (iLenDate, cDT1, cDT2, isGreaterThan, iStat)
        ('IW_IsTimeGreaterThan', [_P_INT, _CHAR, _CHAR, _P_INT, _P_INT]),
    ]

    for name, argtypes in _sigs:
        _safe_register(dll, name, argtypes)


# ===================================================================
# BUDGET EXPORTS  (IWFM_Budget_Exports)
# ===================================================================

def _register_budget(dll):
    _sigs = [
        ('IW_Budget_OpenFile', [_CHAR, _P_INT, _P_INT]),
        ('IW_Budget_CloseFile', [_P_INT]),
        ('IW_Budget_GetNLocations', [_P_INT, _P_INT]),

        # (cLocNames, iLenLocNames, NLocations, iLocArray, iStat)
        ('IW_Budget_GetLocationNames', [_CHAR, _P_INT, _P_INT, _P_INT, _P_INT]),

        ('IW_Budget_GetNTimeSteps', [_P_INT, _P_INT]),

        # (cDates, iLenDates, cInterval, iLenInterval, NData, iLocArray, iStat)
        ('IW_Budget_GetTimeSpecs', [_CHAR, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT, _P_INT]),

        ('IW_Budget_GetNTitleLines', [_P_INT, _P_INT]),
        ('IW_Budget_GetTitleLength', [_P_INT, _P_INT]),

        # (NTitles, iLocation, FactArea, LengthUnit, AreaUnit, VolumeUnit,
        #  iLenUnit, cAltLocName, iLenAltLocName, cTitles, iLenTitles,
        #  iLocArray, iStat)
        ('IW_Budget_GetTitleLines', [
            _P_INT, _P_INT, _P_DBL, _CHAR, _CHAR, _CHAR,
            _P_INT, _CHAR, _P_INT, _CHAR, _P_INT,
            _P_INT, _P_INT,
        ]),

        # (iLoc, NColumns, iStat)
        ('IW_Budget_GetNColumns', [_P_INT, _P_INT, _P_INT]),

        # (iLoc, cColHeaders, iLenColHeaders, NColumns, LengthUnit,
        #  AreaUnit, VolumeUnit, iLenUnit, iLocArray, iStat)
        ('IW_Budget_GetColumnHeaders', [
            _P_INT, _CHAR, _P_INT, _P_INT, _CHAR,
            _CHAR, _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iLoc, nReadCols, iReadCols, cBegin, cEnd, iLenDate,
        #  cInterval, iLenInterval, rFactLT, rFactAR, rFactVL,
        #  nTimes_In, Values, nTimes_Out, iStat)
        ('IW_Budget_GetValues', [
            _P_INT, _P_INT, _P_INT, _CHAR, _CHAR, _P_INT,
            _CHAR, _P_INT, _P_DBL, _P_DBL, _P_DBL,
            _P_INT, _P_DBL, _P_INT, _P_INT,
        ]),

        # (iLoc, iCol, cInterval, iLenInterval, cBegin, cEnd, iLenDate,
        #  rFactLT, rFactAR, rFactVL, iDim_In, iDim_Out,
        #  Dates, Values, iStat)
        ('IW_Budget_GetValues_ForAColumn', [
            _P_INT, _P_INT, _CHAR, _P_INT, _CHAR, _CHAR, _P_INT,
            _P_DBL, _P_DBL, _P_DBL, _P_INT, _P_INT,
            _P_DBL, _P_DBL, _P_INT,
        ]),

        ('IW_Budget_AreNColumnsSame', [_P_INT, _P_INT]),
    ]

    for name, argtypes in _sigs:
        _safe_register(dll, name, argtypes)


# ===================================================================
# ZBUDGET EXPORTS  (IWFM_ZBudget_Exports)
# ===================================================================

def _register_zbudget(dll):
    _sigs = [
        ('IW_ZBudget_OpenFile', [_CHAR, _P_INT, _P_INT]),

        ('IW_ZBudget_GenerateZoneList_FromFile', [_CHAR, _P_INT, _P_INT]),

        # (iZExtent, iNElems, iElems, iLayers, iZones,
        #  nZonesWithNames, iZonesWithNames, iLenZoneNames, cZoneNames,
        #  iLocArray, iStat)
        ('IW_ZBudget_GenerateZoneList', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT, _CHAR,
            _P_INT, _P_INT,
        ]),

        ('IW_ZBudget_CloseFile', [_P_INT]),

        # (iNZones, iZones, iNColsMax, iCols, cBegin, iLenDate,
        #  cInterval, iLenInterval, rFactAR, rFactVL, rValues, iStat)
        ('IW_ZBudget_GetValues_ForSomeZones_ForAnInterval', [
            _P_INT, _P_INT, _P_INT, _P_INT, _CHAR, _P_INT,
            _CHAR, _P_INT, _P_DBL, _P_DBL, _P_DBL, _P_INT,
        ]),

        # (iZone, iNCols, iCols, cBegin, cEnd, iLenDate,
        #  cInterval, iLenInterval, rFactAR, rFactVL,
        #  iNTimes_In, rValues, iNTimes_Out, iStat)
        ('IW_ZBudget_GetValues_ForAZone', [
            _P_INT, _P_INT, _P_INT, _CHAR, _CHAR, _P_INT,
            _CHAR, _P_INT, _P_DBL, _P_DBL,
            _P_INT, _P_DBL, _P_INT, _P_INT,
        ]),

        ('IW_ZBudget_GetNTimeSteps', [_P_INT, _P_INT]),

        # (cDates, iLenDates, cInterval, iLenInterval, NData, iLocArray, iStat)
        ('IW_ZBudget_GetTimeSpecs', [_CHAR, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT, _P_INT]),

        # (NColumnsMax, AreaUnit, VolumeUnit, iLenUnit, iLenColHeaders,
        #  cColHeaders, NColumns, iLocArray, iStat)
        ('IW_ZBudget_GetColumnHeaders_General', [
            _P_INT, _CHAR, _CHAR, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iZone, NColumnsList, iColumnsList, NColumnsMax,
        #  AreaUnit, VolumeUnit, iLenUnit, iLenColHeaders,
        #  cColHeaders, NColumns, iLocArray, iColsDiversified, iStat)
        ('IW_ZBudget_GetColumnHeaders_ForAZone', [
            _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT, _P_INT,
        ]),

        ('IW_ZBudget_GetNZones', [_P_INT, _P_INT]),

        # (iNZones, iZoneList, iStat)
        ('IW_ZBudget_GetZoneList', [_P_INT, _P_INT, _P_INT]),

        # (iNZones, iLenZoneNames, cZoneNames, iLocArray, iStat)
        ('IW_ZBudget_GetZoneNames', [_P_INT, _P_INT, _CHAR, _P_INT, _P_INT]),

        ('IW_ZBudget_GetNTitleLines', [_P_INT, _P_INT]),

        # (iNTitles, iZone, rFactAR, cUnitAR, cUnitVL, iLenUnit,
        #  cTitles, iLenTitles, iLocArray, iStat)
        ('IW_ZBudget_GetTitleLines', [
            _P_INT, _P_INT, _P_DBL, _CHAR, _CHAR, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),
    ]

    for name, argtypes in _sigs:
        _safe_register(dll, name, argtypes)


# ===================================================================
# MODEL EXPORTS  (IWFM_Model_Exports) -- 161 functions
# ===================================================================

def _register_model(dll):
    _sigs = [
        # ------------------------------------------------------------------
        # Constructor / Destructor
        # ------------------------------------------------------------------
        # (iLen_PP, cPP, iLen_Sim, cSim, iLen_WSA, cWSA, iLen_Log, cLog,
        #  HasWSAFile, iStat)
        #   -- note: WSA variant has extra file-name pair
        ('IW_Model_WSA_New', [
            _P_INT, _CHAR, _P_INT, _CHAR, _P_INT, _CHAR,
            _P_INT, _P_INT, _P_INT, _P_INT,
        ]),

        # (iLen_PP, cPP, iLen_Sim, cSim, iLen_Log, cLog, HasLogFile, iStat)
        ('IW_Model_New', [
            _P_INT, _CHAR, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT, _P_INT,
        ]),

        ('IW_Model_Kill', [_P_INT]),

        ('IW_Model_GetCurrentModelID', [_P_INT, _P_INT]),
        ('IW_Model_Switch', [_P_INT, _P_INT]),
        ('IW_Model_IsModelInstantiated', [_P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Wells
        # ------------------------------------------------------------------
        ('IW_Model_GetNWells', [_P_INT, _P_INT]),
        ('IW_Model_GetWellIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetWellCoordinates', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetWellPerfTopBottom', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetWellNElems', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetWellElems', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNElemPumps', [_P_INT, _P_INT]),
        ('IW_Model_GetElemPumpIDs', [_P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Water demand
        # ------------------------------------------------------------------
        # (iDiv, iLenInterval, cInterval, rFact, rDemand, iStat)
        ('IW_Model_GetFutureWaterDemand_ForDiversion', [
            _P_INT, _P_INT, _CHAR, _P_DBL, _P_DBL, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Time
        # ------------------------------------------------------------------
        ('IW_Model_GetCurrentDateAndTime', [_P_INT, _CHAR, _P_INT]),
        ('IW_Model_GetNTimeSteps', [_P_INT, _P_INT]),

        # (cDates, iLenDates, cInterval, iLenInterval, NData, iLocArray, iStat)
        ('IW_Model_GetTimeSpecs', [_CHAR, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT, _P_INT]),

        # (cIntervals, iLenIntervals, NIntervals, NData, iLocArray, iStat)
        ('IW_Model_GetOutputIntervals', [_CHAR, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT]),

        ('IW_Model_IsEndOfSimulation', [_P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Budget via model
        # ------------------------------------------------------------------
        ('IW_Model_GetBudget_N', [_P_INT, _P_INT]),

        # (NBudgets, iLocationType, iBudgetType, cBudgetList, iLenBudgetList,
        #  iLocArray, iStat)
        ('IW_Model_GetBudget_List', [
            _P_INT, _P_INT, _P_INT, _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iBudgetType, iLoc, NColumns, iStat)
        ('IW_Model_GetBudget_NColumns', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # (iBudgetType, iLoc, NColumns, cUnit_LT, cUnit_AR, cUnit_VL,
        #  iLenUnit, iLenColTitles, NColTitles, cColTitles, iStat)
        ('IW_Model_GetBudget_ColumnTitles', [
            _P_INT, _P_INT, _P_INT, _CHAR, _CHAR, _CHAR,
            _P_INT, _P_INT, _P_INT, _CHAR, _P_INT,
        ]),

        # (iBudgetType, iLoc, iNCols, iCols, NMonths,
        #  cBeginDate, cEndDate, rFactVL, iLenDate,
        #  rFlows, rDates, NFlows, NFlows_In,
        #  cInterval, iLenInterval, iStat)
        ('IW_Model_GetBudget_MonthlyAverageFlows', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_DBL, _P_DBL, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT,
        ]),

        # (iBudgetType, iLoc, iNCols, iCols, NYears,
        #  cBeginDate, cEndDate, rFactVL, iLenDate,
        #  iReadCols, rFlows, NFlows, NFlows_In, NReadCols,
        #  cInterval, iLenInterval, iWaterYear, iStat)
        ('IW_Model_GetBudget_AnnualFlows', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iBudgetType, iLocationIndex, iNCols, iCols, iLenDate,
        #  cBeginDate, cEndDate, iLenInterval, cInterval,
        #  rFactLT, rFactAR, rFactVL,
        #  rOutputDates, iNTimes_In, rOutputValues, iDataTypes,
        #  iNTimes_Out, iStat)
        ('IW_Model_GetBudget_TSData', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _CHAR,
            _P_DBL, _P_DBL, _P_DBL,
            _P_DBL, _P_INT, _P_DBL, _P_INT,
            _P_INT, _P_INT,
        ]),

        # (iBudgetType, iLoc, iNCols, iCols, NYears,
        #  cBeginDate, cEndDate, iLenDate, rFactVL, iReadCols,
        #  NReadCols, rFlows, NFlows, NFlows_In, NReadCols2,
        #  cInterval, iLenInterval, iWaterYear, iStat)
        ('IW_Model_GetBudget_AnnualFlows_1', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _P_DBL, _P_INT,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iLoc, NLayers, cBeginDate, cEndDate, iLenDate, cInterval,
        #  rFactVL, rFactLT, iNTimes_In, rValues, iNTimes_Out, iStat)
        ('IW_Model_GetBudget_CumGWStorChange', [
            _P_INT, _P_INT, _CHAR, _CHAR, _P_INT, _CHAR,
            _P_DBL, _P_DBL, _P_INT, _P_DBL, _P_INT, _P_INT,
        ]),

        # (iLoc, NLayers, cBeginDate, cEndDate, rFactVL, iLenDate,
        #  rValues, NYears, iNYears_Out, iStat)
        ('IW_Model_GetBudget_AnnualCumGWStorChange', [
            _P_INT, _P_INT, _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # (iLoc, NLayers, cBeginDate, cEndDate, iLenDate, rFactVL,
        #  NYears, rValues, iNYears_Out, iWaterYear, iStat)
        ('IW_Model_GetBudget_AnnualCumGWStorChange_1', [
            _P_INT, _P_INT, _CHAR, _CHAR, _P_INT, _P_DBL,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # ZBudget via model
        # ------------------------------------------------------------------
        ('IW_Model_GetZBudget_N', [_P_INT, _P_INT]),

        # (NZBudgets, iLocationType, iBudgetType, cList, iLenList, iStat)
        ('IW_Model_GetZBudget_List', [
            _P_INT, _P_INT, _P_INT, _CHAR, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  NColumnsMax, NColumns, iStat)
        ('IW_Model_GetZBudget_NColumns', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  NColumnsMax, NColumns, cUnit_AR, cUnit_VL, iLenUnit,
        #  iLenColTitles, NColTitles, cColTitles, iStat)
        ('IW_Model_GetZBudget_ColumnTitles', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _CHAR, _CHAR, _P_INT,
            _P_INT, _P_INT, _CHAR, _P_INT,
        ]),

        # (iZBudgetType, iZoneID, iNCols, iCols, iZExtent,
        #  iNZones, iElems, iLayers, iZoneIDs, iLenDate,
        #  cBeginDate, cEndDate, iLenInterval, cInterval,
        #  rFactAR, rFactVL, rOutputDates, iNTimes_In,
        #  rOutputValues, iDataTypes, iNTimes_Out, iStat)
        ('IW_Model_GetZBudget_TSData', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _CHAR,
            _P_DBL, _P_DBL, _P_DBL, _P_INT,
            _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  NColumnsMax, NColumns, NMonths,
        #  cBeginDate, cEndDate, rFactVL, iLenDate,
        #  rFlows, rDates, NFlows, NFlows_In,
        #  cInterval, iLenInterval, iStat)
        ('IW_Model_GetZBudget_MonthlyAverageFlows', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_DBL, _P_DBL, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  NColumnsMax, NColumns, NYears,
        #  cBeginDate, cEndDate, rFactVL, iLenDate,
        #  iReadCols, rFlows, NFlows, NFlows_In, NReadCols,
        #  cInterval, iLenInterval, iWaterYear, iStat)
        ('IW_Model_GetZBudget_AnnualFlows', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  NColumnsMax, NColumns, NYears,
        #  cBeginDate, cEndDate, iLenDate, rFactVL, iReadCols,
        #  NReadCols, rFlows, NFlows, NFlows_In, NReadCols2,
        #  cInterval, iLenInterval, iWaterYear, iStat)
        ('IW_Model_GetZBudget_AnnualFlows_1', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _P_DBL, _P_INT,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
            _CHAR, _P_INT, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  iLoc, cBeginDate, cEndDate, iLenDate, cInterval,
        #  rFactVL, rFactLT, iNTimes_In, rValues, iNTimes_Out, iStat)
        ('IW_Model_GetZBudget_CumGWStorChange', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _CHAR, _CHAR, _P_INT, _CHAR,
            _P_DBL, _P_DBL, _P_INT, _P_DBL, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  iLoc, cBeginDate, cEndDate, rFactVL, iLenDate,
        #  rValues, NYears, iNYears_Out, iStat)
        ('IW_Model_GetZBudget_AnnualCumGWStorChange', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _CHAR, _CHAR, _P_DBL, _P_INT,
            _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # (iZBudgetType, iZExtent, iNElems, iElems, iLayers, iZones,
        #  iLoc, cBeginDate, cEndDate, iLenDate, rFactVL,
        #  NYears, rValues, iNYears_Out, iWaterYear, iStat)
        ('IW_Model_GetZBudget_AnnualCumGWStorChange_1', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
            _P_INT, _CHAR, _CHAR, _P_INT, _P_DBL,
            _P_INT, _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Names / Locations
        # ------------------------------------------------------------------
        # (iLocationType, NLocations, iLen, NLocs, cNames, iStat)
        ('IW_Model_GetNames', [_P_INT, _P_INT, _P_INT, _P_INT, _CHAR, _P_INT]),

        ('IW_Model_GetNLocations', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetLocationIDs', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Groundwater
        # ------------------------------------------------------------------
        # (NNodes, NLayers, rHeads, iStat)
        ('IW_Model_GetGWHeadsIC', [_P_INT, _P_INT, _P_DBL, _P_INT]),

        # (iLayer, cOutputBeginDateAndTime, cOutputEndDateAndTime, iLenDate,
        #  rFact, NNodes, NTimes_In, rHeads, rDates, iStat)
        ('IW_Model_GetGWHeads_ForALayer', [
            _P_INT, _CHAR, _CHAR, _P_INT,
            _P_DBL, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),

        # (NNodes, NLayers, iNTimeSteps, rHeads, rDates, iStat)
        ('IW_Model_GetGWHeads_All', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),

        # (NNodes, NLayers, rSubs, rDates, iStat)
        ('IW_Model_GetSubsidence_All', [
            _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Stream flow
        # ------------------------------------------------------------------
        ('IW_Model_GetStrmFlow', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmFlows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmStages', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmNInflows', [_P_INT, _P_INT]),
        ('IW_Model_GetStrmInflowNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmInflowIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmInflows_AtSomeInflows', [_P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT]),

        # ------------------------------------------------------------------
        # Hydrographs
        # ------------------------------------------------------------------
        ('IW_Model_GetNHydrographTypes', [_P_INT, _P_INT]),

        # (NHydTypes, iHydTypeIDs, NHydTypes_In, cHydTypeNames, iLenNames, iStat)
        ('IW_Model_GetHydrographTypeList', [
            _P_INT, _P_INT, _P_INT, _CHAR, _P_INT, _P_INT,
        ]),

        ('IW_Model_GetNHydrographs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetHydrographIDs', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetHydrographCoordinates', [_P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT]),

        # (iHydType, iHydIndex, iLayer, NHydrograph,
        #  cBeginDate, cEndDate, iLenDate, cInterval,
        #  rFact_LT, rFact_VL, iNTimes_In,
        #  rValues, rDates, iNTimes_Out, iDataUnitType, iStat)
        ('IW_Model_GetHydrograph', [
            _P_INT, _P_INT, _P_INT, _P_INT,
            _CHAR, _CHAR, _P_INT, _CHAR,
            _P_DBL, _P_DBL, _P_INT,
            _P_DBL, _P_DBL, _P_INT, _P_INT, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Grid / mesh
        # ------------------------------------------------------------------
        ('IW_Model_GetNodeIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNodeXY', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetNNodes', [_P_INT, _P_INT]),
        ('IW_Model_GetElementIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNElements', [_P_INT, _P_INT]),
        ('IW_Model_GetNLayers', [_P_INT, _P_INT]),
        ('IW_Model_GetNSubregions', [_P_INT, _P_INT]),
        ('IW_Model_GetSubregionIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetSubregionName', [_P_INT, _P_INT, _CHAR, _P_INT]),
        ('IW_Model_GetElemSubregions', [_P_INT, _P_INT, _P_INT]),

        # (NElements, iVertices, NVertices, iStat)
        ('IW_Model_GetElementConfigData', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Stratigraphy
        # ------------------------------------------------------------------
        # (NLayers, X, Y, GSElev, TopElevs, BottomElevs, iStat)
        ('IW_Model_GetStratigraphy_AtXYCoordinate', [
            _P_INT, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_INT,
        ]),

        ('IW_Model_GetGSElev', [_P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferTopElev', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferBottomElev', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferHorizontalK', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquitardVerticalK', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferVerticalK', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferSy', [_P_INT, _P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetAquiferSs', [_P_INT, _P_INT, _P_DBL, _P_INT]),

        # (NNodes, iLayer, Kh, Ss, Sy, Kv, Kquitard, iStat)
        ('IW_Model_GetAquiferParameters', [
            _P_INT, _P_INT, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Parametric grids
        # ------------------------------------------------------------------
        ('IW_Model_GetGWNParametricGrids', [_P_INT, _P_INT]),
        ('IW_Model_GetGWNParametricNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetGWNParametricElements', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetGWParametricNodeXY', [_P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetGWParametricElementConfigData', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # (iGrid, iLayer, NParamNodes, Kh, Ss, Sy, Kv, Kquitard, iStat)
        ('IW_Model_GetGWParametricAquiferParameters', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_DBL, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Stream network
        # ------------------------------------------------------------------
        ('IW_Model_GetStrmNodeIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNStrmNodes', [_P_INT, _P_INT]),
        ('IW_Model_GetReachIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNReaches', [_P_INT, _P_INT]),
        ('IW_Model_GetReaches_ForStrmNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachUpstrmNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachDownstrmNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachOutflowDest', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachOutflowDestTypes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachNNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachStrmNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachGWNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmBottomElevs', [_P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetNStrmRatingTablePoints', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmRatingTable', [_P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmNUpstrmNodes', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmUpstrmNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_IsStrmUpstreamNode', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachNUpstrmReaches', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetReachUpstrmReaches', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Stream flow components
        # ------------------------------------------------------------------
        ('IW_Model_GetStrmNetInflows_ExcDivsInflows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmNetInflows_ExcDivsInflowsGW', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmTributaryInflows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmRainfallRunoff', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmReturnFlows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmPondDrains', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmTileDrains', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmRiparianETs', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmEvap', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmGainFromGW', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmGainFromLakes', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmWSAs', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmNetBypassInflows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetStrmBypassInflows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),

        # ------------------------------------------------------------------
        # Diversions
        # ------------------------------------------------------------------
        ('IW_Model_GetNDiversions', [_P_INT, _P_INT]),
        ('IW_Model_GetDiversionIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmRequiredDiversions_AtSomeDiversions', [
            _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),
        ('IW_Model_GetStrmActualDiversions_AtSomeDiversions', [
            _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),
        ('IW_Model_GetStrmDiversionsExportNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmDiversionNElems', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmDiversionElems', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmDiversionNRechargeZoneElems', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetStrmDiversionRechargeZoneElems', [_P_INT, _P_INT, _P_INT, _P_DBL, _P_INT]),

        # ------------------------------------------------------------------
        # Bypasses
        # ------------------------------------------------------------------
        ('IW_Model_GetNBypasses', [_P_INT, _P_INT]),
        ('IW_Model_GetBypassIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetBypassExportNodes', [_P_INT, _P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetBypassExportDestinationData', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_INT, _P_INT,
        ]),
        ('IW_Model_GetBypassOutflows', [_P_INT, _P_DBL, _P_DBL, _P_INT]),
        ('IW_Model_GetBypassRecoverableLossFactor', [_P_INT, _P_DBL, _P_INT]),
        ('IW_Model_GetBypassNonRecoverableLossFactor', [_P_INT, _P_DBL, _P_INT]),

        # ------------------------------------------------------------------
        # Supply
        # ------------------------------------------------------------------
        # (iSupplyType, NSupply, iSupplyIndices, iPurpose, iStat)
        ('IW_Model_GetSupplyPurpose', [_P_INT, _P_INT, _P_INT, _P_INT, _P_INT]),

        # (iSupplyType, NSupply, iSupplyIndices, rReq, rFact, iStat)
        ('IW_Model_GetSupplyRequirement_Ag', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),
        ('IW_Model_GetSupplyRequirement_Urb', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),
        ('IW_Model_GetSupplyShortAtOrigin_Ag', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),
        ('IW_Model_GetSupplyShortAtOrigin_Urb', [
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),

        # ------------------------------------------------------------------
        # Lakes
        # ------------------------------------------------------------------
        ('IW_Model_GetNLakes', [_P_INT, _P_INT]),
        ('IW_Model_GetLakeIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetNElementsInLake', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetElementsInLake', [_P_INT, _P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Tile drains
        # ------------------------------------------------------------------
        ('IW_Model_GetNTileDrainNodes', [_P_INT, _P_INT]),
        ('IW_Model_GetTileDrainIDs', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_GetTileDrainNodes', [_P_INT, _P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Land use / Ag
        # ------------------------------------------------------------------
        # (iLocationType, cBeginDate, cEndDate, iLenDate,
        #  NLocations, NLandUse, NTimeSteps, rAreas, rFact, iStat)
        ('IW_Model_GetLandUseAreasForTimePeriod', [
            _P_INT, _CHAR, _CHAR, _P_INT,
            _P_INT, _P_INT, _P_INT, _P_DBL, _P_DBL, _P_INT,
        ]),

        ('IW_Model_GetSubregionAgPumpingAverageDepthToGW', [_P_INT, _P_DBL, _P_INT]),

        # (iNZones, iZExtent, iElems, iLayers, rDepth, iStat)
        ('IW_Model_GetZoneAgPumpingAverageDepthToGW', [
            _P_INT, _P_INT, _P_INT, _P_INT, _P_DBL, _P_INT,
        ]),

        ('IW_Model_GetNAgCrops', [_P_INT, _P_INT]),

        # ------------------------------------------------------------------
        # Simulation control
        # ------------------------------------------------------------------
        ('IW_Model_SimulateAll', [_P_INT]),
        ('IW_Model_SimulateForOneTimeStep', [_P_INT]),
        ('IW_Model_SimulateForAnInterval', [_P_INT, _CHAR, _P_INT]),
        ('IW_Model_AdvanceTime', [_P_INT]),
        ('IW_Model_ReadTSData', [_P_INT]),

        # (iNDiver, iDiver, rDiver,
        #  iNBypass, iBypass, rBypass,
        #  iNPump, iPump, rPump,
        #  iNElemPump, iElemPump, rElemPump, iStat)
        ('IW_Model_ReadTSData_Overwrite', [
            _P_INT, _P_INT, _P_DBL,
            _P_INT, _P_INT, _P_DBL,
            _P_INT, _P_INT, _P_DBL,
            _P_INT, _P_INT, _P_DBL, _P_INT,
        ]),

        ('IW_Model_PrintResults', [_P_INT]),
        ('IW_Model_AdvanceState', [_P_INT]),
        ('IW_Model_TurnSupplyAdjustOnOff', [_P_INT, _P_INT, _P_INT]),
        ('IW_Model_RestorePumpingToReadValues', [_P_INT]),
        ('IW_Model_ComputeFutureWaterDemands', [_P_INT, _CHAR, _P_INT]),
        ('IW_Model_SetSupplyAdjustmentMaxIters', [_P_INT, _P_INT]),
        ('IW_Model_SetSupplyAdjustmentTolerance', [_P_DBL, _P_INT]),
        ('IW_Model_DeleteInquiryDataFile', [_P_INT, _CHAR, _P_INT]),
    ]

    for name, argtypes in _sigs:
        _safe_register(dll, name, argtypes)
