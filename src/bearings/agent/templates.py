"""Template → :class:`SessionConfig` build helper.

Per ``docs/architecture-v1.md`` §1.1.4 the ``agent`` layer owns
domain-level glue between the SDK-shaped runtime types
(:class:`bearings.agent.session.SessionConfig`,
:class:`bearings.agent.routing.RoutingDecision`) and the storage layer
(:class:`bearings.db.templates.Template`). The DB layer cannot import
from ``agent`` (arch §3.1 layer rule), so the bridge lives here.

Per ``docs/behavior/chat.md`` the new-session dialog accepts a template
selection that pre-populates the form; per
``docs/behavior/keyboard-shortcuts.md`` §"Create" the ``t`` chord opens
the template picker. The user can edit any pre-populated field before
pressing **Start Session** — i.e. the template values are *defaults*,
not constraints. This module produces the default
:class:`SessionConfig` from a :class:`Template`; the API layer (item
1.10) layers user overrides on top of the result.
"""

from __future__ import annotations

import aiosqlite

from bearings.agent.routing import RoutingDecision
from bearings.agent.session import PermissionProfile, SessionConfig
from bearings.db import templates as templates_db


class TemplateNotFoundError(LookupError):
    """The template id passed to :func:`build_session_config_from_template`
    did not match any row.

    Distinct from :class:`KeyError` so the API layer (item 1.10) can
    distinguish a missing template (404) from any other lookup failure.
    """


async def build_session_config_from_template(
    connection: aiosqlite.Connection,
    template_id: int,
    *,
    session_id: str,
    working_dir: str | None = None,
) -> SessionConfig:
    """Apply a :class:`Template`'s defaults to a fresh :class:`SessionConfig`.

    Resolution order (most specific wins):

    * ``working_dir`` argument — explicit user choice in the new-
      session dialog, takes precedence over the template's
      ``working_dir_default``.
    * Template's ``working_dir_default`` — the template's preferred
      directory.
    * Raises :class:`ValueError` if neither is set: the user must
      pick a working directory per ``docs/behavior/chat.md`` §"When
      the user creates a chat".

    The resulting :class:`SessionConfig` carries:

    * a :class:`RoutingDecision` built from the template's executor /
      advisor / effort fields, sourced as ``"manual"`` (the user
      selected this template intentionally — spec §App A reserves
      ``"tag_rule"`` / ``"system_rule"`` for the routing evaluator).
      Item 1.8 considered swapping this path to call
      :func:`bearings.agent.routing.evaluate`; rejected because a
      template *is* the user's explicit routing choice — running the
      evaluator on top would mean a tag rule could silently override
      the template the user picked, which contradicts the
      new-session-dialog precedence per ``docs/behavior/chat.md``;
    * the template's permission profile;
    * ``db=connection`` so the resulting session can persist its turns;
    * SDK-default values for the rest (the template intentionally does
      not pin every SessionConfig field — the v1 templates surface is
      "model + advisor + effort + permission + tag set + system prompt
      + working dir", per the master-item brief).

    The system-prompt baseline (``Template.system_prompt_baseline``)
    flows through into the prompt assembler at item 1.10's API
    boundary, not via :class:`SessionConfig` directly — the assembler
    reads tag memories + session_instructions per turn, and a template-
    sourced baseline lands as the session's ``description`` /
    ``session_instructions`` field at row creation. Keeping that
    plumbing at the API layer matches arch §1.1.4's "agent does not
    own row-create semantics".
    """
    template = await templates_db.get(connection, template_id)
    if template is None:
        raise TemplateNotFoundError(f"no template with id {template_id}")
    resolved_working_dir = working_dir or template.working_dir_default
    if not resolved_working_dir:
        raise ValueError(
            "build_session_config_from_template requires a working_dir argument when the "
            f"template (id={template_id}, name={template.name!r}) has no working_dir_default"
        )
    decision = RoutingDecision(
        executor_model=template.model,
        advisor_model=template.advisor_model,
        advisor_max_uses=template.advisor_max_uses,
        effort_level=template.effort_level,
        source="manual",
        reason=f"template: {template.name}",
        matched_rule_id=None,
    )
    profile = PermissionProfile(template.permission_profile)
    return SessionConfig(
        session_id=session_id,
        working_dir=resolved_working_dir,
        decision=decision,
        db=connection,
        permission_profile=profile,
    )


__all__ = ["TemplateNotFoundError", "build_session_config_from_template"]
