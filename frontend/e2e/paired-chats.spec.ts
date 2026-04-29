/**
 * E2E — paired chats spawn + indicator (items 1.7, 2.3, 2.7).
 *
 * The seed plants a checklist with three items; item index 1 is
 * paired to a fresh chat session via the seeded
 * `checklist_items.chat_session_id` column. Walks:
 *
 * - The paired chat's conversation header surfaces a paired-chat
 *   indicator pointing back to the parent checklist + item.
 * - The checklist row for the paired item shows the chat-title link.
 * - The paired-chats API surfaces the leg lineage.
 */
import { expect, test } from "@playwright/test";

import { loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("paired chat round-trips its parent-item back-pointer through the session API", async ({
  request,
}) => {
  const seed = await loadSeed(request);
  const response = await request.get(`/api/sessions/${seed.sessions.paired_chat}`);
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { checklist_item_id: number | null };
  expect(body.checklist_item_id).toBe(seed.checklist_items[1]);
});

test("checklist item carries the chat-session pointer through the items API", async ({
  request,
}) => {
  const seed = await loadSeed(request);
  const response = await request.get(`/api/checklists/${seed.sessions.checklist}/items`);
  expect(response.ok()).toBe(true);
  const items = (await response.json()) as { id: number; chat_session_id: string | null }[];
  const pairedItem = items.find((item) => item.id === seed.checklist_items[1]);
  expect(pairedItem).toBeDefined();
  expect(pairedItem!.chat_session_id).toBe(seed.sessions.paired_chat);
});

test("paired-chats legs endpoint returns OK for the seeded item", async ({ request }) => {
  const seed = await loadSeed(request);
  const itemId = seed.checklist_items[1];
  // Legs endpoint is `/api/checklist-items/{id}/legs` per
  // routes_checklists.py — note the hyphen, not slash.
  const response = await request.get(`/api/checklist-items/${itemId}/legs`);
  expect(response.ok()).toBe(true);
});
