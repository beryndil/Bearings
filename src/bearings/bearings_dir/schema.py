"""Pydantic v2 schemas for the five `.bearings/` file shapes.

Every field has a cap so a malicious or accidentally-huge file can't
blow past a reasonable token budget when the prompt pipeline reads it
next turn. `description` ≤ 500 and history `summary` ≤ 200 come from
the v0.4 spec.

All `datetime` fields serialise as ISO-8601 strings through Pydantic's
default JSON/TOML coercion so TOML round-trips cleanly (TOML's own
datetime type also works — `tomllib` parses both).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Field length caps — keep tight. The prompt pipeline reads these files
# every turn; a 50KB description balloons the system prompt.
_MAX_DESCRIPTION = 500
_MAX_SUMMARY = 200
_MAX_NAME = 120
_MAX_PATH = 4096
_MAX_COMMAND = 2048
_MAX_LIST_ITEMS = 64

# Schema version so older or newer clients can detect a mismatch. Bumps
# follow semver: additive fields don't require a bump, breaking renames
# do. v0.6.0 ships schema version 1.
SCHEMA_VERSION = 1


def _utc_now() -> datetime:
    """Timezone-aware UTC now — never return a naive datetime so round-
    trip through TOML preserves the offset."""
    return datetime.now(UTC)


class _Base(BaseModel):
    """Shared config: forbid unknown keys so a typo in a hand-edited
    file fails fast instead of being silently dropped on next write."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Manifest(_Base):
    """`manifest.toml` — directory identity, slow-changing.

    Written once at onboarding, updated only when the directory's
    identity actually shifts (rename, git remote change, etc.).
    Everything volatile belongs in `state.toml`.
    """

    schema_version: int = SCHEMA_VERSION
    name: str = Field(max_length=_MAX_NAME)
    path: str = Field(max_length=_MAX_PATH)
    description: str = Field(default="", max_length=_MAX_DESCRIPTION)
    git_remote: str | None = Field(default=None, max_length=_MAX_PATH)
    language: str | None = Field(default=None, max_length=_MAX_NAME)
    created_at: datetime = Field(default_factory=_utc_now)


class EnvironmentBlock(_Base):
    """Subset of `state.toml` describing environment health. Kept as a
    distinct type because step 3 of the onboarding ritual (and
    `bearings check`) writes exactly these fields."""

    python_version: str | None = Field(default=None, max_length=_MAX_NAME)
    venv_path: str | None = Field(default=None, max_length=_MAX_PATH)
    lockfile_fresh: bool | None = None
    migrations_applied: bool | None = None
    notes: list[str] = Field(default_factory=list)
    last_validated: datetime = Field(default_factory=_utc_now)

    @field_validator("notes")
    @classmethod
    def _cap_notes(cls, value: list[str]) -> list[str]:
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError(f"notes capped at {_MAX_LIST_ITEMS} entries")
        for entry in value:
            if len(entry) > _MAX_SUMMARY:
                raise ValueError(f"note entry > {_MAX_SUMMARY} chars")
        return value


class State(_Base):
    """`state.toml` — per-session belief about current state.

    Holds volatile, session-scoped knowledge: current git branch, last
    validation timestamp, last-known dirty-tree flag. Gets rewritten
    on every session open / `bearings check` run.
    """

    schema_version: int = SCHEMA_VERSION
    branch: str | None = Field(default=None, max_length=_MAX_NAME)
    dirty: bool | None = None
    environment: EnvironmentBlock = Field(default_factory=EnvironmentBlock)
    last_session_id: str | None = Field(default=None, max_length=_MAX_NAME)
    updated_at: datetime = Field(default_factory=_utc_now)


class PendingOperation(_Base):
    """One in-flight operation. The key file — what this whole system
    exists to make visible to the next session.

    `started` is a timezone-aware datetime so stale-op detection (30-
    day flag in v0.6.1) has a clean comparison against `_utc_now()`.
    `owner` is the session id that opened it; `None` for ops entered
    via `bearings pending add` outside a live session.
    """

    name: str = Field(max_length=_MAX_NAME)
    description: str = Field(default="", max_length=_MAX_DESCRIPTION)
    command: str | None = Field(default=None, max_length=_MAX_COMMAND)
    owner: str | None = Field(default=None, max_length=_MAX_NAME)
    started: datetime = Field(default_factory=_utc_now)


class Pending(_Base):
    """`pending.toml` — wraps a list of operations. TOML can't hold a
    top-level array, so the file body is `[[operations]]` tables."""

    schema_version: int = SCHEMA_VERSION
    operations: list[PendingOperation] = Field(default_factory=list)

    @field_validator("operations")
    @classmethod
    def _cap_operations(cls, value: list[PendingOperation]) -> list[PendingOperation]:
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError(f"operations capped at {_MAX_LIST_ITEMS} entries")
        return value


class HistoryEntry(_Base):
    """`history.jsonl` — one line per session visit.

    Per decision #2, `session_id` is the Bearings sessions-row id
    (stable across reconnects, visible in the DB). `started` is set
    when the WS connects; `ended` stamps on disconnect. If the end
    hook never fires (crash), `ended` stays `None` and the next
    session can see the prior one ended unclean.
    """

    schema_version: int = SCHEMA_VERSION
    session_id: str = Field(max_length=_MAX_NAME)
    started: datetime = Field(default_factory=_utc_now)
    ended: datetime | None = None
    branch: str | None = Field(default=None, max_length=_MAX_NAME)
    commits: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=_MAX_SUMMARY)
    status: Literal["clean", "unclean", "in_progress"] = "in_progress"

    @field_validator("commits")
    @classmethod
    def _cap_commits(cls, value: list[str]) -> list[str]:
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError(f"commits capped at {_MAX_LIST_ITEMS} entries")
        for sha in value:
            if len(sha) > _MAX_NAME:
                raise ValueError(f"commit sha > {_MAX_NAME} chars")
        return value
