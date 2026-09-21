# iwfm-io API index

Every public name in `iwfm-io`, one line each, grouped by what you are
trying to do. **Check here before writing a function that reads, writes,
parses, converts or aggregates IWFM data - if it is in this list, call it
instead of reimplementing it.** Hand-rolled IWFM code gets the `24:00`
date convention, the `Cc*` comment characters, load-bearing terminating
comments and simulation-anchored budget windows wrong.

Search it from anywhere:

```bash
iwfm-io api budget        # matching names, with signatures
iwfm-io api --path        # this file's location on disk
```

`import iwfm_io` then `iwfm_io.find("water year")` runs the same search
in process. Names shown as `plots.x`, `pest.x` and `dll.x` live in those
subpackages; everything else is top-level (`from iwfm_io import
open_model`). Full argument semantics live in `docs/api-reference.md`
(<https://github.com/SercanC/iwfm-io/blob/main/docs/api-reference.md>).

*Generated from the package by `python -m iwfm_io._api_index --write` -
edit the docstrings, not this file.*

*340 public names.*

## Start here - open a model

`open_model()` finds the model's main files and results; `describe()` says what it contains. The adapter's DataFrame accessors answer most questions without touching a reader.

- `open_model(path, preprocessor=None, simulation=None, results_dir=None, strict=True)` - Open an IWFM model from its folder - the simplest way to read a model.
- `find(query: 'Optional[str]' = None) -> 'List[Entry]'` - Print the public names matching ``query``, and return them.
- `IOModelAdapter(preprocessor=None, simulation=None, heads_hdf=None, budget_hdfs=None, hydrograph_, ...)` - Adapter presenting IO-reader data through the same ``_df()`` API as :class:`~iwfm_io.dll.model.IWFMModel`.
  - `.available_budgets` - Sorted budget names this adapter can serve -- HDF and text (``.bud``) sources alike.
  - `.available_zbudgets` - Sorted zone-budget names with an HDF source.
  - `.bc_series(node, layer=None, raw=False, expand=True)` - The boundary condition at a GW node (and layer), searching all four BC files.
  - `.budget_df(budget_name, location, begin_date=None, end_date=None, interval=None, columns=Non, ...)` - Return DataFrame(DatetimeIndex) of budget time series.
  - `.bypasses_df()` - Return DataFrame: bypass_id, export_node, dest_type, dest, rec_loss, nonrec_loss.
  - `.column_usage(role)` - Reverse lookup: who references each column of a time-series file.
  - `.component(name)` - A parsed component/sub-file by registry name, lazily read and cached (e.g.
  - `.crop_series(kind, crop, element=None, raw=False, expand=True)` - A land-use driver series for one crop/land-use at an element.
  - `.describe()` - Return a JSON-serializable summary of the model.
  - `.diversion_series(diversion_id, kind='delivery', scaled=True, raw=False, expand=True)` - One diversion's series from the Diversions file - its ``"delivery"``, ``"max"``, ``"recoverable_loss"``, ``"nonrecovera...
  - `.diversions_df()` - Return DataFrame: diversion_id, export_node, dest_type, dest_id, name, elements, recharge_elements.
  - `.element_pumping(element_id, kind='pumping', scaled=True, raw=False, expand=True)` - An element's pumping series from the time-series pumping file - its ICOLSK column times its FRACSK share.
  - `.elements_df()` - Return GeoDataFrame: element_id, node1-4, subregion, geometry(Polygon).
  - `.gw_main` - The parsed groundwater main (``GWMain``) or ``None``.
  - `.heads_df(layer, begin_date=None, end_date=None, day_index=False)` - Return DataFrame(DatetimeIndex) with one column per node.
  - `.heads_file` - Path of the head output this adapter serves (HDF or text), or ``None``.
  - `.hydrograph_df(hdf_name, column=None, begin_date=None, end_date=None, day_index=False, **kwargs)` - Return DataFrame(DatetimeIndex) from a hydrograph HDF5.
  - `.lake_max_elevation(lake_id=None, raw=False, expand=True)` - A lake's maximum-elevation series from the MaxLakeElev file (``lake_id`` optional for single-lake models).
  - `.lakes_df()` - Return DataFrame: lake_id, n_elements, elements(list).
  - `.model_root` - Root folder :func:`open_model` discovered the model in (``None`` for an adapter built from explicit file objects).
  - `.n_diversions` - (undocumented)
  - `.n_elements` - (undocumented)
  - `.n_lakes` - (undocumented)
  - `.n_layers` - (undocumented)
  - `.n_nodes` - (undocumented)
  - `.n_reaches` - (undocumented)
  - `.n_stream_nodes` - (undocumented)
  - `.n_subregions` - (undocumented)
  - `.n_wells` - (undocumented)
  - `.nodes_df()` - Return GeoDataFrame: node_id, x, y, geometry(Point).
  - `.preprocessor` - The parsed preprocessor main (``PreprocessorMain``) or ``None``.
  - `.reaches_df()` - Return DataFrame: reach_id, n_nodes, outflow_dest, name.
  - `.reload()` - Drop every cached table so the next access re-reads the files.
  - `.series(role, column, raw=False, expand=True)` - One referenced time-series column as a ``date``/``value`` DataFrame - the thing a pointer column points at.
  - `.simulation` - The parsed simulation main (``SimulationMain``) or ``None``.
  - `.stratigraphy_df()` - Return DataFrame: node_id, elevation, aquitard_1, aquifer_1, ...
  - `.stream_flows_df(factor=1.0, stat='mean')` - Per-stream-node flow components from the stream node budget HDF.
  - `.stream_main` - The parsed stream main (``StreamMain``) or ``None``.
  - `.stream_nodes_df()` - Return GeoDataFrame: stream_node_id, reach_id, gw_node_id, geometry(Point).
  - `.stream_rating_tables_df()` - Return DataFrame: stream_node_id, bottom_elev, stage, flow.
  - `.subregions_df()` - Return DataFrame: subregion_id, name.
  - `.subsidence_df(factor=1.0)` - Not available from IO readers without live DLL snapshot.
  - `.tile_drains_df()` - Return GeoDataFrame: id, node, x, y, geometry(Point).
  - `.timeseries(role)` - The parsed time-series file for a pointer-target role, lazily read and cached (e.g.
  - `.to_gis(path, layers=None, crs=None, node_data=None, element_data=None)` - Write the model's spatial layers to a GeoPackage or shapefiles.
  - `.to_vtk(path, point_data=None, cell_data=None, z_scale=1.0, layers=None)` - Write the model as a 3D layered mesh to a VTK ``.vtu`` file.
  - `.urban_series(kind, element=None, raw=False, expand=True)` - An urban driver series at an element: ``"population"``, ``"per_capita_use"``, ``"water_use_specs"``, ``"et"``, ``"retur...
  - `.validate_references()` - Validate every cross-file reference: pointer columns within the target file's column count, entity IDs present in the g...
  - `.well_pumping(well_id, kind='pumping', scaled=True, raw=False, expand=True)` - A well's pumping series from the time-series pumping file - its ICOLWL column times its FRACWL share (``scaled=False``...
  - `.wells_df()` - Return GeoDataFrame: well_id, x, y, radius, perf_top, perf_bot, name, geometry(Point).

## Dates, water years & IWFM conventions

Never parse IWFM dates by hand - `MM/DD/YYYY_24:00` means the END of that day, and `iwfm_day` owns the off-by-one.

- `expand_recurring(data, begin, end)` - Expand IWFM recurring-year time-series data onto a real period.
- `format_iwfm_date(dt: 'datetime') -> 'str'` - Format a datetime as an IWFM date string ``MM/DD/YYYY_HH:MM``.
- `iwfm_day(times)` - The day each timestamp *belongs to* under the ``24:00`` convention.
- `parse_iwfm_date(date_str: 'str') -> 'datetime'` - Parse an IWFM date string ``MM/DD/YYYY_HH:MM`` into a datetime.
- `water_year(times)` - Water year each timestamp belongs to (Oct 1 - Sep 30, labeled by the ending year), honoring the ``24:00`` convention vi...

## Read model outputs (heads, budgets, hydrographs)

- `read_budget_hdf(path: 'Union[str, Path]', interval: 'Optional[str]' = None) -> 'Dict'` - Read an IWFM budget HDF5 file into a dictionary of DataFrames.
- `read_budget_text(path: 'Union[str, Path]') -> 'dict'` - Read a text budget file (.bud) into a dict of DataFrames.
- `read_final_state_out(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read a final state file (FinalGWHeads.out, FinalLakeElev.out, etc.).
- `read_flow_out(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read a flow output file (BoundaryFlow.out, FaceFlow.out, VerticalFlow.out).
- `read_head_all_out(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read GWHeadAll.out - groundwater heads at all nodes.
- `read_head_hdf(path: 'Union[str, Path]', n_nodes: 'Optional[int]' = None, n_la, ...) -> 'pd.DataFrame'` - Read the IWFM groundwater-head-at-all-nodes HDF5 file (``GWHeadAll.hdf``).
- `read_hydrograph_hdf(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read an IWFM hydrograph HDF5 file into a single DataFrame.
- `read_hydrograph_out(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read GWHyd.out, StrmHyd.out, or similar hydrograph text output.
- `read_hydrograph_out_with_metadata(path: 'Union[str, Path]') -> 'dict'` - Read hydrograph .out file with metadata.
- `read_velocity_out(path: 'Union[str, Path]') -> 'pd.DataFrame'` - Read GWVelocities.out - element centroid velocities per timestep.
- `read_zbudget_hdf(path: 'Union[str, Path]', zone_def: 'Union[ZoneDefinition, str, Path, N, ...) -> 'Dict'` - Read an IWFM Zone Budget HDF5 file.
- `read_zone_def(path: 'Union[str, Path]') -> 'ZoneDefinition'` - Read an IWFM zone definition file for Z-Budget post-processing.

## Read input files

- `read_all_land_use_areas(rootzone_main, element_areas=None) -> 'pd.DataFrame'` - Read all land use area files of a model into one DataFrame.
- `read_bc_main(path: 'str | Path', follow_references: 'bool' = False) -> 'BCMain'` - Read the boundary conditions main file (e.g.
- `read_boundary_ts(path: 'str | Path') -> 'BoundaryTSFile'` - Read a time-series boundary conditions file (e.g.
- `read_bypass_specs(path: 'str | Path') -> 'BypassSpecsFile'` - Read an IWFM bypass specification file (e.g.
- `read_constrained_head_bc(path: 'str | Path') -> 'ConstrainedHeadBCFile'` - Read a constrained general head boundary conditions file.
- `read_diver_specs(path: 'str | Path') -> 'DiverSpecsFile'` - Read an IWFM diversion specification file (e.g.
- `read_diversions(path: 'str | Path') -> 'DiversionsFile'` - Read an IWFM surface water diversion data file (e.g.
- `read_elem_pump(path: 'str | Path', n_layers: 'int | None' = None) -> 'ElemPumpFile'` - Read an element pumping specification file (e.g.
- `read_elements(path: 'str | Path', node_file: 'NodeFile | None' = None) -> 'ElementFile'` - Read an IWFM element configuration file (e.g.
- `read_et(path: 'str | Path') -> 'ETFile'` - Read an IWFM evapotranspiration file (e.g.
- `read_general_head_bc(path: 'str | Path') -> 'GeneralHeadBCFile'` - Read a general head boundary conditions file.
- `read_gw_main(path: 'str | Path', follow_references: 'bool' = False) -> 'GWMain'` - Read the groundwater component main input file (e.g.
- `read_irigfrac(path: 'str | Path') -> 'IrigFracFile'` - Read an IWFM irrigation fractions file (e.g.
- `read_irr_period(path: 'str | Path') -> 'IrrPeriodFile'` - Read an IWFM irrigation period data file (IPFL, e.g.
- `read_lake_geom(path: 'str | Path') -> 'LakeGeomFile'` - Read an IWFM lake geometry file (e.g.
- `read_lake_main(path: 'str | Path') -> 'LakeMain'` - Read the IWFM lake component main file (e.g.
- `read_land_use_area(path: 'str | Path', columns: 'list[str] | None' = None) -> 'LandUseAreaFile'` - Read an IWFM land use area file (LUFLNP / LUFLP / LUFLU / LUFLNVRV).
- `read_max_lake_elev(path: 'str | Path') -> 'TimeSeriesFile'` - Read an IWFM maximum lake elevation file (e.g.
- `read_native_veg_main(path: 'str | Path', n_elements: 'int | None' = None) -> 'NativeVegFile'` - Read the native and riparian vegetation main file (NVRVFL).
- `read_nodes(path: 'str | Path') -> 'NodeFile'` - Read an IWFM node coordinate file (e.g.
- `read_nonponded_ag_main(path: 'str | Path', n_elements: 'int | None' = None) -> 'NonPondedAgFile'` - Read the non-ponded agricultural crops main file (AGNPFL).
- `read_ponded_ag_main(path: 'str | Path', n_elements: 'int | None' = None) -> 'PondedAgFile'` - Read the ponded agricultural crops main file (PFL).
- `read_precip(path: 'str | Path') -> 'PrecipFile'` - Read an IWFM precipitation file (e.g.
- `read_preprocessor(path: 'str | Path', follow_references: 'bool' = True, stric, ...) -> 'PreprocessorMain'` - Read the preprocessor main input file.
- `read_pump_main(path: 'str | Path', follow_references: 'bool' = False) -> 'PumpMain'` - Read the pumping component main file (e.g.
- `read_rootzone_main(path: 'str | Path', n_elements: 'int | None' = None) -> 'RootZoneMain'` - Read the IWFM root zone component main file.
- `read_simulation(path: 'str | Path', follow_references: 'bool' = False, strict, ...) -> 'SimulationMain'` - Read the IWFM simulation main file (e.g.
- `read_spec_flow_bc(path: 'str | Path') -> 'SpecifiedFlowBCFile'` - Read a specified flow boundary conditions file.
- `read_spec_head_bc(path: 'str | Path') -> 'SpecifiedHeadFile'` - Read a specified head boundary conditions file (e.g.
- `read_strata(path: 'str | Path', n_nodes: 'int | None' = None) -> 'StratigraphyFile'` - Read an IWFM stratigraphy file (e.g.
- `read_stream_geom(path: 'str | Path', node_file: 'NodeFile | None' = None) -> 'StreamGeomFile'` - Read an IWFM stream geometry file (e.g.
- `read_stream_inflow(path: 'str | Path') -> 'StreamInflowFile'` - Read an IWFM stream inflow file (e.g.
- `read_stream_main(path: 'str | Path') -> 'StreamMain'` - Read an IWFM stream main file (e.g.
- `read_subsidence(path: 'str | Path') -> 'SubsidenceFile'` - Read the subsidence component main file (e.g.
- `read_supply_adjust(path: 'str | Path') -> 'SupplyAdjustFile'` - Read an IWFM supply adjustment file (e.g.
- `read_surface_flow_dest(path: 'str | Path') -> 'SurfaceFlowDestFile'` - Read a surface flow destination file (e.g.
- `read_swshed(path: 'str | Path') -> 'SWShedFile'` - Read the IWFM small watershed file (e.g.
- `read_tile_drain(path: 'str | Path') -> 'TileDrainFile'` - Read a tile drain parameter file (e.g.
- `read_timeseries_file(path: 'str | Path', has_factor: 'bool | None' = None, has, ...) -> 'TimeSeriesDataFile'` - Read any standard IWFM time-series data file.
- `read_ts_pumping(path: 'str | Path') -> 'TSPumpingFile'` - Read a time-series pumping data file (e.g.
- `read_unsatzone(path: 'str | Path') -> 'UnsatZoneFile'` - Read the IWFM unsaturated zone file (e.g.
- `read_urban_main(path: 'str | Path', n_elements: 'int | None' = None) -> 'UrbanFile'` - Read the urban lands main file (URBFL).
- `read_well_spec(path: 'str | Path') -> 'WellSpecFile'` - Read a well specification file (e.g.

## Write input files

Writers regenerate a whole file from its DataFrames and refuse cells IWFM would misread (NaN, `/` in a name, missing layers). Edit the DataFrame and write it - never patch the text.

- `initial_heads_from_head_all(head_all, date=None)` - Build an initial-heads table from one ``GWHeadAll.out`` timestep.
- `write_bc_main(bc: 'BCMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the boundary conditions main file.
- `write_boundary_ts(bt: 'BoundaryTSFile', path: 'str | Path') -> 'None'` - Write a time-series boundary conditions file.
- `write_bypass_specs(bs: 'BypassSpecsFile', path: 'str | Path') -> 'None'` - Write an IWFM bypass specification file.
- `write_constrained_head_bc(ch: 'ConstrainedHeadBCFile', path: 'str | Path') -> 'None'` - Write a constrained general head boundary conditions file.
- `write_diver_specs(ds: 'DiverSpecsFile', path: 'str | Path') -> 'None'` - Write an IWFM diversion specification file.
- `write_diversions(dv: 'DiversionsFile', path: 'str | Path') -> 'None'` - Write an IWFM surface water diversion data file.
- `write_elem_pump(ep: 'ElemPumpFile', path: 'str | Path') -> 'None'` - Write an element pumping specification file.
- `write_elements(elem_file: 'ElementFile', path: 'str | Path') -> 'None'` - Write an IWFM element configuration file.
- `write_et(et: 'ETFile', path: 'str | Path') -> 'None'` - Write an IWFM evapotranspiration file.
- `write_general_head_bc(gh: 'GeneralHeadBCFile', path: 'str | Path') -> 'None'` - Write a general head boundary conditions file.
- `write_gw_initial_conditions(path: 'str | Path', heads, facthp: 'float' = 1.0, header: "'list[str] |, ...) -> 'None'` - Write an IWFM groundwater initial-conditions (restart) file.
- `write_gw_main(gw: 'GWMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the groundwater component main file.
- `write_irigfrac(irig: 'IrigFracFile', path: 'str | Path') -> 'None'` - Write an IWFM irrigation fractions file.
- `write_irr_period(ip: 'IrrPeriodFile', path: 'str | Path') -> 'None'` - Write an IWFM irrigation period data file (IPFL).
- `write_lake_geom(lake_file: 'LakeGeomFile', path: 'str | Path') -> 'None'` - Write an IWFM lake geometry file.
- `write_lake_main(lake: 'LakeMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the IWFM lake component main file.
- `write_land_use_area(lu: 'LandUseAreaFile', path: 'str | Path') -> 'None'` - Write an IWFM land use area file (LUFLNP / LUFLP / LUFLU / LUFLNVRV).
- `write_max_lake_elev(ts: 'TimeSeriesFile', path: 'str | Path') -> 'None'` - Write an IWFM maximum lake elevation file.
- `write_native_veg_main(nv: 'NativeVegFile', path: 'str | Path', base_dir: 'str | Path | None', ...) -> 'None'` - Write the native and riparian vegetation main file (NVRVFL).
- `write_nodes(node_file: 'NodeFile', path: 'str | Path') -> 'None'` - Write an IWFM node coordinate file.
- `write_nonponded_ag_main(np_ag: 'NonPondedAgFile', path: 'str | Path', base_dir: 'str | Path | N, ...) -> 'None'` - Write the non-ponded agricultural crops main file (AGNPFL).
- `write_ponded_ag_main(pa: 'PondedAgFile', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the ponded agricultural crops main file (PFL).
- `write_precip(precip: 'PrecipFile', path: 'str | Path') -> 'None'` - Write an IWFM precipitation file.
- `write_preprocessor(pp: 'PreprocessorMain', path: 'str | Path', base_dir: 'str | Path | Non, ...) -> 'None'` - Write the preprocessor main input file.
- `write_pump_main(pm: 'PumpMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the pumping component main file.
- `write_rootzone_main(rz: 'RootZoneMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the IWFM root zone component main file.
- `write_simulation(sim: 'SimulationMain', path: 'str | Path', base_dir: 'str | Path | None, ...) -> 'None'` - Write the IWFM simulation main file.
- `write_spec_flow_bc(sf: 'SpecifiedFlowBCFile', path: 'str | Path') -> 'None'` - Write a specified flow boundary conditions file.
- `write_spec_head_bc(sf: 'SpecifiedHeadFile', path: 'str | Path') -> 'None'` - Write a specified head boundary conditions file.
- `write_strata(strata_file: 'StratigraphyFile', path: 'str | Path') -> 'None'` - Write an IWFM stratigraphy file.
- `write_stream_geom(stream_file: 'StreamGeomFile', path: 'str | Path') -> 'None'` - Write an IWFM stream geometry file.
- `write_stream_inflow(sf: 'StreamInflowFile', path: 'str | Path') -> 'None'` - Write an IWFM stream inflow file.
- `write_stream_main(sm: 'StreamMain', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write an IWFM stream main file.
- `write_subsidence(sub: 'SubsidenceFile', path: 'str | Path', base_dir: 'str | Path | None, ...) -> 'None'` - Write the subsidence component main file.
- `write_subsidence_file` - Alias of `write_subsidence`.
- `write_supply_adjust(sa: 'SupplyAdjustFile', path: 'str | Path') -> 'None'` - Write an IWFM supply adjustment file.
- `write_surface_flow_dest(sfd, path: 'str | Path') -> 'None'` - Write a surface flow destination file (DESTFL).
- `write_swshed(sw: 'SWShedFile', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the IWFM small watershed file (e.g.
- `write_tile_drain(td: 'TileDrainFile', path: 'str | Path') -> 'None'` - Write a tile drain parameter file.
- `write_timeseries_file(ts: 'TimeSeriesDataFile', path: 'str | Path') -> 'None'` - Write a standard IWFM time-series data file.
- `write_ts_pumping(ts: 'TSPumpingFile', path: 'str | Path') -> 'None'` - Write a time-series pumping data file.
- `write_unsatzone(uz: 'UnsatZoneFile', path: 'str | Path', base_dir: 'str | Path | None', ...) -> 'None'` - Write the IWFM unsaturated zone file (e.g.
- `write_urban_main(ur: 'UrbanFile', path: 'str | Path', base_dir: 'str | Path | None' = None) -> 'None'` - Write the urban lands main file (URBFL).
- `write_well_spec(ws: 'WellSpecFile', path: 'str | Path') -> 'None'` - Write a well specification file.

## Aggregate & collect across runs

- `aggregate_budget(df: 'pd.DataFrame', period: 'str' = 'WY', data_types: 'Optional, ...) -> 'pd.DataFrame'` - Aggregate IWFM budget output over water years, calendar years, or months - with the right rule per component.
- `budget_component_agg(name) -> 'str'` - How an IWFM budget component aggregates over a period.
- `collect_budgets(runs: 'Dict[str, Path]', budget_files: 'Dict[str, str]', locati, ...) -> 'pd.DataFrame'` - Collect budget HDF5 files from multiple model runs into a long-form DataFrame.
- `collect_gwheads(runs: 'Dict[str, Path]', head_file: 'str' = 'GWHeadAll.hdf', no, ...) -> 'pd.DataFrame'` - Collect GW-head-at-all-nodes HDF5 files from multiple runs into a long-form DataFrame.
- `collect_hydrographs(runs: 'Dict[str, Path]', hydrograph_files: 'Dict[str, str]', si, ...) -> 'pd.DataFrame'` - Collect hydrograph HDF5 files from multiple runs into a long-form DataFrame.
- `collect_zbudgets(runs: 'Dict[str, Path]', zbudget_files: 'Dict[str, str]', zone_, ...) -> 'pd.DataFrame'` - Collect zone-budget HDF5 files from multiple runs into a long-form DataFrame.

## Compare model runs

- `budget_difference(a, b, budget, location, interval=None, begin_date=None, end_date=None)` - Budget difference ``B - A`` for one budget and location.
- `compare_models(a, b, layers=None, include_files=True, file_subdirs=None, max_workers=8)` - Compare two models and return a JSON-serializable report.
- `diff_model_files(path_a, path_b, subdirs=None, max_workers=8)` - Checksum-based file comparison of two model folders.
- `head_difference(a, b, layer, begin_date=None, end_date=None)` - Groundwater head difference ``B - A`` for one layer.

## Scenarios & running IWFM

- `create_scenario(base_dir, out_dir, changes=None, subdirs=('Preprocessor', 'Simulation', 'Budget', ...)` - Copy a model folder and apply modifications to the copy.
- `replace_text(relpath, old, new, count=-1)` - Literal text replacement in one file of the scenario.
- `run_budget(model_dir, **kwargs)` - Run the IWFM Budget post-processor.
- `run_model(model_dir, steps=('preprocessor', 'simulation'), bin_dir=None, timeout=None, quie, ...)` - Run the IWFM toolchain for a model folder.
- `run_preprocessor(model_dir, **kwargs)` - Run the IWFM PreProcessor.
- `run_simulation(model_dir, **kwargs)` - Run the IWFM Simulation.
- `run_zbudget(model_dir, **kwargs)` - Run the IWFM ZBudget post-processor.
- `RunError(message, results)` - A step failed under ``run_model(check=True)``.
- `RunResult(step: 'str', exe: 'str', input_file: 'str', returncode: 'int', elapsed: ', ...) -> None` - Outcome of one IWFM tool run.
- `set_keyed_value(relpath, keyword, value)` - Change a ``VALUE / KEYWORD`` line in an IWFM input file.

## Validate a model

- `validate_elements(element_file: 'Any', node_file: 'Any | None' = None) -> 'list[str]'` - Validate a parsed element file.
- `validate_nodes(node_file: 'Any') -> 'list[str]'` - Validate a parsed node file.
- `validate_preprocessor(pp: 'Any') -> 'list[str]'` - Validate a complete preprocessor file set.
- `validate_stratigraphy(strata_file: 'Any', node_file: 'Any | None' = None) -> 'list[str]'` - Validate a parsed stratigraphy file.

## Observation wells & stream gauges

- `assign_gauge_sequences(gauge_metadata, link: 'Optional[GaugeLink]' = None, order: 's, ...) -> "'pd.DataFrame'"` - Fill missing within-group gauge sequence numbers (pure function).
- `assign_sequences(gwl_metadata, link: 'Optional[HydrographLink]' = None, order:, ...) -> "'pd.DataFrame'"` - Fill missing within-group sequence numbers (pure function).
- `build_well_mapping(model, wells, kh=None, spatial: 'str' = 'nearest', k: 'int' = 4, ...) -> 'WellMapping'` - Build the well-to-mesh mapping (the expensive, run-once step).
- `composite_well_hydrographs(link: 'HydrographLink', hyd_output, fractions) -> "'pd.DataFrame'"` - Composite per-layer hydrograph series into per-well series.
- `enrich_gwl_metadata(model, gwl_metadata, link: 'Optional[HydrographLink]' = None, ...) -> "'pd.DataFrame'"` - Add derived columns to a gwl_metadata frame (never required).
- `GaugeLink(links: "'pd.DataFrame'", unmatched_gauges: "'list'", orphan_names: "'list, ...) -> None` - Result of :func:`link_stream_hydrographs`.
  - `.summary() -> 'dict'` - (undocumented)
- `gwl_metadata_from_legacy(df) -> "'pd.DataFrame'"` - Convert a legacy well-keys frame to the gwl_metadata schema.
- `HydrographLink(links: "'pd.DataFrame'", unmatched_wells: "'list'", orphan_stems: "'list', ...) -> None` - Result of :func:`link_hydrographs`.
  - `.summary() -> 'dict'` - (undocumented)
- `link_hydrographs(gwl_metadata, gw_main, on: 'str' = 'site_code', name_sep: 'st, ...) -> 'HydrographLink'` - Link metadata wells to the GW main's hydrograph entries by name.
- `link_stream_hydrographs(gauge_metadata, stream_main, on: 'str' = 'site_code', name_sep: 'O, ...) -> 'GaugeLink'` - Link gauge metadata to the Stream MAIN hydrograph entries by name.
- `pest.build_well_mapping` - Alias of `build_well_mapping`.
- `pest.select_best_layers` - Alias of `select_best_layers`.
- `pest.WellMapping` - Alias of `WellMapping`.
- `select_best_layers(mapping: 'WellMapping', heads, obs, min_n: 'int' = 6, default_la, ...) -> "'pd.Series'"` - Pick each well's best single layer by RMSE against observations.
- `stream_hydrograph_series(link: 'GaugeLink', hyd_output, ihsqr: 'Optional[int]' = None, ...) -> "'pd.DataFrame'"` - Extract per-gauge series from stream hydrograph output.
- `validate_gauge_metadata(df) -> "'list'"` - Check a gauge_metadata frame; returns problem strings (empty = OK).
- `validate_gwl_metadata(df) -> "'list'"` - Check a gwl_metadata frame; returns problem strings (empty = OK).
- `WellMapping(wells: "'pd.DataFrame'", weights: "'pd.DataFrame'", n_layers: 'int') -> None` - Well-to-mesh mapping with per-(node, layer) composite weights.
  - `.composite(heads) -> "'pd.DataFrame'"` - Composite per-well heads from node x layer simulated heads.
  - `.from_csv(path) -> "'WellMapping'"` - (undocumented)
  - `.to_csv(path) -> 'None'` - Persist as one denormalized CSV (the ``fracs.csv`` role).

## HEC-DSS / CalSim coupling

- `calsim_streamflow_series(link: 'CalSimLink', dss_file, units: 'str' = 'cfs') -> "'pd.DataFrame'"` - Extract per-gauge CalSim channel-flow series from a DV DSS file.
- `CalSimLink(links: "'pd.DataFrame'", unmatched_gauges: "'list'", orphan_arcs: "'list'") -> None` - Result of :func:`link_calsim_channels`.
  - `.summary() -> 'dict'` - (undocumented)
- `cfs_to_taf(frame) -> "'pd.DataFrame'"` - Convert period-average CFS to TAF per period (pure function).
- `dss_catalog(dss_file, pattern: 'str' = '') -> "'pd.DataFrame'"` - Catalog the time-series records of a HEC-DSS file.
- `link_calsim_channels(gauge_metadata, dss, on: 'str' = 'calsim_bpart', cpart: 'Optional, ...) -> 'CalSimLink'` - Link gauge metadata to CalSim channel arcs in a DSS file.
- `read_dss_timeseries(dss_file, paths) -> "'pd.DataFrame'"` - Read regular time-series records into a wide DataFrame.

## GIS & VTK export

- `elements_gdf(model, crs=None, data=None)` - Finite elements as a Polygon layer.
- `export_gis(model, path, layers=None, crs=None, node_data=None, element_data=None)` - Write a model's spatial layers to a GeoPackage or shapefiles.
- `export_vtk(model, path, point_data=None, cell_data=None, z_scale=1.0, layers=None)` - Write the model as a 3D layered mesh to a VTK ``.vtu`` file.
- `export_vtk_timeseries(model, out_dir, name='heads', begin_date=None, end_date=None, stride=1, z_scale=1, ...)` - Write simulated heads as a ParaView time series (``.pvd``).
- `GIS_LAYERS` - tuple constant: ('nodes', 'elements', 'subregions', 'streams', 'stream_nodes', 'lakes', 'tile_drains', 'wells')
- `lakes_gdf(model, crs=None)` - Lakes as merged element polygons.
- `nodes_gdf(model, crs=None, data=None, stratigraphy=True)` - Grid nodes as a Point layer.
- `stream_nodes_gdf(model, crs=None)` - Stream nodes as a Point layer (at their groundwater nodes).
- `streams_gdf(model, crs=None)` - Stream reaches as a LineString layer.
- `subregions_gdf(model, crs=None)` - Subregions as dissolved element polygons.
- `tile_drains_gdf(model, crs=None)` - Tile drains as a Point layer (``id``, ``node``, ``x``, ``y``).
- `wells_gdf(model, crs=None)` - Pumping wells as a Point layer (from the well specification file).

## Plotting (iwfm_io.plots)

All plot functions take an `IWFMModel` or `IOModelAdapter` and return `(fig, ax)`; most accept `save_path=` and `close=`.

- `plots.animations.animate_depth_to_water(model, layer, begin_date, end_date, interval_frames=1, cmap='YlOrRd', levels=20, ...)` - Animate depth-to-water (GSE minus head) over time.
- `plots.animations.animate_gw_heads(model, layer, begin_date, end_date, interval_frames=1, cmap='coolwarm_r', levels=, ...)` - Create an animation of groundwater head contours over time.
- `plots.animations.animate_stream_flows(model, layer, begin_date, end_date, interval_frames=1, figsize=(10, 8), fps=4, sa, ...)` - Animate stream flow by varying line width and color over time.
- `plots.calibration.plot_ensemble_hydrograph(ensemble, observed=None, base='base', original=None, quantiles=(0.05, 0.95), ylab, ...)` - Ensemble time-series band with base realization and observations.
- `plots.calibration.plot_obs_vs_sim(data, observed='observed', simulated='simulated', hexbin_threshold=5000, ax=None, ...)` - Observed vs simulated 1:1 plot with fit statistics.
- `plots.calibration.plot_parameter_histograms(results, parameters=None, group=None, par_data=None, iterations=None, max_pars=20, ...)` - Prior-vs-posterior histograms, one panel per parameter.
- `plots.calibration.plot_parameter_railing(source, n_top=25, ax=None, figsize=(8, 6), save_path=None, dpi=150, close=False)` - Stacked horizontal bars: % of ensemble values at bounds, per group.
- `plots.calibration.plot_phi_by_group(source, n_top=20, iterations=None, ax=None, figsize=(8, 7), save_path=None, dpi=1, ...)` - Horizontal bars of mean per-group phi, first vs last iteration.
- `plots.calibration.plot_phi_convergence(source, kind='composite', log=True, ax=None, figsize=(8, 5), save_path=None, dpi=, ...)` - Box-plot the ensemble phi distribution per IES iteration.
- `plots.calibration.plot_residual_butterfly(stats, metric='mean_res', n_top=30, ax=None, figsize=(8, 7), save_path=None, dpi=, ...)` - Diverging horizontal bars of a residual metric by group.
- `plots.calibration.plot_residual_map(stats, x='x', y='y', metric='mean_res', model=None, vlim=None, size=25, ax=None, ...)` - Map a residual metric at observation locations.
- `plots.connectivity.plot_bypass_flow_diagram(model, ax=None, figsize=(12, 10), save_path=None, close=False)` - Bypass routing diagram with loss fractions.
- `plots.connectivity.plot_diversion_network(model, ax=None, figsize=(12, 10), save_path=None, close=False)` - Graph visualization showing diversion flow paths.
- `plots.cross_sections.animate_cross_section(model, points, layer, begin_date, end_date, n_samples=80, interval_frames=1, figs, ...)` - Animate the water table along a cross-section over time.
- `plots.cross_sections.plot_multi_layer_head_panel(model, points, begin_date, end_date, n_samples=80, time_index=0, figsize=(14, 10), ...)` - Same transect, one subplot per layer, showing how head responses differ by depth.
- `plots.maps.plot_aquifer_parameter(model, parameter='Kh', layer=1, ax=None, cmap='viridis', title=None, label=None, ...)` - Plot a per-element map of an aquifer parameter for a given layer.
- `plots.maps.plot_depth_to_water(model, layer=1, ax=None, cmap='YlGnBu', levels=20, title=None, label='Depth to Wa, ...)` - Plot depth to water (ground surface minus head at last output timestep).
- `plots.maps.plot_grid_mesh(model, color_by='subregion', ax=None, figsize=(10, 8), title='Model Grid', cmap=', ...)` - Plot the finite-element mesh, optionally colored by subregion.
- `plots.maps.plot_ground_surface_elevation(model, ax=None, cmap='terrain', levels=25, title='Ground Surface Elevation', labe, ...)` - Plot a filled contour map of ground surface elevation.
- `plots.maps.plot_gw_head_contour(model, layer=1, time_index=None, begin_date=None, end_date=None, factor=1.0, ax=N, ...)` - Plot a groundwater head contour map.
- `plots.maps.plot_head_change(model, layer, heads_t1, heads_t2, ax=None, cmap='coolwarm', levels=20, title=None, ...)` - Plot the difference between two head arrays (t2 minus t1).
- `plots.maps.plot_lake_and_diversion_elements(model, ax=None, figsize=(10, 8), title='Lakes & Diversions', lake_color='deepskyb, ...)` - Highlight lake and diversion element groups on the model grid.
- `plots.maps.plot_layer_thickness(model, layer=1, ax=None, cmap='YlOrBr', levels=20, title=None, label='Thickness (, ...)` - Plot a filled contour map of aquifer layer thickness.
- `plots.maps.plot_stream_network(model, color_by='reach', ax=None, cmap='tab20', linewidth=2.0, alpha=0.9, title=', ...)` - Plot the stream network on top of the model grid.
- `plots.maps.plot_tile_drain_locations(model, ax=None, figsize=(10, 8), title='Tile Drain Locations', marker='s', marker, ...)` - Plot tile drain node locations on the model grid.
- `plots.maps.plot_well_locations(model, ax=None, cmap='plasma', figsize=(10, 8), title='Well Locations', show_grid, ...)` - Plot well locations colored/sized by perforation depth.
- `plots.plot_contour_map(source, node_values, ax=None, cmap='viridis', levels=20, label='', title='', fill, ...)` - Plot a contour map from node values.
- `plots.plot_element_map(source, values, ax=None, cmap='viridis', label='', title='', show_mesh=False, vmi, ...)` - Plot a color-filled element map.
- `plots.profiles.plot_stratigraphic_cross_section(model, points, n_samples=100, show_heads=True, layer_colors=None, ax=None, figsiz, ...)` - Plot a stratigraphic cross-section along a transect.
- `plots.profiles.plot_stream_longitudinal_profile(model, reach_ids=None, ax=None, figsize=(14, 5), save_path=None, close=False)` - Plot stream bottom elevation along reaches.
- `plots.seasonal.plot_budget_polar_seasonal(model, budget_type, location, begin_date, end_date, components=None, fact_vl=2.29, ...)` - Polar seasonal plot from budget monthly averages.
- `plots.seasonal.plot_calendar_heatmap(dates, values, value_label='Flow', cmap='YlGnBu', ax=None, figsize=(12, 6), save_, ...)` - Year x month heatmap of monthly values.
- `plots.seasonal.plot_polar_seasonal(monthly_values, labels=None, title='Seasonal Pattern', ax=None, figsize=(8, 8), s, ...)` - 12-month values on a polar axis.
- `plots.seasonal.plot_ridgeline(dates, values, value_label='Head', ax=None, figsize=(10, 10), cmap='viridis', ove, ...)` - Overlapping monthly hydrographs for successive years.
- `plots.spatial_patterns.plot_head_vs_gse_scatter(model, layer=1, ax=None, figsize=(8, 8), save_path=None, close=False)` - Scatter plot of initial head vs ground surface elevation.
- `plots.spatial_patterns.plot_small_multiples(model, layer, begin_date, end_date, n_panels=None, cmap='coolwarm_r', levels=15, ...)` - Tile the same head contour map for each year.
- `plots.spatial_patterns.plot_sparkline_grid(model, layer, begin_date, end_date, n_points=50, figsize=(14, 10), save_path=None, ...)` - Plot tiny hydrographs at sampled node locations on the map.
- `plots.stream_analysis.plot_stream_aquifer_exchange_map(model, layer=1, factor=1.0, show_heads=True, ax=None, figsize=(10, 8), save_path=, ...)` - Spatial map of GW gain/loss magnitude at each stream node.
- `plots.stream_analysis.plot_stream_gain_loss_profile(model, reach_ids=None, factor=1.0, ax=None, figsize=(14, 5), save_path=None, clos, ...)` - Longitudinal plot coloring each segment by GW gain/loss.
- `plots.subsidence.plot_subsidence_bowl(model, subsidence_values, layer=None, cmap='Reds', levels=20, ax=None, figsize=(1, ...)` - Contour map of cumulative subsidence.
- `plots.subsidence.plot_subsidence_vs_head(heads_ts, subsidence_ts, dates=None, node_label='', ax=None, figsize=(8, 6), save, ...)` - Cross-plot of subsidence vs head at a single node over time.
- `plots.summary.plot_aquifer_parameter_histograms(model, layer=1, bins=40, include_aquitard_kv=True, ax=None, figsize=(12, 8), save, ...)` - Histogram grid of aquifer parameters for a single layer.
- `plots.summary.plot_budget_annual_bars(model, budget_type, location, begin_date, end_date, fact_vl=2.295684113865932e-05, ...)` - Grouped or stacked bar chart of annual budget totals.
- `plots.summary.plot_budget_monthly_average(model, budget_type, location, begin_date, end_date, fact_vl=2.295684113865932e-05, ...)` - Grouped bar chart of monthly-average budget flows.
- `plots.summary.plot_budget_pie(model, budget_type, location, begin_date, end_date, interval='1MON', length_unit=, ...)` - Pie chart of average absolute flow by budget component.
- `plots.summary.plot_rating_curve(model, stream_nodes, log_scale=False, ax=None, figsize=(8, 6), save_path=None, ti, ...)` - Stage-discharge rating curves for one or more stream nodes.
- `plots.summary.plot_supply_vs_demand(model, location_type, locations, supply_type, supplies, factor=1.0, ax=None, figs, ...)` - Grouped bar chart of supply requirements vs shortages.
- `plots.summary.plot_water_balance_summary(model, budget_type, location, begin_date, end_date, interval='1MON', length_unit=, ...)` - Horizontal bar chart of mean inflows (positive) and outflows (negative).
- `plots.supply_demand.plot_budget_supply_gap(model, budget_type, location, supply_col, demand_col, begin_date, end_date, inter, ...)` - Supply gap timeline from budget time-series columns.
- `plots.supply_demand.plot_pumping_depth_vs_shortage(depth_to_gw, shortage, location_labels=None, ax=None, figsize=(8, 6), save_path=N, ...)` - Scatter plot correlating depth-to-GW with supply shortfall.
- `plots.supply_demand.plot_subregion_depth_vs_shortage(model, supply_type, factor=1.0, ax=None, figsize=(8, 6), save_path=None)` - Depth vs shortage for all subregions using model API.
- `plots.supply_demand.plot_supply_gap_timeline(dates, requirement, actual, label='Water Supply', ax=None, figsize=(12, 5), save_, ...)` - Stacked area: requirement on top, actual delivery below, gap in red.
- `plots.timeseries.plot_budget_timeseries(model, budget_type, location, begin_date=None, end_date=None, interval='1MON', st, ...)` - Plot budget components as a stacked area chart or multi-line chart.
- `plots.timeseries.plot_cumulative_gw_storage_change(model, subregions, begin_date=None, end_date=None, interval='1MON', fact_vl=1.0, ...)` - Line chart of cumulative groundwater storage change.
- `plots.timeseries.plot_gw_head_hydrographs(model, node_indices, layer=1, begin_date=None, end_date=None, interval='1MON', la, ...)` - Multi-line plot of groundwater head vs.
- `plots.timeseries.plot_land_use_area_timeseries(model, begin_date=None, end_date=None, lu_types=None, fact_area=1.0, title='Land, ...)` - Stacked area chart of land-use categories over time.
- `plots.timeseries.plot_stream_flow_hydrograph(model, stream_node_indices, begin_date=None, end_date=None, interval='1MON', fact, ...)` - Plot stream flow vs.
- `plots.timeseries.plot_stream_stage_hydrograph(model, stream_node_indices, begin_date=None, end_date=None, interval='1MON', fact, ...)` - Plot stream stage (water surface elevation) vs.
- `plots.timeseries.plot_zbudget_timeseries(model, zbudget_type, zone_id, columns, zone_extent, elements, layers, zone_ids, b, ...)` - Plot zone-budget components over time.
- `plots.trends.plot_drought_drawdown_rate(model, layer, begin_date, end_date, drought_start_idx=None, drought_end_idx=None, ...)` - Map of head decline rate during a drought window.
- `plots.trends.plot_head_trend_map(model, layer, begin_date, end_date, ax=None, figsize=(10, 8), save_path=None, clo, ...)` - Map of linear head trend (slope) at every node.
- `plots.trends.plot_recovery_lag_map(model, layer, begin_date, end_date, recovery_threshold=0.9, ax=None, figsize=(10, ...)` - Map of recovery time after heads reach their minimum.
- `plots.trends.plot_seasonal_amplitude_map(model, layer, begin_date, end_date, ax=None, figsize=(10, 8), save_path=None, clo, ...)` - Map of (max head - min head) at each node over the period.
- `plots.water_balance.plot_budget_butterfly(model, budget_type, location, begin_date, end_date, interval='1MON', fact_vl=2.29, ...)` - Butterfly chart from model budget time-series averages.
- `plots.water_balance.plot_budget_sankey(model, budget_type, location, begin_date, end_date, interval='1MON', fact_vl=2.29, ...)` - Sankey of the average water-year budget.
- `plots.water_balance.plot_butterfly_chart(names, values, title='Inflows vs Outflows', ax=None, figsize=(10, 8), save_path=N, ...)` - Mirrored horizontal bar chart: inflows left, outflows right.
- `plots.water_balance.plot_cumulative_departure(model, budget_type, location, begin_date, end_date, interval='1MON', inflow_cols=, ...)` - Running sum of (total inflow - total outflow) over time.
- `plots.water_balance.plot_water_balance_sankey(names, values, title='Water Balance', ax=None, figsize=(14, 8), save_path=None, c, ...)` - Sankey diagram of water balance components.

## Calibration (iwfm_io.pest)

- `pest.accretion_depletion(df, pairs, obs_type: 'Optional[str]' = None, scheme='standard') -> "'pd.DataFrame'"` - Stream gain between gauges: ``downstream - upstream``.
- `pest.apply_kriging_factors(factors, pp_values, log: 'bool' = False) -> "'pd.Series'"` - Interpolate pilot-point values to targets (the FAC2REAL role).
- `pest.apply_parameters(run_dir, actions: 'Sequence[ApplyAction]', log_path: 'str' =, ...) -> "'pd.DataFrame'"` - Apply all value files onto the model inputs (forward-run step).
- `pest.ApplyAction(reader: 'str', path: 'str', table: 'str', column: 'str', values_file: 'st, ...) -> None` - One declarative write-back: value file -> model-input table column.
- `pest.balance_pst_weights(pst_path, budgets: 'Dict[str, float]', residuals=None, **kwargs) -> "'WeightBalance'"` - Balance weights of a classic ``.pst`` control file via pyemu.
- `pest.balance_weights(obs_data, residuals, budgets: 'Dict[str, float]', split: 'str', ...) -> 'WeightBalance'` - Rescale observation weights so group phi hits per-category targets.
- `pest.budget_observations(source, budget: 'Optional[str]' = None, locations: 'Optional[, ...) -> "'pd.DataFrame'"` - Extract named budget-component observations.
- `pest.build_parameters(specs: 'Sequence[ParamSpec]', pargp_overrides: 'Optional[Dict]', ...) -> 'ParamBundle'` - Build PEST parameter artifacts from declarative specs.
- `pest.compute_kriging_factors(pilot_points, targets, variogram, max_points: 'int' = 12, sea, ...) -> "'pd.DataFrame'"` - Ordinary-kriging weights from pilot points to target locations.
- `pest.decode_obs_name(name, scheme='standard') -> 'ObsName'` - Decode one observation name into an :class:`ObsName`.
- `pest.decode_obs_names(names, scheme='standard') -> "'pd.DataFrame'"` - Decode many observation names into a DataFrame.
- `pest.diagnose_ies(results, par_data=None, scheme='standard', category_of: 'Opti, ...) -> 'IesDiagnostics'` - Distill a PESTPP-IES run into metrics, signals, and a summary.
- `pest.DiagThresholds(phiredstp: 'float' = 0.01, collapse_ratio: 'float' = 0.3, conflict_system, ...) -> None` - Cut-offs that turn metrics into boolean signals.
- `pest.encode_obs_name(obs_type, location, time=None, scheme='standard') -> 'str'` - Encode one observation name.
- `pest.encode_obs_names(obs_types, locations, times=None, scheme='standard') -> "'pd.Series'"` - Encode many observation names (vectorized-friendly).
- `pest.ExpVariogram(a: 'float', nugget: 'float' = 0.0, anisotropy: 'float' = 1.0, bearing: 'f, ...) -> None` - Exponential: ``?
- `pest.GauVariogram(a: 'float', nugget: 'float' = 0.0, anisotropy: 'float' = 1.0, bearing: 'f, ...) -> None` - Gaussian: ``?
- `pest.get_scheme(scheme: 'Union[str, NameScheme]') -> 'NameScheme'` - Resolve a scheme by registry name, or pass an instance through.
- `pest.GroupSequenceScheme(type_len: 'int' = 3, date_format: 'str' = '%y%m%d')` - Legacy-style ``{type}{group:02d}{seq:04d}_{date}`` names.
  - `.decode(name: 'str') -> 'ObsName'` - (undocumented)
  - `.encode(parts: 'ObsName') -> 'str'` - (undocumented)
  - `.location(group, seq, group_digits: 'int' = 2, seq_digits: 'int' = 4) -> 'str'` - Build the location token from (group, seq).
- `pest.head_changes(df, kind: 'str', month: 'int' = 3, from_month: 'int' = 3, to_, ...) -> "'pd.DataFrame'"` - Temporal head-change series from a long-form head record.
- `pest.ies_stats(results, observed=None, iterations=None, by=None) -> "'pd.DataFrame'"` - Per-``(iteration, realization, group)`` statistics for an IES run.
- `pest.IesDiagnostics(case: 'str', state: 'dict' = <factory>) -> None` - Result of :func:`diagnose_ies`.
  - `.signals` - All boolean signals from all sections, flattened.
  - `.summary() -> 'str'` - (undocumented)
  - `.to_json(path=None) -> 'str'` - (undocumented)
- `pest.IesResults(directory: 'Path', case: 'str', par_files: 'Dict[int, Path]' = <factory>, ...) -> None` - Handle to a discovered set of PESTPP-IES output files.
  - `.base_rei(iteration=None) -> "'pd.DataFrame'"` - Base-realization residuals (``<case>.<iter>.base.rei``).
  - `.best_realization(iteration=None, kind: 'str' = 'composite') -> 'str'` - Name of the minimum-phi realization in an iteration (default last).
  - `.describe() -> 'dict'` - JSON-serializable inventory + phi summary (agent-friendly).
  - `.iterations` - Sorted iterations for which any ensemble file exists.
  - `.obs(iteration=None) -> "'pd.DataFrame'"` - Simulated-observation ensemble for one iteration (default: last).
  - `.obs_all() -> "'pd.DataFrame'"` - All observation ensembles, ``(iteration, real_name)`` MultiIndex.
  - `.obs_plus_noise() -> "'Optional[pd.DataFrame]'"` - Observation-plus-noise realizations, or None if not written.
  - `.par(iteration=None) -> "'pd.DataFrame'"` - Parameter ensemble for one iteration (default: last available).
  - `.par_all() -> "'pd.DataFrame'"` - All parameter ensembles, ``(iteration, real_name)`` MultiIndex.
  - `.pdc() -> "'Optional[pd.DataFrame]'"` - Prior-data-conflict table (``<case>.pdc.csv``), or None.
  - `.phi(kind: 'str' = 'composite') -> "'pd.DataFrame'"` - Tidy phi: columns ``iteration, real_name, phi``.
  - `.phi_groups() -> "'pd.DataFrame'"` - Tidy per-group phi: columns ``iteration, real_name, group, phi``.
  - `.phi_summary(kind: 'str' = 'composite') -> "'pd.DataFrame'"` - Per-iteration phi summary (total_runs, mean, std, min, max).
- `pest.load_ies_ensembles(path) -> 'IesResults'` - Discover PESTPP-IES output files and return an :class:`IesResults`.
- `pest.long_term_stats(df, stat: 'str' = 'mean', min_n: 'int' = 1, obs_type: 'Option, ...) -> "'pd.DataFrame'"` - One whole-record statistic per site (dateless observations).
- `pest.match_sim_to_obs(sim, obs, method: 'str' = 'linear', max_gap=None, extrapolate=None) -> "'pd.DataFrame'"` - Interpolate simulated series to observation timestamps.
- `pest.METRICS` - list constant: ['n', 'mean_res', 'med_res', 'mean_abs_res', 'max_abs_res', 'rmse', 'r2', 'nse', 'kge']
- `pest.NameScheme()` - Base class for observation-name schemes.
  - `.decode(name: 'str') -> 'ObsName'` - (undocumented)
  - `.decode_many(names: 'Iterable[str]') -> "'pd.DataFrame'"` - (undocumented)
  - `.encode(parts: 'ObsName') -> 'str'` - (undocumented)
  - `.encode_many(parts: 'Iterable[ObsName]') -> "'pd.Series'"` - (undocumented)
- `pest.ObsFileSpec(names: "'list'", layout: 'str' = 'fixed', value_format: 'str' = '%16.8E', ...) -> None` - Spec for one model-output file and its instruction file.
  - `.from_frame(df, name_col: 'str' = 'obsnme', **kwargs) -> "'ObsFileSpec'"` - Build a spec from any frame with an observation-name column.
  - `.obs_data(values=None, weight=1.0, group=None) -> "'pd.DataFrame'"` - Starter observation-data rows (PEST++ v2 external layout).
  - `.read_output(path) -> "'pd.Series'"` - Parse an output file using this spec's semantics (the same columns/markers PEST would use).
  - `.verify_round_trip(values=None) -> 'None'` - Assert write -> parse reproduces the values (setup-time check).
  - `.write_ins(path) -> 'None'` - Write the PEST instruction file.
  - `.write_output(values, path) -> 'None'` - Write the model-output file (the forward-run fast path).
- `pest.ObsName(obs_type: 'str', location: 'str', time: 'Optional[pd.Timestamp]' = None) -> None` - Decoded parts of a structured observation name.
- `pest.ParamBundle(par_data: "'pd.DataFrame'", pargp_data: "'pd.DataFrame'", tpl_texts: 'Dic, ...) -> None` - Everything :func:`build_parameters` produced.
  - `.verify() -> 'None'` - Assert: filling each template with parval1 reproduces the initial value file exactly.
  - `.write(directory) -> 'None'` - Write all templates and initial value files into *directory*.
- `pest.ParamSpec(name: 'str', values_file: 'str', keys: "'pd.DataFrame'", zone_col: 'Optio, ...) -> None` - Declare one parameterized quantity and its grouping.
  - `.key_cols` - (undocumented)
  - `.parameter_names() -> "'pd.Series'"` - Per-row parameter name (rows of one zone share a name).
- `pest.parrep_v2(pst_path, values, noptmax: 'int' = 0) -> 'None'` - Put parameter values into a PEST++ v2 control file, in place.
- `pest.Period(name: 'str', months: "'tuple'", rep: 'str') -> None` - One averaging period of the typical-hydrograph year.
  - `.rep_month_day() -> "'tuple'"` - (undocumented)
- `pest.PERIODS_QUARTERLY` - tuple constant: (Period(name='winter', months=(12, 1, 2), rep='01/15'), Period(name='spring', months=(3, 4, 5), r...
- `pest.PERIODS_SPRING_FALL` - tuple constant: (Period(name='spring', months=(1, 2, 3, 4), rep='03/01'), Period(name='fall', months=(8, 9, 10, 1...
- `pest.pest_setup_from_model(model_dir, obs, dest_dir, case: 'str' = 'iwfm_cal', paramete, ...) -> 'QuickstartSetup'` - Build a runnable pestpp-ies template directory from a model folder.
- `pest.PestSetup(case: 'str' = 'case', command: 'Optional[str]' = None, python: 'Optional[str]' = None)` - Builder for a runnable PEST++ v2 template directory.
  - `.add_observations(obs_data, spec: 'ObsFileSpec', output_file: 'str', ins_file: 'Op, ...) -> "'PestSetup'"` - Add observations: the v2 obs-data rows plus the paired output/instruction spec.
  - `.add_parameters(bundle: 'ParamBundle', actions: 'Sequence[ApplyAction]' = ()) -> "'PestSetup'"` - Add a parameter bundle and the apply actions that consume its value files in the forward run.
  - `.add_run_step(label: 'str', command: 'str') -> "'PestSetup'"` - Append a forward-run step (model run, extraction, ...).
  - `.write(dest_dir) -> 'Path'` - Write the complete template directory; returns its path.
- `pest.place_pilot_points_grid(model_or_nodes, spacing: 'float', zones=None, buffer: 'Option, ...) -> "'pd.DataFrame'"` - Regular pilot-point grid clipped to the model's node cloud.
- `pest.QuickstartSetup(template: 'Path', case: 'str', paired: "'pd.DataFrame'", par_data: "'pd.D, ...) -> None` - Result of :func:`pest_setup_from_model`.
  - `.summary() -> 'dict'` - (undocumented)
- `pest.RatioChain(_params: "'dict'" = <factory>, _derived: "'dict'" = <factory>) -> None` - Anchor + bounded-ratio parameter chains with ordering guarantees.
  - `.add_derived(name: 'str', expr: 'str') -> "'RatioChain'"` - Declare a derived quantity as an expression over previously declared parameters and derived names.
  - `.add_parameter(name: 'str', bounds: 'Tuple[float, float]', initial: 'Optional[, ...) -> "'RatioChain'"` - Declare a free (PEST-adjustable) parameter.
  - `.assert_ordering(constraints: 'Sequence[Tuple[str, str, str]]', include_midpoint: 'bool', ...) -> 'None'` - Check ordering constraints at every bound corner.
  - `.derived` - (undocumented)
  - `.evaluate(values: 'Dict[str, float]') -> "'dict'"` - PEST parameter values in -> all derived quantities out.
  - `.par_data(name_format: 'str' = '{name}') -> "'pd.DataFrame'"` - PEST++ v2 parameter-data rows for the free parameters.
  - `.parameters` - (undocumented)
- `pest.read_gw_overwrite(path) -> "'pd.DataFrame'"` - Read an IWFM groundwater parameter overwrite file.
- `pest.read_rei(path) -> "'pd.DataFrame'"` - Read a PEST residual file (``.rei`` / ``.res``).
- `pest.read_smp(path, date_format: 'Optional[str]' = None, fixed_width: 'bool, ...) -> "'pd.DataFrame'"` - Read a PEST SMP bore-sample file.
- `pest.read_t2p_pilot_points(path) -> "'pd.DataFrame'"` - Read a Texture2Par pilot-point locations file (``BEGIN PP_LOCS``).
- `pest.register_scheme(name: 'str', scheme: 'NameScheme') -> 'None'` - Register a (project-specific) naming scheme under ``name``.
- `pest.rei_stats(rei, by: 'Union[str, list]' = 'group', weighted_only: 'bool', ...) -> "'pd.DataFrame'"` - Statistics from a PEST residual file (``.rei``/``.res``).
- `pest.resample_month_end(df, how: 'str' = 'mean', iwfm_convention: 'bool' = True) -> "'pd.DataFrame'"` - Aggregate a long-form series to month-end timestamps.
- `pest.residual_stats(df, by=None, observed: 'str' = 'observed', simulated: 'str' =, ...) -> "'pd.DataFrame'"` - Goodness-of-fit statistics on a long-form observed/simulated frame.
- `pest.run_finals(results, template_dir, dest_dir, iteration=None, realization: 'str' = ', ...) -> 'Path'` - Stage a rerun of one ensemble realization (the "finals" run).
- `pest.setup_agents(template_dir, n: 'int', dest_root=None, pst: 'Optional[str]' =, ...) -> "'list[Path]'"` - Create *n* PEST++ agent directories from a template.
- `pest.slugify_label(label) -> 'str'` - Make a budget location/component label safe for PEST names.
- `pest.SphVariogram(a: 'float', nugget: 'float' = 0.0, anisotropy: 'float' = 1.0, bearing: 'f, ...) -> None` - Spherical: reaches the sill exactly at ``h = a``.
- `pest.StandardScheme(sep: 'str' = '_', date_format: 'str' = '%Y%m%d')` - Default ``{type}{sep}{location}[{sep}{date}]`` scheme, lowercase.
  - `.decode(name: 'str') -> 'ObsName'` - (undocumented)
  - `.decode_many(names: 'Iterable[str]') -> "'pd.DataFrame'"` - (undocumented)
  - `.encode(parts: 'ObsName') -> 'str'` - (undocumented)
- `pest.typical_hydrographs(df, clusters, periods: 'Optional[Sequence]' = None, start, ...) -> 'TypicalHydrographs'` - Compute cluster-average typical hydrographs (CalcTypHyd).
- `pest.TypicalHydrographs(series: "'pd.DataFrame'", well_means: "'pd.Series'", wells: "'pd.DataFrame'") -> None` - Result of :func:`typical_hydrographs`.
  - `.summary() -> 'dict'` - (undocumented)
- `pest.validate_obs_names(names, max_len: 'int' = 200) -> 'list'` - Check observation names for PEST-compatibility problems.
- `pest.vertical_head_difference(df, pairs, obs_type: 'Optional[str]' = None, scheme='standard') -> "'pd.DataFrame'"` - Head difference between paired completions: ``shallow - deep``.
- `pest.WeightBalance(obs_data: "'pd.DataFrame'", report: "'pd.DataFrame'") -> None` - Result of :func:`balance_weights`.
- `pest.write_forward_run(path, steps: 'Sequence', python: 'Optional[str]' = None) -> 'Path'` - Generate the fail-fast forward-run script PEST++ invokes.
- `pest.write_gw_overwrite(path, df, factors=None, time_unit: 'str' = '1MON') -> 'None'` - Write an IWFM groundwater parameter overwrite file.
- `pest.write_manager_script(directory, pst: 'Optional[str]' = None, exe: 'str' = 'pestpp-ies', port, ...) -> 'Path'` - Write the manager start script next to the control file.
- `pest.write_smp(df, path, date_format: 'str' = 'dd/mm/yyyy', max_site_len: 'Optional[in, ...) -> 'None'` - Write a PEST SMP bore-sample file.
- `pest.write_t2p_pilot_points(path, df) -> 'None'` - Write a Texture2Par ``BEGIN PP_LOCS`` pilot-point file.

## DLL wrapper (iwfm_io.dll - Windows x64, optional)

- `dll.BudgetTypeID()` - Budget type identifiers.
- `dll.close_log_file(dll)` - Close the DLL log file.
- `dll.DataUnitTypeID()` - Data unit type identifiers.
- `dll.download_dll(version='2025.0.1747', dest_dir=None, force=False, show_progress=True)` - Download an official IWFM DLL build to the user DLL directory.
- `dll.FlowDestTypeID()` - Flow destination type identifiers.
- `dll.get_kernel_version(dll)` - Return the IWFM kernel version string.
- `dll.get_last_message(dll)` - Return the last DLL error/status message.
- `dll.get_n_intervals(dll, begin_date, end_date, interval)` - Return the number of time intervals between two dates.
- `dll.get_version(dll)` - Return the IWFM application version string.
- `dll.increment_time(dll, date_time, interval, count=1)` - Increment a date-time string by *count* intervals.
- `dll.is_time_greater_than(dll, dt1, dt2)` - Return True if *dt1* is later than *dt2*.
- `dll.IWFMBudget(hdf_file, dll_version=None, dll_path=None)` - Read an IWFM budget HDF5/binary file.
  - `.are_n_columns_same()` - Return True if all locations have the same number of columns.
  - `.get_column_headers(location, length_unit='FT', area_unit='SQ FT', volume_unit='CU FT')` - Return column header strings for a location.
  - `.get_location_names()` - Return a list of budget location names.
  - `.get_n_columns(location)` - Return the number of data columns for a location.
  - `.get_time_specs()` - Return dict with 'dates' list, 'interval' string.
  - `.get_title_lines(location, fact_area=1.0, length_unit='FT', area_unit='SQ FT', volume_unit='CU FT', ...)` - Return title lines for a location.
  - `.get_values(location, columns, begin_date, end_date, interval, fact_lt=1.0, fact_ar=1.0, fact, ...)` - Read budget values for selected columns at a location.
  - `.get_values_for_column(location, column, interval, begin_date, end_date, fact_lt=1.0, fact_ar=1.0, fact_, ...)` - Read a single column from an HDF budget file.
  - `.n_locations` - Number of budget locations.
  - `.n_timesteps` - Number of time steps in the budget file.
  - `.n_title_lines` - Number of persistent title lines.
  - `.title_length` - Maximum title line length.
- `dll.IWFMError(message, status_code=-1)` - Exception raised when an IWFM DLL function returns a non-zero status.
- `dll.IWFMModel(preprocessor_file, simulation_file='', wsa_file='', is_routed_streams=True, is_fo, ...)` - Python wrapper around the IWFM simulation model DLL.
  - `.advance_state()` - Advance the model state in time.
  - `.advance_time()` - Advance the simulation clock by one time step.
  - `.budget_df(budget_type, location, begin_date=None, end_date=None, interval=None, columns=Non, ...)` - Return DataFrame(DatetimeIndex) of budget time series.
  - `.bypasses_df()` - Return DataFrame: bypass_id, export_node, dest_type, dest, rec_loss, nonrec_loss.
  - `.close()` - Kill the model and free resources.
  - `.compute_future_water_demands(end_date)` - Compute future water demands up to end_date.
  - `.current_date_time` - Current simulation date-time string.
  - `.delete_inquiry_data_file(dll, sim_filename)` - Delete the inquiry data file (``IW_ModelData_ForInquiry.bin``) of a simulation.
  - `.describe()` - Return a JSON-serializable summary of the model.
  - `.diversions_df()` - Return DataFrame: diversion_id, export_node, n_elements, elements(list).
  - `.elements_df()` - Return GeoDataFrame of elements: element_id, node1-4, subregion, geometry(Polygon).
  - `.get_actual_diversions(div_indices, factor=1.0)` - (undocumented)
  - `.get_aquifer_bottom_elevation()` - (undocumented)
  - `.get_aquifer_horizontal_k()` - (undocumented)
  - `.get_aquifer_parameters()` - Return all aquifer parameters as a dict of arrays.
  - `.get_aquifer_specific_storage()` - (undocumented)
  - `.get_aquifer_specific_yield()` - (undocumented)
  - `.get_aquifer_top_elevation()` - Shape (n_nodes, n_layers).
  - `.get_aquifer_vertical_k()` - (undocumented)
  - `.get_aquitard_vertical_k()` - (undocumented)
  - `.get_budget_annual(budget_type, location, begin_date, end_date, fact_vl=1.0, lu_type=0, swshed_comp=0)` - Return annual flows (water year).
  - `.get_budget_annual_cum_gw_storage_change(subregion, begin_date, end_date, fact_vl=1.0)` - (undocumented)
  - `.get_budget_annual_cum_gw_storage_change_v2(subregion, begin_date, end_date, fact_vl=1.0, calendar_year=False)` - (undocumented)
  - `.get_budget_annual_v2(budget_type, location, begin_date, end_date, fact_vl=1.0, lu_type=0, swshed_comp=, ...)` - Return annual flows with calendar/water year option.
  - `.get_budget_column_titles(budget_type, location, length_unit='FT', area_unit='SQ FT', volume_unit='CU FT')` - (undocumented)
  - `.get_budget_cum_gw_storage_change(subregion, begin_date, end_date, interval, fact_vl=1.0)` - (undocumented)
  - `.get_budget_list()` - Return list of dicts with 'name', 'budget_type', 'location_type'.
  - `.get_budget_monthly_average(budget_type, location, begin_date, end_date, fact_vl=1.0, lu_type=0, swshed_comp=0)` - Return monthly average flows.
  - `.get_budget_n_columns(budget_type, location)` - (undocumented)
  - `.get_budget_timeseries(budget_type, location, columns, begin_date, end_date, interval, fact_lt=1.0, fact, ...)` - Read budget time-series data for selected columns at a location.
  - `.get_bypass_export_dest_data(bypass_indices)` - (undocumented)
  - `.get_bypass_export_nodes(bypass_indices)` - (undocumented)
  - `.get_bypass_ids()` - (undocumented)
  - `.get_bypass_non_recoverable_loss_factor(bypass)` - (undocumented)
  - `.get_bypass_outflows(factor=1.0)` - (undocumented)
  - `.get_bypass_recoverable_loss_factor(bypass)` - (undocumented)
  - `.get_diversion_elements(div)` - (undocumented)
  - `.get_diversion_export_nodes(div_indices)` - (undocumented)
  - `.get_diversion_ids()` - (undocumented)
  - `.get_diversion_n_elements(div)` - (undocumented)
  - `.get_diversion_n_recharge_zone_elements(div)` - (undocumented)
  - `.get_diversion_recharge_zone_elements(div)` - (undocumented)
  - `.get_elem_pump_ids()` - (undocumented)
  - `.get_element_config(element)` - Return vertex node indices for an element (4 values; 0 = triangle).
  - `.get_element_ids()` - (undocumented)
  - `.get_element_subregions()` - (undocumented)
  - `.get_elements_in_lake(lake)` - (undocumented)
  - `.get_future_water_demand_for_diversion(div, date, factor=1.0)` - (undocumented)
  - `.get_ground_surface_elevation()` - (undocumented)
  - `.get_gw_heads_all(previous=False, factor=1.0)` - Current timestep heads, shape (n_nodes, n_layers).
  - `.get_gw_heads_for_layer(layer, begin_date, end_date, factor=1.0)` - Return (dates, heads) for a layer over a date range.
  - `.get_gw_heads_initial()` - Shape (n_nodes, n_layers).
  - `.get_hydrograph(hyd_type, index, layer, begin_date, end_date, interval, fact_lt=1.0, fact_vl=1.0)` - Return (dates, values) for a hydrograph.
  - `.get_hydrograph_coordinates(location_type)` - (undocumented)
  - `.get_hydrograph_ids(location_type)` - (undocumented)
  - `.get_hydrograph_type_list()` - Return list of dicts with 'name' and 'location_type'.
  - `.get_lake_ids()` - (undocumented)
  - `.get_land_use_areas(begin_date, end_date, lu_type, lu, n_elements=None, fact_area=1.0)` - Return land use areas, shape (n_elements, n_times).
  - `.get_location_ids(location_type)` - (undocumented)
  - `.get_n_ag_crops()` - (undocumented)
  - `.get_n_budgets()` - (undocumented)
  - `.get_n_elements_in_lake(lake)` - (undocumented)
  - `.get_n_hydrograph_types()` - (undocumented)
  - `.get_n_hydrographs(location_type)` - (undocumented)
  - `.get_n_locations(location_type)` - (undocumented)
  - `.get_n_parametric_elements(grid_id)` - (undocumented)
  - `.get_n_parametric_grids()` - (undocumented)
  - `.get_n_parametric_nodes(grid_id)` - (undocumented)
  - `.get_n_rating_table_points(stream_node)` - (undocumented)
  - `.get_n_stream_inflows()` - (undocumented)
  - `.get_n_tile_drain_nodes()` - (undocumented)
  - `.get_n_zbudgets()` - (undocumented)
  - `.get_names(location_type)` - (undocumented)
  - `.get_node_coordinates()` - Return (x, y) arrays of node coordinates.
  - `.get_node_ids()` - (undocumented)
  - `.get_output_intervals()` - Return list of available output interval strings.
  - `.get_parametric_aquifer_parameters(grid_id)` - (undocumented)
  - `.get_parametric_element_config(grid_id, elem_id)` - (undocumented)
  - `.get_parametric_node_xy(grid_id)` - (undocumented)
  - `.get_reach_downstream_nodes()` - (undocumented)
  - `.get_reach_gw_nodes(reach)` - (undocumented)
  - `.get_reach_ids()` - (undocumented)
  - `.get_reach_n_nodes(reach)` - (undocumented)
  - `.get_reach_n_upstream_reaches(reach)` - (undocumented)
  - `.get_reach_outflow_dest_types()` - (undocumented)
  - `.get_reach_outflow_destinations()` - (undocumented)
  - `.get_reach_stream_nodes(reach)` - (undocumented)
  - `.get_reach_upstream_nodes()` - (undocumented)
  - `.get_reach_upstream_reaches(reach)` - (undocumented)
  - `.get_reaches_for_stream_nodes(node_indices)` - (undocumented)
  - `.get_required_diversions(div_indices, factor=1.0)` - (undocumented)
  - `.get_stratigraphy_at_xy(x, y)` - Return stratigraphy at a coordinate.
  - `.get_stream_bottom_elevations()` - (undocumented)
  - `.get_stream_bypass_inflows(factor=1.0)` - (undocumented)
  - `.get_stream_evaporation(factor=1.0)` - (undocumented)
  - `.get_stream_flow(node, factor=1.0)` - (undocumented)
  - `.get_stream_flows(factor=1.0)` - (undocumented)
  - `.get_stream_gain_from_gw(factor=1.0)` - (undocumented)
  - `.get_stream_gain_from_lakes(factor=1.0)` - (undocumented)
  - `.get_stream_inflow_ids()` - (undocumented)
  - `.get_stream_inflow_nodes()` - (undocumented)
  - `.get_stream_inflows_at(inflow_indices, factor=1.0)` - (undocumented)
  - `.get_stream_n_upstream_nodes(node)` - (undocumented)
  - `.get_stream_net_bypass_inflows(factor=1.0)` - (undocumented)
  - `.get_stream_net_inflows_exc_divs_inflows(factor=1.0)` - (undocumented)
  - `.get_stream_net_inflows_exc_divs_inflows_gw(factor=1.0)` - (undocumented)
  - `.get_stream_node_ids()` - (undocumented)
  - `.get_stream_pond_drains(factor=1.0)` - (undocumented)
  - `.get_stream_rainfall_runoff(factor=1.0)` - (undocumented)
  - `.get_stream_rating_table(stream_node)` - (undocumented)
  - `.get_stream_return_flows(factor=1.0)` - (undocumented)
  - `.get_stream_riparian_et(factor=1.0)` - (undocumented)
  - `.get_stream_stages(factor=1.0)` - (undocumented)
  - `.get_stream_tile_drains(factor=1.0)` - (undocumented)
  - `.get_stream_tributary_inflows(factor=1.0)` - (undocumented)
  - `.get_stream_upstream_nodes(node)` - (undocumented)
  - `.get_stream_wsa_flows(factor=1.0)` - (undocumented)
  - `.get_subregion_ag_pumping_avg_depth_to_gw()` - (undocumented)
  - `.get_subregion_ids()` - (undocumented)
  - `.get_subregion_name(subregion)` - (undocumented)
  - `.get_subsidence_all(factor=1.0)` - Current timestep subsidence, shape (n_nodes, n_layers).
  - `.get_supply_purpose(supply_type, supplies)` - (undocumented)
  - `.get_supply_requirement_ag(location_type, locations, factor=1.0)` - (undocumented)
  - `.get_supply_requirement_urban(location_type, locations, factor=1.0)` - (undocumented)
  - `.get_supply_short_at_origin_ag(supply_type, supplies, factor=1.0)` - (undocumented)
  - `.get_supply_short_at_origin_urban(supply_type, supplies, factor=1.0)` - (undocumented)
  - `.get_tile_drain_ids()` - (undocumented)
  - `.get_tile_drain_nodes()` - (undocumented)
  - `.get_time_specs()` - Return dict with 'dates', 'interval' (cached; the clock does not move in inquiry mode, and simulate/advance calls clear...
  - `.get_well_coordinates()` - (undocumented)
  - `.get_well_elements(well)` - (undocumented)
  - `.get_well_ids()` - (undocumented)
  - `.get_well_n_elements(well)` - (undocumented)
  - `.get_well_perforation_top_bottom()` - (undocumented)
  - `.get_zbudget_column_titles(zbudget_type, zone_id, zone_extent, elements, layers, zone_ids, area_unit='SQ FT', ...)` - (undocumented)
  - `.get_zbudget_list()` - (undocumented)
  - `.get_zbudget_n_columns(zbudget_type, zone_id, zone_extent, elements, layers, zone_ids)` - (undocumented)
  - `.get_zbudget_timeseries(zbudget_type, zone_id, columns, zone_extent, elements, layers, zone_ids, begin_da, ...)` - Read Z-Budget time-series data for a zone.
  - `.get_zone_ag_pumping_avg_depth_to_gw(elements, zones, n_zones)` - (undocumented)
  - `.heads_df(layer, begin_date=None, end_date=None, day_index=False)` - Return DataFrame(DatetimeIndex) with one column per node.
  - `.hydrograph_df(hyd_type, index, layer, begin_date=None, end_date=None, interval=None, fact_lt=1., ...)` - Return DataFrame(DatetimeIndex) with a single 'value' column.
  - `.is_end_of_simulation` - True if simulation has reached its end.
  - `.is_stream_upstream_node(node1, node2)` - (undocumented)
  - `.lakes_df()` - Return DataFrame: lake_id, n_elements, elements(list).
  - `.n_bypasses` - (undocumented)
  - `.n_diversions` - (undocumented)
  - `.n_elem_pumps` - (undocumented)
  - `.n_elements` - (undocumented)
  - `.n_lakes` - (undocumented)
  - `.n_layers` - (undocumented)
  - `.n_nodes` - (undocumented)
  - `.n_reaches` - (undocumented)
  - `.n_stream_nodes` - (undocumented)
  - `.n_subregions` - (undocumented)
  - `.n_timesteps` - Total number of simulation time steps.
  - `.n_wells` - (undocumented)
  - `.nodes_df()` - Return GeoDataFrame of nodes: node_id, x, y, geometry(Point).
  - `.print_results()` - Write simulation results for the current time step.
  - `.reaches_df()` - Return DataFrame: reach_id, n_nodes, outflow_dest, name.
  - `.read_timeseries_data()` - Read time-series input data for the current time step.
  - `.read_timeseries_data_overwrite(region_lu_areas, diversions_idx, diversions_val, inflows_idx, inflows_val, bypass, ...)` - Read time-series data with user-supplied overrides.
  - `.restore_pumping_to_read_values()` - Restore pumping to file-specified values.
  - `.set_supply_adjustment_max_iters(n)` - Set maximum iterations for supply adjustment.
  - `.set_supply_adjustment_tolerance(tol)` - Set convergence tolerance for supply adjustment.
  - `.simulate()` - Run the entire simulation.
  - `.simulate_interval(interval)` - Simulate for a specified interval (e.g.
  - `.simulate_timestep()` - Advance one time step.
  - `.stratigraphy_df()` - Return DataFrame: node_id, elevation, aquitard_1, aquifer_1, ...
  - `.stream_flows_df(factor=1.0)` - Return DataFrame of current-timestep stream flow components.
  - `.stream_nodes_df()` - Return GeoDataFrame: stream_node_id, reach_id, gw_node_id, geometry(Point).
  - `.stream_rating_tables_df()` - Return DataFrame: stream_node_id, bottom_elev, stage, flow.
  - `.subregions_df()` - Return DataFrame: subregion_id, name.
  - `.subsidence_df(factor=1.0)` - Return DataFrame of current-timestep subsidence: node_id, layer_1, ..., layer_N.
  - `.supply_demand_df(location_type, locations, factor=1.0)` - Return DataFrame: location_id, ag_requirement, urban_requirement, ag_shortage, urban_shortage.
  - `.switch_to(dll, model_id)` - Make *model_id* the DLL's active model.
  - `.tile_drains_df()` - Return GeoDataFrame: id, node, x, y, geometry(Point).
  - `.turn_supply_adjustment(diversion=True, pumping=True)` - Turn supply adjustment on/off.
  - `.wells_df()` - Return GeoDataFrame: well_id, x, y, perf_top, perf_bot, geometry(Point).
- `dll.IWFMZBudget(hdf_file, dll_version=None, dll_path=None)` - Read an IWFM zone-budget HDF5 file.
  - `.generate_zone_list(zone_extent, elements, layers, zones, zone_names_ids=None, zone_names=None)` - Generate zone list from arrays.
  - `.generate_zone_list_from_file(zone_def_file)` - Load zone definitions from an ASCII file.
  - `.get_column_headers_for_zone(zone, columns_list=None, area_unit='SQ FT', volume_unit='CU FT', max_columns=500)` - Return column headers diversified for a specific zone.
  - `.get_column_headers_general(area_unit='SQ FT', volume_unit='CU FT', max_columns=200)` - Return general column headers (lumped inter-zone flows).
  - `.get_time_specs()` - Return dict with 'dates' list and 'interval' string.
  - `.get_title_lines(zone, fact_ar=1.0, area_unit='SQ FT', volume_unit='CU FT')` - Return title lines for a zone.
  - `.get_values_for_zone(zone, columns, begin_date, end_date, interval, fact_ar=1.0, fact_vl=1.0)` - Read Z-Budget data for a single zone.
  - `.get_values_for_zones_interval(zones, columns_per_zone, begin_date, interval, fact_ar=1.0, fact_vl=1.0)` - Read Z-Budget data for multiple zones for a single time interval.
  - `.get_zone_list()` - Return array of zone IDs.
  - `.get_zone_names()` - Return list of zone names.
  - `.n_timesteps` - Number of time steps.
  - `.n_title_lines` - Number of title lines.
  - `.n_zones` - Number of zones (excluding undefined zone).
- `dll.LandUseTypeID()` - Land use type identifiers (v2 - most complete).
- `dll.list_dll_versions()` - Return installed DLL version strings, sorted alphabetically.
- `dll.load_all_type_ids(dll)` - Populate all enum classes from the DLL.
- `dll.load_dll(version=None, dll_path=None, download=True)` - Load the IWFM DLL and register all function signatures.
- `dll.LocationTypeID()` - Location type identifiers (v1 - includes Diversion and Bypass).
- `dll.log_last_message(dll)` - Write the last message to the log file.
- `dll.set_log_file(dll, path)` - Set the DLL log file path.
- `dll.SupplyTypeID()` - Supply type identifiers.
- `dll.ZBudgetTypeID()` - Zone-budget type identifiers.
- `dll.ZoneExtentID()` - Zone extent identifiers.

## Low-level parsing primitives & data models

- `ConversionFactor(value: 'float' = 1.0, keyword: 'str' = '', unit_label: 'str' = '') -> None` - A conversion factor with its keyword and optional unit label.
- `FileHeader(version: 'str | None' = None, comment_lines: 'list[str]' = <factory>) -> None` - Metadata from the top of an IWFM file.
- `IWFMFileReader(path: 'str | Path', strict: 'bool | None' = None) -> 'None'` - Sequential reader for IWFM text files.
  - `.check_version(header: 'FileHeader', supported, *, known=(), what: 'str' = 'file') -> 'str | None'` - Gate a reader on the file's ``#version`` header.
  - `.data_eof` - True when no data line remains (only comments, or nothing).
  - `.degrade(msg: 'str', lineno: 'int | None' = None) -> 'None'` - Report a recoverable problem.
  - `.degrade_unknown_keyword(line: 'str', block: 'str', *, expected: 'tuple[str, ...] | set[str]' = ()) -> 'bool'` - Report a keyed line whose keyword a keyword-driven block does not model.
  - `.drain_comments() -> 'list[str]'` - Return and clear accumulated comment lines.
  - `.eof` - True when all lines have been consumed.
  - `.error(msg: 'str', lineno: 'int | None' = None) -> 'IWFMParseError'` - Build an :class:`IWFMParseError` carrying file, line and section.
  - `.from_lines(lines: 'list[str]', *, path: 'str | Path | None' = None, line, ...) -> 'IWFMFileReader'` - Build a reader over raw *lines* (comments included) instead of a file on disk.
  - `.lineno` - 1-based file line number of the most recently consumed line (:attr:`lineno0` before any line was read).
  - `.n_lines` - Number of lines held by this reader.
  - `.next_data_line() -> 'str'` - Return the next non-comment line, accumulating skipped comments.
  - `.next_line() -> 'str'` - Return the next raw line (comment or data) and advance.
  - `.peek_data_line() -> 'str | None'` - Peek at the next non-comment line without consuming it.
  - `.peek_keyword() -> 'str'` - Uppercased first word of the next data line's ``/ keyword`` part, without consuming it (``""`` for a keyword-less line...
  - `.read_data_table(n_rows: 'int', n_cols: 'int | None' = None, what: 'str' = 't, ...) -> 'list[list[str]]'` - Read *n_rows* of whitespace-delimited data.
  - `.read_dss_pathnames(spec: 'TimeSeriesSpec') -> 'list[tuple[int, str]]'` - Read DSS pathname assignments (col_id, pathname) pairs.
  - `.read_floats(n: 'int', what: 'str' = 'values') -> 'list[float]'` - Read one data line holding *n* numbers.
  - `.read_header() -> 'FileHeader'` - Read the file header: optional version line + leading comments.
  - `.read_ints(n: 'int', what: 'str' = 'values') -> 'list[int]'` - Read one data line holding *n* integers.
  - `.read_keyed_float() -> 'tuple[float, str]'` - Read a keyed float value.
  - `.read_keyed_int() -> 'tuple[int, str]'` - Read a keyed integer value.
  - `.read_keyed_path(base_dir: 'str | Path | None' = None) -> 'tuple[str | None, str]'` - Read a keyed file path, resolving relative to *base_dir*.
  - `.read_keyed_value() -> 'tuple[str, str]'` - Read a ``VALUE / KEYWORD`` line.
  - `.read_row(n_cols: 'int', what: 'str' = 'row', *, min_cols: 'int | None' = None) -> 'list[str]'` - Read one data line as tokens, requiring at least *min_cols* (default *n_cols*) of them.
  - `.read_timeseries_spec() -> 'TimeSeriesSpec'` - Read a 5-parameter time-series header block.
  - `.read_ts_rows(n_columns: 'int', col_names: 'list[str] | None' = None, *, what, ...) -> 'pd.DataFrame'` - Read ``DATE v1 ..
  - `.section(name: 'str')` - Name the section being read, for error messages.
  - `.section_name` - The current section context (nested names joined by ``" > "``).
  - `.skip_to_end() -> 'list[str]'` - Consume all remaining lines and return them.
  - `.tail_cursor() -> 'IWFMFileReader'` - Consume the rest of the file into a new :class:`IWFMFileReader` (see :meth:`from_lines`) that reports this file's path,...
  - `.to_floats(tokens: 'list[str]', what: 'str' = 'value', lineno: 'int | None', ...) -> 'list[float]'` - Convert *tokens* to floats, naming line and column on failure.
  - `.to_ints(tokens: 'list[str]', what: 'str' = 'value', lineno: 'int | None' = None) -> 'list[int]'` - Convert *tokens* to integers, naming line and column on failure.
  - `.warn_once(key: 'str', msg: 'str') -> 'None'` - Emit an :class:`IWFMReadWarning` once per file per *key*.
- `IWFMFileWriter(path: 'str | Path | None' = None) -> 'None'` - Sequential writer for IWFM text files.
  - `.flush(path: 'str | Path | None' = None) -> 'None'` - Write all accumulated lines to the output file.
  - `.lines` - The accumulated output lines.
  - `.to_string() -> 'str'` - Return all lines joined as a single string.
  - `.write_comment(text: 'str') -> 'None'` - Write a single comment line.
  - `.write_comments(lines: 'list[str]') -> 'None'` - Write multiple comment lines (each through :meth:`write_comment`).
  - `.write_data_line(tokens: 'list[object]', widths: 'list[int] | None' = None, note: 'str' = '') -> 'None'` - Write a single row of whitespace-delimited data.
  - `.write_data_table(df: 'pd.DataFrame', widths: 'list[int] | None' = None, include_index: ', ...) -> 'None'` - Write a DataFrame as whitespace-delimited rows.
  - `.write_dss_pathnames(pathnames: 'list[tuple[int, str]]') -> 'None'` - Write DSS pathname assignments (validated against the spec's NCOL when a spec was written first -- IWFM reads exactly N...
  - `.write_header(header: 'FileHeader') -> 'None'` - Write a :class:`FileHeader` (version + comment lines).
  - `.write_keyed_path(path: 'str | None', keyword: 'str', base_dir: 'str | Path | None' = Non, ...) -> 'None'` - Write a file-path keyed value.
  - `.write_keyed_value(value: 'object', keyword: 'str', width: 'int' = 50, comment: 'str' = '') -> 'None'` - Write a ``VALUE / KEYWORD comment`` line.
  - `.write_raw(line: 'str') -> 'None'` - Write a raw line as-is (a line break inside it raises).
  - `.write_timeseries_data(df: 'pd.DataFrame', col_width: 'int' = 18) -> 'None'` - Write time-series data rows.
  - `.write_timeseries_spec(spec: 'TimeSeriesSpec', keywords: 'list[str] | None' = None) -> 'None'` - Write a 5-parameter time-series header.
  - `.write_version_header(version: 'str') -> 'None'` - Write a version header like ``#4.0``.
- `IWFMParseError(msg: 'str', *, path=None, lineno: 'int | None' = None, section: 'str' = '') -> 'None'` - Malformed content or unexpected end of data in an IWFM file.
- `IWFMReadWarning(...)` - A reader kept going past malformed input (lenient mode only).
- `models.FlatTimeSeriesSpecMixin()` - ``.spec`` view for time-series files that store the spec flat.
  - `.spec` - The five spec parameters as a :class:`TimeSeriesSpec` snapshot.
- `models.RootZoneMain(header: 'FileHeader' = <factory>, convergence: 'float' = 0.001, max_itera, ...) -> None` - Parsed root zone component main file (e.g.
  - `.k_ponded() -> 'Any'` - Ponded hydraulic conductivity per element, as IWFM uses it.
- `models.TimeSeriesSpecAccessMixin()` - Flat ``n_columns`` / ``factor`` / ...
  - `.dss_file` - (undocumented)
  - `.factor` - (undocumented)
  - `.n_columns` - (undocumented)
  - `.n_steps_update` - (undocumented)
  - `.repeat_freq` - (undocumented)
- `models.TS_SPEC_FIELDS` - tuple constant: ('n_columns', 'factor', 'n_steps_update', 'repeat_freq', 'dss_file')
- `strict_mode(enabled: 'bool' = True)` - Context manager setting the reader mode for the enclosed block.
- `TimeSeriesDataFile(header: 'FileHeader' = <factory>, keywords: 'list[str]' = <factory>, n_co, ...) -> None` - Generic IWFM time-series data file.
- `TimeSeriesFile(header: 'FileHeader' = <factory>, spec: 'TimeSeriesSpec' = <factory>, dat, ...) -> None` - Generic time-series file container.
- `TimeSeriesSpec(n_columns: 'int' = 0, factor: 'float' = 1.0, n_steps_update: 'int' = 1, r, ...) -> None` - Header parameters for an IWFM time-series data section.
- `ZoneDefinition(extent: 'str' = 'horizontal', zones: 'dict[int, str]' = <factory>, elemen, ...) -> None` - Zone definition for IWFM Z-Budget aggregation.
