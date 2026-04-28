"""Tag → :class:`SessionConfig` default-overlay helper.

Per ``docs/architecture-v1.md`` §1.1.4 the ``agent`` layer owns
domain-level glue between the SDK-shaped runtime types
(:class:`bearings.agent.session.SessionConfig`,
:class:`bearings.agent.routing.RoutingDecision`) and the storage layer
(:class:`bearings.db.tags.Tag`). The DB layer cannot import from
``agent`` (arch §3.1 layer rule), so the bridge lives here.

Per ``docs/behavior/checklists.md`` "the chat inherits the checklist's
working directory, model, and tags" — tags carry inheritance fields
(:attr:`Tag.default_model`, :attr:`Tag.working_dir`) that flow into the
session at creation time. Per ``docs/behavior/chat.md`` §"When the user
creates a chat" the user's explicit picks (working directory,
executor model in the routing-preview line) are also valid sources of
the same fields. This module specifies the precedence so the call site
in the API layer (item 1.5+) is deterministic.

Multi-tag precedence (decided-and-documented)
---------------------------------------------

When a session carries multiple tags whose ``default_model`` /
``working_dir`` fields are both populated, the most-recently-updated
tag wins. The behavior docs are silent on this case — chat.md and
checklists.md describe inheritance from a single source ("the
checklist's working directory, model, and tags") and don't address
multi-tag overlap. Decided rationale:

* **Most-recently-updated**: a user who edits a tag's defaults is
  signalling "this is what I want now"; ``updated_at DESC`` honours
  that intent. If the user wanted explicit precedence they'd reorder
  by name (which we sort ascending elsewhere) or use one tag at a
  time, neither of which surfaces well.

* **Tie-break by id ASC**: deterministic when two tags share an
  ``updated_at`` (possible inside one transaction). Lower id = older
  tag = the more-established intent wins on a tie.

* **Caller-supplied override beats every tag**: the API layer can
  pass an explicit ``working_dir`` or executor model, and that
  overrides any tag-derived default. This mirrors
  :func:`bearings.agent.templates.build_session_config_from_template`'s
  resolution order.

If a future arch amendment promotes tag-priority to a first-class
column (sorted-by-priority precedence), this module's helpers stay
backward-compatible — the precedence function gains a sort key.
"""

from __future__ import annotations

from bearings.db.tags import Tag


def resolve_default_model(
    tags: list[Tag],
    *,
    explicit: str | None = None,
) -> str | None:
    """Return the resolved executor model for a session carrying ``tags``.

    Resolution order (most specific wins):

    * ``explicit`` argument — caller's explicit pick from the
      new-session dialog or the API request body.
    * Most-recently-updated tag with a non-null ``default_model``.
    * ``None`` if no source supplies a model — the caller layers
      template / system-default resolution downstream.
    """
    if explicit is not None:
        return explicit
    candidates = [tag for tag in tags if tag.default_model is not None]
    if not candidates:
        return None
    chosen = max(candidates, key=_tag_precedence_key)
    return chosen.default_model


def resolve_working_dir(
    tags: list[Tag],
    *,
    explicit: str | None = None,
) -> str | None:
    """Return the resolved working directory for a session carrying ``tags``.

    Same resolution order as :func:`resolve_default_model`. ``None``
    means no source supplied a directory and the caller must surface a
    validation error to the user (per ``docs/behavior/chat.md`` "a
    working directory" is a required field of the new-session dialog).
    """
    if explicit is not None:
        return explicit
    candidates = [tag for tag in tags if tag.working_dir is not None]
    if not candidates:
        return None
    chosen = max(candidates, key=_tag_precedence_key)
    return chosen.working_dir


def _tag_precedence_key(tag: Tag) -> tuple[str, int]:
    """Sort key for multi-tag precedence: ``(updated_at, -id)`` descending.

    Returns a tuple where ``max(...)`` picks the most-recently-updated
    tag, with the lower-id tag winning on an ``updated_at`` tie. The
    negative id achieves the ASC tie-break under :func:`max` (largest
    negative = smallest absolute id).
    """
    return (tag.updated_at, -tag.id)


__all__ = ["resolve_default_model", "resolve_working_dir"]
