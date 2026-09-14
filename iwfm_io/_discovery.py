"""``open_model()`` — one-call model opening with file discovery.

Finds a model's preprocessor and simulation main files, follows the GW
and stream mains for the component files the adapter can serve DLL-free,
classifies every HDF5 result file by its internal structure, and returns
a wired :class:`~iwfm_io.model_adapter.IOModelAdapter`.  The public entry
point is ``iwfm_io.open_model`` (also re-exported from
``iwfm_io.model_adapter``).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_MAIN_SUFFIXES = (".in", ".dat")

def _find_main_file(root, subdir, patterns):
    """Find a main input file under *root* or *root/subdir*.

    Looks for files with a ``.in``/``.dat`` suffix whose name contains one
    of *patterns* (case-insensitive), preferring names that contain "main".
    """
    search_dirs = [root / subdir, root]
    candidates = []
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            name = f.name.lower()
            if (f.is_file() and f.suffix.lower() in _MAIN_SUFFIXES
                    and any(p in name for p in patterns)):
                candidates.append(f)
        if candidates:
            break
    if not candidates:
        return None
    _stale = ("copy", "backup", "bak", "old", "orig", "(1)", "~")

    def rank(f):
        name = f.name.lower()
        return (0 if "main" not in name else -1,      # prefer *main*
                1 if any(t in name for t in _stale) else 0,   # skip copies
                len(name), name)
    return sorted(candidates, key=rank)[0]


def _sniff_simulation_main(path, max_lines=500):
    """Return True if *path* looks like a simulation main file.

    The simulation main is the only input file with a keyed ``/ BDT``
    line (simulation begin date). Only the first *max_lines* lines are
    scanned so large data files are cheap to reject.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    return False
                if line[:1] in ("C", "c", "*", "/") or not line.strip():
                    continue
                if re.search(r"/\s*BDT\b", line):
                    return True
    except OSError:
        return False
    return False


def _find_simulation_main(root):
    """Find the simulation main file under *root*.

    Tries name patterns first, then falls back to sniffing file contents —
    real-world models often use names the patterns miss (e.g. C2VSimFG's
    ``C2VSimFG.in``).
    """
    found = _find_main_file(root, "Simulation", ("simulation", "sim_"))
    if found is not None:
        return found
    for d in (root / "Simulation", root):
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir(), key=lambda p: (p.suffix.lower() != ".in", p.name)):
            if (f.is_file() and f.suffix.lower() in _MAIN_SUFFIXES
                    and _sniff_simulation_main(f)):
                return f
    return None


def _classify_hdf(path, n_head_columns=None):
    """Classify a results HDF5 file by its internal structure.

    Returns one of ``"budget"``, ``"hydrograph"``, ``"heads"``,
    ``"zbudget"``, or None if the file cannot be read.
    """
    import h5py
    try:
        with h5py.File(path, "r") as f:
            keys = [k for k in f.keys() if k != "Attributes"]
            if not keys:
                return None
            if any(isinstance(f[k], h5py.Group) for k in keys):
                return "zbudget"
            attrs = f["Attributes"].attrs if "Attributes" in f else {}
            if any("DataColumnTypes" in k for k in attrs):
                return "budget"
            descriptor = attrs.get("Descriptor", b"")
            if isinstance(descriptor, bytes):
                descriptor = descriptor.decode(errors="replace")
            if "budget" in str(descriptor).lower():
                return "budget"
            n_cols = f[keys[0]].shape[1] if f[keys[0]].ndim == 2 else None
            if len(keys) == 1 and (
                    (n_head_columns and n_cols == n_head_columns)
                    or "headall" in path.stem.lower()):
                return "heads"
            if len(keys) > 1:
                return "budget"
            return "hydrograph"
    except Exception as exc:
        logger.warning("Could not classify %s: %s", path.name, exc)
        raise _UnreadableResult(path, exc) from exc


class _UnreadableResult(Exception):
    """A results file that could not be opened/classified."""

    def __init__(self, path, exc):
        super().__init__(f"{Path(path).name}: {exc}")
        self.path = Path(path)
        self.reason = f"{type(exc).__name__}: {exc}"


def open_model(path, preprocessor=None, simulation=None, results_dir=None,
               strict=True):
    """Open an IWFM model from its folder — the simplest way to read a model.

    No DLL required; works on any operating system. Point it at the model's
    root folder and it finds the preprocessor and simulation main files and
    all HDF5 result files automatically::

        from iwfm_io import open_model

        model = open_model("path/to/my_model")
        print(model.describe())          # what does this model contain?
        model.nodes_df()                 # grid nodes as a GeoDataFrame
        model.heads_df(layer=1)          # simulated heads, one column per node
        model.budget_df("GW", location=1)  # groundwater budget time series

    Parameters
    ----------
    path : str or Path
        The model root folder (the one containing ``Preprocessor/``,
        ``Simulation/`` and ``Results/``), or a direct path to the
        preprocessor or simulation main file.
    preprocessor : str or Path, optional
        Explicit path to the preprocessor main file. Overrides discovery.
    simulation : str or Path, optional
        Explicit path to the simulation main file. Overrides discovery.
    results_dir : str or Path, optional
        Explicit results folder. Overrides discovery (default:
        ``<root>/Results``).
    strict : bool
        Reader mode for every input file read now or lazily later
        through the adapter.  ``True`` (default): malformed input raises
        :class:`~iwfm_io.IWFMParseError` naming the file, line and
        section.  ``False``: readers warn (:class:`~iwfm_io.IWFMReadWarning`)
        and keep what they could parse.  Equivalent to wrapping the call
        in :func:`iwfm_io.strict_mode`.

    Returns
    -------
    IOModelAdapter
        Ready to use. Call :meth:`~IOModelAdapter.describe` to see what
        was found.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist, or no preprocessor main file can be
        located (the grid geometry is required for everything else).
    """
    from iwfm_io._strict import strict_mode

    with strict_mode(strict):
        return _open_model(path, preprocessor, simulation, results_dir,
                           strict)


def _open_model(path, preprocessor, simulation, results_dir, strict):
    from iwfm_io.model_adapter import IOModelAdapter
    from iwfm_io.readers.preprocessor import read_preprocessor_main
    from iwfm_io.readers.simulation import read_simulation_main

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model path does not exist: {path}")

    # Resolve the model root folder
    path = path.resolve()
    if path.is_dir():
        root = path
    else:
        # A main file was passed directly — classify it and derive the root
        name = path.name.lower()
        if "preproc" in name and preprocessor is None:
            preprocessor = path
        elif simulation is None:
            simulation = path
        # the root is the folder above Preprocessor/ or Simulation/;
        # a main file sitting in the model root keeps that root
        parent = path.parent
        if parent.name.lower() in ("preprocessor", "simulation"):
            root = parent.parent
        else:
            root = parent

    # Discover main files
    if preprocessor is None:
        preprocessor = _find_main_file(root, "Preprocessor", ("preproc",))
    if simulation is None:
        simulation = _find_simulation_main(root)
    if preprocessor is None:
        raise FileNotFoundError(
            f"No preprocessor main file found under {root}.\n"
            "Expected e.g. Preprocessor/PreProcessor_MAIN.IN. Pass the path "
            "explicitly: open_model(root, preprocessor='path/to/main.IN')"
        )

    pp = read_preprocessor_main(preprocessor, follow_references=True)

    sim = None
    if simulation is not None:
        try:
            sim = read_simulation_main(simulation)
        except Exception as exc:
            logger.warning(
                "Could not parse simulation main file %s: %s", simulation, exc)

    # Follow the GW and stream mains for component data that the adapter
    # can serve DLL-free (tile drains, bypasses, aquifer parameters).
    gw_main = None
    stream_main = None
    tile_drain = None
    bypass_specs = None
    well_spec = None
    diver_specs = None
    if sim is not None:
        gw_path = sim.file_paths.get("gw_main")
        if gw_path and Path(gw_path).is_file():
            try:
                from iwfm_io.readers.groundwater import (
                    read_gw_main, read_pump_main, read_tile_drain, read_well_spec)
                gw_main = read_gw_main(gw_path)
                td_path = gw_main.file_paths.get("tile_drain")
                if td_path and Path(td_path).is_file():
                    tile_drain = read_tile_drain(td_path)
                pump_path = gw_main.file_paths.get("pump_main")
                if pump_path and Path(pump_path).is_file():
                    well_path = read_pump_main(pump_path).file_paths.get("well")
                    if well_path and Path(well_path).is_file():
                        well_spec = read_well_spec(well_path)
            except Exception as exc:
                logger.warning("Could not parse GW main/children: %s", exc)
        st_path = sim.file_paths.get("stream_main")
        if st_path and Path(st_path).is_file():
            try:
                from iwfm_io.readers.stream import (
                    read_bypass_specs, read_diver_specs, read_stream_main)
                stream_main = read_stream_main(st_path)
                bp_path = stream_main.file_paths.get("bypass_specs")
                if bp_path and Path(bp_path).is_file():
                    bypass_specs = read_bypass_specs(bp_path)
                dv_path = stream_main.file_paths.get("diver_specs")
                if dv_path and Path(dv_path).is_file():
                    diver_specs = read_diver_specs(dv_path)
            except Exception as exc:
                logger.warning("Could not parse stream main/children: %s", exc)

    # Discover and classify result HDF5 files
    if results_dir is None:
        results_dir = root / "Results"
    else:
        results_dir = Path(results_dir)

    heads_hdf = None
    budget_hdfs = {}
    hydrograph_hdfs = {}
    zbudget_hdfs = {}
    results_errors = []
    if results_dir.is_dir():
        n_head_columns = None
        try:
            n_nodes = len(pp.nodes)
            n_head_columns = n_nodes * pp.n_layers
        except Exception:
            pass
        for f in sorted(results_dir.glob("*.hdf")):
            try:
                kind = _classify_hdf(f, n_head_columns)
            except _UnreadableResult as bad:
                results_errors.append({"path": str(bad.path),
                                       "error": bad.reason})
                continue
            if kind == "heads":
                heads_hdf = f
            elif kind == "budget":
                budget_hdfs[f.stem] = f
            elif kind == "hydrograph":
                hydrograph_hdfs[f.stem] = f
            elif kind == "zbudget":
                zbudget_hdfs[f.stem] = f
        if heads_hdf is None:
            # A fresh simulation run writes text heads (GWHeadAll.out);
            # the HDF equivalent only exists once the DLL has opened the
            # model in inquiry mode. Fall back to the text file.
            for f in sorted(results_dir.glob("*.out")):
                if "headall" in f.stem.lower():
                    heads_hdf = f
                    break

    # Text .bud budgets (packaged/older models often ship these instead
    # of budget HDFs; the Budget post-processor also writes them).  HDF
    # wins when the same budget exists in both formats — matched on a
    # normalized stem so e.g. Strm.bud defers to StrmBud.hdf.
    import re as _re

    def _budget_stem(name):
        norm = _re.sub(r"[^A-Z0-9]", "", str(name).upper())
        return norm[:-3] if norm.endswith("BUD") else norm

    budget_texts = {}
    hdf_stems = {_budget_stem(k) for k in budget_hdfs}
    for bud_dir in (results_dir, root / "Budget"):
        if not bud_dir.is_dir():
            continue
        for f in sorted(bud_dir.glob("*.bud")):
            key = f.stem
            if _budget_stem(key) in hdf_stems or key in budget_texts:
                continue
            budget_texts[key] = f

    adapter = IOModelAdapter(
        preprocessor=pp,
        simulation=sim,
        heads_hdf=heads_hdf,
        budget_hdfs=budget_hdfs,
        hydrograph_hdfs=hydrograph_hdfs,
        stream_main=stream_main,
        bypass_specs=bypass_specs,
        tile_drain=tile_drain,
        zbudget_hdfs=zbudget_hdfs,
        gw_main=gw_main,
        well_spec=well_spec,
        diver_specs=diver_specs,
        budget_texts=budget_texts,
        strict=strict,
    )
    adapter._root = root
    adapter._results_errors = results_errors
    return adapter
