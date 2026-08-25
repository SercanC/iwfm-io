"""
Writers for IWFM root zone component files.

Mirror-images of :mod:`iwfm_io.readers.rootzone` — the main file and the
four sub-component mains (non-ponded ag, ponded ag, urban, native
vegetation) regenerate entirely from the parsed dataclasses.
"""

from __future__ import annotations

from pathlib import Path

from iwfm_io._writer import IWFMFileWriter
from iwfm_io.models.rootzone import (
    LandUseAreaFile,
    NativeVegFile,
    NonPondedAgFile,
    PondedAgFile,
    RootZoneMain,
    UrbanFile,
)
from iwfm_io.readers.rootzone import (
    _SOIL_COLS_V411,
    _SOIL_COLS_V412,
    PONDED_CROP_TYPES,
)
from iwfm_io.writers._param_blocks import fmt_num, write_table_rows


def write_rootzone_main(
    rz: RootZoneMain,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the IWFM root zone component main file.

    Parameters
    ----------
    rz : RootZoneMain
    path : str or Path
    base_dir : str or Path, optional
        Simulation working directory (folder of the simulation main
        file) for relativising the referenced paths — IWFM resolves
        them against that folder.  When omitted, absolute paths are
        written.
    """
    w = IWFMFileWriter(path)
    w.write_header(rz.header)

    w.write_keyed_value(rz.convergence, "RZCONV")
    w.write_keyed_value(rz.max_iterations, "RZITERMX")
    w.write_keyed_value(rz.factor_cn, "FACTCN")
    w.write_keyed_value(rz.gw_uptake, "GWUPTK")

    if rz.path_order:
        # Replay the keyed block (paths + factors) in file order with
        # the original keywords — the keyword set varies by version.
        # IWFM reads the sub-file list as consecutive data lines until
        # a comment line terminates it, so the comment emitted at the
        # transition from file paths to the conversion factors is
        # load-bearing, not decoration.
        prev_kind = None
        for kind, keyword, key in rz.path_order:
            if prev_kind == "path" and kind == "scalar":
                w.write_comment("C  end of file list")
            if kind == "path":
                w.write_keyed_path(rz.file_paths.get(key), keyword,
                                   base_dir=base_dir)
            else:
                w.write_keyed_value(rz.config.get(key), keyword)
            prev_kind = kind
    else:
        path_keys = [
            "nonponded_ag", "ponded_ag", "urban", "native_veg",
            "return_flow", "reuse_frac", "irig_period", "moisture_src",
            "ag_water_demand", "lwu_budget", "rz_budget", "lwu_zbudget",
            "rz_zbudget", "area_scale",
        ]
        labels = [
            "AGNPFL", "PFL", "URBFL", "NVRVFL", "RFFL", "RUFL", "IPFL",
            "MSRCFL", "AGWDFL", "LWUBUDFL", "RZBUDFL", "ZLWUBUDFL",
            "ZRZBUDFL", "ARSCLFL",
        ]
        for key, label in zip(path_keys, labels):
            w.write_keyed_path(rz.file_paths.get(key), label)

    # Per-element soil parameter table, regenerated from the DataFrame
    # (column order follows the file version the model was read from)
    w.write_comment("C  Soil, Precipitation and Runoff Destination Parameters")
    df = rz.element_params
    if df is not None:
        columns = (_SOIL_COLS_V412 if "icdstag" in df.columns
                   else _SOIL_COLS_V411)
        columns = [c for c in columns if c in df.columns]
        write_table_rows(w, df, columns,
                         widths=[8] + [10] * (len(columns) - 1))

    w.flush()


# ------------------------------------------------------------------
# Shared helpers for the sub-component mains
# ------------------------------------------------------------------

def _write_element_table(w: IWFMFileWriter, df, label: str) -> None:
    """Write a per-element table (``IE  v1 .. vn`` rows).

    Mirrors :func:`iwfm_io.readers.rootzone._read_element_table` — the
    reader detects the end of a table by an element id of 0 or an id
    that does not increase, so the rows themselves delimit the table.
    A comment separator is emitted for readability (readers skip it).
    """
    w.write_comment(f"C  {label}")
    if df is None:
        return
    columns = list(df.columns)
    write_table_rows(w, df, columns,
                     widths=[8] + [12] * (len(columns) - 1))


def _write_keyed_codes(w: IWFMFileWriter, codes: list[str],
                       keyword: str) -> None:
    for i, code in enumerate(codes, start=1):
        w.write_keyed_value(code, f"{keyword}[{i}]", width=24)


# ------------------------------------------------------------------
# Non-ponded agricultural crops main
# ------------------------------------------------------------------

def write_nonponded_ag_main(
    np_ag: NonPondedAgFile,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the non-ponded agricultural crops main file (AGNPFL).

    Parameters
    ----------
    np_ag : NonPondedAgFile
    path : str or Path
    base_dir : str or Path, optional
        Simulation working directory for relativising the referenced
        paths (IWFM resolves them against that folder).
    """
    w = IWFMFileWriter(path)
    w.write_header(np_ag.header)
    fp = np_ag.file_paths

    w.write_keyed_value(np_ag.n_crops, "NCROP")
    w.write_keyed_value(np_ag.demand_from_moisture, "FLDMD")
    _write_keyed_codes(w, np_ag.crop_codes, "CCODE")
    w.write_keyed_path(fp.get("land_use_area"), "LUFLNP", base_dir=base_dir)

    w.write_keyed_value(np_ag.n_budget_crops, "NBCROP")
    _write_keyed_codes(w, np_ag.budget_crop_codes, "BCCODE")
    w.write_keyed_path(fp.get("crop_lwu_budget"), "CLWUBUDFL",
                       base_dir=base_dir)
    w.write_keyed_path(fp.get("crop_rz_budget"), "CRZBUDFL",
                       base_dir=base_dir)

    w.write_keyed_path(fp.get("root_depth_fracs"), "RZFRACFL",
                       base_dir=base_dir)
    w.write_keyed_value(np_ag.root_depth_factor, "FACT")
    if np_ag.root_depths is not None:
        w.write_comment("C  Maximum rooting depths")
        for _, row in np_ag.root_depths.iterrows():
            number = np_ag.crop_codes.index(row["crop"]) + 1
            w.write_data_line(
                [number, fmt_num(float(row["root_depth"])),
                 int(row["icroot"])],
                widths=[8, 12, 8])

    _write_element_table(w, np_ag.curve_numbers, "Curve numbers")
    _write_element_table(w, np_ag.et_columns, "ET data columns")
    _write_element_table(w, np_ag.supply_req_columns,
                         "Ag. water supply requirement columns")
    _write_element_table(w, np_ag.irig_period_columns,
                         "Irrigation period columns")

    w.write_keyed_path(fp.get("min_soil_moisture"), "MINSMFL",
                       base_dir=base_dir)
    _write_element_table(w, np_ag.min_moisture_columns,
                         "Minimum soil moisture columns")

    w.write_keyed_path(fp.get("target_soil_moisture"), "TRGSMFL",
                       base_dir=base_dir)
    if fp.get("target_soil_moisture"):
        _write_element_table(w, np_ag.target_moisture_columns,
                             "Target soil moisture columns")

    _write_element_table(w, np_ag.return_flow_columns,
                         "Return flow fraction columns")
    _write_element_table(w, np_ag.reuse_columns, "Reuse fraction columns")

    w.write_keyed_path(fp.get("min_perc"), "DPFL", base_dir=base_dir)
    if fp.get("min_perc"):
        _write_element_table(w, np_ag.min_perc_columns,
                             "Minimum percolation columns")

    _write_element_table(w, np_ag.initial_conditions, "Initial conditions")
    w.flush()


# ------------------------------------------------------------------
# Ponded agricultural crops main
# ------------------------------------------------------------------

#: Ponded crop role -> file keyword, in file order.
_PONDED_ROOT_KEYWORDS = {
    "rice_fl": "ROOTRI_FL",
    "rice_nfl": "ROOTRI_NFL",
    "rice_ndc": "ROOTRI_NDC",
    "refuge_sl": "ROOTRF_SL",
    "refuge_pr": "ROOTRF_PR",
}


def write_ponded_ag_main(
    pa: PondedAgFile,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the ponded agricultural crops main file (PFL).

    Parameters
    ----------
    pa : PondedAgFile
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(pa.header)
    fp = pa.file_paths

    w.write_keyed_path(fp.get("land_use_area"), "LUFLP", base_dir=base_dir)

    w.write_keyed_value(pa.n_budget_crops, "NBCROP")
    _write_keyed_codes(w, pa.budget_crop_codes, "BCCODE")
    w.write_keyed_path(fp.get("crop_lwu_budget"), "CLWUBUDFL",
                       base_dir=base_dir)
    w.write_keyed_path(fp.get("crop_rz_budget"), "CRZBUDFL",
                       base_dir=base_dir)

    w.write_keyed_value(pa.root_depth_factor, "FACT")
    for crop in PONDED_CROP_TYPES:
        w.write_keyed_value(fmt_num(pa.root_depths.get(crop, 0.0)),
                            _PONDED_ROOT_KEYWORDS[crop], width=24)

    _write_element_table(w, pa.curve_numbers, "Curve numbers")
    _write_element_table(w, pa.et_columns, "ET data columns")
    _write_element_table(w, pa.supply_req_columns,
                         "Ag. water supply requirement columns")
    _write_element_table(w, pa.irig_period_columns,
                         "Irrigation period columns")

    w.write_keyed_path(fp.get("ponding_depth"), "PNDTHFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("rice_refuge_ops"), "FLOWFL", base_dir=base_dir)

    _write_element_table(w, pa.ponding_depth_columns,
                         "Ponding depth columns")
    _write_element_table(w, pa.app_depth_columns,
                         "Application depth columns (non-flooded rice)")
    _write_element_table(w, pa.return_flow_columns,
                         "Return flow fraction columns")
    _write_element_table(w, pa.reuse_columns, "Reuse fraction columns")
    _write_element_table(w, pa.initial_conditions, "Initial conditions")
    w.flush()


# ------------------------------------------------------------------
# Urban lands main
# ------------------------------------------------------------------

def write_urban_main(
    ur: UrbanFile,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the urban lands main file (URBFL).

    Parameters
    ----------
    ur : UrbanFile
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(ur.header)
    fp = ur.file_paths

    w.write_keyed_path(fp.get("land_use_area"), "LUFLU", base_dir=base_dir)
    w.write_keyed_value(ur.root_depth_factor, "FACT")
    w.write_keyed_value(fmt_num(ur.root_depth), "ROOTURB")
    w.write_keyed_path(fp.get("population"), "POPULFL", base_dir=base_dir)
    w.write_keyed_path(fp.get("per_capita_use"), "WTRUSEFL",
                       base_dir=base_dir)
    w.write_keyed_path(fp.get("water_use_specs"), "URBSPECFL",
                       base_dir=base_dir)

    _write_element_table(w, ur.element_params, "Urban element parameters")
    _write_element_table(w, ur.initial_conditions, "Initial conditions")
    w.flush()


# ------------------------------------------------------------------
# Land use area files
# ------------------------------------------------------------------

def write_land_use_area(lu: LandUseAreaFile, path: str | Path) -> None:
    """Write an IWFM land use area file (LUFLNP / LUFLP / LUFLU / LUFLNVRV).

    Regenerates the shared land use area layout: the 4-parameter spec
    block, then per-timestep blocks of one row per element where only
    the block's first row carries the date.  The row formatting is
    vectorized so C2VSimFG-sized files (millions of rows) write in
    well under a minute.

    Parameters
    ----------
    lu : LandUseAreaFile
    path : str or Path
    """
    import numpy as np

    w = IWFMFileWriter(path)
    w.write_header(lu.header)

    kw = lu.keywords if len(lu.keywords) == 4 else [
        "FACTLN", "NSPLN", "NFQLN", "DSSFL"]
    w.write_keyed_value(lu.factor, kw[0])
    w.write_keyed_value(lu.n_steps_update, kw[1])
    w.write_keyed_value(lu.repeat_freq, kw[2])
    w.write_keyed_value(lu.dss_file, kw[3])
    # Same load-bearing terminating comment as the 5-parameter
    # time-series spec block: without it IWFM consumes the first data
    # row while resolving the (possibly blank) DSS filename.
    w.write_comment("C  end of specification")

    if lu.dss_file and lu.dss_pathnames is not None:
        for _, row in lu.dss_pathnames.iterrows():
            w.write_data_line(
                [int(row["element_id"]), int(row["lu_type"]),
                 str(row["pathname"])],
                widths=[8, 8, 4])
        w.flush()
        return

    df = lu.data
    if df is not None and len(df):
        value_cols = [c for c in df.columns
                      if c not in ("date", "element_id")]
        dates = df["date"].astype(str).to_numpy()
        # A row opens a new timestep block when its date differs from
        # the previous row's; only those rows carry the date.
        new_block = np.empty(len(df), dtype=bool)
        new_block[0] = True
        new_block[1:] = dates[1:] != dates[:-1]
        date_field = np.where(
            new_block, np.char.rjust(dates.astype("U19"), 19), " " * 19)
        elem_field = np.char.mod("%7d",
                                 df["element_id"].to_numpy(int))
        vals = df[value_cols].to_numpy(float)
        lines = np.char.add(date_field, elem_field)
        for j in range(vals.shape[1]):
            lines = np.char.add(lines, np.char.mod("%15.6g", vals[:, j]))
        w.lines.extend(lines.tolist())

    w.flush()


# ------------------------------------------------------------------
# Native and riparian vegetation main
# ------------------------------------------------------------------

def write_native_veg_main(
    nv: NativeVegFile,
    path: str | Path,
    base_dir: str | Path | None = None,
) -> None:
    """Write the native and riparian vegetation main file (NVRVFL).

    Parameters
    ----------
    nv : NativeVegFile
    path : str or Path
    base_dir : str or Path, optional
    """
    w = IWFMFileWriter(path)
    w.write_header(nv.header)

    w.write_keyed_path(nv.file_paths.get("land_use_area"), "LUFLNVRV",
                       base_dir=base_dir)
    w.write_keyed_value(nv.root_depth_factor, "FACT")
    w.write_keyed_value(fmt_num(nv.root_depth_native), "ROOTNV")
    w.write_keyed_value(fmt_num(nv.root_depth_riparian), "ROOTRV")

    _write_element_table(w, nv.element_params,
                         "Native/riparian element parameters")
    _write_element_table(w, nv.initial_conditions, "Initial conditions")
    w.flush()
