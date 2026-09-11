"""
Stream gauges: metadata, hydrograph linking, and series extraction.

The stream-side counterpart of the well/GWL machinery in
:mod:`iwfm_io.wells`, minus the vertical dimension: stream flow and
stage hydrographs attach to a single stream node, so linking and
extraction are one-to-one.

The **`gauge_metadata` frame** is a documented schema, not a file
format — primary facts only, persisted (or not) with plain pandas:

    gauge_id         stable user identity (required, unique)
    group, seq       user spatial identifier + within-group order
    site_code        e.g. a USGS/CDEC station id (the usual link key)
    hydrograph_name  explicit link override when it differs

Workflow::

    link = link_stream_hydrographs(gauge_metadata, stream_main)
    flows = stream_hydrograph_series(link, read_hydrograph_hdf(...))
    gauge_metadata = assign_gauge_sequences(gauge_metadata, link)

Downstream, the existing calibration machinery applies unchanged:
``accretion_depletion`` for gauge pairs, ``match_sim_to_obs`` /
``residual_stats`` for pairing and metrics, and the ``"grouped"``
observation-name scheme for location-ordered names.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from iwfm_io.wells import _fill_sequences, normalize_hydrograph_output

__all__ = ["validate_gauge_metadata", "GaugeLink",
           "link_stream_hydrographs", "stream_hydrograph_series",
           "assign_gauge_sequences"]

logger = logging.getLogger(__name__)

GAUGE_METADATA_REQUIRED = ("gauge_id",)


def validate_gauge_metadata(df) -> "list":
    """Check a gauge_metadata frame; returns problem strings (empty = OK)."""
    problems = []
    for col in GAUGE_METADATA_REQUIRED:
        if col not in df.columns:
            problems.append(f"missing required column {col!r}")
    if "gauge_id" in df.columns:
        ids = df["gauge_id"]
        if ids.isna().any():
            problems.append(f"{int(ids.isna().sum())} null gauge_id value(s)")
        dup = ids[ids.notna() & ids.astype(str).duplicated()]
        if len(dup):
            problems.append(
                f"duplicate gauge_id(s): {sorted(set(dup.astype(str)))[:5]}")
    if "seq" in df.columns and df["seq"].notna().any():
        if "group" not in df.columns:
            problems.append("seq present but no group column")
        else:
            grouped = df[df["seq"].notna()]
            dup = grouped.duplicated(subset=["group", "seq"])
            if dup.any():
                problems.append(
                    f"{int(dup.sum())} duplicate (group, seq) pair(s)")
    return problems


@dataclass
class GaugeLink:
    """Result of :func:`link_stream_hydrographs`.

    Attributes
    ----------
    links : pandas.DataFrame
        One row per matched hydrograph entry: ``gauge_id, hyd_id``
        (1-based spec position — the output-column order),
        ``node_id, name``.
    unmatched_gauges : list
        ``gauge_id`` values with no hydrograph entry.
    orphan_names : list
        Spec names with no metadata row.
    ihsqr : int or None
        The file's output-type flag (0 flow, 1 stage, 2 both) when the
        source carried it.
    n_specs : int or None
        Total number of hydrograph spec entries (NOUTR) — the width of
        one output block, needed to locate the stage block when
        ``ihsqr = 2``.
    """

    links: "pd.DataFrame"
    unmatched_gauges: "list"
    orphan_names: "list"
    ihsqr: Optional[int] = None
    n_specs: Optional[int] = None

    def summary(self) -> dict:
        return {
            "n_gauges_linked": int(self.links["gauge_id"].nunique()),
            "n_hydrographs_linked": int(len(self.links)),
            "n_unmatched_gauges": len(self.unmatched_gauges),
            "n_orphan_names": len(self.orphan_names),
            "ihsqr": self.ihsqr,
        }


def _spec_frame(stream_main) -> "tuple[pd.DataFrame, Optional[int]]":
    """Resolve *stream_main* to (specs frame, ihsqr)."""
    ihsqr = None
    specs = stream_main
    if isinstance(specs, (str,)) or hasattr(specs, "__fspath__"):
        from iwfm_io.readers.stream import read_stream_main
        specs = read_stream_main(specs)
    if hasattr(specs, "hydrograph_specs"):
        ihsqr = getattr(specs, "config", {}).get("ihsqr")
        specs = specs.hydrograph_specs
    if isinstance(specs, list):
        specs = pd.DataFrame(specs)
    if not isinstance(specs, pd.DataFrame) or specs.empty:
        raise ValueError(
            "no stream hydrograph specs found (NOUTR = 0, or an "
            "unsupported source type)")
    for col in ("node_id", "name"):
        if col not in specs.columns:
            raise ValueError(f"hydrograph specs have no column {col!r}")
    specs = specs.reset_index(drop=True)
    if "hyd_id" not in specs.columns:
        specs["hyd_id"] = range(1, len(specs) + 1)
    return specs, ihsqr


def link_stream_hydrographs(gauge_metadata, stream_main,
                            on: str = "site_code",
                            name_sep: Optional[str] = None) -> GaugeLink:
    """Link gauge metadata to the Stream MAIN hydrograph entries by name.

    Parameters
    ----------
    gauge_metadata : pandas.DataFrame
    stream_main : StreamMain, path, spec list, or DataFrame
        The parsed stream main (its ``hydrograph_specs`` +
        ``config["ihsqr"]`` are used), a path to it, or the specs
        directly (``node_id, name`` rows in file order).
    on : str, default "site_code"
        Metadata column matched against spec names (case-insensitive,
        whitespace-stripped). Duplicate non-null values are an error.
    name_sep : str, optional
        When given, only the part of each spec name before the last
        *name_sep* is matched (stem matching, like the wells-side
        ``%layer`` convention). Default: full-name matching.

    Returns
    -------
    GaugeLink
    """
    problems = validate_gauge_metadata(gauge_metadata)
    if problems:
        raise ValueError("invalid gauge_metadata: " + "; ".join(problems))
    if on not in gauge_metadata.columns:
        raise ValueError(f"gauge_metadata has no column {on!r}")
    specs, ihsqr = _spec_frame(stream_main)

    names = specs["name"].astype(str).str.strip()
    stems = names
    if name_sep is not None:
        stems = names.str.rsplit(name_sep, n=1).str[0].str.strip()

    key = gauge_metadata[on].astype(str).str.strip()
    nonnull = key[gauge_metadata[on].notna()]
    dup = nonnull[nonnull.str.casefold().duplicated()]
    if len(dup):
        raise ValueError(
            f"gauge_metadata[{on!r}] has duplicate value(s): "
            f"{sorted(set(dup))[:5]} — ambiguous join")
    lookup = {k.casefold(): g for k, g in
              zip(nonnull, gauge_metadata.loc[nonnull.index, "gauge_id"])}

    matched = stems.str.casefold().map(lookup)
    ok = matched.notna()
    links = pd.DataFrame({
        "gauge_id": matched[ok].values,
        "hyd_id": specs.loc[ok, "hyd_id"].astype(int).values,
        "node_id": pd.to_numeric(specs.loc[ok, "node_id"],
                                 errors="coerce").values,
        "name": names[ok].values,
    }).sort_values("hyd_id").reset_index(drop=True)

    linked = set(links["gauge_id"])
    link = GaugeLink(
        links=links,
        unmatched_gauges=[g for g in gauge_metadata["gauge_id"]
                          if g not in linked],
        orphan_names=sorted(set(stems[~ok])),
        ihsqr=ihsqr,
        n_specs=len(specs),
    )
    logger.info("link_stream_hydrographs: %s", link.summary())
    return link


def stream_hydrograph_series(link: GaugeLink, hyd_output,
                             ihsqr: Optional[int] = None,
                             quantity: Optional[str] = None
                             ) -> "pd.DataFrame":
    """Extract per-gauge series from stream hydrograph output.

    Parameters
    ----------
    link : GaugeLink
    hyd_output : pandas.DataFrame
        Time-indexed hydrograph output; columns may be hydrograph ids
        (ints) or positional ``col_N`` labels.
    ihsqr : int, optional
        Output-type flag override (default: the link's). ``0`` (flow)
        and ``1`` (stage) map column *N* to spec entry *N*. ``2``
        (both) writes two blocks in spec order — flows in columns
        1..NOUTR, then stages in columns NOUTR+1..2*NOUTR (layout
        validated against a sample-model IHSQR=2 run whose flow block
        is identical to the IHSQR=0 output).
    quantity : {"flow", "stage"}, optional
        Which block to extract from an ``ihsqr = 2`` output (required
        there, since the file carries both). For single-quantity
        outputs it may be given as an assertion of what the file
        contains and raises on mismatch.

    Returns
    -------
    pandas.DataFrame
        time × gauge_id. Requires exactly one linked hydrograph per
        gauge (ambiguous links raise).
    """
    ihsqr = link.ihsqr if ihsqr is None else ihsqr
    if quantity is not None and quantity not in ("flow", "stage"):
        raise ValueError("quantity must be 'flow' or 'stage'")
    if ihsqr == 2:
        if quantity is None:
            raise ValueError(
                "IHSQR=2 output carries both quantities — pass "
                "quantity='flow' or quantity='stage'")
    elif quantity is not None:
        printed = {0: "flow", 1: "stage"}.get(ihsqr)
        if printed is not None and quantity != printed:
            raise ValueError(
                f"quantity={quantity!r} requested but IHSQR={ihsqr} "
                f"prints {printed} only")
    h = normalize_hydrograph_output(hyd_output)
    counts = link.links.groupby("gauge_id").size()
    multi = counts[counts > 1]
    if len(multi):
        raise ValueError(
            f"{len(multi)} gauge(s) link to multiple hydrograph "
            f"entries, e.g. {list(multi.index[:3])} — disambiguate the "
            f"metadata or the spec names")
    offset = 0
    if ihsqr == 2 and quantity == "stage":
        n = link.n_specs
        if n is None:
            if len(h.columns) % 2:
                raise ValueError(
                    "cannot locate the stage block: link has no "
                    "n_specs and the output column count is odd")
            n = len(h.columns) // 2
        if len(h.columns) < 2 * n:
            raise ValueError(
                f"the hydrograph output has {len(h.columns)} columns for "
                f"{n} hydrographs -- it holds the flow block only (the "
                "HDF version of StrmHyd carries flows; stages are in the "
                "text StrmHyd.out). Pass the text output for stage.")
        offset = n
    wanted = [int(i) + offset for i in link.links["hyd_id"]]
    missing = set(wanted) - set(h.columns)
    if missing:
        raise KeyError(
            f"hydrograph output is missing {len(missing)} column(s), "
            f"e.g. {sorted(missing)[:3]} -- it has {len(h.columns)} "
            "columns; check the quantity and that the output matches "
            "the stream main's hydrograph specs")
    out = h[wanted]
    out.columns = list(link.links["gauge_id"])
    return out


def assign_gauge_sequences(gauge_metadata,
                           link: Optional[GaugeLink] = None,
                           order: str = "stream_node") -> "pd.DataFrame":
    """Fill missing within-group gauge sequence numbers (pure function).

    Same fill-only ledger semantics as
    :func:`iwfm_io.assign_sequences`: existing ``seq`` values are never
    changed, and the caller persists the returned frame.

    Parameters
    ----------
    gauge_metadata : pandas.DataFrame
        Needs ``group``; ``seq`` created if absent.
    link : GaugeLink, optional
        Required for the default ordering.
    order : str, default "stream_node"
        ``stream_node`` orders new numbers by the linked stream-node
        number (along-network, upstream first). ``north_to_south`` /
        ``south_to_north`` / ``west_to_east`` / ``east_to_west`` use
        metadata ``x``/``y`` columns.
    """
    if "group" not in gauge_metadata.columns:
        raise ValueError("gauge_metadata needs a 'group' column")
    out = gauge_metadata.copy()
    if "seq" not in out.columns:
        out["seq"] = pd.array([pd.NA] * len(out), dtype="Int64")
    out["seq"] = out["seq"].astype("Int64")

    if order == "stream_node":
        if link is None:
            raise ValueError("order='stream_node' requires link=")
        per_gauge = link.links.groupby("gauge_id")["node_id"].first()
        coords = out["gauge_id"].map(per_gauge)
        ascending = True
    else:
        orders = {"north_to_south": ("y", False),
                  "south_to_north": ("y", True),
                  "west_to_east": ("x", True),
                  "east_to_west": ("x", False)}
        if order not in orders:
            raise ValueError(
                f"order must be 'stream_node' or one of {sorted(orders)}")
        coord_col, ascending = orders[order]
        if coord_col not in out.columns:
            raise ValueError(
                f"order {order!r} needs a {coord_col!r} metadata column")
        coords = pd.to_numeric(out[coord_col], errors="coerce")
    return _fill_sequences(out, coords, ascending)
