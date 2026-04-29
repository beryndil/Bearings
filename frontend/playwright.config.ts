/**
 * Playwright configuration for the Bearings v1 E2E suite (master item 3.1).
 *
 * What this wires up:
 *
 * - `testDir: "e2e"` — every spec lives under `frontend/e2e/`.
 * - `webServer` — spawns the hermetic FastAPI fixture from
 *   `scripts/e2e_server.py`, serving the committed
 *   `src/bearings/web/dist/` bundle on `127.0.0.1:8789`. Playwright
 *   blocks until `/_e2e/health` returns 200, then dispatches specs.
 * - `use.baseURL` — every `await page.goto("/...")` resolves against
 *   the test port; specs never hard-code the host.
 * - `expect.timeout` — generous (8s) because the streaming-event
 *   replay path occasionally pauses on the WebSocket handshake.
 * - Single project (Chromium) by default; the CI workflow can fan
 *   the matrix out to webkit / firefox once the suite stabilises.
 *
 * The committed `dist/` is the artifact every run reads — Playwright
 * does NOT invoke `npm run build`. Per item 3.1's done-when, the
 * E2E suite serves whatever bundle ships at the head of the branch.
 */
import { defineConfig, devices } from "@playwright/test";

const E2E_PORT = Number(process.env.BEARINGS_E2E_PORT ?? 8789);
const E2E_BASE_URL = `http://127.0.0.1:${E2E_PORT}`;

export default defineConfig({
  testDir: "e2e",
  testMatch: /.*\.spec\.ts/,
  // Tests are independent — failing one should not abort the others;
  // CI gets a complete picture of the breakage on the first run.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  expect: {
    timeout: 8_000,
  },
  use: {
    baseURL: E2E_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // `cd ..` because Playwright runs from `frontend/`; the e2e
    // server lives at the repo root under `scripts/`. `uv run`
    // ensures the venv-managed Python is used so the import path
    // resolves whether or not the parent shell has the venv active.
    command: `cd .. && uv run python scripts/e2e_server.py --port ${E2E_PORT}`,
    url: `${E2E_BASE_URL}/_e2e/health`,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe",
    timeout: 60_000,
  },
});
