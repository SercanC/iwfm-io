"""iwfm_io.dll — ctypes wrapper for the IWFM Fortran DLL (Windows x64).

Optional: everything else in ``iwfm_io`` works without it, on any OS.
The DLL provides live simulation state (stepping a run from Python,
current-timestep queries); for reading and analyzing model files use
:func:`iwfm_io.open_model` instead.

Quick start (Windows)::

    from iwfm_io.dll import IWFMModel, download_dll

    download_dll("2025.0.1747")   # once; -> ~/.iwfm/dlls/

    with IWFMModel(
        preprocessor_file="Preprocessor/PreProcessor_MAIN.IN",
        simulation_file="Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as model:
        print(model.describe())
"""

from .model import IWFMModel
from .budget import IWFMBudget
from .zbudget import IWFMZBudget
from ._errors import IWFMError
from ._dll import load_dll, list_dll_versions
from .download import download_dll
from .misc import (
    get_version,
    get_kernel_version,
    set_log_file,
    close_log_file,
    get_last_message,
    log_last_message,
    load_all_type_ids,
    get_n_intervals,
    increment_time,
    is_time_greater_than,
    BudgetTypeID,
    ZBudgetTypeID,
    LandUseTypeID,
    LocationTypeID,
    FlowDestTypeID,
    SupplyTypeID,
    ZoneExtentID,
    DataUnitTypeID,
)

__all__ = [
    "IWFMModel",
    "IWFMBudget",
    "IWFMZBudget",
    "IWFMError",
    "load_dll",
    "list_dll_versions",
    "download_dll",
    "get_version",
    "get_kernel_version",
    "set_log_file",
    "close_log_file",
    "get_last_message",
    "log_last_message",
    "load_all_type_ids",
    "get_n_intervals",
    "increment_time",
    "is_time_greater_than",
    "BudgetTypeID",
    "ZBudgetTypeID",
    "LandUseTypeID",
    "LocationTypeID",
    "FlowDestTypeID",
    "SupplyTypeID",
    "ZoneExtentID",
    "DataUnitTypeID",
]
