# DLL Inquiry-Mode Limitations — Root-Cause Analysis

**IWFM source analyzed**: 2025.0 kernel (`Package_Model`, `Class_Model_ForInquiry`,
`IWFM_Model_Exports_C`, stream/GW connector classes)
**Scope**: three failure classes seen when a model is opened with
`is_for_inquiry=True`: partial-instantiation errors, a stream-exchange
access violation, and invalid hydrograph dates. Companion document:
`DLL_RETURN_FLOW_SKIP_BUG.md` (the spurious duplicate-node error).

---

## How inquiry mode actually works

`IW_Model_New(..., IsForInquiry=1)` does **not** build the simulation
model. If a cache file `IW_ModelData_ForInquiry.bin` exists in the
simulation folder (it is written at the end of every full simulation
run by `Model_ForInquiry%PrintModelData`), the DLL:

1. reads static preprocessor geometry from the PP binary file
   (grid, stratigraphy, stream/lake/GW connectors, *static* stream
   package), and
2. reads the cache's metadata: hydrograph/budget file lists, well and
   diversion specs, reach/node IDs and names, counts.
3. Sets `Model%lModel_ForInquiry_Defined = .TRUE.` and **returns without
   instantiating** RootZone, dynamic AppGW, dynamic AppStream,
   UnsatZone, SmallWatersheds, or the GW ZBudget component.

Getters that need those live components check
`lModel_ForInquiry_Defined` and return the "Model is instantiated only
partially" warning with `iStat = -1`.

**There is no DLL export that reports this state.**
`IW_Model_IsModelInstantiated` only answers "is any model open" — it
does not expose the inquiry/partial flag. A caller must track the
`is_for_inquiry` flag it passed (which `IWFMModel` now does).

---

## 1. Partial instantiation (plot tests 11, 20, 38, 54, 58)

Complete list of exported getters gated by the partial-instantiation
guard in the 2025.0 kernel:

| Export | Failing feature |
|---|---|
| `IW_Model_GetTileDrainNodes` | tile drain nodes |
| `IW_Model_GetHydrographCoordinates` | (some paths) |
| `IW_Model_GetNBypasses` | bypass count |
| `IW_Model_GetSubregionAgPumpingAverageDepthToGW` | pumping depth |
| `IW_Model_GetZoneAgPumpingAverageDepthToGW` | pumping depth |
| `IW_Model_GetNAgCrops` | crop count |
| `IW_Model_GetSupplyRequirement_Ag` / `_Urb` | supply requirement |
| `IW_Model_GetSupplyShortAtOrigin_Ag` / `_Urb` | supply shortage |
| `IW_Model_GetStrmBottomElevs`, `IW_Model_GetStrmStages` | stream pkg v5.0 models only |

**Fundamental vs. fixable.** Two of the five features our plot tests
exercise genuinely require live simulation state and can never work in
inquiry mode: supply requirement (computed water demand) and ag-pumping
depth-to-GW (needs current heads). The other three — tile-drain node
mapping, ag crop count, bypass count — are **static input data** that
fail only because DWR's cache writer (`PrintModelData`) does not include
them in `IW_ModelData_ForInquiry.bin`. They could be added upstream with
small changes; worth reporting to DWR as an enhancement.

**Practical guidance**: run the simulation once so the cache exists, and
use `is_for_inquiry=False` for these getters; or read the equivalent
static data DLL-free with `iwfm_io` (e.g. `read_tile_drain`,
`read_bypass_specs`, crop counts from the RootZone files).

---

## 2. Access violation in stream–GW exchange (plot tests 39, 40)

`IW_Model_GetStrmGainFromGW` crashes the whole Python process with an
access violation (null read) on the DLL build shipped in this repo.

**Root cause**: the connector state array
`BaseStrmGWConnectorType%StrmGWFlow` is allocated **only** by
`CompileConductance`, which runs during full stream instantiation from
the simulation main file. The inquiry path loads the connector from the
preprocessor binary (`ReadPreprocessedData`), which sets the connector's
`lDefined = .TRUE.` but never allocates `StrmGWFlow`. The connector
wrapper only checks `lDefined`, so the base-class getter multiplies an
unallocated array (`Flow = Connector%StrmGWFlow * ...`) — a null
dereference.

**Fixed upstream, crashes here**: the current 2025.0 kernel adds a
partial-instantiation guard at the top of `GetStrmGainFromGW`
("...cannot be retrieved from a model that is instantiated for
inquiry!"), so newer DLL builds fail politely. Builds that predate the
guard — including the repo's — crash. A latent unguarded twin
(`GetStrmSeepToGW_AtOneNode`) still exists upstream but has no C export,
so it is unreachable from Python.

**Wrapper mitigation (implemented)**: `IWFMModel.get_stream_gain_from_gw`
and `get_stream_gain_from_lakes` now raise a clean `IWFMError` when the
model was opened with `is_for_inquiry=True`, instead of letting the DLL
take down the process. With `is_for_inquiry=False` the arrays are
allocated and the calls work on all builds.

---

## 3. Invalid hydrograph dates (plot tests 15, 16)

`IW_Model_GetHydrograph` returns `iNTimes_Out = SIZE(rDates)` — the size
of the **requested window allocation**, not the number of entries read.
The true valid count *is* computed inside the HDF reader
(`MIN(SIZE(Data), nTime - iTimeOffset)`, used to size the hyperslab)
but is discarded — it is never propagated up the call chain.

When the requested window extends past the data actually on file:

- **Dates**: unfilled slots stay zero Julian; the DLL layer then applies
  the Julian→Excel shift (`- 2415020.0`) across the whole buffer, so the
  tail becomes exactly `-2415020.0`.
- **Values**: worse — the HDF read buffer is allocated with `MOLD=` (no
  initialization) and only the leading block is filled, so the tail of
  the values array is **uninitialized memory**, not zeros. It can look
  plausible while being garbage.

**Wrapper mitigation (implemented)**: `IWFMModel.get_hydrograph` masks
*both* returned arrays to entries with `date > 0` before returning, so
callers only ever see valid pairs.

**Upstream fix (for a DWR report)**: propagate the block size computed
in `Class_HDF5FileType::ReadData_OneColumn_...` up through
`GetHydrograph_GivenFile` to the export's `iNTimes_Out`, and/or
zero-initialize the read buffer.

---

## Summary of wrapper-level changes

| Issue | Change in `iwfm/model.py` |
|---|---|
| No queryable inquiry state | `IWFMModel` stores `_is_for_inquiry` |
| Stream-exchange crash | `get_stream_gain_from_gw` / `_from_lakes` raise `IWFMError` in inquiry mode |
| Garbage hydrograph tails | `get_hydrograph` masks dates *and* values by `date > 0` |
| Partial instantiation | unchanged — the DLL's own error is already clean; use simulation mode or `iwfm_io` readers |
