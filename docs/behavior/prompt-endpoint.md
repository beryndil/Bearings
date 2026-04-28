# Prompt endpoint — observable behavior

The prompt endpoint is the HTTP facade for injecting a user-role prompt into a chat session from outside the WebSocket. It is what the bearings CLI's `send` subcommand uses, what an orchestrator session uses to drive its executor sessions, and what an executor session uses to call back to its orchestrator. This document lists the observable wire behavior; implementation choices are governed by `docs/architecture-v1.md`.

Sibling subsystems referenced here:
[chat](chat.md), [bearings-cli](bearings-cli.md), [checklists](checklists.md).

## Request shape

```
POST /api/sessions/<session_id>/prompt
Content-Type: application/json
Authorization: Bearer <token>           # only when auth is enabled

{ "content": "<prompt text>" }
```

* `<session_id>` is the target session's id, exactly as it appears in the sidebar URL or in `/api/sessions` listings.
* `content` is required, must be a string, and must be non-empty after trimming surrounding whitespace.
* Only `content` is read from the body. Additional fields are ignored at the boundary; clients should not rely on side-effects from other keys.
* `Authorization` is required when the server has auth enabled. Missing or invalid tokens get a 401 from the auth middleware before this endpoint sees the request.

The server **only** accepts JSON. A form-encoded or query-string body is rejected with 422.

## 202 semantics

The success response is **HTTP 202 Accepted**:

```
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/sessions/<session_id>

{ "queued": true, "session_id": "<session_id>" }
```

* The 202 means the prompt has been **queued** for the session's runner — not that the agent has produced any output, not that any tool has been called, not that the turn has finished.
* The `Location` header points back to the session resource; clients can `GET` it to poll session metadata, but the prompt's *output* is observable only through:
  * the WebSocket stream `/ws/sessions/<session_id>` (live events as they happen);
  * `GET /api/sessions/<session_id>/messages` (historical message rows once they have been persisted).
* The body is a small JSON envelope. Clients can rely on the `queued: true` field as a positive ack and on `session_id` echoing back as a sanity check.
* The endpoint **lazily creates the runner** if the target session has no live runner yet (e.g. the runner has been idle long enough to have been torn down). The user observes the runner come up transparently — the next event the WebSocket emits is the message_start for the prompt's turn.

## What the user sees in the UI when they POST during an in-flight turn

When a prompt arrives via the endpoint while the session's runner is mid-turn, the user observes:

* The new prompt is **queued behind the in-flight turn**. The UI shows the new user bubble with a `queued` badge until the previous turn completes. The agent does not interleave responses — turns run end-to-end.
* When the in-flight turn finishes, the queued prompt's badge clears, the agent starts the next turn against the queued prompt, and streaming proceeds normally (see [tool-output-streaming](tool-output-streaming.md)).
* If multiple prompts are POSTed back-to-back while a turn is running, they queue in arrival order. The agent works through the queue one turn at a time.
* The user can interrupt the in-flight turn with the conversation's Stop control, but doing so does not drain the queue — the queued prompts will still run, on the next agent turns.

## Idempotency / dedup behavior

The endpoint is **not idempotent in the HTTP sense**. Two POSTs with the same body submit two distinct prompts.

* There is no client-supplied idempotency key in v1. Each POST adds a new entry to the runner's prompt queue.
* A common orchestrator pattern is to derive a content hash and avoid re-POSTing — that lives outside the endpoint surface; the endpoint will faithfully accept whatever it is sent.
* **Concurrent POSTs.** Two POSTs that race for the same session both succeed, both return 202, and both prompts queue in the order the server received them.

## Rate-limit observable behavior

The endpoint applies a per-session rate-limit gate to protect the runner from being flooded:

* When a client exceeds the configured per-session POST rate over the configured window, the response is **HTTP 429 Too Many Requests** with a JSON body describing the limit and a `Retry-After` header (in seconds) indicating the earliest time the next POST will succeed.
* The 429 does NOT cancel previously-accepted prompts in the queue; it only refuses the over-limit one.
* Inside the rate-limit window, the WebSocket stream is unaffected — clients listening for events keep receiving them.
* The rate limit is per-session, not global. A second session under the same auth token can be POSTed to independently within its own window.

When auth is disabled (loopback-only deploy), the rate-limit is still enforced — the gate exists to protect the agent, not to enforce subscription policy.

## Failure responses

Every error returns a JSON body of the shape `{"detail": "<message>"}` so a curl user can read the failure without parsing structure. The status codes the user observes:

| Status | Meaning |
|---|---|
| **400** | `content` is the empty string after stripping whitespace. |
| **400** | The session exists but its kind does not support prompts (only chat-kind and checklist-kind sessions are runnable; future kinds will be gated here). |
| **401** | Auth is enabled and the request lacks a valid token. |
| **404** | No session matches `<session_id>`. |
| **409** | The session is closed. The body says "session is closed; reopen it before injecting a prompt." Reviving a closed session via a hidden POST would surprise the user, so the gate is explicit. |
| **422** | `content` is missing or not a string. |
| **429** | Rate limit exceeded for this session. Retry after the time given in `Retry-After`. |
| **500** | Server-side failure (DB unavailable, runner-spawn raised). The body's `detail` carries a short reason; the request can be retried after a backoff. |

## Observability of the queued prompt

After a successful 202:

* The WebSocket stream for that session emits a fresh `message_start` for the new turn (see [chat](chat.md) anatomy) once the runner picks up the prompt. The new user message row arrives in `GET /api/sessions/<id>/messages` with the same content the POST sent.
* The user message is durably persisted **before** the runner begins the turn. If the server is killed between the POST and the first assistant chunk, the prompt is replayed on next boot — the user sees a "resuming prompt from previous session" hint above the message on reconnect.
* No event indicates "the prompt was accepted" beyond the 202 itself. Clients that need a stronger ack can subscribe to the WebSocket and watch for the `message_start` whose `message_id` corresponds to their newly-persisted user row.

## Cross-session orchestration patterns

The endpoint is the basis of the orchestrator-executor patterns the user runs:

* An **orchestrator session** drives an **executor session** by POSTing to the executor's session id.
* The executor calls back by POSTing to the orchestrator's session id with its DONE / DONE_WITH_CONCERNS / BLOCKED / HANDED_OFF status text.
* The user sees these prompts arrive in the respective sidebars as normal user bubbles; the conversation history makes the orchestration visible after the fact.

There is no separate "orchestration" surface — the endpoint is just a prompt injection. Orchestration is a usage pattern, not a wire protocol.

## What the endpoint does NOT do

* It does not take attachments. Attachments are uploaded through the uploads surface and referenced by the assistant via `[File N]` chips inserted into the conversation; the prompt-endpoint accepts plain text only.
* It does not allow setting model, advisor, effort, or tags per request. Routing is the session's property; the endpoint runs whatever routing the session was created with (or whatever subsequent manual mid-session switch left in place).
* It does not return the assistant's reply. The reply is observable only via the WebSocket stream or by polling `GET /api/sessions/<id>/messages` after the turn completes.
* It does not allow changing the role. Every POSTed prompt is a user-role message; agent-role injection is not exposed.
