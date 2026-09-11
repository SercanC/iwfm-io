"""
Readers for IWFM root zone component files.

The root zone is the most complex IWFM component with many sub-files.
``read_rootzone_main`` parses the main file completely: convergence
parameters, sub-file references, conversion factors, and the per-element
soil parameter table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import warnings

from iwfm_io._parser import IWFMFileReader, IWFMReadWarning
from iwfm_io._tokens import (
    is_comment,
    is_iwfm_date,
    split_keyed_line,
    tokenize_data_line,
)
from iwfm_io.models.rootzone import (
    LandUseAreaFile,
    NativeVegFile,
    NonPondedAgFile,
    PondedAgFile,
    RootZoneMain,
    SurfaceFlowDestFile,
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
    element_params = None
    rows = []
    columns: list[str] | None = None
    with reader.section("soil parameter table"):
        while True:
            line = reader.peek_data_line()
            if line is None:
                break
            toks = tokenize_data_line(line)
            if columns is None:
                if len(toks) >= len(_SOIL_COLS_V412):
                    columns = _SOIL_COLS_V412
                elif len(toks) >= len(_SOIL_COLS_V411) - 1:
                    columns = _SOIL_COLS_V411
                else:
                    reader.next_data_line()
                    reader.degrade(
                        "soil parameter row: expected at least "
                        f"{len(_SOIL_COLS_V411) - 1} values but found "
                        f"{len(toks)}: {line.strip()!r}")
                    break
            reader.next_data_line()
            vals = reader.to_floats(toks[: len(columns)],
                                    "soil parameter row")
            if len(vals) < len(columns):
                reader.degrade(
                    f"soil parameter row has {len(vals)} of "
                    f"{len(columns)} values (missing values read as NaN)")
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
    what: str | None = None,
    n_rows: int | None = None,
) -> pd.DataFrame | None:
    """Read an IWFM per-element table: ``IE  v1 .. vn`` rows.

    IWFM reads exactly ``NE`` rows (in any order) unless the first row's
    element id is 0, which means "all elements" and is the whole table.
    When *n_rows* (the model's element count) is known that is what is
    read — a short table raises. Without it the table end is inferred:
    rows continue while the element ids are strictly increasing and the
    token count matches (consecutive tables of the same shape are split
    where the id sequence resets), which is only right for decks that
    list elements in ascending order. Extra trailing tokens on a row are
    ignored, matching Fortran list-directed reads (C2VSimFG pads some
    rows with extra zeros).
    """
    n_cols = 1 + len(value_names)
    rows: list[list[float]] = []
    prev_id: int | None = None
    what = f"{what or 'element table'} row"
    with reader.section(what[:-4]):
        while True:
            if n_rows is not None and len(rows) >= n_rows:
                break
            line = reader.peek_data_line()
            if line is None:
                if n_rows is not None and rows:
                    raise reader.error(
                        f"{what}s: file ended after {len(rows)} of "
                        f"{n_rows} element rows")
                break
            toks = tokenize_data_line(line)
            if len(toks) < n_cols:
                if n_rows is not None and rows:
                    raise reader.error(
                        f"{what} {len(rows) + 1}: expected {n_cols} "
                        f"values, got {len(toks)}: {line.strip()!r}")
                break
            if not _is_int_token(toks[0]):
                if n_rows is not None and rows:
                    raise reader.error(
                        f"{what} {len(rows) + 1}: element id is not an "
                        f"integer: {toks[0]!r}")
                # not an element row: the next keyed line / section
                break
            elem = int(float(toks[0]))
            if n_rows is None and prev_id is not None and elem <= prev_id:
                break
            reader.next_data_line()
            vals: list = []
            for i, t in enumerate(toks[1:n_cols], start=2):
                try:
                    vals.append(float(t))
                except ValueError:
                    reader.degrade(
                        f"{what}: column {i} is not a number: {t!r} "
                        "(kept as text; validate_references reports it)")
                    vals.append(t)
            rows.append([elem] + vals)
            if elem == 0:
                break
            prev_id = elem
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["element_id"] + value_names)
    df["element_id"] = df["element_id"].astype(int)
    if as_int:
        _int_columns(reader, df, value_names, what[:-4])
    return df


def _is_int_token(tok: str) -> bool:
    try:
        return float(tok) == int(float(tok))
    except (ValueError, OverflowError):
        return False


def _int_columns(reader: IWFMFileReader, df: pd.DataFrame, cols, what: str):
    """Cast pointer *cols* of *df* to int in place; non-integral values
    are kept as floats with a warning (``validate_references`` reports
    them), NaN placeholders (lenient mode) stay float."""
    for col in cols:
        vals = df[col]
        num = pd.to_numeric(vals, errors="coerce")
        if num.isna().any():
            continue  # lenient-mode text placeholders stay as read
        if (num != num.round()).any():
            warnings.warn(
                f"{reader.path} [{what}]: column {col!r} holds "
                "non-integral pointer values; kept as floats "
                "(validate_references reports them)",
                IWFMReadWarning, stacklevel=3)
            df[col] = num
            continue
        df[col] = num.astype(int)


# Some decks repeat the variable tag inside the inline comment
# ("CO  / CCODE[ 2]  Cotton") — strip it to get the bare description.
_CODE_TAG_RE = re.compile(r"^B?CCODE\s*\[\s*\d+\s*\]\s*", re.IGNORECASE)


def _read_keyed_codes(
    reader: IWFMFileReader, n: int,
) -> tuple[list[str], list[str]]:
    """Read *n* keyed code lines (e.g. ``TO  / CCODE[1]  Tomato``).

    Returns ``(codes, descriptions)``; a description is the inline
    ``/``-comment with any leading ``CCODE[n]``/``BCCODE[n]`` tag
    stripped (empty string when the deck carries none).
    """
    codes, names = [], []
    for _ in range(n):
        value, keyword = reader.read_keyed_value()
        codes.append(value)
        names.append(_CODE_TAG_RE.sub("", keyword).strip())
    return codes, names


# ------------------------------------------------------------------
# Non-ponded agricultural crops main
# ------------------------------------------------------------------

def read_nonponded_ag_main(path: str | Path, n_elements: int | None = None) -> NonPondedAgFile:
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
    crop_codes, crop_descs = _read_keyed_codes(reader, n_crops)
    crop_names = dict(zip(crop_codes, crop_descs))
    land_use_area, _ = reader.read_keyed_value()

    n_budget_crops, _ = reader.read_keyed_int()
    budget_crop_codes, budget_descs = _read_keyed_codes(
        reader, n_budget_crops)
    crop_names.update({c: d for c, d in zip(budget_crop_codes,
                                            budget_descs) if d})
    crop_lwu_budget, _ = reader.read_keyed_value()
    crop_rz_budget, _ = reader.read_keyed_value()

    root_depth_fracs, _ = reader.read_keyed_value()
    root_depth_factor, _ = reader.read_keyed_float()
    rd_rows = []
    with reader.section("root depths"):
        for _ in range(n_crops):
            toks = reader.read_row(3, "root depth row")
            icrop = reader.to_ints(toks[:1], "root depth row")[0]
            if not 1 <= icrop <= n_crops:
                raise reader.error(
                    f"root depth row: crop index {icrop} is outside "
                    f"1..{n_crops}")
            rd_rows.append({
                "crop": crop_codes[icrop - 1],
                "root_depth": reader.to_floats(toks[1:2],
                                               "root depth row")[0],
                "icroot": reader.to_ints(toks[2:3], "root depth row")[0],
            })
    root_depths = pd.DataFrame(rd_rows)

    crop_cols = list(crop_codes)
    curve_numbers = _read_element_table(reader, crop_cols,
                                        what="curve numbers", n_rows=n_elements)
    et_columns = _read_element_table(reader, crop_cols, as_int=True,
                                     what="ET column pointers", n_rows=n_elements)
    supply_req_columns = _read_element_table(
        reader, crop_cols, as_int=True, what="supply requirement pointers", n_rows=n_elements)
    irig_period_columns = _read_element_table(
        reader, crop_cols, as_int=True, what="irrigation period pointers", n_rows=n_elements)

    min_soil_moisture, _ = reader.read_keyed_value()
    min_moisture_columns = _read_element_table(
        reader, crop_cols, as_int=True, what="minimum moisture pointers", n_rows=n_elements)

    target_soil_moisture, _ = reader.read_keyed_value()
    target_moisture_columns = None
    if target_soil_moisture and target_soil_moisture != "*":
        target_moisture_columns = _read_element_table(
            reader, crop_cols, as_int=True, what="target moisture pointers", n_rows=n_elements)

    return_flow_columns = _read_element_table(
        reader, crop_cols, as_int=True, what="return flow pointers", n_rows=n_elements)
    reuse_columns = _read_element_table(
        reader, crop_cols, as_int=True, what="reuse pointers", n_rows=n_elements)

    min_perc, _ = reader.read_keyed_value()
    min_perc_columns = None
    if min_perc and min_perc != "*":
        min_perc_columns = _read_element_table(
            reader, crop_cols, as_int=True, what="minimum percolation pointers", n_rows=n_elements)

    initial_conditions = _read_element_table(
        reader, ["fsoilmp"] + crop_cols, what="initial conditions", n_rows=n_elements)

    return NonPondedAgFile(
        header=header,
        n_crops=n_crops,
        demand_from_moisture=demand_from_moisture,
        crop_codes=crop_codes,
        crop_names=crop_names,
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


def read_ponded_ag_main(path: str | Path, n_elements: int | None = None) -> PondedAgFile:
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
    budget_crop_codes, _ = _read_keyed_codes(reader, n_budget_crops)
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
    curve_numbers = _read_element_table(reader, type_cols,
                                        what="curve numbers", n_rows=n_elements)
    et_columns = _read_element_table(reader, type_cols, as_int=True,
                                     what="ET column pointers", n_rows=n_elements)
    supply_req_columns = _read_element_table(
        reader, type_cols, as_int=True, what="supply requirement pointers", n_rows=n_elements)
    irig_period_columns = _read_element_table(
        reader, type_cols, as_int=True, what="irrigation period pointers", n_rows=n_elements)

    ponding_depth, _ = reader.read_keyed_value()
    rice_refuge_ops, _ = reader.read_keyed_value()

    ponding_depth_columns = _read_element_table(
        reader, type_cols, as_int=True, what="ponding depth pointers", n_rows=n_elements)
    app_depth_columns = _read_element_table(
        reader, ["icdwri_nfl"], as_int=True,
        what="application depth pointers", n_rows=n_elements)
    return_flow_columns = _read_element_table(
        reader, type_cols, as_int=True, what="return flow pointers", n_rows=n_elements)
    reuse_columns = _read_element_table(
        reader, type_cols, as_int=True, what="reuse pointers", n_rows=n_elements)

    initial_conditions = _read_element_table(
        reader, ["fsoilmp"] + type_cols, what="initial conditions", n_rows=n_elements)

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

def read_urban_main(path: str | Path, n_elements: int | None = None) -> UrbanFile:
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
         "iceturb", "icrtfurb", "icrufurb", "icurbspec"],
        what="urban element parameters", n_rows=n_elements)
    if element_params is not None:
        _int_columns(reader, element_params,
                     ("icpopul", "icwtruse", "iceturb", "icrtfurb",
                      "icrufurb", "icurbspec"), "urban element parameters")

    initial_conditions = _read_element_table(
        reader, ["fsoilmp", "soil_moisture"], what="initial conditions", n_rows=n_elements)

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
# Land use area files
# ------------------------------------------------------------------

#: First token of a land use data row that starts a new timestep block.
_LU_DATE_RE = r"\d{1,2}/\d{1,2}/\d{4}_\d{1,2}:\d{2}"


def read_land_use_area(
    path: str | Path,
    columns: list[str] | None = None,
) -> LandUseAreaFile:
    """Read an IWFM land use area file (LUFLNP / LUFLP / LUFLU / LUFLNVRV).

    All four root-zone land use area files (non-ponded crops, ponded
    crops, urban, native/riparian vegetation) share this format.  Each
    timestep is a block of one row per element; only the block's first
    row carries the date.  The parse is vectorized — C2VSimFG's 1 GB
    non-ponded crop area file (3.25M rows x 20 crops) reads in about
    two minutes (but needs a few GB of RAM).

    Parameters
    ----------
    path : str or Path
    columns : list[str], optional
        Names for the area columns, e.g. the crop codes from the
        non-ponded ag main (``NonPondedAgFile.crop_codes``) or
        :data:`PONDED_CROP_TYPES`.  Defaults to ``area_1..area_n``
        with n inferred from the data.

    Returns
    -------
    LandUseAreaFile
        ``data`` is long-format: date, element_id, one column per land
        use.  Dates stay strings (recurring-year data uses year 2500).
    """
    import io as _io

    import numpy as np

    reader = IWFMFileReader(path)
    header = reader.read_header()

    keywords: list[str] = []

    def _kw(keyword: str) -> None:
        keywords.append(keyword.split()[0] if keyword else "")

    factor, kw = reader.read_keyed_float()
    _kw(kw)
    n_steps_update, kw = reader.read_keyed_int()
    _kw(kw)
    repeat_freq, kw = reader.read_keyed_int()
    _kw(kw)
    dss_file, kw = reader.read_keyed_value()
    _kw(kw)

    result = LandUseAreaFile(
        header=header,
        factor=factor,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        dss_file=dss_file,
        keywords=keywords,
    )

    lineno0 = reader.lineno
    tail = reader.skip_to_end()
    raw_idx = [i for i, line in enumerate(tail) if not is_comment(line)]
    raw = [tail[i] for i in raw_idx]

    if dss_file:
        # DSS input: IE  LUTYPE  PATH rows instead of inline data.
        # Plain split, not tokenize_data_line — DSS pathnames are full
        # of "/" which the tokenizer would treat as inline comments.
        rows = []
        for line in raw:
            toks = line.split(None, 2)
            if len(toks) < 3:
                break
            rows.append((int(toks[0]), int(toks[1]), toks[2].strip()))
        if rows:
            result.dss_pathnames = pd.DataFrame(
                rows, columns=["element_id", "lu_type", "pathname"])
        return result

    if not raw:
        result.data = None
        return result

    # Vectorized block parse: rows starting with a date open a new
    # timestep block; the date is split off so every row is numeric,
    # then dates forward-fill down their block.
    s = pd.Series(raw).str.lstrip()
    is_date = s.str.match(_LU_DATE_RE)
    if not is_date.iloc[0]:
        raise reader.error(
            "first land use data row does not start with an IWFM date",
            lineno=lineno0 + raw_idx[0] + 1)
    split = s[is_date].str.split(n=1, expand=True)
    bad = [d for d in split[0] if not is_iwfm_date(d)]
    if bad:
        raise reader.error(
            f"land use block date {bad[0]!r} is not a valid IWFM date "
            "(MM/DD/YYYY_HH:MM)")
    body = s.copy()
    body[is_date] = split[1]
    dates = pd.Series(np.nan, index=s.index, dtype=object)
    dates[is_date] = split[0]

    try:
        df = pd.read_csv(_io.StringIO("\n".join(body)), sep=r"\s+",
                         header=None)
    except (ValueError, pd.errors.ParserError) as exc:
        raise reader.error(
            f"land use rows are not rectangular numeric data ({exc})"
        ) from None
    bad_cols = [c for c in df.columns if df[c].dtype == object]
    if bad_cols:
        col = bad_cols[0]
        bad_rows = df.index[pd.to_numeric(df[col], errors="coerce").isna()]
        r = int(bad_rows[0])
        raise reader.error(
            f"land use row column {col + 1} is not a number: "
            f"{df.at[r, col]!r}", lineno=lineno0 + raw_idx[r] + 1)
    n_areas = len(df.columns) - 1
    if columns is not None:
        if len(columns) != n_areas:
            raise ValueError(
                f"{path}: {len(columns)} column names given but the "
                f"file has {n_areas} area columns")
        names = list(columns)
    else:
        names = [f"area_{i + 1}" for i in range(n_areas)]
    df.columns = ["element_id"] + names
    elem = df["element_id"]
    if (elem != elem.round()).any():
        r = int(elem.index[elem != elem.round()][0])
        raise reader.error(
            f"land use row element id is not an integer: {elem[r]!r}",
            lineno=lineno0 + raw_idx[r] + 1)
    df["element_id"] = elem.astype(int)
    df[names] = df[names].astype(float)
    df.insert(0, "date", dates.ffill().to_numpy())

    dup = df.duplicated(["date", "element_id"])
    if dup.any():
        r = int(df.index[dup][0])
        raise reader.error(
            f"element {int(df.at[r, 'element_id'])} appears twice in the "
            f"{df.at[r, 'date']} block — a block is missing its date or "
            "repeats an element", lineno=lineno0 + raw_idx[r] + 1)

    result.data = df
    return result


def _element_areas_from_preprocessor(pp) -> "pd.Series":
    """Element areas (shoelace) from preprocessor nodes + elements.

    Pure numpy — no geopandas needed.  ``node4 == 0`` (triangles) is
    handled by repeating the first vertex, which contributes zero area.
    """
    import numpy as np

    nodes = pp.nodes
    elements = pp.elements
    xs = pd.Series(nodes["x"].to_numpy(float),
                   index=nodes["node_id"].to_numpy(int))
    ys = pd.Series(nodes["y"].to_numpy(float),
                   index=nodes["node_id"].to_numpy(int))

    # copy=True: pandas 3 hands out read-only views (copy-on-write)
    conf = elements[["node1", "node2", "node3", "node4"]].to_numpy(dtype=int, copy=True)
    conf[:, 3] = np.where(conf[:, 3] == 0, conf[:, 0], conf[:, 3])
    x = xs.reindex(conf.ravel()).to_numpy().reshape(conf.shape)
    y = ys.reindex(conf.ravel()).to_numpy().reshape(conf.shape)
    xn = np.roll(x, -1, axis=1)
    yn = np.roll(y, -1, axis=1)
    area = 0.5 * np.abs((x * yn - xn * y).sum(axis=1))
    return pd.Series(area, index=elements["element_id"].to_numpy(int),
                     name="area")


def read_all_land_use_areas(
    rootzone_main,
    element_areas=None,
) -> pd.DataFrame:
    """Read all land use area files of a model into one DataFrame.

    Walks the root-zone sub-component mains (non-ponded ag, ponded ag,
    urban, native/riparian vegetation), reads each one's land use area
    file, converts every column to **areas in the model's plane units**
    (e.g. square feet when node coordinates are in feet), and merges
    them on ``date`` + ``element_id``.

    Each file's conversion factor is applied: files with a non-zero
    FACT have their values multiplied by it.  Files with FACT = 0.0
    hold *fractions of the element area*: when ``element_areas`` is
    given they are multiplied by it (becoming areas); without it the
    fractions are kept as-is, and a warning is raised only if the
    result would mix fractions with area columns from non-zero-FACT
    files.

    Parameters
    ----------
    rootzone_main : RootZoneMain, str, or Path
        A parsed :class:`~iwfm_io.models.rootzone.RootZoneMain` or the
        path to the root zone main file.
    element_areas : optional
        Element areas in model plane units, used to convert
        fraction-based files (FACT = 0.0) to areas.  Accepts a
        ``PreprocessorMain`` (areas are computed from its
        nodes/elements), a ``pd.Series`` indexed by element id, or a
        ``{element_id: area}`` dict.  When omitted, fraction-based
        files keep their fractions.

    Returns
    -------
    pd.DataFrame
        Long-format: ``date``, ``element_id``, then one area column
        per land use — non-ponded crops named by their crop codes,
        ponded crops by :data:`PONDED_CROP_TYPES`, plus ``urban``,
        ``native`` and ``riparian``.  A duplicate name is prefixed
        with its group.  Files whose dates differ (e.g. recurring-year
        vs full time series) merge outer, leaving NaN where a file has
        no block for a date.
    """
    from iwfm_io.models.rootzone import RootZoneMain

    if not isinstance(rootzone_main, RootZoneMain):
        rootzone_main = read_rootzone_main(rootzone_main)

    if element_areas is not None and not isinstance(
            element_areas, (dict, pd.Series)):
        element_areas = _element_areas_from_preprocessor(element_areas)
    if isinstance(element_areas, dict):
        element_areas = pd.Series(element_areas)

    # (role, group label, area-column names — None = crop codes from
    # the sub-main)
    groups = [
        ("nonponded_ag", "nonponded", None),
        ("ponded_ag", "ponded", list(PONDED_CROP_TYPES)),
        ("urban", "urban", ["urban"]),
        ("native_veg", "native_veg", ["native", "riparian"]),
    ]

    merged: pd.DataFrame | None = None
    used: set[str] = set()
    kept_fractions = False
    scaled_areas = False
    for role, label, names in groups:
        main_path = rootzone_main.file_paths.get(role)
        if not main_path:
            continue
        if role == "nonponded_ag":
            sub = read_nonponded_ag_main(main_path)
            names = list(sub.crop_codes)
            area_path = sub.file_paths.get("land_use_area")
        elif role == "ponded_ag":
            area_path = read_ponded_ag_main(main_path).file_paths.get(
                "land_use_area")
        elif role == "urban":
            area_path = read_urban_main(main_path).file_paths.get(
                "land_use_area")
        else:
            area_path = read_native_veg_main(main_path).file_paths.get(
                "land_use_area")
        if not area_path:
            continue

        names = [f"{label}_{n}" if n in used else n for n in names]
        used.update(names)
        lu = read_land_use_area(area_path, columns=names)
        df = lu.data
        if df is None:
            raise ValueError(
                f"{area_path}: DSS-based land use data (DSSFL set) "
                "cannot be combined — read the DSS file directly")

        if lu.factor == 0.0:
            # fractions of the element area
            if element_areas is None:
                kept_fractions = True  # leave the fractions as-is
            else:
                scale = df["element_id"].map(element_areas)
                if scale.isna().any():
                    missing = df.loc[scale.isna(), "element_id"].unique()
                    raise ValueError(
                        f"element_areas is missing element ids "
                        f"{missing[:5].tolist()}...")
                df[names] = df[names].mul(scale.to_numpy(), axis=0)
        else:
            df[names] = df[names] * lu.factor
            scaled_areas = True

        merged = df if merged is None else merged.merge(
            df, on=["date", "element_id"], how="outer")

    if merged is None:
        raise ValueError(
            "root zone main references no land use area files")
    if kept_fractions and scaled_areas:
        import warnings
        warnings.warn(
            "combined land use table mixes units: some files have a "
            "non-zero FACT (columns are areas) while others hold "
            "fractions of the element area and no element_areas= was "
            "given to convert them", stacklevel=2)
    return merged


# ------------------------------------------------------------------
# Native and riparian vegetation main
# ------------------------------------------------------------------

def read_native_veg_main(path: str | Path, n_elements: int | None = None) -> NativeVegFile:
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
        ["cn_native", "cn_riparian", "icetnv", "icetrv", "istrmrv"],
        what="native/riparian element parameters", n_rows=n_elements)
    if element_params is not None:
        _int_columns(reader, element_params,
                     ("icetnv", "icetrv", "istrmrv"),
                     "native/riparian element parameters")

    initial_conditions = _read_element_table(
        reader, ["moisture_native", "moisture_riparian"],
        what="initial conditions", n_rows=n_elements)

    return NativeVegFile(
        header=header,
        file_paths={"land_use_area": _resolve(land_use_area)},
        root_depth_factor=root_depth_factor,
        root_depth_native=root_depth_native,
        root_depth_riparian=root_depth_riparian,
        element_params=element_params,
        initial_conditions=initial_conditions,
    )


# ------------------------------------------------------------------
# Surface flow destinations (DESTFL, v4.12+)
# ------------------------------------------------------------------

#: Matches one "(T,D)" destination tuple, tolerating interior spaces.
_DEST_TUPLE_RE = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)")


def read_surface_flow_dest(path: str | Path) -> SurfaceFlowDestFile:
    """Read a surface flow destination file (e.g. ``SurfaceFlowDest.dat``).

    3-param spec (NDSTN, NSPDSTN, NFQDSTN — no FACT, no DSSFL), then
    rows of ``DATE  (T,D) .. (T,D)`` — one type/destination tuple per
    column.  The v4.12 root-zone soil table's ``icdst*`` pointers index
    these columns; types are 0 = outside, 1 = stream node, 3 = lake,
    5 = groundwater.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SurfaceFlowDestFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()

    with reader.section("time-series spec"):
        n_columns, _ = reader.read_keyed_int()
        n_steps_update, _ = reader.read_keyed_int()
        repeat_freq, _ = reader.read_keyed_int()

    rows: list[dict] = []
    with reader.section("surface flow destinations"):
        while True:
            line = reader.peek_data_line()
            if line is None:
                break
            toks = tokenize_data_line(line)
            if not toks or not is_iwfm_date(toks[0]):
                reader.next_data_line()
                reader.degrade(
                    "expected a data row starting with an IWFM date "
                    f"(MM/DD/YYYY_HH:MM) but found {line.strip()[:60]!r}; "
                    "data after this line was not read")
                break
            reader.next_data_line()
            row: dict = {"date": toks[0]}
            body = re.split(r"\s+/", line, maxsplit=1)[0]
            pairs = _DEST_TUPLE_RE.findall(body)
            if len(pairs) < n_columns:
                raise reader.error(
                    f"SurfaceFlowDest row {toks[0]} has {len(pairs)} of "
                    f"{n_columns} expected (type,dest) tuples")
            for i, (typ, dest) in enumerate(pairs[:n_columns], start=1):
                row[f"type_{i}"] = int(typ)
                row[f"dest_{i}"] = int(dest)
            rows.append(row)

    columns = ["date"]
    for i in range(1, n_columns + 1):
        columns += [f"type_{i}", f"dest_{i}"]
    data = pd.DataFrame(rows, columns=columns) if rows else None

    return SurfaceFlowDestFile(
        header=header,
        n_columns=n_columns,
        n_steps_update=n_steps_update,
        repeat_freq=repeat_freq,
        data=data,
    )
