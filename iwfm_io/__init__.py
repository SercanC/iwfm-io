"""
iwfm_io — Python toolkit for the Integrated Water Flow Model (IWFM).

Pure-Python file I/O at the top level (any OS, no DLL required), plus
two subpackages:

- ``iwfm_io.plots`` — 66 matplotlib visualization functions
- ``iwfm_io.dll``   — optional ctypes wrapper for the IWFM Fortran DLL
  (Windows x64; only needed for live simulation state)
- ``iwfm_io.pest``  — PEST(++) calibration support (obs-name codec,
  IES results loader, residual statistics, SMP files, weight
  balancing, run diagnostics; calibration figures in
  ``iwfm_io.plots.calibration``)

.. note::
   Version 2.0 renamed the import package from ``iwfm`` to ``iwfm_io``
   (matching the distribution name, and avoiding collisions with other
   IWFM packages). Migrating 1.x code: ``iwfm.io.X`` → ``iwfm_io.X``,
   ``iwfm.plots`` → ``iwfm_io.plots``, ``iwfm.IWFMModel`` →
   ``iwfm_io.dll.IWFMModel``, ``iwfm.run_model`` → ``iwfm_io.run_model``.

Looking for a function? Search the API index instead of writing your
own — this package reads *and* writes every dataset in every IWFM input
file, and hand-rolled parsers get the conventions wrong::

    import iwfm_io
    iwfm_io.find("water year")     # or, in a shell: iwfm-io api <keyword>

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
    RunError,
    RunResult,
    run_model,
    run_preprocessor,
    run_simulation,
    run_budget,
    run_zbudget,
)

from iwfm_io._tokens import (
    parse_iwfm_date,
    format_iwfm_date,
    iwfm_day,
    water_year,
    expand_recurring,
)
from iwfm_io._parser import IWFMFileReader, IWFMParseError, IWFMReadWarning
from iwfm_io.models.base import (ConversionFactor, FileHeader, TimeSeriesSpec,
                                 ZoneDefinition)
from iwfm_io.models.timeseries import TimeSeriesDataFile, TimeSeriesFile
from iwfm_io._strict import strict_mode
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
    read_irr_period,
    read_supply_adjust,
    read_timeseries_file,
)

# Groundwater readers
from iwfm_io.readers.groundwater import (
    read_gw_main,
    read_bc_main,
    read_spec_head_bc,
    read_spec_flow_bc,
    read_general_head_bc,
    read_constrained_head_bc,
    read_boundary_ts,
    read_pump_main,
    read_well_spec,
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
from iwfm_io.readers.lake import read_lake_main, read_max_lake_elev

# Root zone readers
from iwfm_io.readers.rootzone import (
    read_rootzone_main,
    read_nonponded_ag_main,
    read_ponded_ag_main,
    read_urban_main,
    read_native_veg_main,
    read_land_use_area,
    read_all_land_use_areas,
    read_surface_flow_dest,
)

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
    write_irr_period,
    write_supply_adjust,
    write_timeseries_file,
)

# Groundwater writers
from iwfm_io.writers.groundwater import (
    write_gw_main,
    write_bc_main,
    write_spec_head_bc,
    write_spec_flow_bc,
    write_general_head_bc,
    write_constrained_head_bc,
    write_boundary_ts,
    write_pump_main,
    write_well_spec,
    write_elem_pump,
    write_ts_pumping,
    write_tile_drain,
    write_subsidence,
    write_subsidence as write_subsidence_file,
    write_gw_initial_conditions,
    initial_heads_from_head_all,
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
from iwfm_io.writers.lake import write_lake_main, write_max_lake_elev

# Root zone writers
from iwfm_io.writers.rootzone import (
    write_rootzone_main,
    write_nonponded_ag_main,
    write_ponded_ag_main,
    write_urban_main,
    write_native_veg_main,
    write_land_use_area,
    write_surface_flow_dest,
)

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

# Wells: metadata, hydrograph linking, mapping, compositing
from iwfm_io.wells import (
    WellMapping,
    build_well_mapping,
    select_best_layers,
    validate_gwl_metadata,
    HydrographLink,
    link_hydrographs,
    assign_sequences,
    composite_well_hydrographs,
    enrich_gwl_metadata,
    gwl_metadata_from_legacy,
)

# Stream gauges: metadata, hydrograph linking, series extraction
from iwfm_io.gauges import (
    validate_gauge_metadata,
    GaugeLink,
    link_stream_hydrographs,
    stream_hydrograph_series,
    assign_gauge_sequences,
)

# HEC-DSS reading + CalSim channel-flow linking (pydsstools loaded lazily
# at call time — importing these costs nothing without the [dss] extra)
from iwfm_io.dss import (
    dss_catalog,
    read_dss_timeseries,
    cfs_to_taf,
    CalSimLink,
    link_calsim_channels,
    calsim_streamflow_series,
)

# GIS exports (geopandas/shapely loaded lazily at call time — importing
# these costs nothing without the [geo] extra)
from iwfm_io.gis import (
    GIS_LAYERS,
    export_gis,
    nodes_gdf,
    elements_gdf,
    subregions_gdf,
    streams_gdf,
    stream_nodes_gdf,
    lakes_gdf,
    tile_drains_gdf,
    wells_gdf,
)

# VTK exports (pure numpy — no VTK library needed)
from iwfm_io.vtk import (
    export_vtk,
    export_vtk_timeseries,
)

# Multi-run collection helpers + component-aware budget aggregation
from iwfm_io.collect import (
    collect_budgets,
    collect_zbudgets,
    collect_hydrographs,
    collect_gwheads,
    aggregate_budget,
    budget_component_agg,
)

def __getattr__(name):
    # Lazy subpackages: matplotlib loads only when plots are used, and
    # the ctypes layer only when the DLL wrapper is used.
    if name in ("plots", "dll", "pest"):
        import importlib
        return importlib.import_module(f".{name}", __name__)
    # ``iwfm_io.find("budget")`` -- the in-process API index search.
    # Lazy so that ``python -m iwfm_io._api_index`` can regenerate the
    # index without the module being half-imported underneath it.
    if name == "find":
        from iwfm_io._api_index import find as _find
        return _find
    raise AttributeError(f"module 'iwfm_io' has no attribute {name!r}")


__all__ = [
    "plots",
    "dll",
    "pest",
    # Entry point + the workflow this package is built around
    "open_model",
    "find",
    "create_scenario",
    "set_keyed_value",
    "replace_text",
    "compare_models",
    "diff_model_files",
    "head_difference",
    "budget_difference",
    "GIS_LAYERS",
    "export_gis",
    "nodes_gdf",
    "elements_gdf",
    "subregions_gdf",
    "streams_gdf",
    "stream_nodes_gdf",
    "lakes_gdf",
    "tile_drains_gdf",
    "wells_gdf",
    "export_vtk",
    "export_vtk_timeseries",
    # Scenario runner
    "RunError",
    "RunResult",
    "run_model",
    "run_preprocessor",
    "run_simulation",
    "run_budget",
    "run_zbudget",
    # Date utilities
    "parse_iwfm_date",
    "format_iwfm_date",
    "iwfm_day",
    "water_year",
    "expand_recurring",
    "aggregate_budget",
    "budget_component_agg",
    # Parser/writer engine
    "IWFMFileReader",
    "IWFMFileWriter",
    "IWFMParseError",
    "IWFMReadWarning",
    "strict_mode",
    # Shared data models
    "FileHeader",
    "TimeSeriesSpec",
    "ConversionFactor",
    "ZoneDefinition",
    "TimeSeriesFile",
    "TimeSeriesDataFile",
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
    "read_irr_period",
    "read_supply_adjust",
    "read_timeseries_file",
    # Groundwater readers
    "read_gw_main",
    "read_bc_main",
    "read_spec_head_bc",
    "read_spec_flow_bc",
    "read_general_head_bc",
    "read_constrained_head_bc",
    "read_boundary_ts",
    "read_pump_main",
    "read_well_spec",
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
    "read_max_lake_elev",
    # Root zone readers
    "read_rootzone_main",
    "read_nonponded_ag_main",
    "read_ponded_ag_main",
    "read_urban_main",
    "read_native_veg_main",
    "read_land_use_area",
    "read_all_land_use_areas",
    "read_surface_flow_dest",
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
    "write_irr_period",
    "write_supply_adjust",
    "write_timeseries_file",
    # Groundwater writers
    "write_gw_main",
    "write_gw_initial_conditions",
    "initial_heads_from_head_all",
    "write_bc_main",
    "write_spec_head_bc",
    "write_spec_flow_bc",
    "write_general_head_bc",
    "write_constrained_head_bc",
    "write_boundary_ts",
    "write_pump_main",
    "write_well_spec",
    "write_elem_pump",
    "write_ts_pumping",
    "write_tile_drain",
    "write_subsidence",
    "write_subsidence_file",
    # Stream writers
    "write_stream_main",
    "write_stream_inflow",
    "write_diver_specs",
    "write_bypass_specs",
    "write_diversions",
    # Lake writers
    "write_lake_main",
    "write_max_lake_elev",
    # Root zone writers
    "write_rootzone_main",
    "write_nonponded_ag_main",
    "write_ponded_ag_main",
    "write_urban_main",
    "write_native_veg_main",
    "write_land_use_area",
    "write_surface_flow_dest",
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
    # Wells: metadata, hydrograph linking, mapping, compositing
    "WellMapping",
    "build_well_mapping",
    "select_best_layers",
    "validate_gwl_metadata",
    "HydrographLink",
    "link_hydrographs",
    "assign_sequences",
    "composite_well_hydrographs",
    "enrich_gwl_metadata",
    "gwl_metadata_from_legacy",
    "validate_gauge_metadata",
    "GaugeLink",
    "link_stream_hydrographs",
    "stream_hydrograph_series",
    "assign_gauge_sequences",
    "dss_catalog",
    "read_dss_timeseries",
    "cfs_to_taf",
    "CalSimLink",
    "link_calsim_channels",
    "calsim_streamflow_series",
    "collect_budgets",
    "collect_zbudgets",
    "collect_hydrographs",
    "collect_gwheads",
]
