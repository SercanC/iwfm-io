"""Base dataclasses shared across all IWFM file models."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class FileHeader:
    """Metadata from the top of an IWFM file.

    Attributes
    ----------
    version : str or None
        Version string from a ``#4.0`` header, or None.
    comment_lines : list[str]
        Comment lines preceding the first data, preserved for round-trip.
    """

    version: str | None = None
    comment_lines: list[str] = field(default_factory=list)


@dataclass
class ConversionFactor:
    """A conversion factor with its keyword and optional unit label.

    Attributes
    ----------
    value : float
        The numeric factor (e.g. 3.2808 for m→ft).
    keyword : str
        The keyword from the file (e.g. "FACT", "FACTLTOU").
    unit_label : str
        Optional unit string (e.g. "FEET").
    """

    value: float = 1.0
    keyword: str = ""
    unit_label: str = ""


@dataclass
class TimeSeriesSpec:
    """Header parameters for an IWFM time-series data section.

    Attributes
    ----------
    n_columns : int
        Number of data columns (NCOL).
    factor : float
        Conversion factor applied to all values (FACT).
    n_steps_update : int
        Number of timesteps between updates (NSP). 0 or 1 = every step.
    repeat_freq : int
        Repetition frequency flag (NFQ). 0 = no repeat.
    dss_file : str
        Path to HEC-DSS file, or empty string if data is inline.
    """

    n_columns: int = 0
    factor: float = 1.0
    n_steps_update: int = 1
    repeat_freq: int = 0
    dss_file: str = ""


#: The five spec parameters, in :class:`TimeSeriesSpec` field order.
TS_SPEC_FIELDS = ("n_columns", "factor", "n_steps_update", "repeat_freq",
                  "dss_file")


class FlatTimeSeriesSpecMixin:
    """``.spec`` view for time-series files that store the spec flat.

    Some time-series dataclasses hold a :class:`TimeSeriesSpec`
    (``obj.spec.factor``), others carry the five parameters as their own
    fields (``obj.factor``) because they also need ``has_dssfl`` /
    ``keywords`` alongside them.  This mixin gives the flat ones a
    ``spec`` property so code that handles "any time-series file" can
    use one idiom; :class:`TimeSeriesSpecAccessMixin` does the reverse
    for the others.

    Reading builds a fresh :class:`TimeSeriesSpec` **snapshot**, so
    mutating it in place changes nothing -- assign a whole spec back
    (``obj.spec = spec``) to write the fields.  Parameters the class
    does not carry (``SurfaceFlowDestFile`` has no ``dss_file``, for
    instance) keep the spec's default on read and are ignored on write.
    """

    __slots__ = ()

    @property
    def spec(self) -> "TimeSeriesSpec":
        """The five spec parameters as a :class:`TimeSeriesSpec` snapshot."""
        return TimeSeriesSpec(**{name: getattr(self, name)
                                 for name in TS_SPEC_FIELDS
                                 if hasattr(self, name)})

    @spec.setter
    def spec(self, value: "TimeSeriesSpec") -> None:
        for name in TS_SPEC_FIELDS:
            if hasattr(self, name) and hasattr(value, name):
                setattr(self, name, getattr(value, name))


class TimeSeriesSpecAccessMixin:
    """Flat ``n_columns`` / ``factor`` / ... access for ``.spec`` files.

    The mirror of :class:`FlatTimeSeriesSpecMixin`: files that store a
    :class:`TimeSeriesSpec` in ``self.spec`` also answer to the five
    parameter names directly, reading and writing through to the spec.
    """

    __slots__ = ()

    @property
    def n_columns(self) -> int:
        return self.spec.n_columns

    @n_columns.setter
    def n_columns(self, value) -> None:
        self.spec.n_columns = value

    @property
    def factor(self):
        return self.spec.factor

    @factor.setter
    def factor(self, value) -> None:
        self.spec.factor = value

    @property
    def n_steps_update(self) -> int:
        return self.spec.n_steps_update

    @n_steps_update.setter
    def n_steps_update(self, value) -> None:
        self.spec.n_steps_update = value

    @property
    def repeat_freq(self) -> int:
        return self.spec.repeat_freq

    @repeat_freq.setter
    def repeat_freq(self, value) -> None:
        self.spec.repeat_freq = value

    @property
    def dss_file(self) -> str:
        return self.spec.dss_file

    @dss_file.setter
    def dss_file(self, value) -> None:
        self.spec.dss_file = value


@dataclass
class ZoneDefinition:
    """Zone definition for IWFM Z-Budget aggregation.

    Attributes
    ----------
    extent : str
        ``"horizontal"`` (same zones for all layers) or ``"vertical"``
        (layer-specific zone assignments).
    zones : dict[int, str]
        Mapping of zone ID to zone name.
    element_zones : pandas.DataFrame
        Element-to-zone assignments.  Columns are ``[element_id, zone_id]``
        when *extent* is ``"horizontal"``, or ``[element_id, layer, zone_id]``
        when *extent* is ``"vertical"``.
    """

    extent: str = "horizontal"
    zones: dict[int, str] = field(default_factory=dict)
    element_zones: pd.DataFrame = field(default_factory=pd.DataFrame)
