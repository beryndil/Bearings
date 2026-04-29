/**
 * ``use:contextMenu`` Svelte action tests — right-click on the host
 * dispatches into the menu store, Shift held propagates to
 * ``advancedRevealed``, ``disabled: true`` suppresses the dispatch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MENU_ACTION_SESSION_RENAME, MENU_TARGET_SESSION } from "../../config";
import { _resetForTests, contextMenuStore } from "../../context-menu/store.svelte";
import { contextMenu } from "../contextMenu";

beforeEach(() => {
  _resetForTests();
});

afterEach(() => {
  _resetForTests();
});

describe("contextMenu action", () => {
  it("opens the menu on right-click with target + coordinates", () => {
    const node = document.createElement("button");
    document.body.appendChild(node);
    const handlers = { [MENU_ACTION_SESSION_RENAME]: vi.fn() };
    contextMenu(node, { target: MENU_TARGET_SESSION, handlers, data: { sessionId: "ses_a" } });

    const event = new MouseEvent("contextmenu", {
      bubbles: true,
      cancelable: true,
      clientX: 42,
      clientY: 84,
    });
    node.dispatchEvent(event);

    const open = contextMenuStore.open;
    expect(open).not.toBeNull();
    expect(open?.target).toBe(MENU_TARGET_SESSION);
    expect(open?.x).toBe(42);
    expect(open?.y).toBe(84);
    expect(open?.handlers).toStrictEqual(handlers);
    expect(event.defaultPrevented).toBe(true);
  });

  it("Shift-right-click sets advancedRevealed", () => {
    const node = document.createElement("button");
    document.body.appendChild(node);
    contextMenu(node, { target: MENU_TARGET_SESSION, handlers: {} });
    node.dispatchEvent(
      new MouseEvent("contextmenu", { bubbles: true, cancelable: true, shiftKey: true }),
    );
    expect(contextMenuStore.open?.advancedRevealed).toBe(true);
  });

  it("disabled suppresses the dispatch", () => {
    const node = document.createElement("button");
    document.body.appendChild(node);
    contextMenu(node, { target: MENU_TARGET_SESSION, handlers: {}, disabled: true });
    node.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(contextMenuStore.open).toBeNull();
  });

  it("destroy unsubscribes the listener", () => {
    const node = document.createElement("button");
    document.body.appendChild(node);
    const ret = contextMenu(node, { target: MENU_TARGET_SESSION, handlers: {} });
    ret.destroy();
    node.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
    expect(contextMenuStore.open).toBeNull();
  });
});
