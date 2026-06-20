/**
 * Unit tests for ``src/lib/utils/menuConfig.ts`` (N-13).
 *
 * Acceptance criteria covered:
 *
 * 1. Returns empty pin/hide lists when the API returns no context_menus field.
 * 2. Correctly maps context_menus.pin / hide from the API response.
 * 3. Caches the result — second call does not issue a second fetch.
 * 4. Falls back to empty config on fetch error.
 * 5. ``_resetMenusConfigForTests`` clears the cache so the next call re-fetches.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetMenusConfigForTests,
  fetchMenusConfig,
  type MenusConfig,
} from "../menuConfig";

// ---------------------------------------------------------------------------
// Fetch stub
// ---------------------------------------------------------------------------

function makeOkResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function makeErrorResponse(): Response {
  return new Response("Internal Server Error", { status: 500 });
}

const fetchSpy = vi.spyOn(globalThis, "fetch");

beforeEach(() => {
  _resetMenusConfigForTests();
  fetchSpy.mockReset();
});

afterEach(() => {
  _resetMenusConfigForTests();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("fetchMenusConfig", () => {
  it("(1) returns empty pin/hide when API omits context_menus", async () => {
    fetchSpy.mockResolvedValueOnce(makeOkResponse({ commands_scope: "project" }));
    const cfg: MenusConfig = await fetchMenusConfig();
    expect(cfg.pin).toEqual([]);
    expect(cfg.hide).toEqual([]);
  });

  it("(2) maps pin and hide from context_menus", async () => {
    fetchSpy.mockResolvedValueOnce(
      makeOkResponse({
        context_menus: {
          pin: ["session.fork.from_last_message"],
          hide: ["session.copy_share_link"],
        },
      }),
    );
    const cfg = await fetchMenusConfig();
    expect(cfg.pin).toEqual(["session.fork.from_last_message"]);
    expect(cfg.hide).toEqual(["session.copy_share_link"]);
  });

  it("(3) caches the result — second call does not re-fetch", async () => {
    fetchSpy.mockResolvedValue(makeOkResponse({ context_menus: { pin: ["x"], hide: [] } }));
    await fetchMenusConfig();
    await fetchMenusConfig();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("(4) falls back to empty config on fetch error", async () => {
    fetchSpy.mockResolvedValueOnce(makeErrorResponse());
    const cfg = await fetchMenusConfig();
    expect(cfg.pin).toEqual([]);
    expect(cfg.hide).toEqual([]);
  });

  it("(5) _resetMenusConfigForTests clears cache so next call re-fetches", async () => {
    fetchSpy.mockResolvedValue(makeOkResponse({ context_menus: { hide: ["a"] } }));
    await fetchMenusConfig();
    _resetMenusConfigForTests();
    await fetchMenusConfig();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
