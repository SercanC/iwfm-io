"""Dataclasses for IWFM stream component input files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from iwfm_io.models.base import FileHeader, TimeSeriesSpec


@dataclass
class StreamMain:
    """Parsed stream main file (e.g. ``Stream_MAIN.dat``).

    Attributes
    ----------
    header : FileHeader
    file_paths : dict[str, str or None]
        Keyed by role: inflow, diver_specs, bypass_specs, diversions,
        strm_bud_hdf, diver_detail_hdf.
    config : dict
        Hydrograph output settings: n_hydrographs, ihsqr, factvrou,
        unitvrou, factltou, unitltou, hydro_out_file.
        Node budget settings: n_node_budgets, node_bud_file.
        Reach bed settings: factk, tunitk, factl.
        intrctype, starfl.
    hydrograph_specs : list[dict]
        One entry per hydrograph: keys ``node_id`` (int), ``name`` (str).
    node_budget_nodes : list[int]
        Stream node IDs for node budget output.
    reach_params : pd.DataFrame
        Columns: reach_id (int), conductance (float), width (float),
        bed_thickness (float).
    evaporation : pd.DataFrame or None
        Stream evaporation table (None when evaporation is not
        simulated).  Columns: stream_node, icetst (column in the ET
        file; 0 = none), icarst (column in the stream surface area
        file STARFL; 0 = computed from wetted perimeter).
    """

    header: FileHeader = field(default_factory=FileHeader)
    file_paths: dict[str, str | None] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    hydrograph_specs: list[dict] = field(default_factory=list)
    node_budget_nodes: list[int] = field(default_factory=list)
    reach_params: Any = None  # DataFrame
    evaporation: Any = None  # DataFrame


@dataclass
class StreamInflowFile:
    """Parsed stream inflow file (e.g. ``StreamInflow.dat``).

    Attributes
    ----------
    header : FileHeader
    spec : TimeSeriesSpec
        5-param time-series spec: NCOLSTRM, FACTSTRM, NSPSTRM, NFQSTRM, DSSFL.
    node_assignments : list[tuple[int, int]]
        Pairs of (column_id, stream_node_id) mapping inflow columns to nodes.
    data : pd.DataFrame or None
        Inline time-series data with a ``date`` column (IWFM date strings)
        plus value columns ``col_1``, ``col_2``, ...  None if using DSS.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments if reading from DSS.
    """

    header: FileHeader = field(default_factory=FileHeader)
    spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    node_assignments: list[tuple[int, int]] = field(default_factory=list)
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class DiverSpecsFile:
    """Parsed surface water diversion specification file (e.g. ``DiverSpecs.dat``).

    Attributes
    ----------
    header : FileHeader
    n_diversions : int
        Number of diversions (NRDV).
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_diversions: int = 0
    #: Per-diversion table: diversion_id, export_node (0 = import from
    #: outside), max_col/max_frac (max-diversion column in the
    #: diversions data file + fraction), recov_loss_col/frac,
    #: nonrecov_loss_col/frac, spill_col/frac (older formats only),
    #: dest_type (0=outside, 2=element, 4=subregion, 6=element group),
    #: dest_id, delivery_col/frac, irig_frac_col (column in the
    #: irrigation fractions file), adjust_col (column in the supply
    #: adjustment file), name.
    data: Any = None
    #: NGRP — number of delivery element groups.
    n_groups: int = 0
    #: Parsed delivery element groups: [{group_id, elements: [int]}, …]
    delivery_groups: list = field(default_factory=list)
    #: Recharge zones (recoverable-loss areas), one per diversion:
    #: [{group_id, elements: [int], fractions: [float]}, …]
    recharge_zones: list = field(default_factory=list)
    #: Diversion spill locations (older stream-package formats only),
    #: one per diversion: [{group_id, elements: [stream nodes],
    #: fractions: [float]}, …]; empty in newer formats.
    spill_locations: list = field(default_factory=list)

    @property
    def delivery_groups_df(self):
        """Delivery element groups as a long-format DataFrame
        (columns: group_id, element_id)."""
        from iwfm_io.readers._element_groups import element_groups_to_df
        return element_groups_to_df(self.delivery_groups)

    @property
    def recharge_zones_df(self):
        """Recharge zones as a long-format DataFrame
        (columns: group_id = diversion id, element_id, fraction)."""
        from iwfm_io.readers._element_groups import element_groups_to_df
        return element_groups_to_df(self.recharge_zones)

    @property
    def spill_locations_df(self):
        """Spill locations as a long-format DataFrame (columns:
        group_id = diversion id, element_id = stream node, fraction)."""
        from iwfm_io.readers._element_groups import element_groups_to_df
        return element_groups_to_df(self.spill_locations)


@dataclass
class BypassSpecsFile:
    """Parsed stream bypass specification file (e.g. ``BypassSpecs.dat``).

    Attributes
    ----------
    header : FileHeader
    n_bypasses : int
        Number of bypasses (NBYPS).
    factors : dict
        Conversion factors: factx (float), tunitx (str), facty (float),
        tunity (str).
    bypass_data : pd.DataFrame or None
        One row per bypass. Columns: bypass_id (int), stream_node (int),
        dest_type (int), dest (int), idivc (int), divrl (float),
        divnl (float), name (str).
    rating_tables : dict[int, pd.DataFrame]
        Keyed by bypass_id. Only present when ``idivc < 0``.
        Each DataFrame has columns: divx (float), divy (float).
    seepage_zones : list[dict]
        One entry per bypass: keys ``bypass_id`` (int), ``n_elements`` (int),
        ``elements`` (list[dict] with keys ``element_id``, ``fraction``).
    """

    header: FileHeader = field(default_factory=FileHeader)
    n_bypasses: int = 0
    factors: dict = field(default_factory=dict)
    bypass_data: Any = None  # DataFrame
    rating_tables: dict = field(default_factory=dict)
    seepage_zones: list[dict] = field(default_factory=list)

    @property
    def seepage_zones_df(self):
        """Seepage zones as a long-format DataFrame
        (columns: bypass_id, element_id, fraction)."""
        import pandas as pd
        records = [
            {"bypass_id": z["bypass_id"],
             "element_id": e["element_id"],
             "fraction": e["fraction"]}
            for z in self.seepage_zones for e in z["elements"]
        ]
        return pd.DataFrame(
            records, columns=["bypass_id", "element_id", "fraction"])


@dataclass
class DiversionsFile:
    """Parsed surface water diversion data file (e.g. ``Diversions.dat``).

    Attributes
    ----------
    header : FileHeader
    spec : TimeSeriesSpec
        5-param time-series spec: NCOLDV, FACTDV, NSPDV, NFQDV, DSSFL.
    data : pd.DataFrame or None
        Inline time-series data with a ``date`` column (IWFM date strings)
        plus value columns ``col_1``, ``col_2``, ...  None if using DSS.
    dss_pathnames : list[tuple[int, str]]
        DSS pathname assignments if reading from DSS.
    """

    header: FileHeader = field(default_factory=FileHeader)
    spec: TimeSeriesSpec = field(default_factory=TimeSeriesSpec)
    data: Any = None  # DataFrame
    dss_pathnames: list[tuple[int, str]] = field(default_factory=list)
