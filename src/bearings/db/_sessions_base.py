"""Shared Session dataclass, validators, and SQL filter-clause builders.

Private module — not part of the public API.  Imported by sessions_read,
sessions_write, sessions_update, and sessions_messages to avoid duplicating
the dataclass definition and its invariant validators.
"""

from __future__ import annotations

from dataclasses import dataclass

from bearings.config.constants import (
    EXECUTOR_MODEL_FULL_ID_PREFIX,
    KNOWN_EFFORT_LEVELS,
    KNOWN_EXECUTOR_MODELS,
    KNOWN_SDK_PERMISSION_MODES,
    KNOWN_SESSION_KINDS,
    SESSION_CLOSING_SUMMARY_MAX_LENGTH,
    SESSION_CLOSING_SUMMARY_MIN_LENGTH,
    SESSION_DESCRIPTION_MAX_LENGTH,
    SESSION_TITLE_MAX_LENGTH,
)

# ---------------------------------------------------------------------------
# Model-name predicate
# ---------------------------------------------------------------------------


def _is_known_model(name: str) -> bool:
    """Match short-name or full-SDK-id model names (mirrors agent/routing.py)."""
    return name in KNOWN_EXECUTOR_MODELS or name.startswith(EXECUTOR_MODEL_FULL_ID_PREFIX)


# ---------------------------------------------------------------------------
# Session.__post_init__ validators
# ---------------------------------------------------------------------------


def _validate_session_required(id: str, title: str, working_dir: str, model: str) -> None:
    """Raise if any required string field is empty."""
    if not id:
        raise ValueError("Session.id must be non-empty")
    if not title:
        raise ValueError("Session.title must be non-empty")
    if not working_dir:
        raise ValueError("Session.working_dir must be non-empty")
    if not model:
        raise ValueError("Session.model must be non-empty")


def _validate_session_lengths(
    title: str,
    description: str | None,
    session_instructions: str | None,
) -> None:
    """Raise if title, description, or session_instructions exceed length caps."""
    if len(title) > SESSION_TITLE_MAX_LENGTH:
        raise ValueError(
            f"Session.title must be ≤ {SESSION_TITLE_MAX_LENGTH} chars (got {len(title)})"
        )
    if description is not None and len(description) > SESSION_DESCRIPTION_MAX_LENGTH:
        raise ValueError(
            f"Session.description must be ≤ {SESSION_DESCRIPTION_MAX_LENGTH} chars "
            f"(got {len(description)})"
        )
    if (
        session_instructions is not None
        and len(session_instructions) > SESSION_DESCRIPTION_MAX_LENGTH
    ):
        raise ValueError(
            f"Session.session_instructions must be ≤ "
            f"{SESSION_DESCRIPTION_MAX_LENGTH} chars (got {len(session_instructions)})"
        )


def _validate_session_enums(kind: str, permission_mode: str | None) -> None:
    """Raise if kind or permission_mode fall outside their known alphabets."""
    if kind not in KNOWN_SESSION_KINDS:
        raise ValueError(f"Session.kind {kind!r} not in {sorted(KNOWN_SESSION_KINDS)}")
    if permission_mode is not None and permission_mode not in KNOWN_SDK_PERMISSION_MODES:
        raise ValueError(
            f"Session.permission_mode {permission_mode!r} not in "
            f"{sorted(KNOWN_SDK_PERMISSION_MODES)}"
        )


def _validate_session_numerics(
    max_budget_usd: float | None,
    total_cost_usd: float,
    message_count: int,
) -> None:
    """Raise if any numeric field violates its floor constraint."""
    if max_budget_usd is not None and max_budget_usd < 0:
        raise ValueError(f"Session.max_budget_usd must be ≥ 0 if set (got {max_budget_usd})")
    if total_cost_usd < 0:
        raise ValueError(f"Session.total_cost_usd must be ≥ 0 (got {total_cost_usd})")
    if message_count < 0:
        raise ValueError(f"Session.message_count must be ≥ 0 (got {message_count})")


def _validate_session_closing(closing_summary: str | None) -> None:
    """Raise if closing_summary violates its min/max length bounds."""
    if closing_summary is None:
        return
    length = len(closing_summary)
    if length < SESSION_CLOSING_SUMMARY_MIN_LENGTH:
        raise ValueError(
            f"Session.closing_summary must be ≥ "
            f"{SESSION_CLOSING_SUMMARY_MIN_LENGTH} chars when set (got {length})"
        )
    if length > SESSION_CLOSING_SUMMARY_MAX_LENGTH:
        raise ValueError(
            f"Session.closing_summary must be ≤ "
            f"{SESSION_CLOSING_SUMMARY_MAX_LENGTH} chars (got {length})"
        )


def _validate_session_routing(
    model: str,
    routing_advisor_model: str | None,
    routing_advisor_max_uses: int,
    routing_effort_level: str,
) -> None:
    """Raise if routing fields violate model, max_uses, or effort_level constraints."""
    if not _is_known_model(model):
        raise ValueError(
            f"Session.model {model!r} is neither a known short name "
            f"{sorted(KNOWN_EXECUTOR_MODELS)} nor a full SDK ID prefixed with "
            f"{EXECUTOR_MODEL_FULL_ID_PREFIX!r}"
        )
    if routing_advisor_model is not None and not _is_known_model(routing_advisor_model):
        raise ValueError(
            f"Session.routing_advisor_model {routing_advisor_model!r} "
            f"is neither a known short name {sorted(KNOWN_EXECUTOR_MODELS)} "
            f"nor a full SDK ID prefixed with {EXECUTOR_MODEL_FULL_ID_PREFIX!r}"
        )
    if routing_advisor_max_uses < 0:
        raise ValueError(
            f"Session.routing_advisor_max_uses must be ≥ 0 (got {routing_advisor_max_uses})"
        )
    if routing_effort_level not in KNOWN_EFFORT_LEVELS:
        raise ValueError(
            f"Session.routing_effort_level {routing_effort_level!r} "
            f"not in {sorted(KNOWN_EFFORT_LEVELS)}"
        )


# ---------------------------------------------------------------------------
# Session dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    """Row mirror for the ``sessions`` table.

    Validation (``__post_init__``) covers: empty required fields, kind and
    permission_mode alphabets, title/description/session_instructions length
    caps, non-negative numerics, model recognition, routing field bounds.
    """

    id: str
    kind: str
    title: str
    description: str | None
    session_instructions: str | None
    working_dir: str
    model: str
    permission_mode: str | None
    max_budget_usd: float | None
    total_cost_usd: float
    message_count: int
    last_context_pct: float | None
    last_context_tokens: int | None
    last_context_max: int | None
    pinned: bool
    error_pending: bool
    checklist_item_id: int | None
    created_at: str
    updated_at: str
    last_viewed_at: str | None
    last_completed_at: str | None
    closed_at: str | None
    closing_summary: str | None
    routing_advisor_model: str | None
    routing_advisor_max_uses: int
    routing_effort_level: str
    pivot_message_id: str | None
    parent_session_id: str | None
    template_id: int | None
    # T2-07: classification flag — set by spawn_classify route.
    classified: bool

    def __post_init__(self) -> None:
        _validate_session_required(self.id, self.title, self.working_dir, self.model)
        _validate_session_lengths(self.title, self.description, self.session_instructions)
        _validate_session_enums(self.kind, self.permission_mode)
        _validate_session_numerics(self.max_budget_usd, self.total_cost_usd, self.message_count)
        _validate_session_closing(self.closing_summary)
        _validate_session_routing(
            self.model,
            self.routing_advisor_model,
            self.routing_advisor_max_uses,
            self.routing_effort_level,
        )


# ---------------------------------------------------------------------------
# SQL filter-clause builders (shared by list_all / list_paged)
# ---------------------------------------------------------------------------

_NO_SEVERITY_EXISTS = (
    "NOT EXISTS ("
    "SELECT 1 FROM session_tags st_sv "
    "JOIN tags t_sv ON t_sv.id = st_sv.tag_id "
    "WHERE st_sv.session_id = sessions.id AND t_sv.class = 'severity'"
    ")"
)


def _validate_list_all_args(kind: str | None, tag_ids: tuple[int, ...] | None) -> None:
    """Raise if kind or tag_ids violate list_all preconditions."""
    if kind is not None and kind not in KNOWN_SESSION_KINDS:
        raise ValueError(f"list_all: kind {kind!r} not in {sorted(KNOWN_SESSION_KINDS)}")
    if tag_ids is not None and len(tag_ids) == 0:
        raise ValueError(
            "list_all: tag_ids must be non-empty when provided (use None for no filter)"
        )


def _append_tag_ids_filter(
    tag_ids: tuple[int, ...] | None,
    clauses: list[str],
    args: list[object],
) -> None:
    """Append the legacy flat OR tag_ids JOIN clause when provided."""
    if tag_ids is not None:
        placeholders = ",".join(["?"] * len(tag_ids))
        clauses.append(f"session_tags.tag_id IN ({placeholders})")
        args.extend(tag_ids)


def _append_section_filter(
    tag_ids_section: tuple[int, ...] | None,
    clauses: list[str],
    args: list[object],
) -> None:
    """Append a plain EXISTS subquery for project or other tag classes."""
    if tag_ids_section:
        placeholders = ",".join(["?"] * len(tag_ids_section))
        clauses.append(
            "EXISTS (SELECT 1 FROM session_tags st_section "
            "WHERE st_section.session_id = sessions.id "
            f"AND st_section.tag_id IN ({placeholders}))"
        )
        args.extend(tag_ids_section)


def _append_severity_filter(
    severity_none: bool,
    tag_ids_severity: tuple[int, ...] | None,
    clauses: list[str],
    args: list[object],
) -> None:
    """Append the severity-section filter (OR-within for severity_none + ids)."""
    if severity_none and tag_ids_severity:
        placeholders = ",".join(["?"] * len(tag_ids_severity))
        clauses.append(
            f"({_NO_SEVERITY_EXISTS} OR EXISTS ("
            "SELECT 1 FROM session_tags st_sv2 "
            "WHERE st_sv2.session_id = sessions.id "
            f"AND st_sv2.tag_id IN ({placeholders})))"
        )
        args.extend(tag_ids_severity)
    elif severity_none:
        clauses.append(_NO_SEVERITY_EXISTS)
    elif tag_ids_severity:
        _append_section_filter(tag_ids_severity, clauses, args)


# ---------------------------------------------------------------------------
# update_fields sentinel + per-field validators
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _apply_title_field(
    title: object,
    assignments: list[str],
    params: list[object],
) -> None:
    """Validate and queue the title field update when not _SENTINEL."""
    if title is _SENTINEL:
        return
    if not isinstance(title, str) or not title:
        raise ValueError("update_fields: title must be a non-empty string")
    if len(title) > SESSION_TITLE_MAX_LENGTH:
        raise ValueError(f"update_fields: title must be ≤ {SESSION_TITLE_MAX_LENGTH} chars")
    assignments.append("title = ?")
    params.append(title)


def _apply_description_field(
    description: object,
    assignments: list[str],
    params: list[object],
) -> None:
    """Validate and queue the description field update when not _SENTINEL."""
    if description is _SENTINEL:
        return
    if description is not None:
        if not isinstance(description, str):
            raise ValueError("update_fields: description must be a string or None")
        if len(description) > SESSION_DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"update_fields: description must be ≤ {SESSION_DESCRIPTION_MAX_LENGTH} chars"
            )
    assignments.append("description = ?")
    params.append(description)


def _apply_budget_field(
    max_budget_usd: object,
    assignments: list[str],
    params: list[object],
) -> None:
    """Validate and queue the max_budget_usd field update when not _SENTINEL."""
    if max_budget_usd is _SENTINEL:
        return
    if max_budget_usd is not None:
        if not isinstance(max_budget_usd, (int, float)):
            raise ValueError("update_fields: max_budget_usd must be a number or None")
        if max_budget_usd < 0:
            raise ValueError("update_fields: max_budget_usd must be ≥ 0")
    assignments.append("max_budget_usd = ?")
    params.append(max_budget_usd)


def _apply_instructions_field(
    session_instructions: object,
    assignments: list[str],
    params: list[object],
) -> None:
    """Validate and queue the session_instructions field update when not _SENTINEL."""
    if session_instructions is _SENTINEL:
        return
    if session_instructions is not None:
        if not isinstance(session_instructions, str):
            raise ValueError("update_fields: session_instructions must be a string or None")
        if len(session_instructions) > SESSION_DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"update_fields: session_instructions must be ≤ "
                f"{SESSION_DESCRIPTION_MAX_LENGTH} chars"
            )
    assignments.append("session_instructions = ?")
    params.append(session_instructions)
