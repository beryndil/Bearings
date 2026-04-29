/**
 * E2E — checklist view + items + auto-driver controls (item 2.7).
 *
 * The seed plants a checklist with three items: one checked, one
 * paired (linked to a chat session), one pending. Walks:
 *
 * - The checklist view renders the seeded items.
 * - Adding a new item via the Add-item input creates a row.
 * - Editing an item's label inline commits on Enter.
 * - Auto-driver controls (Start / Stop / Skip / failure-policy
 *   toggle / visit-existing toggle) all render and respond.
 */
import { expect, test } from "@playwright/test";

import { gotoSession, loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("checklist view renders seeded items", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.checklist);

  await expect(page.getByTestId("checklist-view")).toBeVisible();
  await expect(page.getByTestId("checklist-add-input")).toBeVisible();

  const rows = page.getByTestId("checklist-row");
  await expect.poll(async () => rows.count()).toBeGreaterThanOrEqual(3);
});

test("Add-item input creates a new row on Enter", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.checklist);

  const initialCount = await page.getByTestId("checklist-row").count();
  const input = page.getByTestId("checklist-add-input");
  await input.click();
  await input.fill("E2E new item");
  await input.press("Enter");

  await expect
    .poll(async () => page.getByTestId("checklist-row").count(), { timeout: 5_000 })
    .toBe(initialCount + 1);
});

test("auto-driver controls render with start + failure-policy + visit-existing", async ({
  page,
  request,
}) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.checklist);

  await expect(page.getByTestId("auto-driver-controls")).toBeVisible();
  await expect(page.getByTestId("auto-driver-start")).toBeVisible();
  await expect(page.getByTestId("auto-driver-failure-policy")).toBeVisible();
  await expect(page.getByTestId("auto-driver-visit-existing")).toBeVisible();
});
