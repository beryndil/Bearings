/**
 * Tests for the ``/api/checklist-items/{id}/spawn-chat`` typed client
 * (item 1.7 / 2.7). Verifies URL shape, body projection, and the
 * ``created`` flag the idempotent path returns.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { spawnPairedChat } from "../paired_chats";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("spawnPairedChat", () => {
  it("POSTs to /api/checklist-items/<id>/spawn-chat with the supplied body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          chat_session_id: "ses_b",
          item_id: 7,
          title: "Implement",
          working_dir: "/wd",
          model: "sonnet",
          created: true,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    const result = await spawnPairedChat(7, { spawned_by: "user" });
    expect(result.created).toBe(true);
    expect(result.chat_session_id).toBe("ses_b");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/spawn-chat");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ spawned_by: "user" }));
  });

  it("returns created=false on the idempotent re-click (HTTP 200)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          chat_session_id: "ses_b",
          item_id: 7,
          title: "Implement",
          working_dir: "/wd",
          model: "sonnet",
          created: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const result = await spawnPairedChat(7);
    expect(result.created).toBe(false);
  });
});
