/**
 * Component tests for :class:`ChecklistChat`.
 *
 * - Renders the no-selection empty state when ``chatSessionId`` is null.
 * - Renders the breadcrumb + the embedded Conversation pane when a chat
 *   id is supplied.
 * - Surfaces parsed sentinels from the latest assistant turn.
 *
 * The agent WebSocket and history fetch are stubbed via the
 * Conversation pane's existing mock pattern (``vi.mock`` of
 * ``agent.svelte`` + ``vi.stubGlobal("fetch", ...)``).
 */
import { render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../agent.svelte", () => ({
  connectSession: vi.fn(),
  disconnectSession: vi.fn(),
}));

import ChecklistChat from "../ChecklistChat.svelte";
import { _resetForTests as resetConversation } from "../../../stores/conversation.svelte";
import type { MessageTurnView } from "../../../stores/conversation.svelte";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  resetConversation();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakeAssistantTurn(body: string): MessageTurnView {
  return {
    id: "m_a",
    role: "assistant",
    body,
    thinking: "",
    complete: true,
    toolCalls: [],
    routing: null,
    error: null,
    createdAt: null,
  };
}

describe("ChecklistChat — empty selection", () => {
  it("renders the empty-state copy when chatSessionId is null", () => {
    const { getByTestId } = render(ChecklistChat, { props: { chatSessionId: null } });
    expect(getByTestId("checklist-chat-empty")).toBeInTheDocument();
  });
});

describe("ChecklistChat — paired", () => {
  it("renders the breadcrumb when itemLabel is supplied", () => {
    fetchMock.mockResolvedValue({
      status: 200,
      statusText: "OK",
      json: async () => [],
    });
    const { getByTestId } = render(ChecklistChat, {
      props: { chatSessionId: "ses_a", itemLabel: "ship the feature" },
    });
    expect(getByTestId("checklist-chat-breadcrumb")).toHaveTextContent("ship the feature");
  });

  it("renders the embedded Conversation pane (testid bubbles up from child)", () => {
    fetchMock.mockResolvedValue({
      status: 200,
      statusText: "OK",
      json: async () => [],
    });
    const { getByTestId } = render(ChecklistChat, {
      props: { chatSessionId: "ses_a" },
    });
    // The Conversation component carries a ``conversation`` testid;
    // we only assert it renders (its internal hydration is covered by
    // its own test suite).
    expect(getByTestId("conversation")).toBeInTheDocument();
  });
});

describe("ChecklistChat — sentinel summary", () => {
  it("renders the empty-sentinel copy when the latest assistant turn has none", () => {
    fetchMock.mockResolvedValue({ status: 200, statusText: "OK", json: async () => [] });
    const stubConversation = {
      sessionId: "ses_a",
      turns: [fakeAssistantTurn("plain body, no sentinel here")],
      lastSeq: 0,
      loading: false,
      error: null,
    };
    const { getByTestId } = render(ChecklistChat, {
      props: {
        chatSessionId: "ses_a",
        conversationStore: stubConversation,
      },
    });
    expect(getByTestId("checklist-chat-sentinels-empty")).toBeInTheDocument();
  });

  it("renders one chip per parsed sentinel kind in the latest assistant turn", () => {
    fetchMock.mockResolvedValue({ status: 200, statusText: "OK", json: async () => [] });
    const stubConversation = {
      sessionId: "ses_a",
      turns: [
        fakeAssistantTurn(
          'before <bearings:sentinel kind="followup_blocking"><label>x</label></bearings:sentinel>' +
            '<bearings:sentinel kind="item_done" /> done.',
        ),
      ],
      lastSeq: 0,
      loading: false,
      error: null,
    };
    const { getAllByTestId } = render(ChecklistChat, {
      props: {
        chatSessionId: "ses_a",
        conversationStore: stubConversation,
      },
    });
    const chips = getAllByTestId("checklist-chat-sentinel-chip");
    expect(chips).toHaveLength(2);
    expect(chips.map((c) => c.dataset.sentinelKind)).toEqual(["followup_blocking", "item_done"]);
  });
});
