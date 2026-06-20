/**
 * InspectorContext tests — title / description / context-window
 * fields render from the fixture session, with the documented
 * placeholders when the wire value is null. Also covers the
 * assembled-context section wired to ``getSessionSystemPrompt``.
 */
import { render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InspectorContext from "../InspectorContext.svelte";
import { INSPECTOR_STRINGS } from "../../../config";
import type { SessionOut, SystemPromptLayersOut } from "../../../api/sessions";
import * as sessionsApi from "../../../api/sessions";

function fakeSession(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: "ses_a",
    kind: "chat",
    title: "Fixture title",
    description: null,
    session_instructions: null,
    working_dir: "/wd",
    model: "sonnet",
    permission_mode: null,
    max_budget_usd: null,
    total_cost_usd: 0,
    message_count: 0,
    last_context_pct: null,
    last_context_tokens: null,
    last_context_max: null,
    pinned: false,
    error_pending: false,
    checklist_item_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    last_viewed_at: null,
    last_completed_at: null,
    closed_at: null,
    closing_summary: null,
    ...overrides,
  };
}

function fakeLayersOut(layers: SystemPromptLayersOut["layers"] = []): SystemPromptLayersOut {
  return {
    layers,
    total_tokens: layers.reduce((s, l) => s + l.token_count, 0),
    token_count_approximate: true,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("InspectorContext — labelled fields", () => {
  it("renders the heading", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByText } = render(InspectorContext, {
      props: { session: fakeSession() },
    });
    expect(getByText(INSPECTOR_STRINGS.contextHeading)).toBeInTheDocument();
  });

  it("renders the session title verbatim", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId } = render(InspectorContext, {
      props: { session: fakeSession({ title: "Designing the inspector" }) },
    });
    expect(getByTestId("inspector-context-title")).toHaveTextContent("Designing the inspector");
  });

  it("renders the description when set, the empty placeholder otherwise", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId, rerender } = render(InspectorContext, {
      props: { session: fakeSession({ description: "multi-line\nplug" }) },
    });
    expect(getByTestId("inspector-context-description")).toHaveTextContent("multi-line plug");

    rerender({ session: fakeSession({ description: null }) });
    expect(getByTestId("inspector-context-description")).toHaveTextContent(
      INSPECTOR_STRINGS.contextDescriptionEmpty,
    );
  });

  it("formats the last context-window pressure as a percent", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId, rerender } = render(InspectorContext, {
      props: { session: fakeSession({ last_context_pct: 0.42 }) },
    });
    expect(getByTestId("inspector-context-last-pct")).toHaveTextContent("42%");

    rerender({ session: fakeSession({ last_context_pct: null }) });
    expect(getByTestId("inspector-context-last-pct")).toHaveTextContent(
      INSPECTOR_STRINGS.contextLastContextNotSeen,
    );
  });

  it("formats the last context tokens with locale-grouped digits", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId } = render(InspectorContext, {
      props: { session: fakeSession({ last_context_tokens: 175500 }) },
    });
    // ``toLocaleString`` defaults to the runtime locale; the
    // separator glyph (comma, narrow no-break space, etc.) varies, so
    // assert the digit triplets are present with any single-character
    // separator between them rather than pinning the glyph.
    const text = getByTestId("inspector-context-last-tokens").textContent ?? "";
    expect(text).toMatch(/175.?500/);
  });

  it("renders the not-seen-yet placeholder when last_context_tokens is null", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId } = render(InspectorContext, {
      props: { session: fakeSession({ last_context_tokens: null }) },
    });
    expect(getByTestId("inspector-context-last-tokens")).toHaveTextContent(
      INSPECTOR_STRINGS.contextLastContextNotSeen,
    );
  });

  it("renders the context-window max with the same formatter", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    const { getByTestId, rerender } = render(InspectorContext, {
      props: { session: fakeSession({ last_context_max: 200000 }) },
    });
    const text = getByTestId("inspector-context-last-max").textContent ?? "";
    expect(text).toMatch(/200.?000/);

    rerender({ session: fakeSession({ last_context_max: null }) });
    expect(getByTestId("inspector-context-last-max")).toHaveTextContent(
      INSPECTOR_STRINGS.contextLastContextNotSeen,
    );
  });
});

describe("InspectorContext — assembled context section", () => {
  it("shows loading copy while the system-prompt fetch is in-flight", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    render(InspectorContext, { props: { session: fakeSession() } });
    expect(screen.getByTestId("inspector-context-assembled-loading")).toHaveTextContent(
      INSPECTOR_STRINGS.contextAssembledLoading,
    );
  });

  it("shows error copy when the fetch rejects", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockRejectedValue(new Error("500"));
    render(InspectorContext, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("inspector-context-assembled-error")).toHaveTextContent(
        INSPECTOR_STRINGS.contextAssembledError,
      );
    });
  });

  it("renders assembled layers with token counts on success", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "baseline", body: "base", token_count: 10, source_path: null },
        { kind: "session_instructions", body: "steer", token_count: 5, source_path: null },
      ]),
    );
    render(InspectorContext, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("inspector-context-assembled-layers")).toBeInTheDocument();
    });
    expect(screen.getByTestId("inspector-context-assembled-baseline")).toHaveTextContent(
      INSPECTOR_STRINGS.instructionsLayerTokensLabel(10),
    );
    expect(
      screen.getByTestId("inspector-context-assembled-session_instructions"),
    ).toHaveTextContent(INSPECTOR_STRINGS.instructionsLayerTokensLabel(5));
  });

  it("renders the total token count row", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "baseline", body: "b", token_count: 20, source_path: null },
        { kind: "tag_memory", body: "m", token_count: 8, source_path: null },
      ]),
    );
    render(InspectorContext, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("inspector-context-assembled-total")).toHaveTextContent(
        INSPECTOR_STRINGS.instructionsLayerTokensLabel(28),
      );
    });
  });

  it("renders source_path for tag_claude_md layers", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        {
          kind: "tag_claude_md",
          body: "tag content",
          token_count: 3,
          source_path: "/home/user/.claude/tags/bearings/CLAUDE.md",
        },
      ]),
    );
    render(InspectorContext, { props: { session: fakeSession() } });
    await waitFor(() => {
      const dd = screen.getByTestId("inspector-context-assembled-tag_claude_md");
      expect(dd.textContent).toContain("/home/user/.claude/tags/bearings/CLAUDE.md");
    });
  });

  it("renders the assembled heading", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(fakeLayersOut([]));
    render(InspectorContext, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.queryByTestId("inspector-context-assembled-loading")).toBeNull();
    });
    expect(screen.getByText(INSPECTOR_STRINGS.contextAssembledHeading)).toBeInTheDocument();
  });
});
