"""
iwfm_io — Python toolkit for the Integrated Water Flow Model (IWFM).

Pure-Python file I/O at the top level (any OS, no DLL required), plus
two subpackages:

- ``iwfm_io.plots`` — 58 matplotlib visualization functions
- ``iwfm_io.dll``   — optional ctypes wrapper for the IWFM Fortran DLL
  (Windows x64; only needed for live simulation state)

.. note::
   Version 2.0 renamed the import package from ``iwfm`` to ``iwfm_io``
   (matching the distribution name, and avoiding collisions with other
   IWFM packages). Migrating 1.x code: ``iwfm.io.X`` → ``iwfm_io.X``,
   ``iwfm.plots`` → ``iwfm_io.plots``, ``iwfm.IWFMModel`` →
   ``iwfm_io.dll.IWFMModel``, ``iwfm.run_model`` → ``iwfm_io.run_model``.

Quick-start::

    from iwfm_io import open_model

    # Point at the model folder — main files and results are found for you
    model = open_model(".assets/sample_model")
    print(model.describe())            # what does this model contain?
    model.nodes_df()                   # grid nodes (GeoDataFrame)
    model.heads_df(layer=1)            # simulated heads per node
    model.budget_df("GW", location=1)  # groundwater budget time series

Or read individual files::

    from iwfm_io import read_preprocessor, read_simulation

    pp = read_preprocessor(".assets/sample_model/Preprocessor/PreProcessor_MAIN.IN")
    print(pp.nodes)          # GeoDataFrame of nodes
    print(pp.stratigraphy)   # DataFrame of layer geometry

    sim = read_simulation(".assets/sample_model/Simulation/Simulation_MAIN.IN")
    print(sim.sim_begin, sim.sim_end)
"""

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("iwfm-io")
    del _pkg_version
except Exception:  # not installed (e.g. running from a source checkout)
    __version__ = "0.0.0.dev0"

from iwfm_io.run import (
    RunResult,
    run_model,
    run_preprocessor,
    run_simulation,
    run_budget,
    run_zbudget,
)

from iwfm_io._tokens import parse_iwfm_date, format_iwfm_date
from iwfm_io._parser import IWFMFileReader
from iwfm_io._writer import IWFMFileWriter
from iwfm_io.model_adapter import IOModelAdapter, open_model
from iwfm_io.compare import (
    compare_models,
    diff_model_files,
    head_difference,
    budget_difference,
)
from iwfm_io.scenario import create_scenario, set_keyed_value, replace_text

# Preprocessor readers
from iwfm_io.readers.preprocessor import (
    read_nodes,
    read_elements,
    read_strata,
    read_stream_geom,
    read_lake_geom,
    read_preprocessor_main as read_preprocessor,
)

# Simulation readers
from iwfm_io.readers.simulation import read_simulation_main as read_simulation
from iwfm_io.readers.timeseries import (
    read_precip,
    read_et,
    read_irigfrac,
    read_supply_adjust,
)

# Groundwater readers
from iwfm_io.readers.groundwater import (
    read_gw_main,
    read_bc_main,
    read_spec_head_bc,
    read_boundary_ts,
    read_pump_main,
    read_elem_pump,
    read_ts_pumping,
    read_tile_drain,
    read_subsidence,
)

# Stream readers
from iwfm_io.readers.stream import (
    read_stream_main,
    read_stream_inflow,
    read_diver_specs,
    read_bypass_specs,
    read_diversions,
)

# Lake readers
from iwfm_io.readers.lake import read_lake_main

# Root zone readers
from iwfm_io.readers.rootzone import read_rootzone_main

# Misc readers
from iwfm_io.readers.misc import read_swshed, read_unsatzone

# HDF5 output readers
from iwfm_io.readers.hdf5 import (
    read_budget_hdf,
    read_hydrograph_hdf,
    read_head_hdf,
    read_zone_def,
    read_zbudget_hdf,
)

# Text output readers
from iwfm_io.readers.text_output import (
    read_hydrograph_out,
    read_hydrograph_out_with_metadata,
    read_head_all_out,
    read_final_state_out,
    read_flow_out,
    read_velocity_out,
    read_budget_text,
)

# Preprocessor writers
from iwfm_io.writers.preprocessor import (
    write_nodes,
    write_elements,
    write_strata,
    write_stream_geom,
    write_lake_geom,
    write_preprocessor_main as write_preprocessor,
)

# Simulation writers
from iwfm_io.writers.simulation import write_simulation_main as write_simulation
from iwfm_io.writers.timeseries import (
    write_precip,
    write_et,
    write_irigfrac,
    write_supply_adjust,
)

# Groundwater writers
from iwfm_io.writers.groundwater import (
    write_gw_main,
    write_bc_main,
    write_spec_head_bc,
    write_boundary_ts,
    write_pump_main,
    write_elem_pump,
    write_ts_pumping,
    write_tile_drain,
    write_subsidence as write_subsidence_file,
)

# Stream writers
from iwfm_io.writers.stream import (
    write_stream_main,
    write_stream_inflow,
    write_diver_specs,
    write_bypass_specs,
    write_diversions,
)

# Lake writers
from iwfm_io.writers.lake import write_lake_main

# Root zone writers
from iwfm_io.writers.rootzone import write_rootzone_main

# Misc writers
from iwfm_io.writers.misc import write_swshed, write_unsatzone

# Validation
from iwfm_io._validation import (
    validate_nodes,
    validate_elements,
    validate_stratigraphy,
    validate_preprocessor,
)

# Model adapter
from iwfm_io.model_adapter import IOModelAdapter

# Multi-run collection helpers
from iwfm_io.collect import (
    collect_budgets,
    collect_zbudgets,
    collect_hydrographs,
    collect_gwheads,
)

def __getattr__(name):
    # Lazy subpackages: matplotlib loads only when plots are used, and
    # the ctypes layer only when the DLL wrapper is used.
    if name in ("plots", "dll"):
        import importlib
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module 'iwfm_io' has no attribute {name!r}")


__all__ = [
    "plots",
    "dll",
    # Scenario runner
    "RunResult",
    "run_model",
    "run_preprocessor",
    "run_simulation",
    "run_budget",
    "run_zbudget",
    # Date utilities
    "parse_iwfm_date",
    "format_iwfm_date",
    # Parser/writer engine
    "IWFMFileReader",
    "IWFMFileWriter",
    # Preprocessor readers
    "read_preprocessor",
    "read_nodes",
    "read_elements",
    "read_strata",
    "read_stream_geom",
    "read_lake_geom",
    # Simulation readers
    "read_simulation",
    "read_precip",
    "read_et",
    "read_irigfrac",
    "read_supply_adjust",
    # Groundwater readers
    "read_gw_main",
    "read_bc_main",
    "read_spec_head_bc",
    "read_boundary_ts",
    "read_pump_main",
    "read_elem_pump",
    "read_ts_pumping",
    "read_tile_drain",
    "read_subsidence",
    # Stream readers
    "read_stream_main",
    "read_stream_inflow",
    "read_diver_specs",
    "read_bypass_specs",
    "read_diversions",
    # Lake readers
    "read_lake_main",
    # Root zone readers
    "read_rootzone_main",
    # Misc readers
    "read_swshed",
    "read_unsatzone",
    # HDF5 output readers
    "read_budget_hdf",
    "read_hydrograph_hdf",
    "read_head_hdf",
    "read_zone_def",
    "read_zbudget_hdf",
    # Text output readers
    "read_hydrograph_out",
    "read_hydrograph_out_with_metadata",
    "read_head_all_out",
    "read_final_state_out",
    "read_flow_out",
    "read_velocity_out",
    "read_budget_text",
    # Preprocessor writers
    "write_preprocessor",
    "write_nodes",
    "write_elements",
    "write_strata",
    "write_stream_geom",
    "write_lake_geom",
    # Simulation writers
    "write_simulation",
    "write_precip",
    "write_et",
    "write_irigfrac",
    "write_supply_adjust",
    # Groundwater writers
    "write_gw_main",
    "write_bc_main",
    "write_spec_head_bc",
    "write_boundary_ts",
    "write_pump_main",
    "write_elem_pump",
    "write_ts_pumping",
    "write_tile_drain",
    "write_subsidence_file",
    # Stream writers
    "write_stream_main",
    "write_stream_inflow",
    "write_diver_specs",
    "write_bypass_specs",
    "write_diversions",
    # Lake writers
    "write_lake_main",
    # Root zone writers
    "write_rootzone_main",
    # Misc writers
    "write_swshed",
    "write_unsatzone",
    # Validation
    "validate_nodes",
    "validate_elements",
    "validate_stratigraphy",
    "validate_preprocessor",
    # Model adapter
    "IOModelAdapter",
    # Multi-run collection helpers
    "collect_budgets",
    "collect_zbudgets",
    "collect_hydrographs",
    "collect_gwheads",
]
