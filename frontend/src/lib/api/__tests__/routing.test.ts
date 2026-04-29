/**
 * Tests for the ``/api/routing/preview`` typed client (item 2.4) —
 * verifies the request shape (POST body matches spec §9 ``{ tags,
 * message }``), the response decode, and the error contract.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../client";
import { previewRouting } from "../routing";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("previewRouting", () => {
  it("POSTs to /api/routing/preview with the supplied body and decodes the response", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          executor: "sonnet",
          advisor: "opus",
          advisor_max_uses: 5,
          effort: "auto",
          source: "tag_rule",
          reason: "Workhorse default",
          matched_rule_id: 7,
          evaluated_rules: [3, 5, 7],
          quota_downgrade_applied: false,
          quota_state: { overall_used_pct: 0.42, sonnet_used_pct: 0.18 },
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    const result = await previewRouting({ tags: [1, 2], message: "hello world" });

    expect(result.executor).toBe("sonnet");
    expect(result.advisor).toBe("opus");
    expect(result.quota_downgrade_applied).toBe(false);
    expect(result.quota_state["overall_used_pct"]).toBe(0.42);

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("/api/routing/preview");
    const requestInit = init as RequestInit;
    expect(requestInit.method).toBe("POST");
    expect(requestInit.body).toBe(JSON.stringify({ tags: [1, 2], message: "hello world" }));
  });

  it("throws ApiError on a 422 (bad shape)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "bad" }), {
        status: 422,
        statusText: "Unprocessable Entity",
        headers: { "content-type": "application/json" },
      }),
    );
    let captured: unknown = null;
    try {
      await previewRouting({ tags: [], message: "" });
    } catch (error) {
      captured = error;
    }
    expect(captured).toBeInstanceOf(ApiError);
    expect((captured as ApiError).status).toBe(422);
  });
});
