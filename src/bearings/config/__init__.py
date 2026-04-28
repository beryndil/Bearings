"""Bearings v1 runtime configuration package.

Two public surfaces:

* :mod:`bearings.config.constants` — every spec / arch / behavior
  numeric or string default as a ``Final[...]`` named constant.
  Downstream modules import from there instead of hard-coding
  literals.
* :mod:`bearings.config.settings` — the pydantic-settings root model
  that loads from XDG TOML + ``BEARINGS_`` env vars + defaults.

Per ``docs/architecture-v1.md`` §1.1.2 the package keeps the type-hint
container (pydantic models) separate from the numeric source-of-truth
(named constants) so the auditor's "no inline literals downstream"
gate (item 0.5 done-when) becomes a grep: any numeric Final outside
``config/constants.py`` is a violation.
"""

from bearings.config.settings import Settings, xdg_config_path

__all__ = ["Settings", "xdg_config_path"]
