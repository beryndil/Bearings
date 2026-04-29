/**
 * Tests for :mod:`stores/memories.svelte.ts`.
 *
 * Per the item-2.10 done-when, this file owns the integration check
 * that the memories surface reads ``/api/tags/<id>/memories``: the
 * store calls :func:`listTagMemories` which the typed-fetch wrapper
 * dispatches against that path. Asserting the URL on the fetch mock
 * locks the wire integration without standing up a real backend.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  _resetForTests,
  createMemoryFor,
  deleteMemoryFor,
  memoriesStore,
  refreshMemories,
  setActiveTag,
  updateMemoryFor,
} from "../memories.svelte";

beforeEach(() => {
  _resetForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("memories store — refresh", () => {
  it("setActiveTag schedules a refresh and stores the response", async () => {
    // ``mockImplementation`` returns a fresh Response per call so the
    // body isn't consumed twice — the auto-scheduled refresh from
    // setActiveTag and the explicit refreshMemories call below both
    // need their own readable body.
    const buildResponse = (): Response =>
      new Response(
        JSON.stringify([
          {
            id: 1,
            tag_id: 7,
            title: "T",
            body: "B",
            enabled: true,
            created_at: "2026-04-29T00:00:00Z",
            updated_at: "2026-04-29T00:00:00Z",
          },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => buildResponse());
    setActiveTag(7);
    // Wait for the auto-scheduled refresh from setActiveTag.
    await Promise.resolve();
    await Promise.resolve();
    await refreshMemories(7);
    expect(memoriesStore.tagId).toBe(7);
    expect(memoriesStore.memories).toHaveLength(1);
    // Per done-when: the integration goes through /api/tags/<id>/memories.
    const calls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calls).toContain("/api/tags/7/memories");
  });

  it("setActiveTag(null) clears the scope without fetching", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    setActiveTag(null);
    expect(memoriesStore.tagId).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("memories store — write helpers", () => {
  it("createMemoryFor POSTs and refetches", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 1,
            tag_id: 7,
            title: "T",
            body: "B",
            enabled: true,
            created_at: "2026-04-29T00:00:00Z",
            updated_at: "2026-04-29T00:00:00Z",
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    setActiveTag(7);
    await Promise.resolve();
    fetchMock.mockClear();
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 9,
            tag_id: 7,
            title: "T",
            body: "B",
            enabled: true,
            created_at: "2026-04-29T00:00:00Z",
            updated_at: "2026-04-29T00:00:00Z",
          }),
          { status: 201, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    await createMemoryFor(7, { title: "T", body: "B", enabled: true });
    const methods = fetchMock.mock.calls.map((c) => c[1]?.method ?? "GET");
    expect(methods).toContain("POST");
    expect(methods).toContain("GET");
  });

  it("updateMemoryFor PATCHes /api/memories/{id}", async () => {
    setActiveTag(7);
    await Promise.resolve();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 9,
            tag_id: 7,
            title: "T",
            body: "B",
            enabled: false,
            created_at: "2026-04-29T00:00:00Z",
            updated_at: "2026-04-29T00:00:00Z",
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    await updateMemoryFor(9, { title: "T", body: "B", enabled: false });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/memories/9");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("PATCH");
  });

  it("deleteMemoryFor DELETEs /api/memories/{id}", async () => {
    setActiveTag(7);
    await Promise.resolve();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    await deleteMemoryFor(9);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/memories/9");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("DELETE");
  });
});
