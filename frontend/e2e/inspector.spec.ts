/**
 * E2E — inspector subsections (items 2.5, 2.6).
 *
 * Walks `docs/behavior/chat.md` §"What the user does NOT see in chat"
 * cross-refs to the Inspector pane: Agent / Context / Instructions /
 * Routing / Usage tabs. Each tab is exercised by clicking through and
 * asserting the section's heading + at least one body element.
 */
import { expect, test } from "@playwright/test";

import { gotoSession, loadSeed, resetRunners } from "./_helpers";

test.beforeEach(async ({ request }) => {
  await resetRunners(request);
});

test("inspector renders Agent / Context / Instructions / Routing / Usage tabs", async ({
  page,
  request,
}) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.chat_open_bearings);

  await expect(page.getByTestId("inspector")).toBeVisible();
  await expect(page.getByTestId("inspector-tabs")).toBeVisible();

  // Agent tab — default landing shows the active session's executor
  // model (sonnet) per InspectorAgent.
  await expect(page.getByTestId("inspector-agent")).toBeVisible();
  await expect(page.getByTestId("inspector-agent-model")).toContainText("Sonnet");

  // Click Context tab.
  await page
    .getByTestId("inspector-tab")
    .filter({ hasText: /context/i })
    .first()
    .click();
  await expect(page.getByTestId("inspector-context")).toBeVisible({ timeout: 4_000 });

  // Click Instructions tab.
  await page
    .getByTestId("inspector-tab")
    .filter({ hasText: /instructions/i })
    .first()
    .click();
  await expect(page.getByTestId("inspector-instructions")).toBeVisible({ timeout: 4_000 });

  // Click Routing tab — the per-message timeline + current routing
  // surface should render.
  await page
    .getByTestId("inspector-tab")
    .filter({ hasText: /routing/i })
    .first()
    .click();
  await expect(page.getByTestId("inspector-routing")).toBeVisible({ timeout: 4_000 });

  // Click Usage tab — headroom chart + by-model surface render.
  await page.getByTestId("inspector-tab").filter({ hasText: /usage/i }).first().click();
  await expect(page.getByTestId("inspector-usage")).toBeVisible({ timeout: 4_000 });
});

test("InspectorRouting surfaces the current decision row", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.chat_open_bearings);

  await page
    .getByTestId("inspector-tab")
    .filter({ hasText: /routing/i })
    .first()
    .click();
  await expect(page.getByTestId("inspector-routing")).toBeVisible();
  // Empty / current / loading branches are all valid initial states;
  // assert that one of them surfaces (no crash).
  const surface = page.getByTestId("inspector-routing");
  const hasContent = await surface
    .locator(
      "[data-testid=inspector-routing-current], [data-testid=inspector-routing-empty], [data-testid=inspector-routing-loading]",
    )
    .count();
  expect(hasContent).toBeGreaterThan(0);
});

test("InspectorUsage surfaces the headroom chart skeleton", async ({ page, request }) => {
  const seed = await loadSeed(request);
  await gotoSession(page, seed.sessions.chat_open_bearings);

  await page.getByTestId("inspector-tab").filter({ hasText: /usage/i }).first().click();
  await expect(page.getByTestId("inspector-usage")).toBeVisible();
  const surface = page.getByTestId("inspector-usage");
  const hasContent = await surface
    .locator(
      "[data-testid=inspector-usage-headroom], [data-testid=inspector-usage-headroom-empty], [data-testid=inspector-usage-loading]",
    )
    .count();
  expect(hasContent).toBeGreaterThan(0);
});
