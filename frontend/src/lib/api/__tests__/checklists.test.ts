/**
 * Tests for the ``/api/checklists/*`` + ``/api/checklist-items/*``
 * typed client (item 2.7). Verifies URL shape, body projection, and
 * the error contract for the routes the ChecklistView surfaces drive.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ChecklistApiError,
  checkChecklistItem,
  createChecklistItem,
  deleteChecklistItem,
  getChecklistOverview,
  indentChecklistItem,
  linkChecklistItemChat,
  moveChecklistItem,
  outdentChecklistItem,
  pauseChecklistRun,
  resumeChecklistRun,
  skipCurrentChecklistRun,
  startChecklistRun,
  stopChecklistRun,
  unlinkChecklistItemChat,
  updateChecklistItem,
} from "../checklists";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getChecklistOverview", () => {
  it("GETs /api/checklists/<id>", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ checklist_id: "cl_a", items: [], active_run: null }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const overview = await getChecklistOverview("cl_a");
    expect(overview.checklist_id).toBe("cl_a");
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklists/cl_a");
  });
});

describe("createChecklistItem", () => {
  it("POSTs to /api/checklists/<id>/items", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 7 }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    await createChecklistItem("cl_a", { label: "x" });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklists/cl_a/items");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ label: "x" }));
  });
});

describe("updateChecklistItem (PATCH wrapper)", () => {
  it("PATCHes /api/checklist-items/<id>", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 7 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    await updateChecklistItem(7, { label: "renamed" });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("PATCH");
    expect(init.body).toBe(JSON.stringify({ label: "renamed" }));
  });

  it("throws ChecklistApiError on 422", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "bad" }), {
        status: 422,
        statusText: "Unprocessable Entity",
        headers: { "content-type": "application/json" },
      }),
    );
    let captured: unknown = null;
    try {
      await updateChecklistItem(7, {});
    } catch (error) {
      captured = error;
    }
    expect(captured).toBeInstanceOf(ChecklistApiError);
    expect((captured as ChecklistApiError).status).toBe(422);
  });
});

describe("deleteChecklistItem (DELETE wrapper)", () => {
  it("DELETEs /api/checklist-items/<id> and tolerates 204 empty body", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deleteChecklistItem(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("DELETE");
  });
});

describe("check / link / unlink / move / indent / outdent helpers", () => {
  function stubResponse(body: object): Response {
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }

  it("checkChecklistItem hits .../check", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await checkChecklistItem(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/check");
  });

  it("linkChecklistItemChat hits .../link with body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await linkChecklistItemChat(7, { chat_session_id: "ses_x" });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/link");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(JSON.stringify({ chat_session_id: "ses_x" }));
  });

  it("unlinkChecklistItemChat hits .../unlink", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await unlinkChecklistItemChat(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/unlink");
  });

  it("moveChecklistItem hits .../move with parent + sort_order", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await moveChecklistItem(7, { parent_item_id: 3, sort_order: 200 });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/move");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(JSON.stringify({ parent_item_id: 3, sort_order: 200 }));
  });

  it("indentChecklistItem hits .../indent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await indentChecklistItem(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/indent");
  });

  it("outdentChecklistItem hits .../outdent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(stubResponse({ id: 7 }));
    await outdentChecklistItem(7);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklist-items/7/outdent");
  });
});

describe("run-control helpers", () => {
  function stubResponse(body: object, status = 200): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  }

  it("startChecklistRun hits .../run/start with policy + visit_existing", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(stubResponse({ id: 1 }, 201));
    await startChecklistRun("cl_a", { failure_policy: "skip", visit_existing: true });
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/checklists/cl_a/run/start");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBe(JSON.stringify({ failure_policy: "skip", visit_existing: true }));
  });

  it("stopChecklistRun / pauseChecklistRun / resumeChecklistRun / skipCurrentChecklistRun reach the right urls", async () => {
    // ``Response`` bodies are single-consumption; every call returns a
    // fresh stub so the four awaits don't race over a drained stream.
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => Promise.resolve(stubResponse({ id: 1 })));
    await stopChecklistRun("cl_a");
    await pauseChecklistRun("cl_a");
    await resumeChecklistRun("cl_a");
    await skipCurrentChecklistRun("cl_a");
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls).toEqual([
      "/api/checklists/cl_a/run/stop",
      "/api/checklists/cl_a/run/pause",
      "/api/checklists/cl_a/run/resume",
      "/api/checklists/cl_a/run/skip-current",
    ]);
  });
});
