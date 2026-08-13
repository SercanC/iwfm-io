"""
iwfm_io.pest — PEST(++) calibration support for IWFM models.

Utilities for building and post-processing PEST / PEST++ calibrations of
IWFM models. Pure Python (pandas); ``pyemu`` is an optional companion for
control-file manipulation and geostatistics, never a hard dependency.

Currently provided:

- Observation-name codec (``encode_obs_name`` / ``decode_obs_name`` and
  vectorized counterparts): structured, round-trip-safe conversion between
  ``(obs_type, location, time)`` and PEST observation names, with a
  registry for project-specific legacy naming schemes.
- PESTPP-IES results loader (``load_ies_ensembles`` → :class:`IesResults`):
  lazy, cached access to per-iteration parameter/observation ensembles,
  tidy phi tables, per-group phi, prior-data conflict, obs+noise, and
  base-realization residuals (``read_rei``).
- Residual/calibration statistics (``residual_stats``, ``rei_stats``,
  ``ies_stats``): RMSE, bias, R², NSE, KGE, phi contributions — grouped
  by any columns, vectorized to ensemble scale.
- SMP bore-sample files (``read_smp`` / ``write_smp``): the interchange
  format of the DWR/IWFM2OBS calibration toolchain, as long-form
  ``site, datetime, value`` frames.
- Phi-budget weight balancing (``balance_weights``): rescale observation
  weights so each category contributes a target phi, pyemu-free on
  v2-style observation-data tables (``balance_pst_weights`` adapts
  classic .pst files through pyemu).
- IES diagnostics (``diagnose_ies`` → :class:`IesDiagnostics`): phi
  convergence/collapse, prior-data conflict, ensemble-wide bound
  railing, residual bias/trends, outliers, objective balance — as a
  compact JSON state + boolean signals + text summary.
- Sim-to-obs matching (``match_sim_to_obs``, ``resample_month_end``):
  IWFM2OBS-equivalent time interpolation of simulated hydrographs to
  observation timestamps, gap-guarded, 24:00-convention aware.

Quick-start::

    from iwfm_io.pest import encode_obs_name, decode_obs_names

    name = encode_obs_name("gwh", "w1234", "2000-10-31")
    # 'gwh_w1234_20001031'

    parts = decode_obs_names(obs_df.index)   # DataFrame: obs_type, location, time
"""

from iwfm_io.pest.ies import (
    IesResults,
    load_ies_ensembles,
    read_rei,
)
from iwfm_io.pest.smp import (
    read_smp,
    write_smp,
)
from iwfm_io.pest.sim2obs import (
    match_sim_to_obs,
    resample_month_end,
)
from iwfm_io.pest.diagnostics import (
    DiagThresholds,
    IesDiagnostics,
    diagnose_ies,
)
from iwfm_io.pest.weights import (
    WeightBalance,
    balance_weights,
    balance_pst_weights,
)
from iwfm_io.pest.stats import (
    METRICS,
    residual_stats,
    rei_stats,
    ies_stats,
)
from iwfm_io.pest.names import (
    ObsName,
    NameScheme,
    StandardScheme,
    register_scheme,
    get_scheme,
    encode_obs_name,
    decode_obs_name,
    encode_obs_names,
    decode_obs_names,
    validate_obs_names,
)

__all__ = [
    "IesResults",
    "load_ies_ensembles",
    "read_rei",
    "read_smp",
    "write_smp",
    "match_sim_to_obs",
    "resample_month_end",
    "WeightBalance",
    "balance_weights",
    "balance_pst_weights",
    "DiagThresholds",
    "IesDiagnostics",
    "diagnose_ies",
    "METRICS",
    "residual_stats",
    "rei_stats",
    "ies_stats",
    "ObsName",
    "NameScheme",
    "StandardScheme",
    "register_scheme",
    "get_scheme",
    "encode_obs_name",
    "decode_obs_name",
    "encode_obs_names",
    "decode_obs_names",
    "validate_obs_names",
]
