/**
 * RuleRow tests — verifies field rendering, edit affordances, and
 * the spec §8 "Review:" prefix highlight (override-rate >
 * :data:`OVERRIDE_RATE_REVIEW_THRESHOLD`).
 */
import { fireEvent, render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import RuleRow from "../RuleRow.svelte";
import {
  OVERRIDE_RATE_REVIEW_THRESHOLD,
  ROUTING_EDITOR_STRINGS,
  ROUTING_MATCH_TYPE_ALWAYS,
  ROUTING_MATCH_TYPE_KEYWORD,
  ROUTING_MATCH_TYPE_LENGTH_GT,
  ROUTING_MATCH_TYPE_REGEX,
} from "../../../config";
import type { RoutingRuleOut, SystemRoutingRuleOut } from "../../../api/routingRules";

function fakeTagRule(overrides: Partial<RoutingRuleOut> = {}): RoutingRuleOut & {
  kind: "tag";
} {
  return {
    id: 1,
    tag_id: 100,
    priority: 50,
    enabled: true,
    match_type: ROUTING_MATCH_TYPE_KEYWORD,
    match_value: "architect",
    executor_model: "sonnet",
    advisor_model: "opus",
    advisor_max_uses: 5,
    effort_level: "auto",
    reason: "Workhorse default",
    created_at: 0,
    updated_at: 0,
    ...overrides,
    kind: "tag",
  };
}

function fakeSystemRule(
  overrides: Partial<SystemRoutingRuleOut> = {},
): SystemRoutingRuleOut & { kind: "system" } {
  return {
    id: 11,
    priority: 1000,
    enabled: true,
    match_type: ROUTING_MATCH_TYPE_ALWAYS,
    match_value: null,
    executor_model: "sonnet",
    advisor_model: "opus",
    advisor_max_uses: 5,
    effort_level: "auto",
    reason: "Workhorse default",
    seeded: false,
    created_at: 0,
    updated_at: 0,
    ...overrides,
    kind: "system",
  };
}

function noopHandlers() {
  return {
    onPatch: vi.fn(),
    onDuplicate: vi.fn(),
    onDelete: vi.fn(),
    onTest: vi.fn(),
  };
}

describe("RuleRow — field rendering", () => {
  it("renders priority, match-type, match-value, executor, advisor, effort, reason", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    expect((getByTestId("rule-row-priority") as HTMLInputElement).value).toBe("50");
    expect((getByTestId("rule-row-match-type") as HTMLSelectElement).value).toBe(
      ROUTING_MATCH_TYPE_KEYWORD,
    );
    expect((getByTestId("rule-row-match-value") as HTMLInputElement).value).toBe("architect");
    expect((getByTestId("rule-row-executor") as HTMLSelectElement).value).toBe("sonnet");
    expect((getByTestId("rule-row-advisor") as HTMLSelectElement).value).toBe("opus");
    expect((getByTestId("rule-row-effort") as HTMLSelectElement).value).toBe("auto");
    expect(getByTestId("rule-row-reason")).toHaveValue("Workhorse default");
  });

  it("disables the match-value input when match_type=always", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({
          match_type: ROUTING_MATCH_TYPE_ALWAYS,
          match_value: null,
        }),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    expect(getByTestId("rule-row-match-value")).toBeDisabled();
  });

  it("hides the advisor max-uses input when no advisor is selected", () => {
    const { queryByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({ advisor_model: null }),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    expect(queryByTestId("rule-row-advisor-max-uses")).toBeNull();
  });

  it("shows the seeded badge for a seeded system rule", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeSystemRule({ seeded: true }),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    const badge = getByTestId("rule-row-seeded");
    expect(badge).toHaveTextContent(ROUTING_EDITOR_STRINGS.rowSeededIndicatorLabel);
  });

  it("flags invalid regex with the spec-mandated row warning", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({
          match_type: ROUTING_MATCH_TYPE_REGEX,
          match_value: "[unclosed",
        }),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    expect(getByTestId("rule-row-invalid-regex")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.rowMatchValueInvalidRegex,
    );
  });
});

describe("RuleRow — Review highlighting (spec §8 + §10)", () => {
  it("does not render the Review prefix when override-rate is at or below the threshold", () => {
    const { queryByTestId, getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: OVERRIDE_RATE_REVIEW_THRESHOLD,
        ...noopHandlers(),
      },
    });
    expect(queryByTestId("rule-row-review-flag")).toBeNull();
    expect(getByTestId("rule-row")).toHaveAttribute("data-review", "false");
  });

  it("renders the Review prefix when override-rate exceeds the threshold", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: OVERRIDE_RATE_REVIEW_THRESHOLD + 0.05,
        ...noopHandlers(),
      },
    });
    const flag = getByTestId("rule-row-review-flag");
    expect(flag.textContent).toContain(ROUTING_EDITOR_STRINGS.reviewPrefix);
    expect(getByTestId("rule-row")).toHaveAttribute("data-review", "true");
    expect(flag.getAttribute("title")).toMatch(/Override rate \d+%/);
  });

  it("does not render the Review prefix when override-rate is null", () => {
    const { queryByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    expect(queryByTestId("rule-row-review-flag")).toBeNull();
  });
});

describe("RuleRow — edit affordances fire onPatch", () => {
  it("priority change fires onPatch with the new priority", async () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({ priority: 50 }),
        overrideRate: null,
        onPatch: (body) => {
          expect(body.priority).toBe(75);
        },
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    const input = getByTestId("rule-row-priority") as HTMLInputElement;
    input.value = "75";
    await fireEvent.change(input);
  });

  it("match-type change clears the match_value when pivoting into 'always'", async () => {
    const onPatch = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({
          match_type: ROUTING_MATCH_TYPE_KEYWORD,
          match_value: "stale value",
        }),
        overrideRate: null,
        onPatch,
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    const select = getByTestId("rule-row-match-type") as HTMLSelectElement;
    select.value = ROUTING_MATCH_TYPE_ALWAYS;
    await fireEvent.change(select);
    expect(onPatch).toHaveBeenCalledTimes(1);
    expect(onPatch.mock.calls[0][0]).toMatchObject({
      match_type: ROUTING_MATCH_TYPE_ALWAYS,
      match_value: null,
    });
  });

  it("enable checkbox toggle fires onPatch with the new value", async () => {
    const onPatch = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({ enabled: true }),
        overrideRate: null,
        onPatch,
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    const checkbox = getByTestId("rule-row-enabled") as HTMLInputElement;
    await fireEvent.click(checkbox);
    expect(onPatch).toHaveBeenCalled();
    expect(onPatch.mock.calls[0][0].enabled).toBe(false);
  });

  it("advisor=none toggle nulls the advisor_model on the patch payload", async () => {
    const onPatch = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({ advisor_model: "opus" }),
        overrideRate: null,
        onPatch,
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    const select = getByTestId("rule-row-advisor") as HTMLSelectElement;
    select.value = "";
    await fireEvent.change(select);
    expect(onPatch).toHaveBeenCalled();
    expect(onPatch.mock.calls[0][0].advisor_model).toBeNull();
  });

  it("priority change ignores non-numeric values without firing onPatch", async () => {
    const onPatch = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({ priority: 50 }),
        overrideRate: null,
        onPatch,
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    const input = getByTestId("rule-row-priority") as HTMLInputElement;
    input.value = "-3";
    await fireEvent.change(input);
    expect(onPatch).not.toHaveBeenCalled();
  });

  it("length match-type renders the length placeholder", () => {
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule({
          match_type: ROUTING_MATCH_TYPE_LENGTH_GT,
          match_value: "100",
        }),
        overrideRate: null,
        ...noopHandlers(),
      },
    });
    const input = getByTestId("rule-row-match-value") as HTMLInputElement;
    expect(input.placeholder).toBe(ROUTING_EDITOR_STRINGS.rowMatchValuePlaceholderLength);
  });
});

describe("RuleRow — action buttons", () => {
  it("Test button fires onTest", async () => {
    const onTest = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        onPatch: vi.fn(),
        onDuplicate: vi.fn(),
        onDelete: vi.fn(),
        onTest,
      },
    });
    await fireEvent.click(getByTestId("rule-row-test"));
    expect(onTest).toHaveBeenCalledTimes(1);
  });

  it("Duplicate button fires onDuplicate", async () => {
    const onDuplicate = vi.fn();
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        onPatch: vi.fn(),
        onDuplicate,
        onDelete: vi.fn(),
        onTest: vi.fn(),
      },
    });
    await fireEvent.click(getByTestId("rule-row-duplicate"));
    expect(onDuplicate).toHaveBeenCalledTimes(1);
  });

  it("Delete button fires onDelete after confirmation", async () => {
    const onDelete = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        onPatch: vi.fn(),
        onDuplicate: vi.fn(),
        onDelete,
        onTest: vi.fn(),
      },
    });
    await fireEvent.click(getByTestId("rule-row-delete"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(onDelete).toHaveBeenCalledTimes(1);
    confirmSpy.mockRestore();
  });

  it("Delete is suppressed when the user cancels the confirm dialog", async () => {
    const onDelete = vi.fn();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { getByTestId } = render(RuleRow, {
      props: {
        rule: fakeTagRule(),
        overrideRate: null,
        onPatch: vi.fn(),
        onDuplicate: vi.fn(),
        onDelete,
        onTest: vi.fn(),
      },
    });
    await fireEvent.click(getByTestId("rule-row-delete"));
    expect(onDelete).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
