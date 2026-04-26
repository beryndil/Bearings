"""Reorg-operation DTOs: move / split / merge request & result shapes
plus the persistent audit row.

Slice 6 (LLM-assisted analyze, v0.18.0) layered on
`ReorgAnalyzeRequest` / `ReorgAnalyzeResult` / `ReorgProposal` /
`ReorgProposalSession`. The analyzer is read-only — it returns
proposed splits; the frontend orchestrates the actual `/reorg/split`
calls per approved proposal."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .sessions import NewSessionSpec, SessionOut


class ReorgWarning(BaseModel):
    """Advisory issue surfaced by a reorg op — never fatal.

    Slice 2 always returns an empty `warnings` array; Slice 7 (Polish)
    populates this with tool-call-group split detection. The model is
    defined now so the API shape is stable and the future addition is
    non-breaking.
    """

    code: str
    message: str
    details: dict[str, str] = {}


class ReorgMoveRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/move`. `message_ids` must
    be non-empty; the route rejects an empty list with 400 even though
    the underlying primitive tolerates it as a no-op."""

    target_session_id: str
    message_ids: list[str]


class ReorgMoveResult(BaseModel):
    """Response shape shared by `move` and (nested in) `split`.

    `moved` and `tool_calls_followed` come directly from
    `store.MoveResult`; `warnings` is the forward-compatible slot for
    Slice 7's group-split detection — currently always `[]`. `audit_id`
    is the row the route wrote to `reorg_audits`; `None` when the op
    was a no-op (zero moves) so no divider was recorded. The frontend
    threads this into its undo handler so `DELETE /reorg/audits/{id}`
    has a direct target — no lookup race against a concurrent second
    op landing in the same millisecond.
    """

    moved: int
    tool_calls_followed: int
    warnings: list[ReorgWarning] = []
    audit_id: int | None = None


class ReorgSplitRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/split`. `after_message_id`
    is the anchor — every message chronologically after it moves into
    the new session."""

    after_message_id: str
    new_session: NewSessionSpec


class ReorgSplitResult(BaseModel):
    """Response shape for split — the newly created session plus the
    inner move counts. 201 status code signals a resource was created."""

    session: SessionOut
    result: ReorgMoveResult


class ReorgMergeRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/merge`. Moves every message
    on the source session into `target_session_id` in a single op; set
    `delete_source=true` to drop the now-empty source. Merging a
    session into itself is rejected with a 400."""

    target_session_id: str
    delete_source: bool = False


class ReorgMergeResult(BaseModel):
    """Response shape for merge. Carries the same `moved` /
    `tool_calls_followed` / `warnings` / `audit_id` fields as
    move/split, plus `deleted_source` (always matches the request flag
    on success; flip to false means the DELETE call no-op'd because
    the source was already empty of messages and still-live).

    `audit_id` is `None` when no audit row was written — either a
    no-op merge (zero moves) or a merge that deleted the source (the
    cascade would have dropped the row, so the route skips the write)."""

    moved: int
    tool_calls_followed: int
    warnings: list[ReorgWarning] = []
    audit_id: int | None = None
    deleted_source: bool


class ReorgAnalyzeRequest(BaseModel):
    """Body for `POST /sessions/{id}/reorg/analyze`. `mode` picks the
    analyzer: `"heuristic"` runs the deterministic time-gap + Jaccard
    splitter (free, fast, no LLM); `"llm"` calls the SDK and parses a
    structured-JSON proposal list. The route falls back to heuristic
    when `mode="llm"` is requested but `agent.enable_llm_reorg_analyze`
    is False — keeps the failure mode visible in the response
    (`mode_used` echoes the actually-run analyzer)."""

    mode: Literal["llm", "heuristic"] = "heuristic"


class ReorgProposalSession(BaseModel):
    """Inline session draft attached to each proposal. The frontend
    treats this as a starting point — title / description / tag_ids
    are pre-populated from the analyzer's suggestion (heuristic copies
    source tags + auto-titles "Segment N (M messages)"; LLM picks a
    topical title and inherits source tags). `tag_ids` is non-empty by
    construction so the downstream `/reorg/split` call passes the v0.2.13
    tag-required gate without further validation. Severity tag is always
    copied from the source (per migration 0021 invariant —
    `ensure_default_severity` backfills if the LLM somehow drops it)."""

    title: str
    description: str | None = None
    tag_ids: list[int]


class ReorgProposal(BaseModel):
    """One proposed split — a contiguous run of messages the analyzer
    thinks belongs to a single topical thread.

    `message_ids` is ordered by source-session creation order; the
    frontend renders them as a collapsible preview on each proposal
    card. `topic` is the analyzer's one-line label (heuristic emits
    "Segment N"; LLM emits a topic phrase). `rationale` is a short
    explanation the LLM mode produces; heuristic mode emits a
    deterministic "split on time gap >2h" / "topic shift" string so
    the UI has consistent surface to render. `confidence` is the LLM's
    self-reported [0..1] score; heuristic mode emits 1.0 for time-gap
    splits and 0.6 for topic-distance splits (advisory — not used to
    auto-approve, just to sort cards)."""

    topic: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    message_ids: list[str]
    suggested_session: ReorgProposalSession


class ReorgAnalyzeResult(BaseModel):
    """Response shape for the analyze endpoint.

    `proposals` is the list of suggested splits — empty when the
    analyzer thinks the source is already coherent. `mode_used`
    echoes which analyzer actually ran (heuristic or llm); `"llm"`
    requests can degrade to `"heuristic"` when the LLM is disabled
    by config or the structured-JSON parse fails twice. `messages_in`
    is the source-session message count the analyzer saw — the UI
    renders it next to a rough cost estimate so the user can decide
    whether to re-run with a different mode. `notes` carries any
    advisory string the analyzer wants to surface (e.g. "fell back
    to heuristic: LLM disabled in config", "LLM JSON parse failed,
    showing heuristic instead"). Empty string when nothing to say."""

    proposals: list[ReorgProposal]
    mode_used: Literal["llm", "heuristic"]
    messages_in: int
    notes: str = ""


class ReorgAuditOut(BaseModel):
    """One persistent divider entry rendered on the source session's
    conversation view. The `target_session_id` FK is `ON DELETE SET
    NULL`, so a stale row with null id + a populated title snapshot
    means "the target was deleted after the move." The UI renders
    "(deleted session)" for that case instead of hiding the row."""

    id: int
    source_session_id: str
    target_session_id: str | None = None
    target_title_snapshot: str | None = None
    message_count: int
    op: Literal["move", "split", "merge"]
    created_at: str
