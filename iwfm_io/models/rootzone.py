"""Dataclasses for IWFM root zone component files.

The per-element "pointer tables" in the sub-component files reference
data columns of other files (crop ET → ET file, return flow → RFFL,
etc.).  An ``element_id`` of 0 in these tables means the row's values
apply to every element.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader


@dataclass
class RootZoneMain:
    """Parsed root zone component main file (e.g. ``RootZone_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    convergence : float
        RZCONV convergence criterion.
    max_iterations : int
        RZITERMX maximum iterations.
    factor_cn : float
        FACTCN conversion factor (e.g., in→ft).
    gw_uptake : int
        GWUPTK flag.
    file_paths : dict[str, str or None]
        References to sub-component files, keyed by role: nonponded_ag,
        ponded_ag, urban, native_veg, return_flow, reuse_frac,
        irig_period, moisture_src, ag_water_demand, lwu_budget,
        rz_budget, lwu_zbudget, rz_zbudget, and (version-dependent)
        area_scale, final_moisture, surface_flow_dest.
    path_order : list[tuple[str, str, str]]
        ("path" | "scalar", keyword, role/config-key) triples in file
        order, used to write the keyed block back with the original
        keywords and ordering.
    config : dict
        Conversion factors: factk, factcprise, tunitk.
    element_params : pd.DataFrame or None
        Per-element soil parameters.  Columns common to all versions:
        element_id, wp, fc, tn, lambda, k, k_ponded (-1 = same as k),
        rhc, cap_rise, irne (column in the Precipitation file), frne,
        imsrc (column in the generic moisture source file).  v4.12+
        adds icdstag/icdsturbin/icdsturbout/icdstnvrv (columns in the
        surface-flow destination file); v4.11 and earlier instead have
        typdest (0=outside, 1=stream node, 2=element, 3=lake,
        4=subregion, 5=groundwater) and dest.
    """

    header: FileHeader = field(default_factory=FileHeader)
    convergence: float = 0.001
    max_iterations: int = 150
    factor_cn: float = 1.0
    gw_uptake: int = 0
    file_paths: dict[str, str | None] = field(default_factory=dict)
    path_order: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    element_params: Any = None


@dataclass
class NonPondedAgFile:
    """Parsed non-ponded agricultural crops main file (AGNPFL).

    Attributes
    ----------
    header : FileHeader
    n_crops : int
        Number of non-ponded crops (NCROP).
    demand_from_moisture : int
        FLDMD flag for how agricultural water demand is computed.
    crop_codes : list[str]
        Two-character crop codes in column order (CCODE).
    file_paths : dict[str, str or None]
        Sub-file references: land_use_area (LUFLNP), root_depth_fracs
        (RZFRACFL), min_soil_moisture (MINSMFL), target_soil_moisture
        (TRGSMFL), min_perc (DPFL), crop_lwu_budget (CLWUBUDFL),
        crop_rz_budget (CRZBUDFL).
    n_budget_crops : int
        NBCROP; ``budget_crop_codes`` lists the selected codes.
    budget_crop_codes : list[str]
    root_depth_factor : float
        FACT for the maximum root depths.
    root_depths : pd.DataFrame or None
        One row per crop: crop (code), root_depth (max, file-native
        units), icroot (column in the root depth fractions file).
    curve_numbers : pd.DataFrame or None
        element_id + one CN column per crop code.
    et_columns : pd.DataFrame or None
        element_id + per-crop column numbers in the ET file.
    supply_req_columns : pd.DataFrame or None
        element_id + per-crop column numbers in the agricultural water
        supply requirement file (AGWDFL); 0 = computed internally.
    irig_period_columns : pd.DataFrame or None
        element_id + per-crop column numbers in the irrigation period
        file (IPFL).
    min_moisture_columns : pd.DataFrame or None
        element_id + per-crop column numbers in MINSMFL.
    target_moisture_columns : pd.DataFrame or None
        element_id + per-crop column numbers in TRGSMFL (None when
        TRGSMFL is blank - target is field capacity).
    return_flow_columns : pd.DataFrame or None
        element_id + per-crop column numbers in the return flow
        fractions file (RFFL).
    reuse_columns : pd.DataFrame or None
        element_id + per-crop column numbers in the reuse fractions
        file (RUFL).
    min_perc_columns : pd.DataFrame or None
        element_id + per-crop column numbers in DPFL (None when DPFL
        is blank).
    initial_conditions : pd.DataFrame or None
        element_id, fsoilmp (fraction of initial moisture due to
        precipitation) + per-crop initial moisture columns.
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_crops: int = 0
    demand_from_moisture: int = 0
    crop_codes: list[str] = field(default_factory=list)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    n_budget_crops: int = 0
    budget_crop_codes: list[str] = field(default_factory=list)
    root_depth_factor: float = 1.0
    root_depths: Any = None  # DataFrame
    curve_numbers: Any = None  # DataFrame
    et_columns: Any = None  # DataFrame
    supply_req_columns: Any = None  # DataFrame
    irig_period_columns: Any = None  # DataFrame
    min_moisture_columns: Any = None  # DataFrame
    target_moisture_columns: Any = None  # DataFrame
    return_flow_columns: Any = None  # DataFrame
    reuse_columns: Any = None  # DataFrame
    min_perc_columns: Any = None  # DataFrame
    initial_conditions: Any = None  # DataFrame


@dataclass
class PondedAgFile:
    """Parsed ponded agricultural crops main file (PFL).

    The five ponded crop types are fixed: rice_fl (flooded
    decomposition), rice_nfl (non-flooded decomposition), rice_ndc (no
    decomposition), refuge_sl (seasonal), refuge_pr (permanent).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        land_use_area (LUFLP), ponding_depth (PNDTHFL), rice_refuge_ops
        (FLOWFL), crop_lwu_budget (CLWUBUDFL), crop_rz_budget
        (CRZBUDFL).
    n_budget_crops : int
    budget_crop_codes : list[str]
    root_depth_factor : float
    root_depths : dict[str, float]
        Root depth per ponded crop keyword (ROOTRI_FL, ...).
    curve_numbers : pd.DataFrame or None
        element_id + CN per ponded crop type.
    et_columns : pd.DataFrame or None
        element_id + per-type column numbers in the ET file.
    supply_req_columns : pd.DataFrame or None
        element_id + per-type column numbers in AGWDFL.
    irig_period_columns : pd.DataFrame or None
        element_id + per-type column numbers in IPFL.
    ponding_depth_columns : pd.DataFrame or None
        element_id + per-type column numbers in PNDTHFL.
    app_depth_columns : pd.DataFrame or None
        element_id + column number in FLOWFL for non-flooded rice
        decomposition water application depth.
    return_flow_columns : pd.DataFrame or None
        element_id + per-type column numbers in FLOWFL.
    reuse_columns : pd.DataFrame or None
        element_id + per-type column numbers in FLOWFL.
    initial_conditions : pd.DataFrame or None
        element_id, fsoilmp + per-type initial moisture (values > 1
        encode ponding depth as root_depth x (SOILM - 1)).
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    n_budget_crops: int = 0
    budget_crop_codes: list[str] = field(default_factory=list)
    root_depth_factor: float = 1.0
    root_depths: dict = field(default_factory=dict)
    curve_numbers: Any = None  # DataFrame
    et_columns: Any = None  # DataFrame
    supply_req_columns: Any = None  # DataFrame
    irig_period_columns: Any = None  # DataFrame
    ponding_depth_columns: Any = None  # DataFrame
    app_depth_columns: Any = None  # DataFrame
    return_flow_columns: Any = None  # DataFrame
    reuse_columns: Any = None  # DataFrame
    initial_conditions: Any = None  # DataFrame


@dataclass
class UrbanFile:
    """Parsed urban lands main file (URBFL).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        land_use_area (LUFLU), population (POPULFL), per_capita_use
        (WTRUSEFL), water_use_specs (URBSPECFL).
    root_depth_factor : float
    root_depth : float
        Urban root depth (ROOTURB, file-native units).
    element_params : pd.DataFrame or None
        One row per element (element_id 0 = all).  Columns: element_id,
        perv_fraction, cn, icpopul (column in POPULFL), icwtruse
        (column in WTRUSEFL), fracdm, iceturb (column in the ET file),
        icrtfurb (column in RFFL), icrufurb (column in RUFL),
        icurbspec (column in URBSPECFL).
    initial_conditions : pd.DataFrame or None
        Columns: element_id, fsoilmp, soil_moisture.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    root_depth_factor: float = 1.0
    root_depth: float = 0.0
    element_params: Any = None  # DataFrame
    initial_conditions: Any = None  # DataFrame


@dataclass
class NativeVegFile:
    """Parsed native and riparian vegetation main file (NVRVFL).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        land_use_area (LUFLNVRV).
    root_depth_factor : float
    root_depth_native : float
        ROOTNV (file-native units).
    root_depth_riparian : float
        ROOTRV (file-native units).
    element_params : pd.DataFrame or None
        One row per element (element_id 0 = all).  Columns: element_id,
        cn_native, cn_riparian, icetnv / icetrv (columns in the ET
        file), istrmrv (stream node supplying unmet riparian ET;
        0 = no access).
    initial_conditions : pd.DataFrame or None
        Columns: element_id, moisture_native, moisture_riparian.
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    root_depth_factor: float = 1.0
    root_depth_native: float = 0.0
    root_depth_riparian: float = 0.0
    element_params: Any = None  # DataFrame
    initial_conditions: Any = None  # DataFrame
