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
- Budget observations (``budget_observations``): named observation
  tables from budget/zbudget output — full series, long-term means, or
  water-year totals per location × component.
- Derived observations (``head_changes``, ``vertical_head_difference``,
  ``accretion_depletion``, ``long_term_stats``): the DWR-proven
  regularizers, as pure transforms applied identically to observed and
  simulated series.
- Multi-layer well observations (``build_well_mapping`` →
  :class:`WellMapping`): map wells onto the mesh, intersect perforations
  with stratigraphy, transmissivity-weight layers; persistable weights
  and a one-matrix-multiply composite for the forward run;
  ``select_best_layers`` resolves unknown completions by RMSE.
- Paired output/instruction writers (:class:`ObsFileSpec`): one spec
  emits both the forward-run output file and its matching ``.ins`` —
  name/column/order consistency by construction, with a built-in
  round-trip check.
- Run orchestration (``setup_agents``, ``write_forward_run``,
  ``run_finals``): hardlinked agent replication, fail-fast forward-run
  scripts, and pyemu-free v2 parrep for finals reruns.
- Parameter write-back (``apply_parameters`` + :class:`ApplyAction`):
  the multiplier apply step — PEST-written value files merged onto base
  parameter tables and regenerated through the round-trip writers, with
  bounds and a bookkeeping log; plus IWFM's native GW parameter
  overwrite file (``write_gw_overwrite`` / ``read_gw_overwrite``).
- Zone/group parameterization (``ParamSpec`` → ``build_parameters`` →
  :class:`ParamBundle`): declarative zones/ties → template files,
  initial value files, and v2 parameter/parameter-group tables, with a
  fill-and-compare verify step.
- Pilot points (``place_pilot_points_grid``, ``compute_kriging_factors``,
  ``apply_kriging_factors``): pure-numpy ordinary kriging on the FE mesh
  (exp/sph/gau variograms, anisotropy, zones) — factors computed once,
  FAC2REAL-style application in the forward run.
- Constrained reparameterization (:class:`RatioChain`): anchor + bounded
  ratio/exponent chains with corner-checked ordering guarantees (no
  invalid ensemble draw), forward-run ``evaluate()``, PEST par rows;
  plus Texture2Par ``PP_LOCS`` file I/O.

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
from iwfm_io.pest.wells import (
    WellMapping,
    build_well_mapping,
    select_best_layers,
)
from iwfm_io.pest.reparam import (
    RatioChain,
    read_t2p_pilot_points,
    write_t2p_pilot_points,
)
from iwfm_io.pest.pilot_points import (
    ExpVariogram,
    SphVariogram,
    GauVariogram,
    place_pilot_points_grid,
    compute_kriging_factors,
    apply_kriging_factors,
)
from iwfm_io.pest.params import (
    ParamSpec,
    ParamBundle,
    build_parameters,
)
from iwfm_io.pest.apply import (
    ApplyAction,
    apply_parameters,
    write_gw_overwrite,
    read_gw_overwrite,
)
from iwfm_io.pest.orchestrate import (
    setup_agents,
    write_manager_script,
    write_forward_run,
    parrep_v2,
    run_finals,
)
from iwfm_io.pest.obsfiles import (
    ObsFileSpec,
)
from iwfm_io.pest.derived import (
    head_changes,
    vertical_head_difference,
    accretion_depletion,
    long_term_stats,
)
from iwfm_io.pest.budget_obs import (
    budget_observations,
    slugify_label,
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
    "budget_observations",
    "slugify_label",
    "head_changes",
    "vertical_head_difference",
    "accretion_depletion",
    "long_term_stats",
    "WellMapping",
    "ObsFileSpec",
    "setup_agents",
    "ApplyAction",
    "ParamSpec",
    "ExpVariogram",
    "RatioChain",
    "read_t2p_pilot_points",
    "write_t2p_pilot_points",
    "SphVariogram",
    "GauVariogram",
    "place_pilot_points_grid",
    "compute_kriging_factors",
    "apply_kriging_factors",
    "ParamBundle",
    "build_parameters",
    "apply_parameters",
    "write_gw_overwrite",
    "read_gw_overwrite",
    "write_manager_script",
    "write_forward_run",
    "parrep_v2",
    "run_finals",
    "build_well_mapping",
    "select_best_layers",
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
