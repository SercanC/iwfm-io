"""iwfm — Python toolkit for the Integrated Water Flow Model (IWFM).

Three parts, usable independently:

- ``iwfm.io`` — read/write IWFM model files directly (any OS, no DLL)
- ``iwfm`` — wrap the IWFM Fortran DLL (Windows x64 only)
- ``iwfm.plots`` — 58 matplotlib visualization functions

Quick start — read a model from its files (recommended; no DLL needed)::

    from iwfm.io import open_model

    model = open_model("path/to/my_model")   # the model root folder
    print(model.describe())                   # what does it contain?
    model.nodes_df()                          # grid as GeoDataFrame
    model.heads_df(layer=1)                   # simulated heads
    model.budget_df("GW", location=1)         # budget time series

    from iwfm.plots import maps
    maps.plot_gw_head_contour(model, layer=1)

Quick start — query a live model through the DLL (Windows)::

    import iwfm

    print(iwfm.list_dll_versions())   # e.g. ['2015.0.1248']

    with iwfm.IWFMModel(
        preprocessor_file="Simulation/PreProcessor.bin",
        simulation_file="Simulation/Simulation_MAIN.IN",
        is_for_inquiry=True,
    ) as model:
        print(model.describe())
        print(model.n_nodes, model.n_elements, model.n_layers)
"""

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("iwfm-io")
    del _pkg_version
except Exception:  # not installed (e.g. running from a source checkout)
    __version__ = "0.0.0.dev0"

from .model import IWFMModel
from .budget import IWFMBudget
from .zbudget import IWFMZBudget
from ._errors import IWFMError
from ._dll import load_dll, list_dll_versions
from .run import (
    RunResult,
    run_model,
    run_preprocessor,
    run_simulation,
    run_budget,
    run_zbudget,
)
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

from . import io  # noqa: F401 — pure-Python file I/O subpackage


def __getattr__(name):
    # Lazy import so `import iwfm` stays fast; matplotlib loads only
    # when plotting is actually used (`iwfm.plots` / `from iwfm import plots`).
    if name == "plots":
        import importlib
        return importlib.import_module(".plots", __name__)
    raise AttributeError(f"module 'iwfm' has no attribute {name!r}")


__all__ = [
    "io",
    "plots",
    "RunResult",
    "run_model",
    "run_preprocessor",
    "run_simulation",
    "run_budget",
    "run_zbudget",
    "IWFMModel",
    "IWFMBudget",
    "IWFMZBudget",
    "IWFMError",
    "load_dll",
    "list_dll_versions",
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
