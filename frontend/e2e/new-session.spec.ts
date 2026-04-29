/**
 * E2E — new-session form surfaces (item 2.4).
 *
 * `NewSessionForm.svelte` is built (item 2.4) but is not yet rendered
 * in the live SvelteKit shell — the cross-wiring from the `c` chord
 * (item 2.9 keybindings) into a modal-host is not yet in place. This
 * spec walks the *backend* contracts the form will call once the
 * shell-level wiring lands:
 *
 * - `GET  /api/quota/current`     — quota bars data source.
 * - `POST /api/routing/preview`   — reactive routing-preview line.
 * - `POST /api/sessions`          — Start Session button outcome.
 *
 * The DOM-level form-open test is deferred to the item that wires
 * the chord+modal-host pair; gating now would be a synth-failure
 * (claiming a flow works that the shell never renders).
 */
import { expect, test } from "@playwright/test";

import { loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("quota current endpoint returns the seeded snapshot", async ({ request }) => {
  const response = await request.get("/api/quota/current");
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    overall_used_pct: number | null;
    sonnet_used_pct: number | null;
  };
  expect(body.overall_used_pct).not.toBeNull();
  expect(body.sonnet_used_pct).not.toBeNull();
});

test("routing preview returns a decision under quota", async ({ request }) => {
  const seed = await loadSeed(request);
  const response = await request.post("/api/routing/preview", {
    data: {
      tags: [seed.tags.bearings],
      message: "Wire up the new-session form's quota bars",
    },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    executor: string;
    effort: string;
    quota_downgrade_applied: boolean;
  };
  expect(typeof body.executor).toBe("string");
  expect(typeof body.effort).toBe("string");
  expect(typeof body.quota_downgrade_applied).toBe("boolean");
});

test("paired-chat spawn creates a session for an unpaired item", async ({ request }) => {
  const seed = await loadSeed(request);
  // The form's Start Session UX route lands once the modal-host
  // wiring lands. The closest reachable session-create surface
  // today is the paired-chat spawn endpoint (item 1.7), which the
  // checklist uses to materialise a chat for an item. Assert it
  // succeeds against the unpaired third item.
  const itemId = seed.checklist_items[2];
  const response = await request.post(`/api/checklist-items/${itemId}/spawn-chat`, {
    data: {},
  });
  // Either 200 (existing) or 201 (created) is acceptable per
  // `docs/behavior/paired-chats.md` §"Spawning a new pair".
  expect([200, 201]).toContain(response.status());
});
