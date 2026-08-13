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

Quick-start::

    from iwfm_io.pest import encode_obs_name, decode_obs_names

    name = encode_obs_name("gwh", "w1234", "2000-10-31")
    # 'gwh_w1234_20001031'

    parts = decode_obs_names(obs_df.index)   # DataFrame: obs_type, location, time
"""

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
