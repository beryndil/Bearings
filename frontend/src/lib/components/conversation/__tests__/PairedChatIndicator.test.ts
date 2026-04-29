/**
 * Component tests for ``PairedChatIndicator`` — placement (rendered),
 * deleted state ("(checklist deleted)"), click dispatch on each
 * segment.
 */
import { fireEvent, render } from "@testing-library/svelte";
import { describe, expect, it, vi } from "vitest";

import PairedChatIndicator from "../PairedChatIndicator.svelte";

describe("PairedChatIndicator", () => {
  it("renders the parent title and item label as two segments", () => {
    const { getByTestId } = render(PairedChatIndicator, {
      props: { parentTitle: "v1 rebuild", itemLabel: "Item 2.3" },
    });
    expect(getByTestId("paired-chat-parent")).toHaveTextContent("v1 rebuild");
    expect(getByTestId("paired-chat-item")).toHaveTextContent("Item 2.3");
  });

  it("dispatches onSelectParent when the parent segment is clicked", async () => {
    const onSelectParent = vi.fn();
    const { getByTestId } = render(PairedChatIndicator, {
      props: { parentTitle: "Checklist", itemLabel: "Leaf", onSelectParent },
    });
    await fireEvent.click(getByTestId("paired-chat-parent"));
    expect(onSelectParent).toHaveBeenCalledTimes(1);
  });

  it("dispatches onScrollToItem when the item segment is clicked", async () => {
    const onScrollToItem = vi.fn();
    const { getByTestId } = render(PairedChatIndicator, {
      props: { parentTitle: "Checklist", itemLabel: "Leaf", onScrollToItem },
    });
    await fireEvent.click(getByTestId("paired-chat-item"));
    expect(onScrollToItem).toHaveBeenCalledTimes(1);
  });

  it("renders the deleted state when both inputs are null", () => {
    const { getByTestId, queryByTestId } = render(PairedChatIndicator, {
      props: { parentTitle: null, itemLabel: null },
    });
    expect(getByTestId("paired-chat-deleted")).toHaveTextContent("(checklist deleted)");
    expect(queryByTestId("paired-chat-parent")).toBeNull();
    expect(queryByTestId("paired-chat-item")).toBeNull();
  });
});
