"""Multi-overlay :class:`SessionConfig` assembler.

Per ``docs/architecture-v1.md`` §1.1.4 + §4.8 every code path that
materialises a fresh :class:`bearings.agent.session.SessionConfig`
flows through one canonical overlay chain. Item 1.7 lays this module
because three concrete consumers all need the same composition:

* paired-chat spawn (``agent/paired_chats.py:spawn_paired_chat``);
* the prompt-endpoint's lazy session creation (out of v0.18.0 scope —
  the endpoint per ``docs/behavior/prompt-endpoint.md`` only ever
  resumes existing sessions, but the assembler is the boundary the
  future create-on-POST surface will call);
* the auto-driver's ``leg_session_factory`` callback
  (``agent/auto_driver_runtime.py``) — each leg is a fresh chat
  session inheriting the parent checklist's tags + working dir.

Overlay precedence (most-specific wins; tested in
``tests/test_session_assembly.py``):

1. **Global default** — :data:`bearings.config.constants` workhorse
   pair (``DEFAULT_TEMPLATE_MODEL`` = ``sonnet``,
   ``DEFAULT_TEMPLATE_ADVISOR_MODEL`` = ``opus``,
   ``DEFAULT_TEMPLATE_ADVISOR_MAX_USES`` = 5,
   ``DEFAULT_TEMPLATE_EFFORT_LEVEL`` = ``auto``,
   ``DEFAULT_TEMPLATE_PERMISSION_PROFILE`` = ``standard``). These are
   the spec §3 priority-1000 always-rule defaults.
2. **Template overlay** — when ``template_id`` is supplied, the
   template's executor / advisor / effort / permission_profile fields
   land per :func:`bearings.agent.templates.build_session_config_from_template`.
3. **Tag-default overlay** — when ``tags`` is non-empty, the tag-side
   ``default_model`` / ``working_dir`` resolve via
   :func:`bearings.agent.tags.resolve_default_model` /
   :func:`bearings.agent.tags.resolve_working_dir`. Tag defaults beat
   template defaults because the user picked the tag *for this
   session* (the template was a starting shape; the tag is the
   classification).
4. **Explicit user input** — every keyword argument the API request
   set (``model``, ``advisor_model``, ``working_dir``, etc.) wins over
   every overlay below it. Mirrors the new-session-dialog observable
   per ``docs/behavior/chat.md`` §"When the user creates a chat":
   what the user typed in the form is what the session gets.

Routing-decision plumbing (item 1.8 forward-carry):

The assembler emits a :class:`RoutingDecision` whose ``source`` is
``"manual"`` when the executor/advisor came from the user's explicit
input or a template, ``"default"`` when no input or rule fired
(pure global default fallback). The full evaluator
(``agent/routing.py:evaluate``) lands in item 1.8 — it will replace
the placeholder shape produced here with a tag-rule / system-rule
match against the first user message. The DB row's ``routing_*``
columns persist the placeholder until 1.8's first turn evaluates.
This is shape **(a) pass-through stub** per the item plug's choice
matrix (decided-and-documented; rationale: the data shape persists
correctly day 1 — 1.8 is a swap-in, not a schema migration).
"""

from __future__ import annotations

import aiosqlite

from bearings.agent.routing import RoutingDecision
from bearings.agent.session import PermissionProfile, SessionConfig
from bearings.agent.tags import resolve_default_model, resolve_working_dir
from bearings.config.constants import (
    DEFAULT_TEMPLATE_ADVISOR_MAX_USES,
    DEFAULT_TEMPLATE_ADVISOR_MODEL,
    DEFAULT_TEMPLATE_EFFORT_LEVEL,
    DEFAULT_TEMPLATE_MODEL,
    DEFAULT_TEMPLATE_PERMISSION_PROFILE,
)
from bearings.db import tags as tags_db
from bearings.db import templates as templates_db
from bearings.db.tags import Tag


class SessionAssemblyError(ValueError):
    """The overlay chain could not assemble a complete :class:`SessionConfig`.

    Distinct from :class:`ValueError` so the API layer (and the
    paired-chat / auto-driver call sites) can pattern-match a missing
    working directory (the one mandatory field that has no default
    anywhere in the chain) versus a SessionConfig field-shape problem.
    """


async def build_session_config(
    connection: aiosqlite.Connection,
    *,
    session_id: str,
    tag_ids: list[int] | None = None,
    template_id: int | None = None,
    working_dir: str | None = None,
    model: str | None = None,
    advisor_model: str | None = None,
    advisor_max_uses: int | None = None,
    effort_level: str | None = None,
    permission_profile: str | None = None,
) -> SessionConfig:
    """Compose a :class:`SessionConfig` from layered defaults.

    Args:
        connection: Open aiosqlite connection (reads tags + templates).
        session_id: The new session's id (caller-supplied;
            :class:`SessionConfig` rejects empty).
        tag_ids: Optional list of tag ids; their
            :attr:`Tag.default_model` / :attr:`Tag.working_dir` flow
            through the precedence chain via
            :func:`bearings.agent.tags.resolve_default_model` /
            :func:`bearings.agent.tags.resolve_working_dir`.
        template_id: Optional template row id; its routing fields land
            below tag overlay but above the global default.
        working_dir: Explicit user pick — wins over every overlay.
        model: Explicit executor pick.
        advisor_model: Explicit advisor pick. Pass ``""`` (empty
            string) to *positively* disable the advisor; ``None``
            means "fall through to overlays".
        advisor_max_uses: Explicit advisor max-uses pick.
        effort_level: Explicit effort label.
        permission_profile: Explicit permission profile name.

    Returns:
        A frozen :class:`SessionConfig` with a placeholder
        :class:`RoutingDecision`. The decision's ``source`` is
        ``"manual"`` if any explicit field was supplied or the template
        contributed; ``"default"`` for the pure global-default fallback.

    Raises:
        SessionAssemblyError: Working directory could not be resolved
            from any overlay.
        TemplateNotFoundError: ``template_id`` does not match a row.
        ValueError: A composed field is invalid against
            :class:`SessionConfig.__post_init__` (e.g. unknown effort
            label, malformed model id).
    """
    tags = await _load_tags(connection, tag_ids)
    template = None
    if template_id is not None:
        template = await templates_db.get(connection, template_id)
        if template is None:
            from bearings.agent.templates import TemplateNotFoundError

            raise TemplateNotFoundError(f"no template with id {template_id}")
    # Mark the source as manual when *any* user-side signal is present
    # (explicit field, template, or non-empty tag set with a
    # default_model). Pure global default = source="default".
    user_supplied_anything = any(
        value is not None
        for value in (
            working_dir,
            model,
            advisor_model,
            advisor_max_uses,
            effort_level,
            permission_profile,
        )
    )
    has_template_contribution = template is not None
    tag_contributes_model = any(t.default_model is not None for t in tags)
    source = (
        "manual"
        if (user_supplied_anything or has_template_contribution or tag_contributes_model)
        else "default"
    )

    # Resolve each routing field — explicit > template > tags > global.
    resolved_model = _resolve_executor_model(
        explicit=model,
        template_value=None if template is None else template.model,
        tags=tags,
    )
    resolved_advisor = _resolve_advisor(
        explicit=advisor_model,
        template_value=None if template is None else template.advisor_model,
    )
    resolved_advisor_max = _resolve_int(
        explicit=advisor_max_uses,
        template_value=None if template is None else template.advisor_max_uses,
        global_value=DEFAULT_TEMPLATE_ADVISOR_MAX_USES,
    )
    resolved_effort = _resolve_str(
        explicit=effort_level,
        template_value=None if template is None else template.effort_level,
        global_value=DEFAULT_TEMPLATE_EFFORT_LEVEL,
    )
    resolved_profile_name = _resolve_str(
        explicit=permission_profile,
        template_value=None if template is None else template.permission_profile,
        global_value=DEFAULT_TEMPLATE_PERMISSION_PROFILE,
    )
    resolved_working_dir = _resolve_working_dir(
        explicit=working_dir,
        template_value=None if template is None else template.working_dir_default,
        tags=tags,
    )
    if not resolved_working_dir:
        raise SessionAssemblyError(
            "working_dir could not be resolved — supply explicitly, set on a tag, "
            "or pick a template with working_dir_default"
        )

    # Build the placeholder routing decision (item 1.8 swap-in target).
    decision = RoutingDecision(
        executor_model=resolved_model,
        advisor_model=resolved_advisor,
        advisor_max_uses=resolved_advisor_max,
        effort_level=resolved_effort,
        source=source,
        reason=_build_reason(
            source=source,
            template_name=None if template is None else template.name,
            tag_count=len(tags),
        ),
        matched_rule_id=None,
    )

    profile = PermissionProfile(resolved_profile_name)
    return SessionConfig(
        session_id=session_id,
        working_dir=resolved_working_dir,
        decision=decision,
        db=connection,
        permission_profile=profile,
    )


async def _load_tags(
    connection: aiosqlite.Connection,
    tag_ids: list[int] | None,
) -> list[Tag]:
    """Resolve ``tag_ids`` to :class:`Tag` rows, dropping any that vanished.

    A tag the API caller named that no longer exists is silently
    dropped (no exception). The decided-and-documented rationale: a
    user who attaches a tag and then deletes it before submit should
    see the post-deletion state — the assembler is downstream of the
    tag CRUD path and treats the input list as a hint, not a contract.
    """
    if not tag_ids:
        return []
    resolved: list[Tag] = []
    for tag_id in tag_ids:
        tag = await tags_db.get(connection, tag_id)
        if tag is not None:
            resolved.append(tag)
    return resolved


def _resolve_executor_model(
    *,
    explicit: str | None,
    template_value: str | None,
    tags: list[Tag],
) -> str:
    """Walk the precedence chain for executor model.

    Order: explicit > tags > template > global default. (Tags beat
    template because the per-session classification is more specific
    than the template starting shape — see module docstring.)
    """
    if explicit is not None:
        return explicit
    tag_resolved = resolve_default_model(tags)
    if tag_resolved is not None:
        return tag_resolved
    if template_value is not None:
        return template_value
    return DEFAULT_TEMPLATE_MODEL


def _resolve_advisor(
    *,
    explicit: str | None,
    template_value: str | None,
) -> str | None:
    """Walk the precedence chain for advisor model.

    The empty-string convention: ``explicit=""`` means the user
    *positively* disabled the advisor in the new-session dialog
    (per ``docs/behavior/chat.md`` advisor toggle), and overrides any
    template default. ``explicit=None`` means "fall through to
    overlays".
    """
    if explicit is not None:
        return explicit if explicit else None
    if template_value is not None:
        return template_value
    return DEFAULT_TEMPLATE_ADVISOR_MODEL


def _resolve_int(
    *,
    explicit: int | None,
    template_value: int | None,
    global_value: int,
) -> int:
    """Walk the precedence chain for an int field with a global fallback."""
    if explicit is not None:
        return explicit
    if template_value is not None:
        return template_value
    return global_value


def _resolve_str(
    *,
    explicit: str | None,
    template_value: str | None,
    global_value: str,
) -> str:
    """Walk the precedence chain for a string field with a global fallback."""
    if explicit is not None:
        return explicit
    if template_value is not None:
        return template_value
    return global_value


def _resolve_working_dir(
    *,
    explicit: str | None,
    template_value: str | None,
    tags: list[Tag],
) -> str | None:
    """Walk the precedence chain for working_dir.

    Returns ``None`` if no overlay supplies a value — the caller
    surfaces :class:`SessionAssemblyError` since working_dir has no
    global default. Tags beat template per the module-level
    precedence rationale.
    """
    if explicit is not None:
        return explicit
    tag_resolved = resolve_working_dir(tags)
    if tag_resolved is not None:
        return tag_resolved
    return template_value


def _build_reason(
    *,
    source: str,
    template_name: str | None,
    tag_count: int,
) -> str:
    """Produce the ``RoutingDecision.reason`` string for the placeholder.

    The exact wording surfaces in the routing-badge tooltip (spec
    §App A) once item 1.8's evaluator runs — until then this is the
    placeholder text. Pinned for stable test assertions.
    """
    if source == "default":
        return "global default (workhorse Sonnet + Opus advisor)"
    if template_name is not None:
        return f"composed: template {template_name!r}, {tag_count} tag(s)"
    if tag_count > 0:
        return f"composed: {tag_count} tag(s) + explicit overrides"
    return "composed: explicit overrides"


__all__ = ["SessionAssemblyError", "build_session_config"]
