"""
Readers for miscellaneous IWFM files (SWShed, UnsatZone).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from iwfm_io._parser import IWFMFileReader
from iwfm_io._tokens import tokenize_data_line
from iwfm_io.models.misc import SWShedFile, UnsatZoneFile
from iwfm_io.readers._param_blocks import LineCursor


def read_swshed(path: str | Path) -> SWShedFile:
    """Read the IWFM small watershed file (e.g. ``SWShed.dat``).

    Parses the watershed definitions (drainage area, receiving stream
    node, and the groundwater nodes that receive baseflow), the root
    zone parameters, the aquifer parameters, and the initial conditions.
    The root-zone table's ``irns`` and ``icets`` columns are column
    numbers in the Precipitation and ET data files respectively.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    SWShedFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Output file paths
    budget_file, _ = reader.read_keyed_path(base_dir)
    final_file, _ = reader.read_keyed_path(base_dir)
    file_paths = {"budget": budget_file, "final": final_file}

    # Number of watersheds and conversion factors
    n_watersheds, _ = reader.read_keyed_int()
    facta, _ = reader.read_keyed_float()
    factq, _ = reader.read_keyed_float()
    tunitq, _ = reader.read_keyed_value()

    config = {"facta": facta, "factq": factq, "tunitq": tunitq}

    # Remaining sections
    raw_lines = reader.skip_to_end()

    watershed_data = None
    watershed_nodes = None
    rootzone_params = None
    aquifer_params = None
    initial_conditions = None
    try:
        cursor = LineCursor(raw_lines)

        # ---- Watershed definitions ----
        # ID AREAS IWBTS NWB IWB QMAXWB, then NWB-1 continuation rows
        # of IWB QMAXWB.  QMAXWB < 0 encodes the receiving layer number.
        ws_rows: list[dict] = []
        node_rows: list[dict] = []
        for _ in range(n_watersheds):
            toks = tokenize_data_line(cursor.next())
            ws_id = int(float(toks[0]))
            n_nodes = int(float(toks[3]))
            ws_rows.append({
                "id": ws_id,
                "area": float(toks[1]),
                "stream_node": int(float(toks[2])),
                "n_gw_nodes": n_nodes,
            })
            if n_nodes > 0:
                node_rows.append({
                    "watershed_id": ws_id,
                    "gw_node": int(float(toks[4])),
                    "qmax": float(toks[5]),
                })
                for _ in range(n_nodes - 1):
                    ctoks = tokenize_data_line(cursor.next())
                    node_rows.append({
                        "watershed_id": ws_id,
                        "gw_node": int(float(ctoks[0])),
                        "qmax": float(ctoks[1]),
                    })
        watershed_data = pd.DataFrame(ws_rows)
        watershed_nodes = pd.DataFrame(node_rows)

        # ---- Root zone parameters ----
        for kw, cast in (("TOLER", float), ("ITERMAX", int),
                         ("FACTL", float), ("FACTCN", float),
                         ("FACTK", float), ("TUNITK", str)):
            if cursor.peek_keyword() == kw:
                config[kw.lower()] = cast(cursor.read_keyed_value()[0])
        rz_cols = ["id", "irns", "frns", "icets", "wp", "fc", "porosity",
                   "lambda", "root_depth", "soil_k", "rhc", "cn"]
        rz_rows = []
        for _ in range(n_watersheds):
            toks = tokenize_data_line(cursor.next())
            rz_rows.append({c: float(t) for c, t in zip(rz_cols, toks)})
        rootzone_params = pd.DataFrame(rz_rows, columns=rz_cols)
        for c in ("id", "irns", "icets", "rhc", "cn"):
            rootzone_params[c] = rootzone_params[c].astype(int)

        # ---- Aquifer parameters ----
        for kw, cast in (("FACTGW", float), ("FACTT", float),
                         ("TUNITT", str)):
            if cursor.peek_keyword() == kw:
                config[kw.lower()] = cast(cursor.read_keyed_value()[0])
        aq_cols = ["id", "gw_threshold_depth", "gw_max_depth",
                   "surface_flow_recession", "baseflow_recession"]
        aq_rows = []
        for _ in range(n_watersheds):
            toks = tokenize_data_line(cursor.next())
            aq_rows.append({c: float(t) for c, t in zip(aq_cols, toks)})
        aquifer_params = pd.DataFrame(aq_rows, columns=aq_cols)
        aquifer_params["id"] = aquifer_params["id"].astype(int)

        # ---- Initial conditions ----
        if cursor.peek_keyword() == "FACT":
            config["fact_ic"] = float(cursor.read_keyed_value()[0])
        ic_cols = ["id", "soil_moisture", "gw_storage"]
        ic_rows = []
        for _ in range(n_watersheds):
            toks = tokenize_data_line(cursor.next())
            ic_rows.append({c: float(t) for c, t in zip(ic_cols, toks)})
        initial_conditions = pd.DataFrame(ic_rows, columns=ic_cols)
        initial_conditions["id"] = initial_conditions["id"].astype(int)
    except (StopIteration, ValueError, IndexError) as exc:
        import warnings
        warnings.warn(
            f"SWShed file only partially parsed ({exc}); unparsed "
            "sections will be missing from written output")

    return SWShedFile(
        header=header,
        file_paths=file_paths,
        n_watersheds=n_watersheds,
        config=config,
        watershed_data=watershed_data,
        watershed_nodes=watershed_nodes,
        rootzone_params=rootzone_params,
        aquifer_params=aquifer_params,
        initial_conditions=initial_conditions,
    )


def read_unsatzone(path: str | Path) -> UnsatZoneFile:
    """Read the IWFM unsaturated zone file (e.g. ``UnsatZone.dat``).

    Parses the per-element unsaturated zone parameter table (NGROUP=0
    layout: one row per element with all unsaturated layers on the same
    line) and the initial moisture conditions.  Parametric-grid layouts
    (NGROUP>0) are kept raw.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    UnsatZoneFile
    """
    reader = IWFMFileReader(path)
    header = reader.read_header()
    base_dir = Path(path).parent

    # Main parameters
    n_unsat_layers, _ = reader.read_keyed_int()
    convergence, _ = reader.read_keyed_float()
    max_iterations, _ = reader.read_keyed_int()

    # Output file paths
    budget_file, _ = reader.read_keyed_path(base_dir)
    zbudget_file, _ = reader.read_keyed_path(base_dir)
    final_file, _ = reader.read_keyed_path(base_dir)
    file_paths = {
        "budget": budget_file,
        "zbudget": zbudget_file,
        "final": final_file,
    }

    # Remaining sections
    raw_lines = reader.skip_to_end()

    config: dict = {}
    ngroup = None
    element_params = None
    initial_moisture = None
    param_names = ["thickness", "porosity", "pore_size_index", "k", "rhc"]
    try:
        cursor = LineCursor(raw_lines)
        ngroup = int(cursor.read_keyed_value()[0])

        factor_vals = tokenize_data_line(cursor.next())
        for name, val in zip(("fx", "fd", "fk"), factor_vals):
            config[name] = float(val)
        if cursor.peek_keyword() == "TUNITZ":
            config["tunitz"] = cursor.read_keyed_value()[0]

        if ngroup == 0:
            # One row per element: IE + (PD PN PI PK PRHC) per layer.
            n_row_tokens = 1 + 5 * n_unsat_layers
            records = []
            while not cursor.eof:
                toks = tokenize_data_line(cursor.peek())
                if len(toks) != n_row_tokens:
                    break
                try:
                    vals = [float(t) for t in toks]
                except ValueError:
                    break
                cursor.next()
                elem = int(vals[0])
                for layer in range(n_unsat_layers):
                    p = vals[1 + 5 * layer: 6 + 5 * layer]
                    records.append([elem, layer + 1] + p)
            if records:
                element_params = pd.DataFrame(
                    records, columns=["element_id", "layer"] + param_names)
                element_params["rhc"] = element_params["rhc"].astype(int)

        # Initial moisture: IE + one value per unsaturated layer
        # (IE = 0 applies the values to all elements).
        ic_rows = []
        while not cursor.eof:
            toks = tokenize_data_line(cursor.peek())
            try:
                vals = [float(t) for t in toks]
            except ValueError:
                break
            if len(vals) != 1 + n_unsat_layers:
                break
            cursor.next()
            row = {"element_id": int(vals[0])}
            for i, v in enumerate(vals[1:], start=1):
                row[f"moisture_layer_{i}"] = v
            ic_rows.append(row)
        if ic_rows:
            initial_moisture = pd.DataFrame(ic_rows)
    except (StopIteration, ValueError, IndexError) as exc:
        import warnings
        warnings.warn(
            f"UnsatZone file only partially parsed ({exc}); unparsed "
            "sections will be missing from written output")

    return UnsatZoneFile(
        header=header,
        n_unsat_layers=n_unsat_layers,
        convergence=convergence,
        max_iterations=max_iterations,
        file_paths=file_paths,
        config=config,
        ngroup=ngroup,
        element_params=element_params,
        initial_moisture=initial_moisture,
    )
