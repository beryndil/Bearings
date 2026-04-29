/**
 * Component tests for ``ToolOutput`` — header, status pip, output
 * stream, truncation marker, error block.
 */
import { render } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";

import ToolOutput from "../ToolOutput.svelte";
import type { ToolCallView } from "../../../stores/conversation.svelte";

function tool(overrides: Partial<ToolCallView> = {}): ToolCallView {
  return {
    id: "t1",
    name: "Bash",
    inputJson: "{}",
    output: "",
    rawLength: 0,
    done: false,
    ok: null,
    durationMs: null,
    errorMessage: null,
    liveElapsedMs: 0,
    ...overrides,
  };
}

describe("ToolOutput", () => {
  it("renders the tool name and an in-flight status pip", () => {
    const { getByTestId } = render(ToolOutput, { props: { call: tool() } });
    expect(getByTestId("tool-output-name")).toHaveTextContent("Bash");
    expect(getByTestId("tool-output-status-pip")).toHaveAttribute("aria-label", "Running");
  });

  it("renders streamed output verbatim", () => {
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ output: "hello\nworld\n" }) },
    });
    expect(getByTestId("tool-output-stream")).toHaveTextContent("hello world");
  });

  it("flips the status pip green on a successful end", () => {
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ done: true, ok: true, durationMs: 10 }) },
    });
    expect(getByTestId("tool-output-status-pip")).toHaveAttribute("aria-label", "Completed");
  });

  it("flips the status pip red and renders the error block on a failed end", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          done: true,
          ok: false,
          durationMs: 5,
          errorMessage: "boom",
          output: "partial\n",
        }),
      },
    });
    expect(getByTestId("tool-output-status-pip")).toHaveAttribute("aria-label", "Failed");
    expect(getByTestId("tool-output-error")).toHaveTextContent("boom");
    // Partial output stays visible per behavior doc §"Partial-output behavior on tool failure".
    expect(getByTestId("tool-output-stream")).toHaveTextContent("partial");
  });

  it("shows the truncation marker when output was elided", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "tail",
          rawLength: 10_000,
        }),
      },
    });
    expect(getByTestId("tool-output-truncated")).toHaveTextContent("9996");
  });
});
