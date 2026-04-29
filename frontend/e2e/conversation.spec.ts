/**
 * E2E — conversation pane + streaming (items 1.7, 1.2, 2.3).
 *
 * The seed plants two persisted messages on the open-Bearings chat
 * (one user-role, one assistant-role). When the user navigates to
 * that session the conversation pane renders both turns from history.
 *
 * Streaming is exercised via the `/_e2e/sessions/{id}/emit` debug
 * router which calls into the runner's ring buffer + fan-out — the
 * conversation pane's WebSocket subscriber should render the new
 * assistant turn live as the `Token` deltas arrive.
 */
import { expect, test } from "@playwright/test";

import { emitDeterministicAssistantTurn, gotoSession, loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("conversation pane renders persisted turns from history", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.chat_open_bearings);

  await expect(page.getByTestId("conversation")).toBeVisible();
  await expect(page.getByTestId("conversation-body")).toBeVisible();

  // Two seeded user-role messages render as two turn rows.
  const turns = page.getByTestId("message-turn");
  await expect.poll(async () => turns.count(), { timeout: 5_000 }).toBeGreaterThanOrEqual(2);
});

test("streaming MessageStart + Token deltas appear live", async ({ page, request }) => {
  const seed = await loadSeed(request);
  const messageId = "msg_e2e_streaming_demo";
  const chunks = ["The ", "routing ", "decision ", "matched ", "the ", "always ", "rule."];

  await gotoSession(page, seed.sessions.chat_open_bearings);
  await expect(page.getByTestId("conversation-body")).toBeVisible();

  // Drive the runner via the debug router; the conversation pane's
  // WebSocket subscriber should pick up the chunks live.
  await emitDeterministicAssistantTurn(
    request,
    seed.sessions.chat_open_bearings,
    messageId,
    chunks,
  );

  // The completed body should appear in some message-turn descendant
  // — assert the joined text is reachable from the conversation body.
  const fullText = chunks.join("");
  await expect(page.getByTestId("conversation-body")).toContainText(fullText, {
    timeout: 8_000,
  });
});

test("paired-chat session row carries the back-pointer to its parent item", async ({ request }) => {
  const seed = await loadSeed(request);
  // Backend round-trip: the paired chat's `checklist_item_id` column
  // points at the seeded item. The PairedChatIndicator component
  // exists (item 2.3) but is not yet wired into the Conversation
  // header in this build — the visible-on-screen check for the chip
  // is deferred to the item that wires it. The data round-trip below
  // is the load-bearing contract.
  const response = await request.get(`/api/sessions/${seed.sessions.paired_chat}`);
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { checklist_item_id: number | null };
  expect(body.checklist_item_id).toBe(seed.checklist_items[1]);
});
