/**
 * Tests for :mod:`stores/vault.svelte.ts`. Owns the integration check
 * that the read-only vault surface goes through ``/api/vault`` +
 * ``/api/vault/search`` + ``/api/vault/{id}``.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
  clearVaultSelection,
  refreshVault,
  selectVaultDoc,
  setVaultSearchQuery,
  vaultStore,
} from "../vault.svelte";

beforeEach(() => {
  _resetForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const fakeListPayload = {
  plans: [],
  todos: [],
  plan_roots: ["/p"],
  todo_globs: ["/t/**/T.md"],
};

describe("vault store — refreshVault", () => {
  it("GETs /api/vault and stores the response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(fakeListPayload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await refreshVault();
    expect(vaultStore.list?.plan_roots).toEqual(["/p"]);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault");
  });
});

describe("vault store — search", () => {
  it("non-empty query GETs /api/vault/search?q=...", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ hits: [], capped: false }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await setVaultSearchQuery("foo");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault/search?q=foo");
    expect(vaultStore.searchResult?.capped).toBe(false);
  });

  it("empty query clears the result without fetching", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    await setVaultSearchQuery("   ");
    expect(vaultStore.searchResult).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("vault store — selection", () => {
  it("selectVaultDoc GETs /api/vault/{id} and stores the doc", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entry: {
            id: 5,
            path: "/x.md",
            slug: "x",
            title: null,
            kind: "plan",
            mtime: 0,
            size: 0,
            last_indexed_at: 0,
            markdown_link: "[x](file:///x.md)",
          },
          body: "hi",
          redactions: [],
          truncated: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    await selectVaultDoc(5);
    expect(vaultStore.selected?.entry.id).toBe(5);
    expect(vaultStore.selected?.body).toBe("hi");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault/5");
  });

  it("clearVaultSelection drops the selected doc", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entry: {
            id: 5,
            path: "/x.md",
            slug: "x",
            title: null,
            kind: "plan",
            mtime: 0,
            size: 0,
            last_indexed_at: 0,
            markdown_link: "",
          },
          body: "",
          redactions: [],
          truncated: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    await selectVaultDoc(5);
    clearVaultSelection();
    expect(vaultStore.selected).toBeNull();
  });
});
