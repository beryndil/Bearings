/**
 * InspectorInstructions tests — layer-breakdown render, empty-state per
 * section, and click-to-open editor/viewer modals.
 *
 * The component fetches ``GET /api/sessions/{id}/system_prompt`` on
 * mount; the tests mock ``getSessionSystemPrompt`` to avoid real network
 * calls.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InspectorInstructions from "../InspectorInstructions.svelte";
import { INSPECTOR_STRINGS } from "../../../config";
import type { SessionOut, SystemPromptLayersOut } from "../../../api/sessions";
import * as sessionsApi from "../../../api/sessions";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fakeSession(overrides: Partial<SessionOut> = {}): SessionOut {
  return {
    id: "ses_a",
    kind: "chat",
    title: "Fixture",
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

function fakeLayersOut(layers: SystemPromptLayersOut["layers"]): SystemPromptLayersOut {
  return {
    layers,
    total_tokens: layers.reduce((s, l) => s + l.token_count, 0),
    token_count_approximate: true,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Loading / error states
// ---------------------------------------------------------------------------

describe("loading state", () => {
  it("shows loading copy while fetch is in-flight", () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockReturnValue(new Promise(() => {}));
    render(InspectorInstructions, { props: { session: fakeSession() } });
    expect(screen.getByTestId("inspector-instructions-loading")).toHaveTextContent(
      INSPECTOR_STRINGS.instructionsLoadingLayers,
    );
  });

  it("shows error copy when fetch rejects", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockRejectedValue(new Error("500"));
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("inspector-instructions-error")).toHaveTextContent(
        INSPECTOR_STRINGS.instructionsLayersError,
      );
    });
  });
});

// ---------------------------------------------------------------------------
// Layer rows render in correct order
// ---------------------------------------------------------------------------

describe("layer rows render in correct order", () => {
  it("renders all five layer sections in display order", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "session_instructions", body: "steer", token_count: 1, source_path: null },
        { kind: "baseline", body: "base", token_count: 1, source_path: null },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-section-session_instructions")).toBeInTheDocument();
    });

    const order = [
      "session_instructions",
      "baseline",
      "project_claude_md",
      "tag_memory",
      "template_baseline",
    ];
    const sections = order.map((k) => screen.getByTestId(`instructions-section-${k}`));
    for (let i = 0; i < sections.length - 1; i++) {
      expect(
        sections[i].compareDocumentPosition(sections[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("renders a clickable layer card for a present layer", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        {
          kind: "baseline",
          body: "some baseline body",
          token_count: 4,
          source_path: null,
        },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-layer-baseline-0")).toBeInTheDocument();
    });
  });

  it("renders source_path for project_claude_md layers", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        {
          kind: "project_claude_md",
          body: "project content",
          token_count: 3,
          source_path: "/home/user/project/CLAUDE.md",
        },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      const card = screen.getByTestId("instructions-layer-project_claude_md-0");
      expect(card.textContent).toContain("/home/user/project/CLAUDE.md");
    });
  });

  it("renders token count on each layer card", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "baseline", body: "x".repeat(40), token_count: 10, source_path: null },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      const card = screen.getByTestId("instructions-layer-baseline-0");
      expect(card.textContent).toContain(INSPECTOR_STRINGS.instructionsLayerTokensLabel(10));
    });
  });
});

// ---------------------------------------------------------------------------
// Empty-state copy on missing layers
// ---------------------------------------------------------------------------

describe("empty-state copy on missing layers", () => {
  it("renders empty-state for session_instructions when absent", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([{ kind: "baseline", body: "base", token_count: 1, source_path: null }]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-empty-session_instructions")).toHaveTextContent(
        INSPECTOR_STRINGS.instructionsLayerEmptyState.session_instructions,
      );
    });
  });

  it("renders empty-state for project_claude_md when absent", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([{ kind: "baseline", body: "base", token_count: 1, source_path: null }]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-empty-project_claude_md")).toHaveTextContent(
        INSPECTOR_STRINGS.instructionsLayerEmptyState.project_claude_md,
      );
    });
  });

  it("renders empty-state for tag_memory when absent", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([{ kind: "baseline", body: "base", token_count: 1, source_path: null }]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-empty-tag_memory")).toHaveTextContent(
        INSPECTOR_STRINGS.instructionsLayerEmptyState.tag_memory,
      );
    });
  });

  it("does not render an empty-state row when layer has content", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([{ kind: "baseline", body: "base", token_count: 1, source_path: null }]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.queryByTestId("instructions-empty-baseline")).toBeNull();
      expect(screen.getByTestId("instructions-layer-baseline-0")).toBeInTheDocument();
    });
  });

  it("session_instructions empty state is a clickable button", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(fakeLayersOut([]));
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      const emptyBtn = screen.getByTestId("instructions-empty-session_instructions");
      expect(emptyBtn.tagName.toLowerCase()).toBe("button");
    });
  });
});

// ---------------------------------------------------------------------------
// Click-to-open modal behavior
// ---------------------------------------------------------------------------

describe("click-to-open modal behavior", () => {
  it("renders the heading from the string table", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(fakeLayersOut([]));
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.queryByTestId("inspector-instructions-loading")).toBeNull();
    });
    expect(screen.getByText(INSPECTOR_STRINGS.instructionsHeading)).toBeInTheDocument();
  });

  it("clicking a session_instructions layer card opens the session instructions editor", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "session_instructions", body: "do xyz", token_count: 2, source_path: null },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-layer-session_instructions-0")).toBeInTheDocument();
    });
    await fireEvent.click(screen.getByTestId("instructions-layer-session_instructions-0"));
    expect(screen.getByTestId("session-instr-edit-modal")).toBeInTheDocument();
  });

  it("clicking a source_path layer card opens the CLAUDE.md file editor", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        {
          kind: "project_claude_md",
          body: "project md content",
          token_count: 4,
          source_path: "/home/user/project/CLAUDE.md",
        },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-layer-project_claude_md-0")).toBeInTheDocument();
    });
    await fireEvent.click(screen.getByTestId("instructions-layer-project_claude_md-0"));
    expect(screen.getByTestId("claudemd-edit-modal")).toBeInTheDocument();
  });

  it("clicking a baseline layer card opens the read-only layer viewer", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        { kind: "baseline", body: "baseline body text", token_count: 3, source_path: null },
      ]),
    );
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-layer-baseline-0")).toBeInTheDocument();
    });
    await fireEvent.click(screen.getByTestId("instructions-layer-baseline-0"));
    expect(screen.getByTestId("layer-view-modal")).toBeInTheDocument();
  });

  it("clicking the session_instructions empty-state button opens the editor", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(fakeLayersOut([]));
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.queryByTestId("inspector-instructions-loading")).toBeNull();
    });
    await fireEvent.click(screen.getByTestId("instructions-empty-session_instructions"));
    expect(screen.getByTestId("session-instr-edit-modal")).toBeInTheDocument();
  });

  it("copy-path button does not open the editor", async () => {
    vi.spyOn(sessionsApi, "getSessionSystemPrompt").mockResolvedValue(
      fakeLayersOut([
        {
          kind: "project_claude_md",
          body: "proj",
          token_count: 1,
          source_path: "/p/CLAUDE.md",
        },
      ]),
    );
    // Stub clipboard to avoid jsdom errors.
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    render(InspectorInstructions, { props: { session: fakeSession() } });
    await waitFor(() => {
      expect(screen.getByTestId("instructions-layer-copy-project_claude_md-0")).toBeInTheDocument();
    });
    await fireEvent.click(screen.getByTestId("instructions-layer-copy-project_claude_md-0"));
    // Modal should NOT have opened.
    expect(screen.queryByTestId("claudemd-edit-modal")).toBeNull();
  });
});
