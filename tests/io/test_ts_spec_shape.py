"""Every time-series file object answers to both spec shapes (issue #40).

Time-series dataclasses come in two layouts: some hold a
:class:`TimeSeriesSpec` in ``.spec``, the rest carry the five spec
parameters as their own fields (they also need ``has_dssfl`` /
``keywords`` next to them).  Code that handles "any time-series file"
should not have to branch, so the flat ones gained a ``.spec`` property
and the others flat pass-throughs.
"""

import pytest

from iwfm_io import TimeSeriesSpec
from iwfm_io.models.base import TS_SPEC_FIELDS
from iwfm_io.models.groundwater import BoundaryTSFile, TSPumpingFile
from iwfm_io.models.rootzone import SurfaceFlowDestFile
from iwfm_io.models.stream import DiversionsFile, StreamInflowFile
from iwfm_io.models.timeseries import (ETFile, IrigFracFile, IrrPeriodFile,
                                       PrecipFile, SupplyAdjustFile,
                                       TimeSeriesDataFile, TimeSeriesFile)

SPEC_SHAPED = [BoundaryTSFile, DiversionsFile, ETFile, PrecipFile,
               StreamInflowFile, TSPumpingFile, TimeSeriesFile]
FLAT_SHAPED = [IrigFracFile, IrrPeriodFile, SupplyAdjustFile,
               SurfaceFlowDestFile, TimeSeriesDataFile]


@pytest.mark.parametrize("cls", SPEC_SHAPED + FLAT_SHAPED,
                         ids=lambda c: c.__name__)
def test_every_ts_class_has_a_spec(cls):
    obj = cls()
    assert isinstance(obj.spec, TimeSeriesSpec)


@pytest.mark.parametrize("cls", SPEC_SHAPED + FLAT_SHAPED,
                         ids=lambda c: c.__name__)
def test_flat_access_agrees_with_the_spec(cls):
    """Where a parameter exists as a field, both idioms give one answer.

    ``.spec`` is the shape every class answers in full; the flat names
    only exist where the file format has the parameter at all (the
    4-parameter files have no FACT, DESTFL has neither FACT nor DSSFL),
    and then the spec reports its neutral default.
    """
    obj = cls()
    for name in TS_SPEC_FIELDS:
        if hasattr(obj, name):
            assert getattr(obj, name) == getattr(obj.spec, name)


def test_factless_files_report_a_neutral_factor_through_the_spec():
    for cls in (IrigFracFile, IrrPeriodFile, SupplyAdjustFile,
                SurfaceFlowDestFile):
        assert not hasattr(cls(), "factor")
        assert cls().spec.factor == 1.0


@pytest.mark.parametrize("cls", SPEC_SHAPED, ids=lambda c: c.__name__)
def test_spec_shaped_writes_through(cls):
    obj = cls()
    obj.n_columns = 7
    obj.factor = 2.5
    obj.n_steps_update = 3
    obj.repeat_freq = 12
    obj.dss_file = "x.dss"
    assert obj.spec == TimeSeriesSpec(7, 2.5, 3, 12, "x.dss")


@pytest.mark.parametrize("cls", FLAT_SHAPED, ids=lambda c: c.__name__)
def test_flat_shaped_spec_setter_writes_the_fields(cls):
    obj = cls()
    obj.spec = TimeSeriesSpec(9, 1.5, 2, 4, "y.dss")
    assert obj.n_columns == 9
    assert obj.n_steps_update == 2
    assert obj.repeat_freq == 4
    if hasattr(obj, "factor"):
        assert obj.factor == 1.5
    if hasattr(obj, "dss_file"):
        assert obj.dss_file == "y.dss"


def test_flat_spec_reflects_later_field_changes():
    obj = TimeSeriesDataFile(n_columns=4, factor=None)
    assert obj.spec.n_columns == 4
    obj.n_columns = 6
    assert obj.spec.n_columns == 6
    # a 4-parameter file has no FACT at all; the spec says so
    assert obj.spec.factor is None


def test_flat_spec_ignores_parameters_the_class_lacks():
    sfd = SurfaceFlowDestFile(n_columns=3)
    assert sfd.spec == TimeSeriesSpec(n_columns=3)
    sfd.spec = TimeSeriesSpec(n_columns=5, dss_file="ignored.dss")
    assert sfd.n_columns == 5
    assert not hasattr(sfd, "dss_file")


def test_spec_is_a_snapshot_not_a_live_view():
    """Documented behaviour: assign a whole spec back to change fields."""
    obj = IrigFracFile(n_columns=2)
    snapshot = obj.spec
    snapshot.n_columns = 99
    assert obj.n_columns == 2


def test_timeseriesspec_is_public():
    import iwfm_io
    assert iwfm_io.TimeSeriesSpec is TimeSeriesSpec
    assert iwfm_io.TimeSeriesDataFile is TimeSeriesDataFile
