# Chat — observable behavior

A chat session is a tagged conversation between the user and one Claude executor (with an optional advisor). This document lists what the user sees and can do; it does not prescribe how any of it is implemented. Implementation choices are governed by `docs/architecture-v1.md`.

Sibling subsystems referenced here:
[paired-chats](paired-chats.md), [tool-output-streaming](tool-output-streaming.md), [prompt-endpoint](prompt-endpoint.md), [keyboard-shortcuts](keyboard-shortcuts.md), [context-menus](context-menus.md).

## When the user creates a chat

The user opens the new-session dialog (sidebar "+" button, the keyboard shortcut documented in [keyboard-shortcuts](keyboard-shortcuts.md), or by selecting a template). The dialog requires:

* at least one tag (every chat must carry ≥1 general tag — see [vault](vault.md) for how tags surface elsewhere);
* a working directory (free-text path or browse);
* a routing selection per spec §6 (executor model, optional advisor model with `max_uses`, effort level);
* a first message body.

The user sees a routing-preview line ("Routed from tag rule …") that updates ~300 ms after each keystroke in the first-message field, after each tag change, and after any manual routing override. Per spec §6 the line text changes to "Manual override" once the user touches the executor / advisor / effort controls. Quota bars (overall + Sonnet) are visible inside the dialog and turn yellow at 80 %, red at 95 %.

If the quota guard would downgrade the routed choice (per spec §4), a yellow banner appears above the Start button: "Routing downgraded to Sonnet (overall quota at NN%). [Use Opus anyway]". Clicking the override restores the original executor and records the override for analytics.

Pressing **Start Session** creates the row, attaches the tags, sends the first message, and opens the new chat in the conversation pane. The sidebar adds a row for the chat under each of its tags.

## When the user opens an existing chat

Clicking a sidebar row selects that chat. The conversation pane renders:

* a header band: title, severity shield, attached tag chips, paired-checklist breadcrumb (when the chat was spawned from a checklist item — see [paired-chats](paired-chats.md)), executor model dropdown, total-cost / context-window indicator, and a quota bar pair;
* the conversation body: every message turn in chronological order, oldest at top;
* a composer: multi-line input, attachment chips, send button, slash-command popup.

Selecting the row also marks the session "viewed" (the green-pip indicator clears). See [keyboard-shortcuts](keyboard-shortcuts.md) for `j` / `k` / `Alt+1..9` navigation between sidebar rows.

## What a message turn looks like

Each turn is one user message followed by zero or more tool calls and exactly one final assistant message. The user-visible anatomy:

* **User bubble** — body text rendered as Markdown, attachment chips at the bottom (`[File 1] foo.log`-style chips opened from [context-menus](context-menus.md) → attachment).
* **Tool-work drawer** (collapsible `<details>`) — one row per tool call. Each row shows tool name, an elapsed-time readout that ticks live while the call is running, and a chevron to expand inline output. Output streams in as it arrives (see [tool-output-streaming](tool-output-streaming.md)). Failed calls render in red. A "⤴ TOOLS" jump button appears on the assistant bubble when the drawer was collapsed during the streaming turn.
* **Assistant bubble** — Markdown body, optional thinking block (collapsible, dim), per-message routing badge (per spec §5) in the corner, "Ask for more detail" button hovering on the right edge.
* **Routing badge** (per spec §5) — short label such as `Sonnet`, `Sonnet → Opus×2`, `Haiku → Opus×1`, `Opus xhigh`. Hovering reveals the routing reason ("matched tag rule: bearings/architect — Hard architectural reasoning").
* **Per-message usage column** (per spec §5) — input / output / cache-read tokens for the executor and (when present) the advisor, surfaced in the inspector’s per-message timeline (see Inspector Routing in [paired-chats](paired-chats.md) — *no, see below: chat owns the per-turn surface; the Inspector subsections sit alongside it*).

## Conversation rendering

The body uses Markdown (CommonMark + GFM) with syntax-highlighted code blocks. Inside any rendered message body the linkifier auto-detects:

* `https://…` and `http://…` URLs — rendered as anchors that open in a new tab with `noopener noreferrer`;
* `file://…` URLs — rendered as anchors the local "Open in editor" handler can dispatch on;
* absolute filesystem paths and (when the session has a working directory) paths shaped like `frontend/src/lib/x.svelte` — resolved against the session's working directory and rendered as `file://` anchors. Paths that can't be resolved against an absolute root are left as plain text rather than producing a broken anchor.

Long lines wrap; pre-formatted code blocks scroll horizontally inside their own container. The conversation auto-scrolls to the bottom on a new turn unless the user has scrolled up — see [tool-output-streaming](tool-output-streaming.md) for the scroll-anchor rules.

## Slash commands in the composer

Typing `/` at the start of the composer opens a filter popup of available commands. The user picks one with arrow keys + Enter, or by clicking. The two slash commands the user observes from the chat surface:

* `/advisor` (spec §7) — when typed as the first token of a message, forces the executor to consult the advisor on this turn regardless of the session's normal advisor wiring. The badge on that turn renders "→ Opus×1" (or higher) even on sessions where the advisor is normally disabled. This is per-turn only; the session config is unchanged.
* `/checkpoint` — inserts a labelled gutter mark in the conversation that the user can later fork from (see [context-menus](context-menus.md) → checkpoint actions).

Slash commands the SDK exposes (e.g. `/clear`, `/compact`) pass through to the underlying agent and are observable as their normal effects rather than a Bearings-specific UI.

## Sending a message

Pressing Enter (or Cmd/Ctrl+Enter, depending on the user's draft-newline preference) sends the composed text. The user observes:

1. The composer empties and a fresh user bubble appears at the bottom of the conversation.
2. A "thinking" pip appears next to the bubble while the executor formulates the first response.
3. As the agent streams its reply, the assistant bubble grows in place. Tool calls open as rows in the tool-work drawer above the assistant bubble. See [tool-output-streaming](tool-output-streaming.md).
4. On turn completion the assistant bubble's routing badge resolves to its final value, the cost/usage indicator in the header updates, and the context-window pressure meter ticks.

The composer remains usable during a turn (the user can type the next message), but pressing send while a turn is in flight queues the next prompt rather than interleaving it. See [prompt-endpoint](prompt-endpoint.md) for the same semantics over HTTP.

## Stopping or interrupting a turn

A **Stop** control appears in the composer area whenever a turn is in flight. Pressing it interrupts the agent at the next safe boundary; the partially-streamed assistant bubble is preserved with a `[stopped]` annotation. The user can immediately type a new message — the session is ready for the next turn.

A small "undo stop" inline appears for a few seconds after stopping, letting the user re-issue the same prompt without retyping it.

## Manual mid-session model switch

The conversation header has an executor dropdown showing the current model. Picking a different model opens a confirmation per spec §7:

```
Switch executor: Sonnet → Opus
This will re-cost ~38,000 input tokens of conversation history at Opus rates.
Estimated impact on overall bucket: +1.4%

[Cancel]   [Switch]
```

Confirming changes the executor for all subsequent turns in this session; turns already streamed keep whatever model produced them. Their badges (per spec §5) preserve the model that ran them. The "estimated" word is part of the dialog text on purpose: the cost preview is approximate.

## Error states

* **Agent error mid-turn.** The current assistant bubble closes with a red error block stating the underlying error message. The session row in the sidebar gains a red flashing pip ("needs attention now"). The user can post another message; if the next turn completes successfully the red flag clears.
* **Auth required / token expired.** The conversation pane shows a banner "Backend requires sign-in" and the composer is disabled until the user re-authenticates.
* **Backend unreachable.** A persistent banner appears at the top of the app shell ("Backend unreachable — retrying"). The conversation continues to render the cached transcript; new sends queue locally and surface a "queued" badge on the user bubble until the connection comes back.
* **Closed session.** The composer is hidden and replaced with a "Reopen session" button. Per [prompt-endpoint](prompt-endpoint.md), HTTP prompts to a closed session return 409 — the same gate the UI enforces.
* **Closed paired-chat-side.** See [paired-chats](paired-chats.md).

## Reconnect / resume

After a network blip or a tab reload the conversation reattaches and any events the agent emitted while the client was away are replayed in order, then the live stream resumes. The user sees the in-flight tool drawer fill in retroactively (no missing rows) and the assistant bubble continues growing from where it left off. If the server was killed mid-turn after the user's prompt was persisted but before any assistant output, the user observes a "resuming prompt from previous session" hint above the user bubble before the agent re-starts the turn.

## The agent loop start/stop semantics

The agent loop for a chat is implicit:

* It starts when the chat is selected for the first time after server boot, or whenever the user sends a prompt to a session whose runner has been idle long enough to have been torn down.
* It runs until the assistant emits the turn-final message, then idles waiting for the next prompt.
* Pressing **Stop** ends the current turn early; the loop returns to idle.
* A long-idle session's runner is torn down server-side (the user observes nothing — the next send transparently spins it back up).
* Closing a session drains its runner; subsequent prompts via [prompt-endpoint](prompt-endpoint.md) get a 409 until the session is reopened.

## What the user does NOT see in chat

These belong to other subsystems:

* The execution chain that produced the routing decision — see the **Inspector Routing** subsection (per spec §6: current models + source + reason, per-message badge timeline, advisor totals, quota delta this session, "Why this model?" expandable evaluation chain).
* The full per-week token rollups — see the **Inspector Usage** subsection (per spec §10: 7-day headroom chart, by-model table, advisor-effectiveness widget, rules-to-review list).
* The autonomous driver progress for a paired chat — see [checklists](checklists.md).
