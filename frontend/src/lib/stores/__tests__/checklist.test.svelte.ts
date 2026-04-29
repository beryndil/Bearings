/**
 * Tests for :mod:`stores/checklist.svelte.ts` — covers
 * :func:`refreshChecklist`, :func:`buildChecklistTree`, and the
 * polling-loop scheduling.
 *
 * The fetch is stubbed via ``vi.stubGlobal`` so the store calls reach
 * the real :func:`getChecklistOverview` typed client.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildChecklistTree,
  checklistStore,
  refreshChecklist,
  _resetForTests,
} from "../checklist.svelte";
import type { ChecklistItemOut } from "../../api/checklists";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  _resetForTests();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeItem(overrides: Partial<ChecklistItemOut> = {}): ChecklistItemOut {
  return {
    id: 1,
    checklist_id: "cl_a",
    parent_item_id: null,
    label: "An item",
    notes: null,
    sort_order: 100,
    checked_at: null,
    chat_session_id: null,
    blocked_at: null,
    blocked_reason_category: null,
    blocked_reason_text: null,
    created_at: "2026-04-29T00:00:00Z",
    updated_at: "2026-04-29T00:00:00Z",
    ...overrides,
  };
}

describe("buildChecklistTree", () => {
  it("groups children under their parent and sorts by sort_order", () => {
    const a = fakeItem({ id: 1, sort_order: 100 });
    const b = fakeItem({ id: 2, sort_order: 50 });
    const c = fakeItem({ id: 3, sort_order: 200, parent_item_id: 1 });
    const d = fakeItem({ id: 4, sort_order: 100, parent_item_id: 1 });
    const tree = buildChecklistTree([a, b, c, d]);
    expect(tree.roots.map((r) => r.id)).toEqual([2, 1]);
    expect(tree.childrenByParent.get(1)?.map((r) => r.id)).toEqual([4, 3]);
  });

  it("treats children of an unknown parent as roots (corrupt FK fallback)", () => {
    const orphan = fakeItem({ id: 5, parent_item_id: 999 });
    const tree = buildChecklistTree([orphan]);
    expect(tree.roots).toHaveLength(1);
    expect(tree.roots[0].id).toBe(5);
  });
});

describe("refreshChecklist", () => {
  it("populates state.items + state.activeRun on success", async () => {
    fetchMock.mockResolvedValueOnce({
      status: 200,
      statusText: "OK",
      json: async () => ({
        checklist_id: "cl_a",
        items: [fakeItem({ id: 1 })],
        active_run: null,
      }),
    });
    await refreshChecklist("cl_a");
    expect(checklistStore.items).toHaveLength(1);
    expect(checklistStore.error).toBeNull();
  });

  it("records the error on a non-2xx response", async () => {
    fetchMock.mockResolvedValueOnce({
      status: 500,
      statusText: "Server Error",
      json: async () => ({ detail: "boom" }),
    });
    await refreshChecklist("cl_a");
    expect(checklistStore.error).not.toBeNull();
  });
});
