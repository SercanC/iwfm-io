"""Data models for IWFM file structures.

The dataclasses the readers return live in per-subsystem modules
(``iwfm_io.models.groundwater``, ``.stream``, ``.rootzone``, ...); the
shared building blocks are re-exported here and from ``iwfm_io``
itself.
"""

from iwfm_io.models.base import (
    ConversionFactor,
    FileHeader,
    FlatTimeSeriesSpecMixin,
    TimeSeriesSpec,
    TimeSeriesSpecAccessMixin,
    TS_SPEC_FIELDS,
    ZoneDefinition,
)
from iwfm_io.models.timeseries import TimeSeriesDataFile, TimeSeriesFile

__all__ = [
    "ConversionFactor",
    "FileHeader",
    "FlatTimeSeriesSpecMixin",
    "TimeSeriesSpec",
    "TimeSeriesSpecAccessMixin",
    "TS_SPEC_FIELDS",
    "ZoneDefinition",
    "TimeSeriesDataFile",
    "TimeSeriesFile",
]
