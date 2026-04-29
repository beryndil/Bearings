/**
 * Component tests for :class:`ChecklistView`.
 *
 * Done-when criteria covered:
 *
 * * Tab / Shift-Tab nesting (calls ``indentItem`` / ``outdentItem``).
 * * Drag-reorder calls ``moveItem`` with the right shape.
 * * Inline label edit + add-input flow.
 * * The flatten + tree helpers are exercised through the rendered DOM.
 *
 * The store is stubbed at the prop seam to keep each test
 * deterministic — the singleton store + polling loop are out of scope
 * here; the store unit tests cover their own slice in
 * ``stores/__tests__/checklist.test.svelte.ts``.
 */
import { fireEvent, render, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChecklistView, { flattenChecklistTree } from "../ChecklistView.svelte";
import {
  buildChecklistTree,
  _resetForTests as resetChecklistStore,
} from "../../../stores/checklist.svelte";
import type { AutoDriverRunOut, ChecklistItemOut } from "../../../api/checklists";

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

interface StubStore {
  checklistId: string | null;
  items: ChecklistItemOut[];
  activeRun: AutoDriverRunOut | null;
  loading: boolean;
  error: Error | null;
}

function makeStubStore(
  items: ChecklistItemOut[],
  activeRun: AutoDriverRunOut | null = null,
): StubStore {
  return {
    checklistId: "cl_a",
    items,
    activeRun,
    loading: false,
    error: null,
  };
}

beforeEach(() => {
  resetChecklistStore();
});

describe("flattenChecklistTree (helper)", () => {
  it("walks roots in sort order, recursing into children", () => {
    const a = fakeItem({ id: 1, sort_order: 100 });
    const b = fakeItem({ id: 2, sort_order: 200 });
    const c = fakeItem({ id: 3, sort_order: 100, parent_item_id: 1 });
    const d = fakeItem({ id: 4, sort_order: 200, parent_item_id: 1 });
    const tree = buildChecklistTree([a, b, c, d]);
    const rows = flattenChecklistTree(tree.roots, tree.childrenByParent);
    expect(rows.map((r) => r.item.id)).toEqual([1, 3, 4, 2]);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 1, 0]);
    // Item 1 has children, so it is not a leaf; items 3, 4, 2 are leaves.
    expect(rows.map((r) => r.isLeaf)).toEqual([false, true, true, true]);
  });
});

describe("ChecklistView — render branches", () => {
  it("renders the empty-state copy when the items list is empty", () => {
    const stubStore = makeStubStore([]);
    const { getByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
      },
    });
    expect(getByTestId("checklist-view-empty")).toBeInTheDocument();
  });

  it("renders one row per item with the right depth attribute", () => {
    const stubStore = makeStubStore([
      fakeItem({ id: 1, sort_order: 100 }),
      fakeItem({ id: 2, sort_order: 100, parent_item_id: 1 }),
    ]);
    const { getAllByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
      },
    });
    const rows = getAllByTestId("checklist-row");
    expect(rows).toHaveLength(2);
    expect(rows[0].dataset.depth).toBe("0");
    expect(rows[1].dataset.depth).toBe("1");
  });
});

describe("ChecklistView — Tab / Shift+Tab nesting", () => {
  it("calls indentItem on Tab", async () => {
    const stubStore = makeStubStore([
      fakeItem({ id: 1, sort_order: 100 }),
      fakeItem({ id: 2, sort_order: 200 }),
    ]);
    const indentItem = vi.fn().mockResolvedValue(fakeItem({ id: 2 }));
    const { getAllByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        indentItem,
      },
    });
    const labels = getAllByTestId("checklist-label");
    await fireEvent.keyDown(labels[1], { key: "Tab" });
    await waitFor(() => expect(indentItem).toHaveBeenCalledWith(2));
  });

  it("calls outdentItem on Shift+Tab", async () => {
    const stubStore = makeStubStore([
      fakeItem({ id: 1, sort_order: 100 }),
      fakeItem({ id: 2, sort_order: 100, parent_item_id: 1 }),
    ]);
    const outdentItem = vi.fn().mockResolvedValue(fakeItem({ id: 2 }));
    const { getAllByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        outdentItem,
      },
    });
    const labels = getAllByTestId("checklist-label");
    await fireEvent.keyDown(labels[1], { key: "Tab", shiftKey: true });
    await waitFor(() => expect(outdentItem).toHaveBeenCalledWith(2));
  });
});

describe("ChecklistView — drag-reorder", () => {
  it("calls moveItem with the dragged + dropped item ids", async () => {
    const target = fakeItem({ id: 2, sort_order: 200 });
    const stubStore = makeStubStore([fakeItem({ id: 1, sort_order: 100 }), target]);
    const moveItem = vi.fn().mockResolvedValue(target);
    const { getAllByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        moveItem,
      },
    });
    const rows = getAllByTestId("checklist-row");
    await fireEvent.dragStart(rows[0]);
    await fireEvent.dragOver(rows[1]);
    await fireEvent.drop(rows[1]);
    await waitFor(() =>
      expect(moveItem).toHaveBeenCalledWith(1, {
        parent_item_id: null,
        sort_order: 201,
      }),
    );
  });

  it("calls moveItem with parent_item_id when shift is held on drop (reparent)", async () => {
    const stubStore = makeStubStore([
      fakeItem({ id: 1, sort_order: 100 }),
      fakeItem({ id: 2, sort_order: 200 }),
    ]);
    const moveItem = vi.fn().mockResolvedValue(fakeItem({ id: 1 }));
    const { getAllByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        moveItem,
      },
    });
    const rows = getAllByTestId("checklist-row");
    await fireEvent.dragStart(rows[0]);
    // jsdom's basic ``Event`` constructor doesn't carry ``shiftKey``
    // through ``fireEvent``'s eventInit projection — define it
    // explicitly on a dispatched event so the production handler's
    // ``event.shiftKey`` read sees the test's shift state.
    const dropEvent = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(dropEvent, "shiftKey", { value: true });
    rows[1].dispatchEvent(dropEvent);
    await waitFor(() => expect(moveItem).toHaveBeenCalledWith(1, { parent_item_id: 2 }));
  });
});

describe("ChecklistView — add-item input", () => {
  it("calls createItem on Enter and clears the input", async () => {
    const stubStore = makeStubStore([]);
    const createItem = vi.fn().mockResolvedValue(fakeItem({ id: 99, label: "fresh" }));
    const { getByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        createItem,
      },
    });
    const input = getByTestId("checklist-add-input") as HTMLInputElement;
    input.value = "fresh";
    await fireEvent.input(input, { target: { value: "fresh" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() =>
      expect(createItem).toHaveBeenCalledWith("cl_a", { label: "fresh", parent_item_id: null }),
    );
  });

  it("ignores an empty Enter (no boundary write)", async () => {
    const stubStore = makeStubStore([]);
    const createItem = vi.fn();
    const { getByTestId } = render(ChecklistView, {
      props: {
        checklistId: "cl_a",
        checklistStore: stubStore,
        setActiveChecklist: vi.fn(),
        pokeChecklist: vi.fn().mockResolvedValue(undefined),
        createItem,
      },
    });
    const input = getByTestId("checklist-add-input") as HTMLInputElement;
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(createItem).not.toHaveBeenCalled();
  });
});
