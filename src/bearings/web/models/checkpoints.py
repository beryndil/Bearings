# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/checkpoints.py`` (G6).

Per ``docs/architecture-v1.md`` §1.1.5 the wire DTOs live alongside
their route module. The shapes mirror :class:`bearings.db.checkpoints.Checkpoint`
plus thin result envelopes for the fork and compare actions.

The ``mypy: disable-error-code=explicit-any`` pragma is the same narrow
carve-out the other ``web/models/*.py`` files make for Pydantic's
metaclass-exposed ``Any`` surface — every public ``BaseModel`` subclass
below has a fully-typed field set.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bearings.config.constants import CHECKPOINT_LABEL_MAX_LENGTH


class CheckpointIn(BaseModel):
    """Request body for ``POST /api/checkpoints``.

    Validators mirror :class:`bearings.db.checkpoints.Checkpoint.__post_init__`
    so a bad payload fails at the wire boundary with a 422 rather than
    surfacing a 500 from the dataclass downstream. ``model_config``
    forbids extra fields so a typo (e.g. ``messageId`` instead of
    ``message_id``) is rejected loudly.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    label: str | None = Field(
        default=None,
        max_length=CHECKPOINT_LABEL_MAX_LENGTH,
        description=(
            "User-visible chip text. When omitted the route layer "
            "synthesises a default per "
            ":data:`bearings.config.constants.DEFAULT_CHECKPOINT_LABEL_TEMPLATE`."
        ),
    )


class CheckpointOut(BaseModel):
    """Response body for checkpoint endpoints.

    One-to-one with :class:`bearings.db.checkpoints.Checkpoint`.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    message_id: str
    label: str
    created_at: str


class CheckpointForkResult(BaseModel):
    """Response body for ``POST /api/checkpoints/{id}/fork``.

    The fork action clones the source session row + replays messages up
    to and including the checkpoint anchor into a new session. The wire
    envelope carries both pieces so the frontend can navigate to the
    new session without a follow-up fetch.
    """

    model_config = ConfigDict(extra="forbid")

    new_session_id: str
    source_session_id: str
    checkpoint_id: str
    message_count: int


class CheckpointDeltaMessage(BaseModel):
    """One message in the delta returned by ``GET /api/checkpoints/{id}/compare``.

    Carries only the fields the diff-view modal needs: identity, role,
    content, and timestamp. Routing/usage columns are omitted -- the
    compare view surfaces *what* was said, not *how* it was routed.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    content: str
    created_at: str


class CheckpointCompareResult(BaseModel):
    """Response body for ``GET /api/checkpoints/{id}/compare``.

    ``delta_messages`` contains every message whose ``rowid`` is
    greater than the anchor message's ``rowid`` -- i.e. every message
    added to the session *after* the checkpoint was created.

    ``delta_message_count`` mirrors ``len(delta_messages)`` and is
    provided as a convenience so the frontend can branch on zero without
    iterating the array before it renders.
    """

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    checkpoint_label: str
    anchor_message_id: str
    delta_message_count: int
    delta_messages: list[CheckpointDeltaMessage]


__all__ = [
    "CheckpointCompareResult",
    "CheckpointDeltaMessage",
    "CheckpointForkResult",
    "CheckpointIn",
    "CheckpointOut",
]
