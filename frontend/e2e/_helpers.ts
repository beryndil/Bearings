/**
 * Shared E2E helpers — seeded id resolution, debug-router event
 * injection, page-load conventions used across every spec.
 *
 * Design notes:
 *
 * - The seed shape is materialised by `scripts/e2e_server.py:_SeedSummary`
 *   and exposed at `GET /_e2e/seed`. Specs never hard-code ids; they
 *   call `loadSeed(page)` once per spec and address sessions / tags /
 *   items by symbolic name.
 * - Streaming flows drive the runner via `POST /_e2e/sessions/{id}/emit`
 *   so a Playwright page can produce deterministic
 *   MessageStart → Token×N → MessageComplete sequences without a real
 *   Claude SDK.
 * - The reset path (`POST /_e2e/runners/reset`) clears the in-process
 *   runner registry between specs so a previous spec's events do not
 *   replay into a new spec's WebSocket subscription.
 */
import type { Page, APIRequestContext } from "@playwright/test";

/** Shape mirrored from `scripts/e2e_server.py:_SeedSummary`. */
interface SeedSummary {
  tags: {
    bearings: number;
    routing: number;
    rebuild: number;
  };
  sessions: {
    chat_open_bearings: string;
    chat_open_routing: string;
    chat_closed: string;
    checklist: string;
    paired_chat: string;
  };
  checklist_items: number[];
  messages: {
    user: string;
    assistant: string;
  };
  memory: number;
}

/** Wire shape for `POST /_e2e/sessions/{id}/emit`. */
interface DebugEventEnvelope {
  type:
    | "message_start"
    | "token"
    | "tool_call_start"
    | "tool_output_delta"
    | "tool_call_end"
    | "message_complete";
  payload: Record<string, string | number | boolean | null>;
}

/** Fetch the deterministic seed-id summary from the e2e server. */
export async function loadSeed(request: APIRequestContext): Promise<SeedSummary> {
  const response = await request.get("/_e2e/seed");
  if (!response.ok()) {
    throw new Error(`/_e2e/seed returned ${response.status()}: ${await response.text()}`);
  }
  return (await response.json()) as SeedSummary;
}

/** Push one debug event into a runner's ring buffer + fan-out. */
async function emitEvent(
  request: APIRequestContext,
  sessionId: string,
  envelope: DebugEventEnvelope,
): Promise<void> {
  const response = await request.post(`/_e2e/sessions/${sessionId}/emit`, {
    data: envelope,
  });
  if (!response.ok()) {
    throw new Error(
      `emit ${envelope.type} for ${sessionId} returned ${response.status()}: ${await response.text()}`,
    );
  }
}

/** Drop every registered runner — between-spec isolation. */
export async function resetRunners(request: APIRequestContext): Promise<void> {
  const response = await request.post("/_e2e/runners/reset");
  if (!response.ok()) {
    throw new Error(`/_e2e/runners/reset returned ${response.status()}`);
  }
}

/** Navigate to the SPA root (sidebar default-landing). */
export async function gotoRoot(page: Page): Promise<void> {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  // Sidebar populates from /api/sessions; wait for the list shell so
  // session rows are reachable before specs interact.
  await page.waitForSelector("[data-testid='session-list']", { timeout: 8_000 });
}

/**
 * Select a session by clicking its sidebar row. The SPA does not use
 * a `/sessions/<id>` URL — the active session is owned by the inspector
 * store and toggled by the click handler. Specs always go through the
 * sidebar; this mirrors what the user does.
 */
export async function gotoSession(page: Page, sessionId: string): Promise<void> {
  await gotoRoot(page);
  // The same session row may appear under multiple tag groups (the
  // sidebar's tag-bucketed view duplicates rows by-design); `.first()`
  // picks any one — the click handler is the same function on every
  // duplicate so subsequent state observation is unaffected.
  const row = page.locator(`[data-testid='session-row'][data-session-id='${sessionId}']`).first();
  await row.waitFor({ state: "visible", timeout: 8_000 });
  await row.click();
  // Allow store + derived stores to settle.
  await page.waitForLoadState("networkidle");
}

/**
 * Fire a deterministic streaming sequence into a session's runner —
 * MessageStart, three Token chunks, MessageComplete. The conversation
 * pane should render the assembled message body live as each chunk
 * arrives.
 */
export async function emitDeterministicAssistantTurn(
  request: APIRequestContext,
  sessionId: string,
  messageId: string,
  chunks: readonly string[],
): Promise<void> {
  await emitEvent(request, sessionId, {
    type: "message_start",
    payload: { message_id: messageId },
  });
  for (const delta of chunks) {
    await emitEvent(request, sessionId, {
      type: "token",
      payload: { message_id: messageId, delta },
    });
  }
  await emitEvent(request, sessionId, {
    type: "message_complete",
    payload: {
      message_id: messageId,
      content: chunks.join(""),
      advisor_calls_count: 0,
    },
  });
}
