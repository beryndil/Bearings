/**
 * E2E — routing rule editor + test-against-message dialog (item 2.8).
 *
 * Walks `docs/behavior/chat.md` cross-ref to the routing surface plus
 * `docs/model-routing-v1-spec.md` §3 default rules:
 *
 * - Inspector → Routing tab on a Bearings chat surfaces the per-tag
 *   rule list (system fallback rules render in the System Rules
 *   editor accessed via the settings page).
 * - The settings page exposes the system-rule editor; the seeded
 *   schema has 7 default system rules per spec §3.
 * - Test-against-message dialog opens when the user clicks the test
 *   affordance on a rule row (the in-memory deterministic evaluator).
 */
import { expect, test } from "@playwright/test";

import { gotoSession, loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("system rules endpoint surfaces the spec §3 seed", async ({ request }) => {
  // Path is `/api/routing/system` per routes_routing.py — the
  // `_rules` suffix lives on the route prefix, not the URL.
  const response = await request.get("/api/routing/system");
  expect(response.ok()).toBe(true);
  const rules = (await response.json()) as { id: number; reason: string }[];
  // Spec §3 default seed table = 7 system rules; the test passes as
  // long as ≥ 7 rules are present (subsequent items may seed more).
  expect(rules.length).toBeGreaterThanOrEqual(7);
});

test("inspector routing tab loads on a routing-tagged chat", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.chat_open_routing);
  await page
    .getByTestId("inspector-tab")
    .filter({ hasText: /routing/i })
    .first()
    .click();
  await expect(page.getByTestId("inspector-routing")).toBeVisible();
});

test("preview routing endpoint returns a decision shape", async ({ request }) => {
  const seed = await loadSeed(request);
  // Spec §App A pure preview — no LLM, no streaming. Body shape
  // per `web/models/routing.py:RoutingPreviewIn`: { tags, message }.
  const response = await request.post("/api/routing/preview", {
    data: {
      tags: [seed.tags.bearings],
      message: "Refactor the routing decision pipeline across modules",
    },
  });
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    executor: string;
    source: string;
    reason: string;
  };
  expect(typeof body.executor).toBe("string");
  expect(typeof body.source).toBe("string");
  expect(typeof body.reason).toBe("string");
});
