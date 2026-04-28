"""Pydantic-settings root model for the Bearings v1 runtime.

Loads configuration from layered sources, in precedence order
(higher overrides lower):

1. Constructor / explicit kwargs (programmatic override; primarily tests).
2. Environment variables prefixed ``BEARINGS_`` (case-insensitive).
3. TOML at the XDG config path (``$XDG_CONFIG_HOME/bearings/config.toml``;
   falls back to ``~/.config/bearings/config.toml`` when the env var is
   unset). A missing file is silently treated as "no overrides".
4. Hard-coded defaults from :mod:`bearings.config.constants`.

Numeric / string defaults are *never* expressed as inline literals in
this module: every field's ``default`` references a named constant from
:mod:`bearings.config.constants`. The auditor's "no inline literals
downstream" gate (item 0.5 done-when) flags any literal here.

Strict validation:

* ``extra="forbid"`` — unknown TOML keys / env vars surface as
  ``ValidationError`` rather than being silently dropped.
* ``case_sensitive=False`` — ``BEARINGS_PORT`` / ``bearings_port`` /
  ``Bearings_Port`` are equivalent. Linux env-var convention is
  uppercase; TOML keys are typically lowercase; the Settings shape
  must accept both without bespoke handling.
* mypy ``--strict`` clean — no ``Any``.

The frame is intentionally narrow: this module ships only the runtime
knobs item 0.5's done-when explicitly names (port, db_path) plus the
spec-driven knobs that are clearly cross-cutting (routing preview
debounce, advisor enable, quota threshold + poll cadence,
override-rate review threshold, tool-output cap). Phase 1 items
introduce additional sub-configs (Auth/Vault/Uploads/...) per
``docs/architecture-v1.md`` §1.1.2 as their feature surface lands.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from bearings.config.constants import (
    DEFAULT_DB_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TOOL_OUTPUT_CAP_CHARS,
    OVERRIDE_RATE_REVIEW_THRESHOLD,
    PCT_MAX,
    PCT_MIN,
    QUOTA_THRESHOLD_PCT,
    ROUTING_PREVIEW_DEBOUNCE_MS,
    TCP_PORT_MAX,
    TCP_PORT_MIN,
    USAGE_POLL_INTERVAL_S,
)

_XDG_CONFIG_HOME_ENV: Final[str] = "XDG_CONFIG_HOME"
_XDG_CONFIG_HOME_DEFAULT: Final[Path] = Path("~/.config").expanduser()
_BEARINGS_CONFIG_RELPATH: Final[Path] = Path("bearings") / "config.toml"


def xdg_config_path() -> Path:
    """Return the XDG-resolved config-file path for Bearings.

    Reads ``$XDG_CONFIG_HOME`` (falls back to ``~/.config``) and appends
    ``bearings/config.toml``. Does not check whether the file exists —
    the TOML source treats a missing file as "no overrides" per
    pydantic-settings' :class:`TomlConfigSettingsSource` semantics.

    A whitespace-only ``XDG_CONFIG_HOME`` is treated as unset (per the
    XDG Base Directory spec, an empty value falls back to the default).
    """
    base = os.environ.get(_XDG_CONFIG_HOME_ENV, "").strip()
    root = Path(base).expanduser() if base else _XDG_CONFIG_HOME_DEFAULT
    return root / _BEARINGS_CONFIG_RELPATH


class Settings(BaseSettings):  # type: ignore[explicit-any]
    # ``disallow_any_explicit = true`` (pyproject.toml) flags this line
    # because pydantic-settings' :class:`BaseSettings` exposes ``Any``-
    # typed metaclass surface. The ignore is the narrowest possible
    # carve-out — every field below is fully typed.
    """Root settings model for the Bearings v1 runtime.

    Field defaults reference named constants from
    :mod:`bearings.config.constants`. See the module docstring for the
    no-inline-literal contract enforced by the item-0.5 audit.
    """

    model_config = SettingsConfigDict(
        env_prefix="BEARINGS_",
        case_sensitive=False,
        extra="forbid",
        env_file=None,
    )

    # Server bind. Master item 0.5 names ``port`` (default 8788) at the
    # top level; the env-var ``BEARINGS_PORT`` resolves directly.
    port: int = Field(default=DEFAULT_PORT, ge=TCP_PORT_MIN, le=TCP_PORT_MAX)
    host: str = Field(default=DEFAULT_HOST)

    # Storage. ``BEARINGS_DB_PATH`` resolves directly; the constants
    # module pre-expands ``~`` so the default is an absolute Path.
    db_path: Path = Field(default=DEFAULT_DB_PATH)

    # Per-tool-call output soft cap (arch §1.1.2 + §4.8 SessionConfig).
    tool_output_cap_chars: int = Field(default=DEFAULT_TOOL_OUTPUT_CAP_CHARS, gt=0)

    # Routing preview debounce override (spec §6 — "~300ms"). The
    # constant value is the spec mandate; this field lets a user retune
    # without an SDK pin bump.
    routing_preview_debounce_ms: int = Field(
        default=ROUTING_PREVIEW_DEBOUNCE_MS,
        gt=0,
    )

    # Master switch for the advisor primitive (spec §2). Defaults to on
    # so the spec's default-policy table fires; the user can disable
    # advisor wiring globally without touching individual rules.
    advisor_enabled: bool = Field(default=True)

    # Quota-guard tuning. The constant is the spec §4 mandate; both
    # fields are user-tunable per spec §13 risk #2.
    quota_threshold_pct: float = Field(default=QUOTA_THRESHOLD_PCT, ge=PCT_MIN, le=PCT_MAX)
    quota_poll_interval_s: int = Field(default=USAGE_POLL_INTERVAL_S, gt=0)

    # Override-rate review threshold (spec §8). User-tunable for noisy
    # rule sets where the default 0.30 produces too many "Review:"
    # highlights to act on.
    override_rate_review_threshold: float = Field(
        default=OVERRIDE_RATE_REVIEW_THRESHOLD,
        ge=PCT_MIN,
        le=PCT_MAX,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer XDG-TOML beneath env vars and explicit kwargs.

        Precedence (high → low, per pydantic-settings tuple order):

        1. ``init_settings`` (constructor kwargs)
        2. ``env_settings`` (``BEARINGS_*`` env vars)
        3. ``TomlConfigSettingsSource`` reading the XDG config path

        Default ``dotenv`` and ``secrets`` sources are dropped: Bearings
        is single-user localhost and does not load .env files or
        Docker-style secrets directories.
        """
        # ``cls`` is the auto-bound classmethod target; pydantic-settings
        # passes the same class explicitly as ``settings_cls`` for the
        # override signature so the body uses the named arg. The other
        # two sources are intentionally dropped (see docstring).
        del cls, dotenv_settings, file_secret_settings
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=xdg_config_path()),
        )


__all__ = ["Settings", "xdg_config_path"]
