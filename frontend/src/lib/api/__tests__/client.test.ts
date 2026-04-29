/**
 * Tests for the typed-fetch wrapper — locks the error-shape contract
 * (non-2xx → :class:`ApiError` carrying status + body) and the
 * query-param projection.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getJson, postJson } from "../client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getJson", () => {
  it("decodes a 2xx JSON body to the requested shape", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ hello: "world" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const body = await getJson<{ hello: string }>("/test");
    expect(body).toEqual({ hello: "world" });
  });

  it("throws ApiError on a 4xx response with the FastAPI detail body attached", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "nope" }), {
        status: 422,
        statusText: "Unprocessable Entity",
        headers: { "content-type": "application/json" },
      }),
    );
    let captured: unknown = null;
    try {
      await getJson("/test");
    } catch (error) {
      captured = error;
    }
    expect(captured).toBeInstanceOf(ApiError);
    const apiError = captured as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.body).toEqual({ detail: "nope" });
  });

  it("appends repeated query keys — ?k=a&k=b — for OR-filter shapes", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("[]", {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await getJson("/test", {
      query: [
        ["k", "a"],
        ["k", "b"],
      ],
    });
    const requestedUrl = String(fetchMock.mock.calls[0][0]);
    expect(requestedUrl).toContain("k=a");
    expect(requestedUrl).toContain("k=b");
  });
});

describe("postJson", () => {
  it("decodes a 2xx JSON body and posts the supplied body verbatim", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const body = await postJson<{ ok: boolean }>("/test", { tags: [1, 2], message: "hi" });
    expect(body).toEqual({ ok: true });
    const callInit = fetchMock.mock.calls[0][1] as RequestInit;
    expect(callInit.method).toBe("POST");
    expect(callInit.body).toBe(JSON.stringify({ tags: [1, 2], message: "hi" }));
    const headers = callInit.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
  });

  it("throws ApiError on a 4xx response with the FastAPI detail body attached", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "bad shape" }), {
        status: 422,
        statusText: "Unprocessable Entity",
        headers: { "content-type": "application/json" },
      }),
    );
    let captured: unknown = null;
    try {
      await postJson("/test", {});
    } catch (error) {
      captured = error;
    }
    expect(captured).toBeInstanceOf(ApiError);
    const apiError = captured as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.body).toEqual({ detail: "bad shape" });
  });
});
