/**
 * TestAgainstMessageDialog tests — verifies the deterministic
 * per-rule evaluation surface (spec §10): paste a message, click
 * Evaluate, render the matched/missed/invalid-regex verdict. No
 * fetch is exercised — the dialog runs the rule's match condition
 * client-side.
 */
import { fireEvent, render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import TestAgainstMessageDialog from "../TestAgainstMessageDialog.svelte";
import {
  ROUTING_EDITOR_STRINGS,
  ROUTING_MATCH_TYPE_KEYWORD,
  ROUTING_MATCH_TYPE_REGEX,
  ROUTING_MATCH_TYPE_ALWAYS,
} from "../../../config";

interface RuleLike {
  id: number;
  match_type: string;
  match_value: string | null;
  executor_model: string;
  advisor_model: string | null;
  advisor_max_uses: number;
  effort_level: string;
  reason: string;
}

function fakeRule(overrides: Partial<RuleLike> = {}): RuleLike {
  return {
    id: 7,
    match_type: ROUTING_MATCH_TYPE_KEYWORD,
    match_value: "architect, refactor",
    executor_model: "sonnet",
    advisor_model: "opus",
    advisor_max_uses: 5,
    effort_level: "auto",
    reason: "Workhorse default",
    ...overrides,
  };
}

describe("TestAgainstMessageDialog — render", () => {
  it("renders the title and intro from the string table", () => {
    const { getByTestId } = render(TestAgainstMessageDialog, {
      props: { rule: fakeRule(), onClose: () => {} },
    });
    expect(getByTestId("test-dialog-title")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.testDialogTitle,
    );
    expect(getByTestId("test-dialog-intro")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.testDialogIntro,
    );
  });

  it("does not render a result before Evaluate is clicked", () => {
    const { queryByTestId } = render(TestAgainstMessageDialog, {
      props: { rule: fakeRule(), onClose: () => {} },
    });
    expect(queryByTestId("test-dialog-result")).toBeNull();
  });
});

describe("TestAgainstMessageDialog — evaluation (deterministic, no LLM)", () => {
  it("renders the matched verdict + decision dl when the rule fires", async () => {
    const rule = fakeRule({ match_type: ROUTING_MATCH_TYPE_KEYWORD });
    const { getByTestId, queryByTestId } = render(TestAgainstMessageDialog, {
      props: { rule, onClose: () => {} },
    });
    const textarea = getByTestId("test-dialog-message") as HTMLTextAreaElement;
    await fireEvent.input(textarea, { target: { value: "Please ARCHITECT a module" } });
    await fireEvent.click(getByTestId("test-dialog-evaluate"));

    const result = getByTestId("test-dialog-result");
    expect(result).toHaveAttribute("data-matched", "true");
    expect(getByTestId("test-dialog-matched")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.testDialogResultMatched,
    );
    expect(getByTestId("test-dialog-executor").textContent).toMatch(/sonnet/i);
    expect(getByTestId("test-dialog-advisor").textContent).toMatch(/opus/i);
    expect(getByTestId("test-dialog-effort").textContent).toMatch(/auto/);
    expect(getByTestId("test-dialog-reason")).toHaveTextContent("Workhorse default");
    expect(queryByTestId("test-dialog-missed")).toBeNull();
  });

  it("renders the missed verdict (no decision dl) when the rule does not fire", async () => {
    const rule = fakeRule({
      match_type: ROUTING_MATCH_TYPE_KEYWORD,
      match_value: "architect",
    });
    const { getByTestId, queryByTestId } = render(TestAgainstMessageDialog, {
      props: { rule, onClose: () => {} },
    });
    await fireEvent.input(getByTestId("test-dialog-message"), {
      target: { value: "Quick syntax question." },
    });
    await fireEvent.click(getByTestId("test-dialog-evaluate"));

    expect(getByTestId("test-dialog-result")).toHaveAttribute("data-matched", "false");
    expect(getByTestId("test-dialog-missed")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.testDialogResultMissed,
    );
    expect(queryByTestId("test-dialog-executor")).toBeNull();
  });

  it("flags invalid regex with the spec-mandated error copy", async () => {
    const rule = fakeRule({
      match_type: ROUTING_MATCH_TYPE_REGEX,
      match_value: "[unclosed",
    });
    const { getByTestId } = render(TestAgainstMessageDialog, {
      props: { rule, onClose: () => {} },
    });
    await fireEvent.input(getByTestId("test-dialog-message"), {
      target: { value: "anything" },
    });
    await fireEvent.click(getByTestId("test-dialog-evaluate"));

    expect(getByTestId("test-dialog-result")).toHaveAttribute("data-invalid-regex", "true");
    expect(getByTestId("test-dialog-invalid-regex")).toHaveTextContent(
      ROUTING_EDITOR_STRINGS.testDialogInvalidRegex,
    );
  });

  it("matches unconditionally for match_type=always (empty message included)", async () => {
    const rule = fakeRule({ match_type: ROUTING_MATCH_TYPE_ALWAYS, match_value: null });
    const { getByTestId } = render(TestAgainstMessageDialog, {
      props: { rule, onClose: () => {} },
    });
    // Click without typing — empty message should still match.
    await fireEvent.click(getByTestId("test-dialog-evaluate"));
    expect(getByTestId("test-dialog-result")).toHaveAttribute("data-matched", "true");
  });
});

describe("TestAgainstMessageDialog — close affordances", () => {
  it("close button fires onClose", async () => {
    const onClose = vi.fn();
    const { getByTestId } = render(TestAgainstMessageDialog, {
      props: { rule: fakeRule(), onClose },
    });
    await fireEvent.click(getByTestId("test-dialog-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape key fires onClose", async () => {
    const onClose = vi.fn();
    render(TestAgainstMessageDialog, {
      props: { rule: fakeRule(), onClose },
    });
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("backdrop click fires onClose; inner click does not", async () => {
    const onClose = vi.fn();
    const { getByTestId } = render(TestAgainstMessageDialog, {
      props: { rule: fakeRule(), onClose },
    });
    await fireEvent.click(getByTestId("test-dialog-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);
    await fireEvent.click(getByTestId("test-dialog"));
    // Clicking the dialog body should not propagate as a backdrop click.
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
