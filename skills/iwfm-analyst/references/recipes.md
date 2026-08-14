# iwfm-io task recipes

All recipes assume:

```python
from iwfm_io import open_model
m = open_model(r"<model_root>")
```

`m.describe()` is the source of truth for budget names, location names,
layer count, and the simulation period.

## Budgets (water balance)

```python
df = m.budget_df("<budget name from describe()>", location=1)
# DataFrame, DatetimeIndex (one row per output step), one column per
# budget term. location: 1-based index or exact location name.
```

- Location 1 is usually "ENTIRE MODEL AREA"; subregions follow.
- Values are model-internal volume units; convert to acre-feet with the
  GW main's FACTVLOU (commonly 2.2957e-5 from cubic feet).
- Water-year totals: `df.resample("YS-OCT").sum()`.
- Older/packaged models may only have **text** budgets (`.bud`):

```python
from iwfm_io.readers.text_output import read_budget_text
sections = read_budget_text(r"...\Results\GW_Budget.bud")  # dict: location -> DataFrame
```

## Heads and depth to water

```python
heads = m.heads_df(layer=1)          # DataFrame: rows=time, cols=node ids
strat = m.stratigraphy_df()          # node_id, elevation (GSE), layers…
dtw   = strat["elevation"].to_numpy() - heads.iloc[-1].to_numpy()  # end of run
```

Subregion averages: map nodes to subregions via `m.elements_df()`
(`node1..node4`, `subregion`), or use
`m.get_subregion_ag_pumping_avg_depth_to_gw()` for the ready-made
per-subregion depth array.

## Hydrographs (observation wells, stream gauges)

```python
m._hydrograph_hdfs                   # discovered hydrograph HDF files
df = m.hydrograph_df("<name>")       # all columns, DatetimeIndex
# Text outputs (e.g. GW_Hydrographs.out) via:
from iwfm_io.readers.text_output import read_hydrograph_out
```

Hydrograph locations/names: `read_gw_main(...).hydrographs` (id, layer,
x, y, name) — useful to find "the well near X".

## Zone budgets

```python
ts = m.get_zbudget_timeseries("GW", zone_id=5, columns=[0, 1, 2])
# zones = subregions; returns {"dates", "values", "data_types"}
```

Custom zones: `iwfm_io.readers.hdf5.read_zbudget_hdf(path, zone_def=ZoneDefinition(...))`.
GB-scale files — first read takes ~10–60 s and is cached on the adapter.

## Compare two model runs

```python
from iwfm_io import compare_models, head_difference, budget_difference
report = compare_models(r"<run_A_root>", r"<run_B_root>")   # file/grid/head/budget diffs
dh = head_difference(r"<run_A_root>", r"<run_B_root>", layer=1)  # B − A DataFrame
```

## Build and run a scenario (confirm with user first)

```python
from iwfm_io import create_scenario, set_keyed_value, replace_text
scen = create_scenario(r"<base_root>", r"<new_root>", changes=[
    set_keyed_value("Simulation/<sim_main>.in", "EDT", "09/30/1995_24:00"),
])
import iwfm_io
iwfm_io.run_model(scen)   # Windows; exes from <model>/Bin or IWFM_BIN_DIR
```

Runtime scales with model size (sample ≈ 40 s; C2VSimFG ≈ 8 h — run in
background and monitor).

For many parallel copies of a large model, `link_unchanged=True`
hardlinks unchanged inputs instead of copying (near-instant, ~zero
marginal disk; changed files stay real copies). Same-volume only —
falls back to copying otherwise.

## Individual input files

```python
from iwfm_io import read_preprocessor
pp = read_preprocessor(r"...\Preprocessor\<main>.in")
pp.nodes; pp.elements; pp.stratigraphy; pp.stream_reaches; pp.lakes
from iwfm_io.readers.groundwater import read_gw_main, read_tile_drain, read_subsidence
from iwfm_io.readers.stream import read_stream_main, read_diversions
```

Writers mirror readers (`iwfm_io.writers.*`) for round-trip edits —
prefer `create_scenario` + change functions over hand-editing.

## GIS export (needs `pip install iwfm-io[geo]`)

```python
m.to_gis(r"model.gpkg", crs="EPSG:26910")   # all layers, one GeoPackage
# layers: nodes (with stratigraphy), elements, subregions (dissolved),
# streams (reach lines), stream_nodes, lakes, tile_drains, wells
```

Non-`.gpkg` path = folder of shapefiles. IWFM files carry no CRS — ask
the user for the projection (California DWR models are commonly UTM 10N
`EPSG:26910` or NAD83 CA Albers `EPSG:3310`); omit `crs` if unknown.
Join results onto layers via `node_data=`/`element_data=` (DataFrames
keyed `node_id`/`element_id`), e.g. end-of-run depth to water. Layers as
GeoDataFrames without writing: `iwfm_io.nodes_gdf(m)` etc.

## 3D VTK export for ParaView (no extra install needed)

```python
m.to_vtk("model.vtu", z_scale=50)   # 3D layered mesh (wedges/hexes)
from iwfm_io import export_vtk_timeseries
export_vtk_timeseries(m, "anim", stride=30)   # -> anim/heads.pvd animation
```

Pure numpy. Cells carry `layer`/`thickness`/`subregion`; per-node data
via `point_data={"name": arr}` with shape `(n_nodes,)` or
`(n_nodes, n_layers)`. Suggest `z_scale` 20–100 for regional models.

## Calibration statistics (observed vs simulated)

```python
from iwfm_io.pest import read_smp, match_sim_to_obs, residual_stats
obs = read_smp(r"<obs_heads.smp>")            # site, datetime, value
matched = match_sim_to_obs(sim, obs)          # sim interpolated to obs times
stats = residual_stats(matched, by="site")    # bias, RMSE, R2, NSE, KGE per well
```

`sim` is any long-form `site, datetime, value` frame — e.g. melt
`m.hydrograph_df(...)` columns, or composite multi-layer wells first:
`link_hydrographs(gwl_metadata, gw_main)` + `composite_well_hydrographs`.
Obs-vs-sim figures: `iwfm_io.plots.calibration` (scatter, residual
histogram/map, hydrograph panels).

## PESTPP-IES run post-processing

```python
from iwfm_io.pest import load_ies_ensembles, ies_stats
r = load_ies_ensembles(r"<master_dir>\<case>.pst")
r.describe()          # orient FIRST: iterations, files found, phi summary
r.phi_summary()       # convergence table; r.best_realization() = min-phi
stats = ies_stats(r)  # fit metrics per (iteration, realization)
```

`.jcb` binary ensembles need pyemu (`pip install iwfm-io[pest]`); CSV
ensembles work with nothing extra. Diagnostics plots:
`iwfm_io.pest.diagnostics` (phi evolution, parameter-change, PDC).

## CalSim streamflows from HEC-DSS (needs `pip install iwfm-io[dss]`)

```python
import pandas as pd
from iwfm_io import dss_catalog, link_calsim_channels, calsim_streamflow_series
cat = dss_catalog(r"<DV.dss>")                    # all records, parts a-f
md = pd.DataFrame({"gauge_id": ["freeport"], "calsim_bpart": ["C_SAC048"]})
link = link_calsim_channels(md, cat, cpart="CHANNEL")
flows = calsim_streamflow_series(link, r"<DV.dss>", units="taf")
```

Monthly period-average records; a January value is stamped Feb 1 00:00
(same end-of-period convention as IWFM's `24:00`), so these align with
IWFM series directly. `units="cfs"` (as stored) or `"taf"`.

## DLL (only for live simulation state)

```python
import iwfm_io
iwfm_io.dll.download_dll("2025.0.1747")           # once; sha256-verified
with iwfm_io.dll.IWFMModel(
    preprocessor_file=r"...\Preprocessor\<main>.IN",   # the .IN, NOT the .bin
    simulation_file=r"...\Simulation\<main>.in",
    is_for_inquiry=True,
) as dm:
    dm.describe()
```

In inquiry mode some getters are unavailable by design (supply/demand,
tile drains, stream exchange…) — the adapter serves all of those from
files instead, so prefer `open_model` unless the DLL is truly needed.
First inquiry open of a model without `IW_ModelData_ForInquiry.bin`
does a full instantiation (minutes on big models) and then caches.
