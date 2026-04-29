/**
 * Component tests for :class:`SentinelEvent` — covers the colour
 * mapping documented in ``docs/behavior/checklists.md`` §"Item-status
 * colors". Each row in the doc table is one assertion.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import SentinelEvent, { pipColorForItem, pipTooltip } from "../SentinelEvent.svelte";
import type { ChecklistItemOut } from "../../../api/checklists";

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

describe("pipColorForItem (helper)", () => {
  it("returns 'none' for a fresh item with no paired chat", () => {
    expect(pipColorForItem(fakeItem(), false)).toBe("none");
  });

  it("returns 'slate' for a paired-but-not-active item", () => {
    expect(pipColorForItem(fakeItem({ chat_session_id: "ses_a" }), false)).toBe("slate");
  });

  it("returns 'blue' when the driver is currently on this item", () => {
    expect(pipColorForItem(fakeItem({ chat_session_id: "ses_a" }), true)).toBe("blue");
  });

  it("returns 'green' for a checked item", () => {
    expect(pipColorForItem(fakeItem({ checked_at: "2026-04-29T01:00:00Z" }), false)).toBe("green");
  });

  it("returns 'amber' for blocked", () => {
    expect(pipColorForItem(fakeItem({ blocked_reason_category: "blocked" }), false)).toBe("amber");
  });

  it("returns 'red' for failed", () => {
    expect(pipColorForItem(fakeItem({ blocked_reason_category: "failed" }), false)).toBe("red");
  });

  it("returns 'grey' for skipped", () => {
    expect(pipColorForItem(fakeItem({ blocked_reason_category: "skipped" }), false)).toBe("grey");
  });
});

describe("pipTooltip (helper)", () => {
  it("returns a non-empty tooltip for every defined colour", () => {
    for (const color of ["none", "slate", "blue", "green", "amber", "red", "grey"] as const) {
      expect(pipTooltip(color).length).toBeGreaterThan(0);
    }
  });
});

describe("SentinelEvent — render", () => {
  it("attaches the colour as data-pip-color", () => {
    const { getByTestId } = render(SentinelEvent, {
      props: { item: fakeItem({ chat_session_id: "ses_a" }), isCurrent: true },
    });
    const pip = getByTestId("sentinel-event");
    expect(pip.dataset.pipColor).toBe("blue");
  });

  it("renders the tooltip via the title attribute", () => {
    const { getByTestId } = render(SentinelEvent, {
      props: { item: fakeItem({ checked_at: "2026-04-29T00:00:00Z" }) },
    });
    const pip = getByTestId("sentinel-event");
    expect(pip.getAttribute("title")).toContain("checked");
  });
});
