"""Model-to-model comparison utilities.

Answers "what is different between these two models?" at three levels:

1. **Files** — :func:`diff_model_files` checksums every file in two model
   folders and reports which are added, removed, or changed. Useful for
   auditing scenario provenance ("what did they modify for this run?").
2. **Structure and results summary** — :func:`compare_models` combines the
   file diff with grid comparison and head-difference statistics into one
   JSON-serializable report.
3. **Numeric differences** — :func:`head_difference` and
   :func:`budget_difference` return aligned ``B − A`` DataFrames ready for
   plotting or statistics.

Example::

    from iwfm_io import open_model, compare_models, head_difference

    report = compare_models("runs/baseline", "runs/scenario")
    print(report["files"]["changed"])       # which input files were edited
    print(report["heads"]["layer_1"])       # rmse / max drawdown vs baseline

    diff = head_difference("runs/baseline", "runs/scenario", layer=1)
    # DataFrame(DatetimeIndex, one column per node) of scenario − baseline

    # Map the end-of-simulation difference with the existing plot helpers:
    from iwfm_io.plots import plot_contour_map
    plot_contour_map(open_model("runs/baseline"), diff.iloc[-1].values,
                     cmap="coolwarm", label="Head change (ft)")
"""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024  # 1 MB read chunks for hashing


# ---------------------------------------------------------------------------
# File-level diff
# ---------------------------------------------------------------------------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _list_files(root, subdirs=None):
    """Relative posix paths of all files under *root* (or its *subdirs*)."""
    root = Path(root)
    if subdirs:
        starts = [root / s for s in subdirs]
    else:
        starts = [root]
    rels = set()
    for start in starts:
        if not start.is_dir():
            continue
        for p in start.rglob("*"):
            if p.is_file():
                rels.add(p.relative_to(root).as_posix())
    return rels


def diff_model_files(path_a, path_b, subdirs=None, max_workers=8):
    """Checksum-based file comparison of two model folders.

    Compares every file that exists under both folders by SHA-256 (files
    whose sizes differ are marked changed without hashing). Hashing runs
    in a thread pool, so large models compare quickly.

    Parameters
    ----------
    path_a, path_b : str or Path
        The two model root folders (e.g. baseline and scenario).
    subdirs : list of str, optional
        Restrict the comparison to these subfolders, e.g.
        ``["Preprocessor", "Simulation"]`` to compare only model inputs
        and ignore Results. ``None`` compares everything.
    max_workers : int
        Thread count for parallel hashing (default 8).

    Returns
    -------
    dict
        JSON-serializable, with sorted lists of relative paths:
        ``only_in_a``, ``only_in_b``, ``changed``, ``identical``, and the
        integer ``n_compared``.
    """
    path_a, path_b = Path(path_a), Path(path_b)
    files_a = _list_files(path_a, subdirs)
    files_b = _list_files(path_b, subdirs)
    common = sorted(files_a & files_b)

    changed, identical, to_hash = [], [], []
    for rel in common:
        fa, fb = path_a / rel, path_b / rel
        if fa.stat().st_size != fb.stat().st_size:
            changed.append(rel)
        else:
            to_hash.append(rel)

    def _pair_differs(rel):
        return rel, _sha256(path_a / rel) != _sha256(path_b / rel)

    if to_hash:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for rel, differs in pool.map(_pair_differs, to_hash):
                (changed if differs else identical).append(rel)

    return {
        "only_in_a": sorted(files_a - files_b),
        "only_in_b": sorted(files_b - files_a),
        "changed": sorted(changed),
        "identical": sorted(identical),
        "n_compared": len(common),
    }


# ---------------------------------------------------------------------------
# Numeric differences
# ---------------------------------------------------------------------------

def _as_adapter(model):
    """Accept a model root path or an already-open IOModelAdapter."""
    from iwfm_io.model_adapter import IOModelAdapter, open_model
    if isinstance(model, IOModelAdapter):
        return model
    return open_model(model)


def _aligned_difference(df_a, df_b):
    """Return ``df_b − df_a`` on their common index and columns."""
    idx = df_a.index.intersection(df_b.index)
    cols = [c for c in df_a.columns if c in set(df_b.columns)]
    return df_b.loc[idx, cols] - df_a.loc[idx, cols]


def head_difference(a, b, layer, begin_date=None, end_date=None):
    """Groundwater head difference ``B − A`` for one layer.

    Parameters
    ----------
    a, b : str, Path, or IOModelAdapter
        The two models (baseline first). Paths are opened via
        :func:`~iwfm_io.open_model`.
    layer : int
        1-based layer number.
    begin_date, end_date : str, optional
        IWFM date strings to restrict the period.

    Returns
    -------
    pandas.DataFrame
        DatetimeIndex over the common simulation period, one column per
        common node. Positive values = higher heads in *b*.
    """
    a, b = _as_adapter(a), _as_adapter(b)
    return _aligned_difference(
        a.heads_df(layer, begin_date=begin_date, end_date=end_date),
        b.heads_df(layer, begin_date=begin_date, end_date=end_date),
    )


def budget_difference(a, b, budget, location, interval=None,
                      begin_date=None, end_date=None):
    """Budget difference ``B − A`` for one budget and location.

    Parameters
    ----------
    a, b : str, Path, or IOModelAdapter
        The two models (baseline first).
    budget : str
        Budget name as discovered by ``open_model`` (e.g. ``"GW"``) —
        see ``model.describe()["results"]["budgets"]``.
    location : int or str
        1-based location index or location name.
    interval : str, optional
        ``"1MON"`` or ``"1YEAR"`` for temporal aggregation.
    begin_date, end_date : str, optional
        IWFM date strings to restrict the period.

    Returns
    -------
    pandas.DataFrame
        DatetimeIndex over the common period, one column per common
        budget component. Positive values = larger in *b*.
    """
    a, b = _as_adapter(a), _as_adapter(b)
    kw = dict(interval=interval, begin_date=begin_date, end_date=end_date)
    return _aligned_difference(
        a.budget_df(budget, location, **kw),
        b.budget_df(budget, location, **kw),
    )


# ---------------------------------------------------------------------------
# One-call comparison report
# ---------------------------------------------------------------------------

def compare_models(a, b, layers=None, include_files=True,
                   file_subdirs=None, max_workers=8):
    """Compare two models and return a JSON-serializable report.

    Combines a checksum file diff, grid comparison, head-difference
    statistics per layer, and budget availability into one summary —
    the comparison counterpart of ``describe()``.

    Parameters
    ----------
    a, b : str, Path, or IOModelAdapter
        The two models (baseline first). Paths are opened via
        :func:`~iwfm_io.open_model`.
    layers : list of int, optional
        Layers for head statistics. Default: all layers of model *a*.
    include_files : bool
        Run :func:`diff_model_files` when both model root folders are
        known (default True).
    file_subdirs : list of str, optional
        Passed to :func:`diff_model_files` (e.g. ``["Preprocessor",
        "Simulation"]`` to diff inputs only).
    max_workers : int
        Thread count for parallel file hashing.

    Returns
    -------
    dict
        Keys: ``grid``, ``files``, ``heads``, ``budgets``. Sections that
        cannot be computed (e.g. a model without heads output) are None.
    """
    a, b = _as_adapter(a), _as_adapter(b)
    report = {}

    # -- Files ----------------------------------------------------------
    report["files"] = None
    if include_files and a._root and b._root:
        report["files"] = diff_model_files(
            a._root, b._root, subdirs=file_subdirs, max_workers=max_workers)

    # -- Grid -----------------------------------------------------------
    def _grid():
        na, nb = a.nodes_df(), b.nodes_df()
        same_counts = (a.n_nodes == b.n_nodes
                       and a.n_elements == b.n_elements
                       and a.n_layers == b.n_layers)
        same_coords = bool(
            same_counts
            and np.allclose(na[["x", "y"]].values, nb[["x", "y"]].values)
        )
        return {
            "identical": same_coords,
            "n_nodes": [int(a.n_nodes), int(b.n_nodes)],
            "n_elements": [int(a.n_elements), int(b.n_elements)],
            "n_layers": [int(a.n_layers), int(b.n_layers)],
        }

    try:
        report["grid"] = _grid()
    except Exception:
        report["grid"] = None

    # -- Heads ----------------------------------------------------------
    report["heads"] = None
    if a._heads_hdf and b._heads_hdf:
        heads = {}
        for layer in layers or range(1, a.n_layers + 1):
            try:
                diff = head_difference(a, b, layer)
                vals = diff.values
                flat_max = np.unravel_index(np.argmax(np.abs(vals)), vals.shape)
                heads[f"layer_{layer}"] = {
                    "rmse": float(np.sqrt(np.mean(vals ** 2))),
                    "mean_diff": float(vals.mean()),
                    "max_abs_diff": float(np.abs(vals).max()),
                    "max_abs_diff_node": str(diff.columns[flat_max[1]]),
                    "max_abs_diff_date": str(diff.index[flat_max[0]].date()),
                }
            except Exception as exc:
                logger.warning("head comparison failed for layer %s: %s",
                               layer, exc)
                heads[f"layer_{layer}"] = None
        report["heads"] = heads

    # -- Budgets --------------------------------------------------------
    buds_a, buds_b = set(a._budget_hdfs), set(b._budget_hdfs)
    report["budgets"] = {
        "common": sorted(buds_a & buds_b),
        "only_in_a": sorted(buds_a - buds_b),
        "only_in_b": sorted(buds_b - buds_a),
    }

    return report
