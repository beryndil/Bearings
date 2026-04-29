"""Auto-suggest session titles plan
(`~/.claude/plans/auto-suggesting-titles.md`).

Single-route module: `POST /sessions/{session_id}/suggest_titles`
returns three candidate titles for an existing chat session, derived
from a one-shot LLM call against the session's recent messages.

Gating mirrors `routes_reorg.reorg_analyze` LLM mode:

- 404 if the session does not exist.
- 400 if the session is not a chat (no messages to summarize).
- 503 if `agent.enable_llm_title_suggest` is False — the operator
  surface can render the message inline and tell the user which
  config key to flip.
- 503 if the suggester returns `(None, reason)` after its retries.

The route writes nothing. The frontend is expected to fill the
title input from the chosen candidate; the user still saves through
the normal `PATCH /sessions/{id}` path."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from bearings.agent.title_suggester import suggest_titles
from bearings.api.auth import require_auth
from bearings.api.models import SuggestTitlesResult
from bearings.db import store

router = APIRouter(
    prefix="/sessions",
    tags=["suggest_titles"],
    dependencies=[Depends(require_auth)],
)


@router.post(
    "/{session_id}/suggest_titles",
    response_model=SuggestTitlesResult,
)
async def suggest_session_titles(
    session_id: str,
    request: Request,
) -> SuggestTitlesResult:
    """Read the session's messages, drive a one-shot LLM call, and
    return three candidate titles. See module docstring for gate
    semantics."""
    conn = request.app.state.db
    settings = request.app.state.settings

    session = await store.get_session(conn, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.get("kind", "chat") != "chat":
        raise HTTPException(
            status_code=400,
            detail=f"suggest_titles requires a chat session (kind={session.get('kind')!r})",
        )

    if not settings.agent.enable_llm_title_suggest:
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM title-suggest disabled in config "
                "(set agent.enable_llm_title_suggest = true in config.toml)"
            ),
        )

    messages = await store.list_messages(conn, session_id)
    model = session.get("model") or settings.agent.model
    titles, notes = await suggest_titles(messages, model=model)
    if titles is None:
        raise HTTPException(
            status_code=503,
            detail=notes or "title suggester failed",
        )
    return SuggestTitlesResult(titles=titles)
