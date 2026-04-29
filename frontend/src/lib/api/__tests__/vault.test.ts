/**
 * Tests for ``api/vault.ts`` — verifies URL shape + query-string
 * encoding + the read-only surface contract per
 * ``docs/behavior/vault.md``.
 *
 * The module intentionally exposes no write helpers (vault is
 * read-only per vault.md §"CRUD flow"); this file's "no write
 * affordances" assertion is the wire-boundary mirror of the
 * VaultPanel test's "no write affordances in the rendered DOM".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import * as vaultModule from "../vault";
import { getVaultDoc, getVaultDocByPath, listVault, searchVault } from "../vault";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("listVault", () => {
  it("GETs /api/vault and returns the bucketed shape", async () => {
    const payload = {
      plans: [
        {
          id: 1,
          path: "/home/user/.claude/plans/bearings.md",
          slug: "bearings",
          title: "Bearings rebuild",
          kind: "plan",
          mtime: 1_700_000_000,
          size: 1024,
          last_indexed_at: 1_700_000_010,
          markdown_link: "[Bearings rebuild](file:///home/user/.claude/plans/bearings.md)",
        },
      ],
      todos: [],
      plan_roots: ["/home/user/.claude/plans"],
      todo_globs: ["/home/user/Projects/**/TODO.md"],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const result = await listVault();
    expect(result.plans).toHaveLength(1);
    expect(result.plans[0].markdown_link).toContain("file://");
    expect(result.plan_roots).toEqual(["/home/user/.claude/plans"]);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault");
  });
});

describe("searchVault", () => {
  it("GETs /api/vault/search?q=...", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ hits: [], capped: false }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await searchVault("foo bar");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault/search?q=foo+bar");
  });

  it("round-trips capped flag", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ hits: [], capped: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const out = await searchVault("a");
    expect(out.capped).toBe(true);
  });
});

describe("getVaultDoc", () => {
  it("GETs /api/vault/{id}", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entry: {
            id: 7,
            path: "/x.md",
            slug: "x",
            title: null,
            kind: "todo",
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
    const out = await getVaultDoc(7);
    expect(out.entry.id).toBe(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault/7");
  });
});

describe("getVaultDocByPath", () => {
  it("GETs /api/vault/by-path?path=...", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          entry: {
            id: 7,
            path: "/abs/x.md",
            slug: "x",
            title: null,
            kind: "todo",
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
    await getVaultDocByPath("/abs/x.md");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/vault/by-path?path=%2Fabs%2Fx.md");
  });
});

describe("read-only surface", () => {
  it("exposes no write helpers — vault.md §CRUD flow", () => {
    // Defensive: a future contributor adding a write helper here
    // would surface the corresponding behavior-doc violation. The
    // assertion is structural — every exported symbol must be a
    // read helper or a TS interface.
    const exports = Object.keys(vaultModule).sort();
    const writeShapes = exports.filter((name) =>
      /create|update|delete|patch|post|write|remove/i.test(name),
    );
    expect(writeShapes).toEqual([]);
  });
});
