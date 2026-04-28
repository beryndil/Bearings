"""Pure builder of SDK-options kwargs from a :class:`RoutingDecision`.

This module lands the three deferred SDK-currency shifts that arch
§5's audit row and item 1.1's a1 audit confirmed are 1.2's territory:

* **Shift #2 — beta headers** (arch §5 #2 / #1).
  ``betas=[ADVISOR_TOOL_BETA_HEADER]`` is wired whenever
  :attr:`RoutingDecision.advisor_model` is non-``None`` so the SDK
  attaches the ``advisor-tool-2026-03-01`` beta. The header ID itself
  lives in :mod:`bearings.config.constants` per the item-0.5 "no inline
  literals" gate.
* **Shift #5 — fallback_model** (arch §5 #5).
  ``fallback_model`` is computed from
  :data:`bearings.config.constants.EXECUTOR_FALLBACK_MODEL` for every
  short-name executor (sonnet → haiku, opus → sonnet, haiku → haiku);
  full-form SDK IDs (``claude-…``) are returned verbatim because the
  spec doesn't define a tier-down for full IDs.
* **Shift #6 — subagent auto-select** (arch §5 #6).
  The ``researcher`` :class:`SubagentSpec` carries ``model='inherit'`` so
  the parent's executor runs it; "Haiku for Explore" is implemented at
  the routing layer (spec §3 priority-30 rule), not by pinning the
  subagent's model. The justification is the trade-off arch §5 #6
  states verbatim: pinning the subagent would override the parent's
  routing and double-cost an Opus parent's Task-tool dispatch.

Shift **#4 (effort levels)** is also threaded through here because it
shares the same call site: the spec-vocabulary
:attr:`RoutingDecision.effort_level` translates to the SDK's
``effort`` literal via :data:`EFFORT_LEVEL_TO_SDK`. ``auto`` maps to
``None`` ("omit the field — let the SDK pick") which downstream
splatters via dict-comprehension at the SDK boundary.

The function returns an :class:`OptionsKwargs` frozen dataclass instead
of an SDK :class:`claude_agent_sdk.ClaudeAgentOptions` directly. Three
reasons:

1. **Decoupling from the SDK type's ``Any``-bearing surface.** The SDK
   options object exposes ``Any`` in fields like ``hooks`` /
   ``mcp_servers`` / ``can_use_tool``; constructing it inside a
   ``mypy --strict`` + ``disallow_any_explicit`` module would force a
   file-level pragma carve-out. Restricting the carve-out to the call
   site (item 1.3+, where the runner composes the full options) is
   strictly better.
2. **Item 1.2's scope.** The ``Done-when`` calls for "WS plumbing +
   intra-call tool-output streaming" — not for full SDK option
   composition (which needs hooks / MCP / can_use_tool surfaces from
   later items). The kwargs carrier names exactly the deferred-shift
   surface and stops.
3. **Audit-friendliness.** Each deferred shift gets a discrete unit
   test against the carrier shape; the auditor doesn't have to mock
   the SDK types to verify the plumbing.

References:

* ``docs/architecture-v1.md`` §1.1.4 (``agent/options.py`` ≤250 lines).
* ``docs/architecture-v1.md`` §5 #1, #2, #4, #5, #6.
* ``docs/model-routing-v1-spec.md`` §App A (RoutingDecision shape) +
  §2 (advisor primitive default policy / max_uses).
"""

from __future__ import annotations

from dataclasses import dataclass

from bearings.agent.routing import RoutingDecision
from bearings.config.constants import (
    ADVISOR_TOOL_BETA_HEADER,
    EFFORT_LEVEL_TO_SDK,
    EXECUTOR_FALLBACK_MODEL,
    EXECUTOR_MODEL_FULL_ID_PREFIX,
)

# Researcher subagent prompt is large and lives in
# ``agent/researcher_prompt.py`` per arch §1.1.4. Item 1.2 doesn't need
# the full prompt body, only the metadata + ``model='inherit'`` wiring;
# a placeholder string keeps the carrier round-trippable in tests.
# Item 1.3+ replaces this with the real prompt import.
_RESEARCHER_DESCRIPTION: str = (
    "Fast agent specialized for exploring codebases. Use this when the "
    "parent needs to find files by patterns, search code for keywords, or "
    "answer questions about the codebase."
)
_RESEARCHER_PROMPT_PLACEHOLDER: str = (
    "(researcher subagent prompt — replaced by agent/researcher_prompt.py "
    "import in item 1.3+; item 1.2 carries the placeholder so the "
    "model='inherit' wiring per arch §5 #6 is verifiable in isolation.)"
)
# Read-only inspection toolset matches arch §5 #6 + the v0.17.x
# precedent (Read/Glob/Grep + write tools elided per the
# subagent's read-only role).
_RESEARCHER_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
)


@dataclass(frozen=True)
class SubagentSpec:
    """Source-of-truth for a Bearings-managed subagent.

    Translates 1:1 to SDK :class:`claude_agent_sdk.types.AgentDefinition`
    at the runtime boundary (deferred to item 1.3+); kept as a plain
    frozen dataclass here so the deferred-shift surface stays
    SDK-decoupled (see module docstring).

    The ``model`` field accepts:

    * ``'inherit'`` — parent's executor runs the subagent (arch §5 #6).
    * Any short name in
      :data:`bearings.config.constants.KNOWN_EXECUTOR_MODELS`.
    * Any full SDK model ID prefixed with
      :data:`bearings.config.constants.EXECUTOR_MODEL_FULL_ID_PREFIX`.

    The validation lives in :meth:`__post_init__` so a typo in a
    deferred-shift wiring fails at construction, not at an SDK call
    site three layers away.
    """

    name: str
    description: str
    prompt: str
    model: str
    tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SubagentSpec.name must be non-empty")
        if not self.description:
            raise ValueError("SubagentSpec.description must be non-empty")
        if not self.prompt:
            raise ValueError("SubagentSpec.prompt must be non-empty")
        if self.model != "inherit" and not self._is_known_model(self.model):
            raise ValueError(
                f"SubagentSpec.model {self.model!r} must be 'inherit', a known short "
                f"name, or a full SDK ID prefixed {EXECUTOR_MODEL_FULL_ID_PREFIX!r}"
            )

    @staticmethod
    def _is_known_model(name: str) -> bool:
        # ``RoutingDecision`` already validates short names; the prefix
        # test alone here covers the ``inherit``-or-full-ID path the
        # subagent surface needs.
        return name.startswith(EXECUTOR_MODEL_FULL_ID_PREFIX)


@dataclass(frozen=True)
class OptionsKwargs:
    """Kwargs payload for :class:`claude_agent_sdk.ClaudeAgentOptions`.

    Names exactly the fields the routing decision determines (arch §5
    deferred shifts #2, #4, #5, #6). The fields the *runner-loop* /
    *MCP-server* / *hooks* surfaces own (``hooks``, ``mcp_servers``,
    ``can_use_tool``, ``cwd``, ``add_dirs``, ``permission_mode``,
    ``allowed_tools``, ``disallowed_tools``, ``setting_sources``,
    ``thinking``, ``max_budget_usd``) are *not* in this carrier — they
    join at the SDK boundary in item 1.3+.

    :attr:`include_partial_messages` is set ``True`` per arch §5 #7 so
    the executor's text/thinking/tool-output deltas stream through the
    SDK's partial-message channel; this is invariant for v1 and is
    therefore baked here rather than tunable per decision.
    """

    model: str
    fallback_model: str
    betas: tuple[str, ...]
    effort: str | None
    advisor_max_uses: int
    include_partial_messages: bool
    subagents: tuple[SubagentSpec, ...]


def build_options_kwargs(decision: RoutingDecision) -> OptionsKwargs:
    """Compute the SDK options kwargs from a :class:`RoutingDecision`.

    Pure function — no I/O, no side effects, no clock reads. Same input
    yields the same output, which is what the unit-test bar in item
    1.2's done-when ("Handles current SDK event shapes") and the
    auditor's "verify each deferred shift lands" rail both depend on.

    Per arch §5 #4: ``effort`` is ``None`` when the decision's
    ``effort_level`` is ``"auto"`` (the SDK has no ``"auto"`` literal
    as of the queried docs; mapping to ``None`` means "omit the field
    so the SDK picks"). The downstream caller splats via
    ``ClaudeAgentOptions(**{k: v for k, v in kwargs.items() if v is not
    None})`` or equivalent.

    Per arch §5 #2: ``betas`` is empty when no advisor is wired. Other
    beta headers can be appended downstream (e.g. context-1m); the
    advisor header is the only one this function decides about.

    Per arch §5 #5: ``fallback_model`` for full-form SDK IDs (any
    string starting with ``claude-``) is the same string verbatim —
    the spec defines no tier-down for full IDs and the SDK is the
    arbiter of fallback at runtime if the user explicitly pinned a
    full ID.

    Per arch §5 #6: the ``researcher`` :class:`SubagentSpec` always
    rides on the kwargs (one entry, ``model='inherit'``). When the
    consumer in item 1.3+ has a config flag ``enable_researcher_subagent``
    set ``False`` (per :class:`SessionConfig` default), it splats only
    a subset of subagents at the SDK boundary.
    """
    advisor = decision.advisor_model
    betas: tuple[str, ...] = (ADVISOR_TOOL_BETA_HEADER,) if advisor is not None else ()
    fallback_model = _resolve_fallback_model(decision.executor_model)
    effort = EFFORT_LEVEL_TO_SDK[decision.effort_level]
    researcher = SubagentSpec(
        name="researcher",
        description=_RESEARCHER_DESCRIPTION,
        prompt=_RESEARCHER_PROMPT_PLACEHOLDER,
        model="inherit",
        tools=_RESEARCHER_TOOLS,
    )
    return OptionsKwargs(
        model=decision.executor_model,
        fallback_model=fallback_model,
        betas=betas,
        effort=effort,
        # ``advisor_max_uses`` rides on the kwargs even when no advisor
        # is wired — the runtime executor enforces the cap when the
        # advisor primitive is actually consulted (spec §2 "the
        # executor stops calling once it has called max_uses times").
        # When ``advisor_model is None`` the executor never calls and
        # the value is moot; carrying it through unchanged simplifies
        # downstream "advisor was wired" reasoning.
        advisor_max_uses=decision.advisor_max_uses,
        include_partial_messages=True,
        subagents=(researcher,),
    )


def _resolve_fallback_model(executor_model: str) -> str:
    """Resolve the SDK ``fallback_model`` for an executor short name.

    Full-form SDK IDs pass through verbatim per arch §5 #5: the spec
    defines no tier-down for full IDs and the SDK is the arbiter of
    fallback at runtime in that case.
    """
    if executor_model.startswith(EXECUTOR_MODEL_FULL_ID_PREFIX):
        return executor_model
    if executor_model in EXECUTOR_FALLBACK_MODEL:
        return EXECUTOR_FALLBACK_MODEL[executor_model]
    # ``RoutingDecision.__post_init__`` rejects unknown short names at
    # construction; reaching this branch means a future short name was
    # added to ``KNOWN_EXECUTOR_MODELS`` without a fallback row. Surface
    # the omission instead of silently mapping to the input.
    raise ValueError(
        f"executor_model {executor_model!r} has no entry in EXECUTOR_FALLBACK_MODEL "
        f"(rebuild constants table to keep it in lockstep with KNOWN_EXECUTOR_MODELS)"
    )


__all__ = [
    "OptionsKwargs",
    "SubagentSpec",
    "build_options_kwargs",
]
