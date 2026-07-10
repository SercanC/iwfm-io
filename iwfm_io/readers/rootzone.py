"""
Readers for IWFM root zone component files.

The root zone is the most complex IWFM component with many sub-files.
``read_rootzone_main`` parses the main file completely: convergence
parameters, sub-file references, conversion factors, and the per-element
soil parameter table.  Raw lines of the tail are also kept for lossless
round-trip writing.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import split_keyed_line, tokenize_data_line
from iwfm_io.models.rootzone import (
    NativeVegFile,
    NonPondedAgFile,
    PondedAgFile,
    RootZoneMain,
    UrbanFile,
)

# Keyword → role for the sub-file references.  The set varies with the
# file version (e.g. v4.11 has FNSMFL where v4.12 has ARSCLFL, and only
# v4.12+ has DESTFL), so the block is parsed keyword-driven.
_PATH_KEYWORDS = {
    "AGNPFL": "nonponded_ag",
    "PFL": "ponded_ag",
    "URBFL": "urban",
    "NVRVFL": "native_veg",
    "RFFL": "return_flow",
    "RUFL": "reuse_frac",
    "IPFL": "irig_period",
    "MSRCFL": "moisture_src",
    "AGWDFL": "ag_water_demand",
    "LWUBUDFL": "lwu_budget",
    "RZBUDFL": "rz_budget",
    "ZLWUBUDFL": "lwu_zbudget",
    "ZRZBUDFL": "rz_zbudget",
    "ARSCLFL": "area_scale",
    "FNSMFL": "final_moisture",
    "DESTFL": "surface_flow_dest",
}
_SCALAR_KEYWORDS = {"FACTK", "FACTCPRISE", "FACTPRISE", "TUNITK"}

# Per-element soil table layouts by column count.  v4.12+ points the
# four surface-flow destinations at columns of the DESTFL time-series
# file; v4.11 and earlier give a single inline TYPDEST/DEST pair.
_SOIL_COLS_V412 = [
    "element_id", "wp", "fc", "tn", "lambda", "k", "k_ponded", "rhc",
    "cap_rise", "irne", "frne", "imsrc",
    "icdstag", "icdsturbin", "icdsturbout", "icdstnvrv",
]
_SOIL_COLS_V411 = [
    "element_id", "wp", "fc", "tn", "lambda", "k", "rhc", "cap_rise",
    "irne", "frne", "imsrc", "typdest", "dest", "k_ponded",
]
_SOIL_INT_COLS = {
    "element_id", "rhc", "irne", "imsrc", "typdest", "dest",
    "icdstag", "icdsturbin", "icdsturbout", "icdstnvrv",
}


def read_rootzone_main(path: str | Path) -> RootZoneMain:
    """Read the IWFM root zone component main file.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    RootZoneMain
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Convergence and iteration parameters
    convergence, _ = reader.read_keyed_float()
    max_iterations, _ = reader.read_keyed_int()
    factor_cn, _ = reader.read_keyed_float()
    gw_uptake, _ = reader.read_keyed_int()

    def _resolve(value: str) -> str | None:
        if not value or value == "*":
            return None
        from iwfm_io._parser import resolve_child_path
        return resolve_child_path(value, base_dir)

    # Keyed block: sub-file paths and conversion factors, identified by
    # keyword because the set differs across file versions.
    file_paths: dict[str, str | None] = {}
    path_order: list[tuple[str, str]] = []
    config: dict = {}
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        value, keyword = split_keyed_line(line)
        kw = keyword.split()[0].upper() if keyword else ""
        if kw in _PATH_KEYWORDS:
            reader.next_data_line()
            role = _PATH_KEYWORDS[kw]
            file_paths[role] = _resolve(value)
            path_order.append(("path", kw, role))
        elif kw in _SCALAR_KEYWORDS:
            reader.next_data_line()
            key = "factcprise" if kw == "FACTPRISE" else kw.lower()
            config[key] = value if kw == "TUNITK" else float(value)
            path_order.append(("scalar", kw, key))
        else:
            break

    # Per-element soil parameter table (runs to EOF)
    raw_lines = reader.skip_to_end()

    element_params = None
    from iwfm_io._tokens import is_comment
    rows = []
    columns: list[str] | None = None
    for line in raw_lines:
        if is_comment(line):
            continue
        toks = tokenize_data_line(line)
        if columns is None:
            if len(toks) >= len(_SOIL_COLS_V412):
                columns = _SOIL_COLS_V412
            elif len(toks) >= len(_SOIL_COLS_V411) - 1:
                columns = _SOIL_COLS_V411
            else:
                break
        try:
            vals = [float(t) for t in toks[: len(columns)]]
        except ValueError:
            break
        vals += [float("nan")] * (len(columns) - len(vals))
        rows.append(vals)
    if rows and columns is not None:
        element_params = pd.DataFrame(rows, columns=columns)
        for col in _SOIL_INT_COLS & set(columns):
            element_params[col] = element_params[col].astype("Int64")

    return RootZoneMain(
        header=header,
        convergence=convergence,
        max_iterations=max_iterations,
        factor_cn=factor_cn,
        gw_uptake=gw_uptake,
        file_paths=file_paths,
        path_order=path_order,
        config=config,
        element_params=element_params,
    )


# ------------------------------------------------------------------
# Shared helpers for the sub-component mains
# ------------------------------------------------------------------

def _make_resolver(base_dir: Path):
    def _resolve(value: str | None) -> str | None:
        if not value or value == "*":
            return None
        # Sub-file paths resolve against the simulation working
        # directory (up to two levels up when the main lives in e.g.
        # Simulation/RootZone/NonPondedAg/): prefer the candidate that
        # exists as a file, then the one whose folder exists.
        rel = value.replace("\\", "/")
        anchors = (base_dir, base_dir.parent, base_dir.parent.parent)
        candidates = [anchor / rel for anchor in anchors]
        for cand in candidates:
            if cand.exists():
                return str(cand)
        for cand in candidates:
            if cand.parent.exists():
                return str(cand)
        return str(candidates[0])
    return _resolve


def _read_element_table(
    reader: IWFMFileReader,
    value_names: list[str],
    as_int: bool = False,
) -> pd.DataFrame | None:
    """Read an IWFM per-element table: ``IE  v1 .. vn`` rows.

    An element id of 0 means the values apply to all elements and ends
    the table.  Otherwise rows continue while the element ids are
    strictly increasing and the token count matches — consecutive
    tables of the same shape are split where the id sequence resets.
    Extra trailing tokens on a row are ignored, matching Fortran
    list-directed reads (C2VSimFG pads some rows with extra zeros).
    """
    n_cols = 1 + len(value_names)
    rows: list[list[float]] = []
    prev_id: int | None = None
    while True:
        line = reader.peek_data_line()
        if line is None:
            break
        toks = tokenize_data_line(line)
        if len(toks) < n_cols:
            break
        try:
            vals = [float(t) for t in toks[:n_cols]]
        except ValueError:
            break
        elem = int(vals[0])
        if prev_id is not None and elem <= prev_id:
            break
        reader.next_data_line()
        rows.append([elem] + vals[1:])
        if elem == 0:
            break
        prev_id = elem
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["element_id"] + value_names)
    df["element_id"] = df["element_id"].astype(int)
    if as_int:
        for col in value_names:
            df[col] = df[col].astype(int)
    return df


def _read_keyed_codes(reader: IWFMFileReader, n: int) -> list[str]:
    """Read *n* keyed code lines (e.g. ``TO  / CCODE[1]``)."""
    codes = []
    for _ in range(n):
        value, _ = reader.read_keyed_value()
        codes.append(value)
    return codes


# ------------------------------------------------------------------
# Non-ponded agricultural crops main
# ------------------------------------------------------------------

def read_nonponded_ag_main(path: str | Path) -> NonPondedAgFile:
    """Read the non-ponded agricultural crops main file (AGNPFL).

    All per-element/crop pointer tables reference data columns in other
    files — see :class:`~iwfm_io.models.rootzone.NonPondedAgFile` for
    which file each table points at.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    NonPondedAgFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    _resolve = _make_resolver(Path(path).parent)

    n_crops, _ = reader.read_keyed_int()
    demand_from_moisture, _ = reader.read_keyed_int()
    crop_codes = _read_keyed_codes(reader, n_crops)
    land_use_area, _ = reader.read_keyed_value()

    n_budget_crops, _ = reader.read_keyed_int()
    budget_crop_codes = _read_keyed_codes(reader, n_budget_crops)
    crop_lwu_budget, _ = reader.read_keyed_value()
    crop_rz_budget, _ = reader.read_keyed_value()

    root_depth_fracs, _ = reader.read_keyed_value()
    root_depth_factor, _ = reader.read_keyed_float()
    rd_rows = []
    for _ in range(n_crops):
        toks = tokenize_data_line(reader.next_data_line())
        rd_rows.append({
            "crop": crop_codes[int(float(toks[0])) - 1],
            "root_depth": float(toks[1]),
            "icroot": int(float(toks[2])),
        })
    root_depths = pd.DataFrame(rd_rows)

    crop_cols = list(crop_codes)
    curve_numbers = _read_element_table(reader, crop_cols)
    et_columns = _read_element_table(reader, crop_cols, as_int=True)
    supply_req_columns = _read_element_table(reader, crop_cols, as_int=True)
    irig_period_columns = _read_element_table(reader, crop_cols, as_int=True)

    min_soil_moisture, _ = reader.read_keyed_value()
    min_moisture_columns = _read_element_table(reader, crop_cols, as_int=True)

    target_soil_moisture, _ = reader.read_keyed_value()
    target_moisture_columns = None
    if target_soil_moisture and target_soil_moisture != "*":
        target_moisture_columns = _read_element_table(
            reader, crop_cols, as_int=True)

    return_flow_columns = _read_element_table(reader, crop_cols, as_int=True)
    reuse_columns = _read_element_table(reader, crop_cols, as_int=True)

    min_perc, _ = reader.read_keyed_value()
    min_perc_columns = None
    if min_perc and min_perc != "*":
        min_perc_columns = _read_element_table(reader, crop_cols, as_int=True)

    initial_conditions = _read_element_table(
        reader, ["fsoilmp"] + crop_cols)

    return NonPondedAgFile(
        header=header,
        n_crops=n_crops,
        demand_from_moisture=demand_from_moisture,
        crop_codes=crop_codes,
        file_paths={
            "land_use_area": _resolve(land_use_area),
            "root_depth_fracs": _resolve(root_depth_fracs),
            "min_soil_moisture": _resolve(min_soil_moisture),
            "target_soil_moisture": _resolve(target_soil_moisture),
            "min_perc": _resolve(min_perc),
            "crop_lwu_budget": _resolve(crop_lwu_budget),
            "crop_rz_budget": _resolve(crop_rz_budget),
        },
        n_budget_crops=n_budget_crops,
        budget_crop_codes=budget_crop_codes,
        root_depth_factor=root_depth_factor,
        root_depths=root_depths,
        curve_numbers=curve_numbers,
        et_columns=et_columns,
        supply_req_columns=supply_req_columns,
        irig_period_columns=irig_period_columns,
        min_moisture_columns=min_moisture_columns,
        target_moisture_columns=target_moisture_columns,
        return_flow_columns=return_flow_columns,
        reuse_columns=reuse_columns,
        min_perc_columns=min_perc_columns,
        initial_conditions=initial_conditions,
    )


# ------------------------------------------------------------------
# Ponded agricultural crops main
# ------------------------------------------------------------------

#: Fixed ponded crop types, in file column order.
PONDED_CROP_TYPES = ["rice_fl", "rice_nfl", "rice_ndc",
                     "refuge_sl", "refuge_pr"]


def read_ponded_ag_main(path: str | Path) -> PondedAgFile:
    """Read the ponded agricultural crops main file (PFL).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    PondedAgFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    _resolve = _make_resolver(Path(path).parent)

    land_use_area, _ = reader.read_keyed_value()

    n_budget_crops, _ = reader.read_keyed_int()
    budget_crop_codes = _read_keyed_codes(reader, n_budget_crops)
    crop_lwu_budget, _ = reader.read_keyed_value()
    crop_rz_budget, _ = reader.read_keyed_value()

    root_depth_factor, _ = reader.read_keyed_float()
    root_key = {"ROOTRI_FL": "rice_fl", "ROOTRI_NFL": "rice_nfl",
                "ROOTRI_NDC": "rice_ndc", "ROOTRF_SL": "refuge_sl",
                "ROOTRF_PR": "refuge_pr"}
    root_depths: dict[str, float] = {}
    for _ in range(len(PONDED_CROP_TYPES)):
        value, keyword = reader.read_keyed_value()
        kw = keyword.split()[0].upper() if keyword else ""
        root_depths[root_key.get(kw, kw.lower())] = float(value)

    type_cols = list(PONDED_CROP_TYPES)
    curve_numbers = _read_element_table(reader, type_cols)
    et_columns = _read_element_table(reader, type_cols, as_int=True)
    supply_req_columns = _read_element_table(reader, type_cols, as_int=True)
    irig_period_columns = _read_element_table(reader, type_cols, as_int=True)

    ponding_depth, _ = reader.read_keyed_value()
    rice_refuge_ops, _ = reader.read_keyed_value()

    ponding_depth_columns = _read_element_table(reader, type_cols, as_int=True)
    app_depth_columns = _read_element_table(
        reader, ["icdwri_nfl"], as_int=True)
    return_flow_columns = _read_element_table(reader, type_cols, as_int=True)
    reuse_columns = _read_element_table(reader, type_cols, as_int=True)

    initial_conditions = _read_element_table(
        reader, ["fsoilmp"] + type_cols)

    return PondedAgFile(
        header=header,
        file_paths={
            "land_use_area": _resolve(land_use_area),
            "ponding_depth": _resolve(ponding_depth),
            "rice_refuge_ops": _resolve(rice_refuge_ops),
            "crop_lwu_budget": _resolve(crop_lwu_budget),
            "crop_rz_budget": _resolve(crop_rz_budget),
        },
        n_budget_crops=n_budget_crops,
        budget_crop_codes=budget_crop_codes,
        root_depth_factor=root_depth_factor,
        root_depths=root_depths,
        curve_numbers=curve_numbers,
        et_columns=et_columns,
        supply_req_columns=supply_req_columns,
        irig_period_columns=irig_period_columns,
        ponding_depth_columns=ponding_depth_columns,
        app_depth_columns=app_depth_columns,
        return_flow_columns=return_flow_columns,
        reuse_columns=reuse_columns,
        initial_conditions=initial_conditions,
    )


# ------------------------------------------------------------------
# Urban lands main
# ------------------------------------------------------------------

def read_urban_main(path: str | Path) -> UrbanFile:
    """Read the urban lands main file (URBFL).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    UrbanFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    _resolve = _make_resolver(Path(path).parent)

    land_use_area, _ = reader.read_keyed_value()
    root_depth_factor, _ = reader.read_keyed_float()
    root_depth, _ = reader.read_keyed_float()
    population, _ = reader.read_keyed_value()
    per_capita_use, _ = reader.read_keyed_value()
    water_use_specs, _ = reader.read_keyed_value()

    element_params = _read_element_table(
        reader,
        ["perv_fraction", "cn", "icpopul", "icwtruse", "fracdm",
         "iceturb", "icrtfurb", "icrufurb", "icurbspec"])
    if element_params is not None:
        for col in ("icpopul", "icwtruse", "iceturb", "icrtfurb",
                    "icrufurb", "icurbspec"):
            element_params[col] = element_params[col].astype(int)

    initial_conditions = _read_element_table(
        reader, ["fsoilmp", "soil_moisture"])

    return UrbanFile(
        header=header,
        file_paths={
            "land_use_area": _resolve(land_use_area),
            "population": _resolve(population),
            "per_capita_use": _resolve(per_capita_use),
            "water_use_specs": _resolve(water_use_specs),
        },
        root_depth_factor=root_depth_factor,
        root_depth=root_depth,
        element_params=element_params,
        initial_conditions=initial_conditions,
    )


# ------------------------------------------------------------------
# Native and riparian vegetation main
# ------------------------------------------------------------------

def read_native_veg_main(path: str | Path) -> NativeVegFile:
    """Read the native and riparian vegetation main file (NVRVFL).

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    NativeVegFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    _resolve = _make_resolver(Path(path).parent)

    land_use_area, _ = reader.read_keyed_value()
    root_depth_factor, _ = reader.read_keyed_float()
    root_depth_native, _ = reader.read_keyed_float()
    root_depth_riparian, _ = reader.read_keyed_float()

    element_params = _read_element_table(
        reader,
        ["cn_native", "cn_riparian", "icetnv", "icetrv", "istrmrv"])
    if element_params is not None:
        for col in ("icetnv", "icetrv", "istrmrv"):
            element_params[col] = element_params[col].astype(int)

    initial_conditions = _read_element_table(
        reader, ["moisture_native", "moisture_riparian"])

    return NativeVegFile(
        header=header,
        file_paths={"land_use_area": _resolve(land_use_area)},
        root_depth_factor=root_depth_factor,
        root_depth_native=root_depth_native,
        root_depth_riparian=root_depth_riparian,
        element_params=element_params,
        initial_conditions=initial_conditions,
    )
