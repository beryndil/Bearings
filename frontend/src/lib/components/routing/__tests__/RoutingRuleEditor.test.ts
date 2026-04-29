/**
 * RoutingRuleEditor tests — verifies the per-tag + system surfaces
 * (spec §3 + §10): list rendering, drag-reorder API call,
 * enable/disable toggle, duplicate, delete.  Also asserts the
 * spec §8 + §10 "Review:" highlight is wired through the
 * override-rate adapter.
 *
 * Tests inject in-memory adapter implementations via the ``adapters``
 * test seam — no fetch is mocked.
 */
import { fireEvent, render, waitFor } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import RoutingRuleEditor from "../RoutingRuleEditor.svelte";
import {
  OVERRIDE_RATE_REVIEW_THRESHOLD,
  ROUTING_EDITOR_STRINGS,
  ROUTING_MATCH_TYPE_KEYWORD,
} from "../../../config";
import type {
  RoutingRuleIn,
  RoutingRuleOut,
  SystemRoutingRuleOut,
} from "../../../api/routingRules";
import type { OverrideRateOut } from "../../../api/usage";

function tagRow(
  id: number,
  priority: number,
  overrides: Partial<RoutingRuleOut> = {},
): RoutingRuleOut {
  return {
    id,
    tag_id: 100,
    priority,
    enabled: true,
    match_type: ROUTING_MATCH_TYPE_KEYWORD,
    match_value: `keyword-${id}`,
    executor_model: "sonnet",
    advisor_model: "opus",
    advisor_max_uses: 5,
    effort_level: "auto",
    reason: `Reason ${id}`,
    created_at: 0,
    updated_at: 0,
    ...overrides,
  };
}

function systemRow(
  id: number,
  priority: number,
  overrides: Partial<SystemRoutingRuleOut> = {},
): SystemRoutingRuleOut {
  return {
    id,
    priority,
    enabled: true,
    match_type: ROUTING_MATCH_TYPE_KEYWORD,
    match_value: `keyword-${id}`,
    executor_model: "sonnet",
    advisor_model: "opus",
    advisor_max_uses: 5,
    effort_level: "auto",
    reason: `Reason ${id}`,
    seeded: false,
    created_at: 0,
    updated_at: 0,
    ...overrides,
  };
}

function buildTagAdapters(initial: RoutingRuleOut[], overrides: OverrideRateOut[] = []) {
  let rows = [...initial];
  return {
    listTagRules: vi.fn(async () => [...rows]),
    createTagRule: vi.fn(async (_tagId: number, body: RoutingRuleIn) => {
      const created: RoutingRuleOut = {
        ...tagRow(1000 + rows.length, body.priority),
        ...body,
        id: 1000 + rows.length,
      };
      rows.push(created);
      return created;
    }),
    updateTagRule: vi.fn(async (id: number, body: RoutingRuleIn) => {
      const next = rows.findIndex((r) => r.id === id);
      const updated: RoutingRuleOut = { ...rows[next], ...body, id };
      rows[next] = updated;
      return updated;
    }),
    deleteTagRule: vi.fn(async (id: number) => {
      rows = rows.filter((r) => r.id !== id);
    }),
    reorderTagRules: vi.fn(async (_tagId: number, idsInOrder: number[]) => {
      rows = idsInOrder
        .map((id, idx) => {
          const found = rows.find((r) => r.id === id);
          return found === undefined ? null : { ...found, priority: (idx + 1) * 10 };
        })
        .filter((r): r is RoutingRuleOut => r !== null);
      return [...rows];
    }),
    listSystemRules: vi.fn(async () => []),
    createSystemRule: vi.fn(async () => {
      throw new Error("system create called on a tag-mode editor");
    }),
    updateSystemRule: vi.fn(async () => {
      throw new Error("system update called on a tag-mode editor");
    }),
    deleteSystemRule: vi.fn(async () => {
      throw new Error("system delete called on a tag-mode editor");
    }),
    getOverrideRates: vi.fn(async () => [...overrides]),
  };
}

function buildSystemAdapters(initial: SystemRoutingRuleOut[], overrides: OverrideRateOut[] = []) {
  let rows = [...initial];
  return {
    listTagRules: vi.fn(async () => []),
    createTagRule: vi.fn(async () => {
      throw new Error("tag create called on a system-mode editor");
    }),
    updateTagRule: vi.fn(async () => {
      throw new Error("tag update called on a system-mode editor");
    }),
    deleteTagRule: vi.fn(async () => {
      throw new Error("tag delete called on a system-mode editor");
    }),
    reorderTagRules: vi.fn(async () => {
      throw new Error("tag reorder called on a system-mode editor");
    }),
    listSystemRules: vi.fn(async () => [...rows]),
    createSystemRule: vi.fn(async (body: RoutingRuleIn) => {
      const created: SystemRoutingRuleOut = {
        ...systemRow(2000 + rows.length, body.priority),
        ...body,
        id: 2000 + rows.length,
        seeded: false,
      };
      rows.push(created);
      return created;
    }),
    updateSystemRule: vi.fn(async (id: number, body: RoutingRuleIn) => {
      const idx = rows.findIndex((r) => r.id === id);
      const updated: SystemRoutingRuleOut = { ...rows[idx], ...body, id };
      rows[idx] = updated;
      return updated;
    }),
    deleteSystemRule: vi.fn(async (id: number) => {
      rows = rows.filter((r) => r.id !== id);
    }),
    getOverrideRates: vi.fn(async () => [...overrides]),
  };
}

describe("RoutingRuleEditor — list rendering (tag mode)", () => {
  it("renders one row per tag rule, in API order", async () => {
    const adapters = buildTagAdapters([tagRow(1, 10), tagRow(2, 20), tagRow(3, 30)]);
    const { findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const rows = await findAllByTestId("rule-row");
    expect(rows.map((r) => r.getAttribute("data-rule-id"))).toEqual(["1", "2", "3"]);
    expect(rows[0].getAttribute("data-rule-kind")).toBe("tag");
  });

  it("renders the loading placeholder before the API resolves", async () => {
    const adapters = buildTagAdapters([tagRow(1, 10)]);
    const { getByTestId, findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    expect(getByTestId("routing-editor-loading")).toBeInTheDocument();
    await findAllByTestId("rule-row");
  });

  it("renders the empty-state copy when no rules are returned", async () => {
    const adapters = buildTagAdapters([]);
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const empty = await findByTestId("routing-editor-empty");
    expect(empty).toHaveTextContent(ROUTING_EDITOR_STRINGS.emptyTag);
  });

  it("renders the error placeholder when the list call rejects", async () => {
    const adapters = {
      ...buildTagAdapters([]),
      listTagRules: vi.fn(async () => {
        throw new Error("boom");
      }),
    };
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    expect(await findByTestId("routing-editor-load-failed")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.loadFailed,
    );
  });
});

describe("RoutingRuleEditor — list rendering (system mode)", () => {
  it("renders system rows + tags each row with kind=system", async () => {
    const adapters = buildSystemAdapters([systemRow(11, 10), systemRow(22, 20)]);
    const { findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "system", adapters },
    });
    const rows = await findAllByTestId("rule-row");
    expect(rows.map((r) => r.getAttribute("data-rule-kind"))).toEqual(["system", "system"]);
    expect(rows.map((r) => r.getAttribute("data-rule-id"))).toEqual(["11", "22"]);
  });

  it("renders the system-mode aria-label on the pane", async () => {
    const adapters = buildSystemAdapters([systemRow(1, 10)]);
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "system", adapters },
    });
    const pane = await findByTestId("routing-editor");
    expect(pane).toHaveAttribute("aria-label", ROUTING_EDITOR_STRINGS.paneAriaLabelSystem);
    expect(pane).toHaveAttribute("data-routing-rule-kind", "system");
  });
});

describe("RoutingRuleEditor — enable/disable toggle", () => {
  it("PATCHes the rule with enabled=false when the checkbox is unchecked", async () => {
    const adapters = buildTagAdapters([tagRow(7, 50, { enabled: true })]);
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const checkbox = (await findByTestId("rule-row-enabled")) as HTMLInputElement;
    await fireEvent.click(checkbox);
    await waitFor(() => {
      expect(adapters.updateTagRule).toHaveBeenCalledTimes(1);
    });
    const [id, body] = adapters.updateTagRule.mock.calls[0];
    expect(id).toBe(7);
    expect((body as RoutingRuleIn).enabled).toBe(false);
  });
});

describe("RoutingRuleEditor — duplicate", () => {
  it("creates a new tag rule cloned from the source row", async () => {
    const adapters = buildTagAdapters([
      tagRow(1, 10, { reason: "First" }),
      tagRow(2, 20, { reason: "Second" }),
    ]);
    const { findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const rows = await findAllByTestId("rule-row");
    const dupBtn = rows[0].querySelector('[data-testid="rule-row-duplicate"]') as HTMLButtonElement;
    await fireEvent.click(dupBtn);
    await waitFor(() => {
      expect(adapters.createTagRule).toHaveBeenCalledTimes(1);
    });
    const [tagId, body] = adapters.createTagRule.mock.calls[0];
    expect(tagId).toBe(100);
    expect((body as RoutingRuleIn).reason).toBe("First");
    expect((body as RoutingRuleIn).priority).toBe(11); // source priority + 1
  });
});

describe("RoutingRuleEditor — delete", () => {
  it("DELETEs and removes the row from the rendered list (system mode)", async () => {
    const adapters = buildSystemAdapters([systemRow(11, 10), systemRow(22, 20)]);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { findAllByTestId, queryAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "system", adapters },
    });
    const rows = await findAllByTestId("rule-row");
    const deleteBtn = rows[0].querySelector('[data-testid="rule-row-delete"]') as HTMLButtonElement;
    await fireEvent.click(deleteBtn);
    await waitFor(() => {
      expect(adapters.deleteSystemRule).toHaveBeenCalledWith(11);
    });
    await waitFor(() => {
      expect(queryAllByTestId("rule-row").length).toBe(1);
    });
    confirmSpy.mockRestore();
  });
});

describe("RoutingRuleEditor — drag-reorder (tag mode)", () => {
  it("calls reorderTagRules with the new id order on drop", async () => {
    const adapters = buildTagAdapters([tagRow(1, 10), tagRow(2, 20), tagRow(3, 30)]);
    const { findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const rows = await findAllByTestId("rule-row");
    // Build a DataTransfer-shaped object that the handler accepts; the
    // component reads ``effectAllowed`` / ``setData`` / ``dropEffect``
    // off ``event.dataTransfer`` and then ignores the content.
    const dataTransfer = {
      effectAllowed: "",
      dropEffect: "",
      setData: vi.fn(),
      getData: vi.fn(() => "0"),
    } as unknown as DataTransfer;
    await fireEvent.dragStart(rows[0], { dataTransfer });
    await fireEvent.dragOver(rows[2], { dataTransfer });
    await fireEvent.drop(rows[2], { dataTransfer });
    await waitFor(() => {
      expect(adapters.reorderTagRules).toHaveBeenCalledTimes(1);
    });
    const [tagId, idsInOrder] = adapters.reorderTagRules.mock.calls[0];
    expect(tagId).toBe(100);
    // Move row 0 (id=1) to position 2 → final order [2, 3, 1].
    expect(idsInOrder).toEqual([2, 3, 1]);
  });
});

describe("RoutingRuleEditor — drag-reorder (system mode)", () => {
  it("re-stamps system-rule priorities via per-rule PATCH at sparse stride", async () => {
    const adapters = buildSystemAdapters([systemRow(11, 10), systemRow(22, 20), systemRow(33, 30)]);
    const { findAllByTestId } = render(RoutingRuleEditor, {
      props: { kind: "system", adapters },
    });
    const rows = await findAllByTestId("rule-row");
    const dataTransfer = {
      effectAllowed: "",
      dropEffect: "",
      setData: vi.fn(),
      getData: vi.fn(() => "2"),
    } as unknown as DataTransfer;
    await fireEvent.dragStart(rows[2], { dataTransfer });
    await fireEvent.dragOver(rows[0], { dataTransfer });
    await fireEvent.drop(rows[0], { dataTransfer });
    await waitFor(() => {
      // Row at original index 2 (id=33) lands at index 0 → priority 10.
      // Row at original index 0 (id=11) shifts to index 1 → priority 20.
      // Row at original index 1 (id=22) shifts to index 2 → priority 30.
      // Only rows whose priority actually changes get a PATCH:
      //   id=33: 30 → 10 (changes)
      //   id=11: 10 → 20 (changes)
      //   id=22: 20 → 30 (changes)
      expect(adapters.updateSystemRule).toHaveBeenCalled();
    });
    const calls = adapters.updateSystemRule.mock.calls;
    const idsCalled = calls.map((c) => c[0]);
    expect(idsCalled).toContain(33);
    expect(idsCalled).toContain(11);
    expect(idsCalled).toContain(22);
  });
});

describe("RoutingRuleEditor — Review highlighting (spec §8 + §10)", () => {
  it("passes override rate down so RuleRow lights the Review prefix", async () => {
    const adapters = buildTagAdapters(
      [tagRow(7, 50)],
      [
        {
          rule_kind: "tag",
          rule_id: 7,
          fired_count: 10,
          overridden_count: 5,
          rate: OVERRIDE_RATE_REVIEW_THRESHOLD + 0.05,
          review: true,
        },
      ],
    );
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const flag = await findByTestId("rule-row-review-flag");
    expect(flag.textContent).toContain(ROUTING_EDITOR_STRINGS.reviewPrefix);
  });

  it("does not light the Review prefix for sub-threshold rules", async () => {
    const adapters = buildTagAdapters(
      [tagRow(8, 60)],
      [
        {
          rule_kind: "tag",
          rule_id: 8,
          fired_count: 10,
          overridden_count: 1,
          rate: OVERRIDE_RATE_REVIEW_THRESHOLD - 0.01,
          review: false,
        },
      ],
    );
    const { findByTestId, queryByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    await findByTestId("rule-row");
    expect(queryByTestId("rule-row-review-flag")).toBeNull();
  });
});

describe("RoutingRuleEditor — add new rule", () => {
  it("creates a tag rule with the documented defaults on Add click", async () => {
    const adapters = buildTagAdapters([]);
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const addBtn = await findByTestId("routing-editor-add");
    await fireEvent.click(addBtn);
    await waitFor(() => {
      expect(adapters.createTagRule).toHaveBeenCalledTimes(1);
    });
    const [tagId, body] = adapters.createTagRule.mock.calls[0];
    expect(tagId).toBe(100);
    expect((body as RoutingRuleIn).match_type).toBe(ROUTING_MATCH_TYPE_KEYWORD);
    expect((body as RoutingRuleIn).executor_model).toBe("sonnet");
    expect((body as RoutingRuleIn).advisor_model).toBe("opus");
  });

  it("creates a system rule (system mode)", async () => {
    const adapters = buildSystemAdapters([]);
    const { findByTestId } = render(RoutingRuleEditor, {
      props: { kind: "system", adapters },
    });
    await fireEvent.click(await findByTestId("routing-editor-add"));
    await waitFor(() => {
      expect(adapters.createSystemRule).toHaveBeenCalledTimes(1);
    });
  });
});

describe("RoutingRuleEditor — Test against message dialog", () => {
  it("opens the dialog when a row's Test action fires; closes on close", async () => {
    const adapters = buildTagAdapters([tagRow(1, 10)]);
    const { findByTestId, queryByTestId } = render(RoutingRuleEditor, {
      props: { kind: "tag", tagId: 100, adapters },
    });
    const testBtn = await findByTestId("rule-row-test");
    await fireEvent.click(testBtn);
    expect(await findByTestId("test-dialog")).toBeInTheDocument();
    await fireEvent.click(await findByTestId("test-dialog-close"));
    await waitFor(() => {
      expect(queryByTestId("test-dialog")).toBeNull();
    });
  });
});
