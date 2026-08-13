"""
Budget-component observations for PEST(++) calibrations.

Budget terms (deep percolation, stream–aquifer interaction, pumping,
storage change, …) per subregion or zone regularize IWFM calibrations —
they constrain the water balance where head data alone cannot. This
module turns IWFM budget output into named observation tables:

:func:`budget_observations` selects components and locations from a
budget (via an ``IOModelAdapter``, a model/Results directory, a budget
``.hdf`` path, or an already-loaded long-form frame — the last covers
z-budgets via ``read_zbudget_hdf``), optionally aggregates in time
(long-term mean or water-year totals), and names each value with the
observation-name codec. The result is a long-form frame ready for the
statistics engine, SMP output, or (once available) paired
output/instruction-file writers.

Location and component labels are slugified for PEST names —
``"Region1 (SR1)"`` → ``region1_sr1``, ``"Deep Percolation"`` →
``deep_percolation`` — while the original labels stay in their own
columns.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Sequence, Union

import pandas as pd

from iwfm_io.pest.names import encode_obs_names

__all__ = ["budget_observations", "slugify_label"]

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_label(label) -> str:
    """Make a budget location/component label safe for PEST names.

    Lowercases and collapses every non-alphanumeric run to a single
    underscore: ``"Region1 (SR1)"`` → ``"region1_sr1"``.
    """
    return _SLUG_RE.sub("_", str(label).lower()).strip("_")


def _budget_frames(source, budget) -> "dict":
    """Resolve *source* to ``{location_label: DataFrame(DatetimeIndex)}``."""
    from iwfm_io.readers.hdf5 import read_budget_hdf

    if isinstance(source, (str, Path)):
        p = Path(source)
        if p.suffix.lower() in (".hdf", ".h5", ".hdf5"):
            return read_budget_hdf(p)["data"]
        from iwfm_io.model_adapter import open_model
        source = open_model(p)
    # duck-typed IOModelAdapter
    hdfs = getattr(source, "_budget_hdfs", None) or {}
    if budget is None:
        raise ValueError(
            f"budget= is required with a model source; available: "
            f"{sorted(hdfs) if hdfs else 'none found'}"
        )
    if budget not in hdfs:
        raise KeyError(
            f"budget {budget!r} not found; available: {sorted(hdfs)}")
    return read_budget_hdf(hdfs[budget])["data"]


def _tidy(frames: dict) -> "pd.DataFrame":
    pieces = []
    for loc, df in frames.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        long = df.reset_index(names="datetime").melt(
            id_vars="datetime", var_name="component", value_name="value")
        long.insert(0, "location", str(loc))
        pieces.append(long)
    if not pieces:
        raise ValueError("no budget data found in source")
    return pd.concat(pieces, ignore_index=True)


def _filter(long, locations, components) -> "pd.DataFrame":
    for col, wanted in (("location", locations), ("component", components)):
        if wanted is None:
            continue
        if isinstance(wanted, str):
            wanted = [wanted]
        slugs = {slugify_label(w) for w in wanted}
        have = long[col].map(slugify_label)
        missing = slugs - set(have)
        if missing:
            raise KeyError(
                f"{col}(s) not found: {sorted(missing)}; available: "
                f"{sorted(set(have))}"
            )
        long = long[have.isin(slugs)]
    return long


def budget_observations(source, budget: Optional[str] = None,
                        locations: Optional[Sequence] = None,
                        components: Optional[Sequence] = None,
                        aggregate: str = "none",
                        obs_type: str = "bud",
                        scheme="standard") -> "pd.DataFrame":
    """Extract named budget-component observations.

    Parameters
    ----------
    source : IOModelAdapter, path, or DataFrame
        A model adapter or model/Results path (with ``budget=``), a
        budget ``.hdf`` file path, or an already-tidied long-form frame
        with ``location, component, datetime, value`` columns (use this
        for z-budgets or custom preprocessing).
    budget : str, optional
        Budget name (e.g. ``"GW"``) — required for model sources.
    locations, components : sequence, optional
        Labels to keep (matched after slugification, so
        ``"Region1 (SR1)"`` and ``"region1_sr1"`` both work).
        Default: everything.
    aggregate : {"none", "mean", "annual"}
        ``none`` — one observation per timestep (dated names);
        ``mean`` — one long-term mean per location × component
        (dateless names, the classic budget-observation setup);
        ``annual`` — water-year sums (named by the Sep-30 WY end).
    obs_type : str, default "bud"
        Observation-type token for the name codec.
    scheme : str or NameScheme
        Observation-name scheme.

    Returns
    -------
    pandas.DataFrame
        Columns ``obsnme, location, component, datetime, value``
        (``datetime`` is NaT for ``aggregate="mean"``). Observation
        names encode ``{obs_type}_{component}_{location}[_{date}]``.

    Examples
    --------
    >>> obs = budget_observations(model, budget="GW",
    ...     components=["Deep Percolation", "Pumping"],
    ...     aggregate="mean")                            # doctest: +SKIP
    """
    if aggregate not in ("none", "mean", "annual"):
        raise ValueError(
            f"aggregate must be 'none', 'mean', or 'annual', got {aggregate!r}")

    if isinstance(source, pd.DataFrame):
        long = source.copy()
        required = {"location", "component", "datetime", "value"}
        if not required <= set(long.columns):
            raise ValueError(
                f"frame source needs columns {sorted(required)}")
    else:
        long = _tidy(_budget_frames(source, budget))

    long = _filter(long, locations, components)
    long["datetime"] = pd.to_datetime(long["datetime"])
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    loc_slug = long["location"].map(slugify_label)
    comp_slug = long["component"].map(slugify_label)
    site = comp_slug + "_" + loc_slug

    if aggregate == "mean":
        out = (long.assign(_site=site)
               .groupby(["_site", "location", "component"], as_index=False)
               ["value"].mean())
        out["datetime"] = pd.NaT
        out["obsnme"] = encode_obs_names(
            obs_type, out["_site"], None, scheme=scheme).values
    elif aggregate == "annual":
        # water year: Oct 1 – Sep 30, labeled by the ending Sep 30
        wy = long["datetime"].sub(pd.Timedelta(seconds=1))
        wy_end = wy.dt.year.where(wy.dt.month < 10, wy.dt.year + 1)
        out = (long.assign(_site=site, _wy=wy_end)
               .groupby(["_site", "location", "component", "_wy"],
                        as_index=False)["value"].sum())
        out["datetime"] = pd.to_datetime(
            out.pop("_wy").astype(str) + "-09-30")
        out["obsnme"] = encode_obs_names(
            obs_type, out["_site"], out["datetime"], scheme=scheme).values
    else:
        out = long.assign(_site=site)
        out["obsnme"] = encode_obs_names(
            obs_type, out["_site"], out["datetime"], scheme=scheme).values

    out = out[["obsnme", "location", "component", "datetime", "value"]]
    return out.sort_values("obsnme").reset_index(drop=True)
