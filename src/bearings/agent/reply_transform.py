# mypy: disable-error-code=explicit-any
"""One-shot LLM text-transformation via the Claude Agent SDK.

Factory for the :data:`bearings.web.routes.reply_actions.run_transform`
callable.  Separated from the route module so the ``agent/`` layer owns the
SDK call and the ``web/`` layer owns the HTTP route.

Wire at startup::

    from bearings.agent.reply_transform import build_run_transform
    import bearings.web.routes.reply_actions as reply_actions_mod

    reply_actions_mod.run_transform = build_run_transform()

Design notes
------------

* Uses :func:`claude_agent_sdk.query` (one-shot, stateless) rather than
  :class:`claude_agent_sdk.ClaudeSDKClient` (stateful, bidirectional).
  Reply-action transforms are stateless: a single user message in, a
  single assistant response out.  The ``query()`` API is the right
  primitive per its docstring.
* ``tools=[]`` disables all built-in tools — the transform is pure
  text-in / text-out and must not browse the filesystem or run bash.
* ``max_turns=1`` caps at one exchange so a model that tries to loop
  terminates cleanly.
* The SDK opens a fresh anonymous session on each call; there is no
  session reuse.  This keeps the surface stateless and avoids leaking
  one user's context into another's transform.
* Errors from the SDK (``is_error=True`` on :class:`ResultMessage`)
  raise :class:`RuntimeError` so the route handler translates them to
  HTTP 502 via its generic ``except Exception`` guard.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk import query as _sdk_query

_LOG = logging.getLogger(__name__)

#: Type alias matching :data:`bearings.web.routes.reply_actions._RunTransformFn`.
_RunTransformFn = Callable[[str, str], Awaitable[str]]


def build_run_transform() -> _RunTransformFn:
    """Return a coroutine function that transforms text via a single Claude turn.

    Each invocation of the returned callable opens a fresh anonymous SDK
    session and collects the :class:`claude_agent_sdk.ResultMessage` from
    the async event stream.

    Raises
    ------
    RuntimeError
        When the SDK returns no :class:`ResultMessage` (unexpected stream end)
        or the result message carries ``is_error=True``.
    """

    async def _transform(content: str, instruction: str) -> str:
        """Apply *instruction* to *content* via one Claude turn."""
        prompt = f"{instruction}\n\n---\n\n{content}"
        result_text: str | None = None
        async for event in _sdk_query(
            prompt=prompt,
            options=ClaudeAgentOptions(max_turns=1, tools=[]),
        ):
            if isinstance(event, ResultMessage):
                if event.is_error:
                    raise RuntimeError(
                        f"reply_transform: SDK query returned is_error=True "
                        f"(result={event.result!r})"
                    )
                result_text = event.result

        if result_text is None:
            raise RuntimeError("reply_transform: SDK query returned no ResultMessage")
        return result_text

    return _transform


__all__ = ["build_run_transform"]
