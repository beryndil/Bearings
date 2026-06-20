/**
 * Route-resolution smoke tests for BUG-NET-24-FE.
 *
 * The /dashboard, /chat, /history, and /paired stub routes were removed
 * in the C-2 gap-closure bundle (no nav surface, no scheduled feature,
 * dead code).  The only remaining stub is ``/preferences`` (redirect to
 * ``/settings``) — verified here.
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ---- SvelteKit shims (declared before any module import that pulls them) ----

vi.mock("$app/navigation", () => ({
  goto: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("$app/state", () => ({
  page: {
    url: { pathname: "", searchParams: { get: () => null } },
    route: { id: "" },
    params: {},
  },
}));

// ---- Imports ----------------------------------------------------------------

import { goto } from "$app/navigation";
import PreferencesPage from "../src/routes/preferences/+page.svelte";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---- Route smoke tests (BUG-NET-24-FE) -------------------------------------

describe("BUG-NET-24-FE — stub route resolution", () => {
  it("/preferences mounts without throwing and calls goto('/settings')", async () => {
    render(PreferencesPage);
    // onMount fires asynchronously — flush the microtask queue.
    await vi.waitFor(() => {
      expect(goto).toHaveBeenCalledWith("/settings", { replaceState: true });
    });
  });
});
