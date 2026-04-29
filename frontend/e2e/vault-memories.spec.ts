/**
 * E2E — vault panel + memories editor (item 2.10).
 *
 * Walks `docs/behavior/vault.md` + the memories editor:
 *
 * - `/vault` route renders the read-only browser over the configured
 *   plan-roots + TODO globs. The seed plants one plan + one TODO so
 *   both sections are non-empty.
 * - `/memories` route renders the per-tag memories editor. The seed
 *   plants one memory under the Bearings tag.
 * - Memories CRUD: create, edit, delete an entry through the API
 *   surface (the editor itself is wired via the same endpoints).
 */
import { expect, test } from "@playwright/test";

import { loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("vault page renders with seeded plan + todo entries", async ({ page }) => {
  await page.goto("/vault");
  await page.waitForLoadState("networkidle");
  // The vault panel renders inside the page's main column.
  const vaultPanelCount = await page.locator("[data-testid^='vault-']").count();
  expect(vaultPanelCount).toBeGreaterThan(0);
});

test("vault list endpoint returns the seeded plan + todo entries", async ({ request }) => {
  const response = await request.get("/api/vault");
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { plans: unknown[]; todos: unknown[] };
  expect(Array.isArray(body.plans)).toBe(true);
  expect(Array.isArray(body.todos)).toBe(true);
  expect(body.plans.length).toBeGreaterThanOrEqual(1);
  expect(body.todos.length).toBeGreaterThanOrEqual(1);
});

test("memories endpoint surfaces the seeded Bearings memory", async ({ request }) => {
  const seed = await loadSeed(request);
  const response = await request.get(`/api/tags/${seed.tags.bearings}/memories`);
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { id: number; title: string }[];
  expect(body.length).toBeGreaterThanOrEqual(1);
  expect(body[0]!.id).toBe(seed.memory);
});

test("memories CRUD round-trip through the API", async ({ request }) => {
  const seed = await loadSeed(request);
  // Create.
  const createResp = await request.post(`/api/tags/${seed.tags.routing}/memories`, {
    data: {
      title: "E2E memory",
      body: "Created from the e2e suite.",
      enabled: true,
    },
  });
  expect(createResp.ok()).toBe(true);
  const created = (await createResp.json()) as { id: number };

  // Update — PATCH replaces the full mutable surface per
  // `TagMemoryIn` (title, body, enabled all required).
  const updateResp = await request.patch(`/api/memories/${created.id}`, {
    data: {
      title: "E2E memory (renamed)",
      body: "Created from the e2e suite.",
      enabled: true,
    },
  });
  expect(updateResp.ok()).toBe(true);
  const updated = (await updateResp.json()) as { title: string };
  expect(updated.title).toBe("E2E memory (renamed)");

  // Delete.
  const deleteResp = await request.delete(`/api/memories/${created.id}`);
  expect(deleteResp.ok()).toBe(true);
});
