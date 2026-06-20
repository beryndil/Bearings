/**
 * Component tests for ``ToolOutput`` — header, status pip, output
 * stream, truncation marker, error block.
 *
 * The "live clock" describe block covers gap-cycle-06-001:
 * elapsed counter ticks every second via ``setInterval`` while in
 * flight, and the ``liveElapsedMs`` floor from ``tool_progress``
 * events prevents a throttled local clock from showing a stale value.
 */
import { render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ToolOutput from "../ToolOutput.svelte";
import { CHAT_TOOL_OUTPUT_HEAD_CHARS, CHAT_TOOL_OUTPUT_TAIL_CHARS } from "../../../config";
import type { ToolCallView } from "../../../stores/conversation.svelte";

function tool(overrides: Partial<ToolCallView> = {}): ToolCallView {
  return {
    id: "t1",
    name: "Bash",
    inputJson: "{}",
    output: "",
    outputHead: "",
    isFolded: false,
    rawLength: 0,
    done: false,
    ok: null,
    durationMs: null,
    errorMessage: null,
    liveElapsedMs: 0,
    startedAt: 0,
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

  it("shows the truncation marker when output was hard-cap elided (not folded)", () => {
    // rawLength >> output.length but isFolded=false simulates the hard-cap path
    // (backend truncated before the soft-cap fold could apply).
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "tail",
          rawLength: 10_000,
          isFolded: false,
        }),
      },
    });
    expect(getByTestId("tool-output-truncated")).toHaveTextContent("9996");
  });
});

/**
 * M-6 two-tier middle-fold truncation (interactive expander).
 *
 * Behavior anchor: ``docs/behavior/tool-output-streaming.md``
 * §"Very-long-output truncation rules" — soft cap folds the middle
 * into an inline "Show full output" expander while keeping head/tail
 * bookends visible.
 */
describe("ToolOutput — two-tier middle fold (M-6)", () => {
  it("renders head + fold banner + tail when isFolded is true", () => {
    const { getByTestId, queryByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "...tail content...",
          outputHead: "...head content...",
          isFolded: true,
          rawLength: CHAT_TOOL_OUTPUT_HEAD_CHARS + 2000 + CHAT_TOOL_OUTPUT_TAIL_CHARS,
          done: true,
          ok: true,
          durationMs: 10,
        }),
      },
    });
    // Head is rendered
    expect(getByTestId("tool-output-head")).toHaveTextContent("head content");
    // Tail is rendered
    expect(getByTestId("tool-output-tail")).toHaveTextContent("tail content");
    // Fold banner present
    expect(getByTestId("tool-output-fold-banner")).toBeInTheDocument();
    // "Show full output" button present
    expect(getByTestId("tool-output-show-full")).toBeInTheDocument();
    // The non-folded stream element is NOT rendered
    expect(queryByTestId("tool-output-stream")).toBeNull();
  });

  it("renders the fold banner with the correct hidden-char count", () => {
    const hiddenChars = 2000;
    const rawLength = CHAT_TOOL_OUTPUT_HEAD_CHARS + hiddenChars + CHAT_TOOL_OUTPUT_TAIL_CHARS;
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "tail",
          outputHead: "head",
          isFolded: true,
          rawLength,
        }),
      },
    });
    // The banner must mention the hidden count
    const banner = getByTestId("tool-output-fold-banner");
    expect(banner.textContent).toContain(hiddenChars.toLocaleString());
  });

  it("clicking Show full output expands to combined head+tail", async () => {
    const { getByTestId, queryByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "TAIL_PART",
          outputHead: "HEAD_PART",
          isFolded: true,
          rawLength: CHAT_TOOL_OUTPUT_HEAD_CHARS + 500 + CHAT_TOOL_OUTPUT_TAIL_CHARS,
          done: true,
          ok: true,
          durationMs: 10,
        }),
      },
    });
    // Click the expander button
    getByTestId("tool-output-show-full").click();
    flushSync();
    // After expansion: stream shows combined content, fold elements gone
    const stream = getByTestId("tool-output-stream");
    expect(stream.textContent).toContain("HEAD_PART");
    expect(stream.textContent).toContain("TAIL_PART");
    expect(queryByTestId("tool-output-fold-banner")).toBeNull();
    expect(queryByTestId("tool-output-show-full")).toBeNull();
  });

  it("non-folded output renders as a single stream block (no fold UI)", () => {
    const { getByTestId, queryByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          output: "normal output",
          outputHead: "",
          isFolded: false,
          rawLength: 13,
          done: true,
          ok: true,
          durationMs: 10,
        }),
      },
    });
    expect(getByTestId("tool-output-stream")).toHaveTextContent("normal output");
    expect(queryByTestId("tool-output-fold-banner")).toBeNull();
    expect(queryByTestId("tool-output-show-full")).toBeNull();
  });
});

/**
 * Input JSON visibility (gap-cycle-06-003).
 *
 * Three criteria from the gap + empty-input compact rendering:
 *   (a) row body contains the inputJson text.
 *   (b) row body still contains the output stream.
 *   (c) inputJson with multi-line JSON renders as multi-line.
 *   (+) empty / ``{}`` input renders as a compact one-liner.
 */
describe("ToolOutput — input JSON visibility (gap-cycle-06-003)", () => {
  it("(a) row body contains the inputJson", () => {
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ inputJson: '{"command": "ls -la"}' }) },
    });
    expect(getByTestId("tool-output-input")).toHaveTextContent('"command": "ls -la"');
  });

  it("(b) row body still contains the output stream", () => {
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ inputJson: '{"command": "ls"}', output: "file1\nfile2\n" }) },
    });
    expect(getByTestId("tool-output-input")).toBeInTheDocument();
    expect(getByTestId("tool-output-stream")).toHaveTextContent("file1");
  });

  it("(c) inputJson with multi-line JSON renders as multi-line", () => {
    const multiline = JSON.stringify({ command: "ls -la", cwd: "/tmp" }, null, 2);
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ inputJson: multiline }) },
    });
    const pre = getByTestId("tool-output-input");
    expect(pre.textContent).toContain("\n");
    expect(pre.textContent).toContain('"command"');
    expect(pre.textContent).toContain('"cwd"');
  });

  it("empty {} input renders as a compact one-liner", () => {
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ inputJson: "{}" }) },
    });
    expect(getByTestId("tool-output-input")).toHaveTextContent("{}");
    // No newlines in a one-liner.
    expect(getByTestId("tool-output-input").textContent).not.toContain("\n");
  });
});

/**
 * Pretty-printed input JSON (gap-cycle-16-002).
 *
 * Three acceptance criteria from the gap:
 *   (a) A ``tool_call_start`` event with compact ``tool_input_json`` results
 *       in a rendered row with a multi-line pretty-printed body (newlines +
 *       2-space indent).
 *   (b) A hydrated tool call (``inputJson`` set at DB-hydration time, not
 *       from a live WS event) likewise renders a pretty-printed body.
 *   (c) A malformed JSON input string renders the raw string verbatim
 *       without throwing.
 *
 * The ``{}`` compact-one-liner case is already covered in the
 * gap-cycle-06-003 describe block above.
 */
describe("ToolOutput — pretty-printed input JSON (gap-cycle-16-002)", () => {
  it("(a) compact tool_call_start inputJson renders as multi-line pretty-printed", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({ inputJson: '{"command":"ls -la","description":"List files"}' }),
      },
    });
    const pre = getByTestId("tool-output-input");
    // Must contain newlines (multi-line).
    expect(pre.textContent).toContain("\n");
    // Keys must appear with 2-space indent.
    expect(pre.textContent).toContain('  "command"');
    expect(pre.textContent).toContain('  "description"');
  });

  it("(b) hydrated (done) tool call likewise renders pretty-printed input", () => {
    // Simulates a ToolCallView populated via hydrateToolCalls — inputJson
    // comes from the DB as compact single-line JSON.
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({
          inputJson: '{"file_path":"/tmp/foo.txt","offset":0}',
          done: true,
          ok: true,
          durationMs: 10,
        }),
      },
    });
    const pre = getByTestId("tool-output-input");
    expect(pre.textContent).toContain("\n");
    expect(pre.textContent).toContain('  "file_path"');
    expect(pre.textContent).toContain('  "offset"');
  });

  it("(c) malformed JSON renders the raw string verbatim without throwing", () => {
    const bad = '{"command": "ls -la"'; // missing closing brace
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ inputJson: bad }) },
    });
    // Must fall back to the raw string, no crash.
    expect(getByTestId("tool-output-input")).toHaveTextContent(bad);
  });
});

/**
 * Linkified output (gap-cycle-06-004).
 *
 * Three criteria from the gap acceptance criteria:
 *   (a) URL in output renders as ``<a target="_blank">`` anchor.
 *   (b) Workspace-relative path resolves against workingDir and renders
 *       a ``data-link-kind="file"`` anchor.
 *   (c) Output with no paths / URLs renders as plain text with no anchors.
 */
describe("ToolOutput — linkified output (gap-cycle-06-004)", () => {
  it("(a) URL in output renders an <a target='_blank'> anchor", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({ output: "see https://example.com for details", done: true, ok: true }),
      },
    });
    const stream = getByTestId("tool-output-stream");
    const anchor = stream.querySelector("a");
    expect(anchor).not.toBeNull();
    expect(anchor!.getAttribute("target")).toBe("_blank");
    expect(anchor!.getAttribute("href")).toBe("https://example.com");
  });

  it("(b) workspace-relative path resolves against workingDir and renders data-link-kind='file' anchor", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({ output: "edited src/bearings/foo.py line 42", done: true, ok: true }),
        workingDir: "/home/user/project",
      },
    });
    const stream = getByTestId("tool-output-stream");
    const anchor = stream.querySelector("a");
    expect(anchor).not.toBeNull();
    expect(anchor!.getAttribute("data-link-kind")).toBe("file");
    expect(anchor!.getAttribute("href")).toBe("file:///home/user/project/src/bearings/foo.py");
  });

  it("(c) output with no paths or URLs renders as plain text with no anchors", () => {
    const { getByTestId } = render(ToolOutput, {
      props: {
        call: tool({ output: "hello world, no links here", done: true, ok: true }),
      },
    });
    const stream = getByTestId("tool-output-stream");
    expect(stream.querySelector("a")).toBeNull();
    expect(stream).toHaveTextContent("hello world, no links here");
  });
});

/**
 * Live-clock behaviour (gap-cycle-06-001).
 *
 * The three sub-cases mirror the acceptance criteria directly:
 *   (a) elapsed display advances via ``setInterval`` ticks while in flight.
 *   (b) interval is cleared when the call completes (``done=true``).
 *   (c) ``liveElapsedMs`` floors the local clock when the server's
 *       keepalive value exceeds ``nowMs - startedAt`` (e.g. backgrounded tab).
 */
describe("ToolOutput — live clock", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("(a) elapsed display advances across two 1-second ticks while in flight", () => {
    const startedAt = Date.now();
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ startedAt, liveElapsedMs: 0 }) },
    });

    // At t=0: both nowMs and startedAt are the same → 0 ms → "00:00".
    flushSync();
    expect(getByTestId("tool-output-elapsed")).toHaveTextContent("00:00");

    // Advance 1 s → setInterval fires → nowMs = startedAt + 1000 → "00:01".
    vi.advanceTimersByTime(1000);
    flushSync();
    expect(getByTestId("tool-output-elapsed")).toHaveTextContent("00:01");

    // Advance another 1 s → "00:02".
    vi.advanceTimersByTime(1000);
    flushSync();
    expect(getByTestId("tool-output-elapsed")).toHaveTextContent("00:02");
  });

  it("(b) interval is cleared once done=true", () => {
    const clearSpy = vi.spyOn(window, "clearInterval");
    const startedAt = Date.now();

    const { rerender } = render(ToolOutput, {
      props: { call: tool({ startedAt, done: false }) },
    });

    // Verify the interval was registered (setInterval fired).
    vi.advanceTimersByTime(1000);
    flushSync();

    // Transition to done — the $effect cleanup should clear the interval.
    rerender({ call: tool({ startedAt, done: true, ok: true, durationMs: 1200 }) });
    flushSync();

    expect(clearSpy).toHaveBeenCalled();
  });

  it("(c) liveElapsedMs floors the display when it exceeds nowMs-startedAt", () => {
    // Local clock says 2 s have elapsed; server's keepalive says 5 s.
    // The larger (server) value must win.
    const startedAt = Date.now() - 2000;
    const { getByTestId } = render(ToolOutput, {
      props: { call: tool({ startedAt, liveElapsedMs: 5000 }) },
    });

    flushSync();
    // Math.max(2000, 5000) = 5000 → "00:05".
    expect(getByTestId("tool-output-elapsed")).toHaveTextContent("00:05");
  });
});
