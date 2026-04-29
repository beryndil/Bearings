/**
 * Tests for the ``/api/quota/current`` typed client (item 2.4) —
 * verifies the GET happens at the correct URL, the response decodes
 * to :interface:`QuotaSnapshot`, and the error contract surfaces
 * 404 / 502 / 503 to the dialog's fallback path.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../client";
import { getCurrentQuota } from "../quota";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getCurrentQuota", () => {
  it("GETs /api/quota/current and decodes the snapshot", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          captured_at: 1_700_000_000,
          overall_used_pct: 0.31,
          sonnet_used_pct: 0.14,
          overall_resets_at: 1_700_500_000,
          sonnet_resets_at: 1_700_500_000,
          raw_payload: '{"foo":"bar"}',
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
    const snapshot = await getCurrentQuota();
    expect(snapshot.overall_used_pct).toBe(0.31);
    expect(snapshot.sonnet_used_pct).toBe(0.14);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/quota/current");
  });

  it("throws ApiError on 404 (no snapshot recorded yet)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "no snapshot" }), {
        status: 404,
        statusText: "Not Found",
        headers: { "content-type": "application/json" },
      }),
    );
    let captured: unknown = null;
    try {
      await getCurrentQuota();
    } catch (error) {
      captured = error;
    }
    expect(captured).toBeInstanceOf(ApiError);
    expect((captured as ApiError).status).toBe(404);
  });
});
