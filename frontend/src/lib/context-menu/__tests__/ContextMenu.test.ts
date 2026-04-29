/**
 * ContextMenu component tests — open / close, action invocation,
 * advanced reveal, keyboard nav, stale target.
 */
import { fireEvent, render } from "@testing-library/svelte";
import { flushSync } from "svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CONTEXT_MENU_STRINGS,
  MENU_ACTION_CHECKPOINT_COPY_ID,
  MENU_ACTION_CHECKPOINT_COPY_LABEL,
  MENU_ACTION_CHECKPOINT_DELETE,
  MENU_ACTION_CHECKPOINT_FORK,
  MENU_TARGET_CHECKPOINT,
} from "../../config";
import { _resetForTests as resetEsc } from "../../keyboard/escCascade";
import ContextMenu from "../ContextMenu.svelte";
import { _resetForTests, closeMenu, contextMenuStore, openMenu } from "../store.svelte";

function openCheckpointMenu(
  opts: {
    handlers?: Record<string, () => void>;
    advanced?: boolean;
    stale?: boolean;
  } = {},
): void {
  flushSync(() => {
    openMenu({
      target: MENU_TARGET_CHECKPOINT,
      x: 100,
      y: 200,
      handlers: opts.handlers ?? {},
      advancedRevealed: opts.advanced ?? false,
      stale: opts.stale ?? false,
      data: { checkpointId: 7 },
    });
  });
}

beforeEach(() => {
  _resetForTests();
  resetEsc();
});

afterEach(() => {
  _resetForTests();
  resetEsc();
});

describe("ContextMenu", () => {
  it("renders nothing when no menu is open", () => {
    const { queryByTestId } = render(ContextMenu);
    expect(queryByTestId("context-menu")).toBeNull();
  });

  it("renders the menu at the recorded coordinates and target", () => {
    const { getByTestId } = render(ContextMenu);
    openCheckpointMenu();
    const menu = getByTestId("context-menu");
    expect(menu).toHaveAttribute("data-target", MENU_TARGET_CHECKPOINT);
    expect((menu as HTMLElement).style.left).toBe("100px");
    expect((menu as HTMLElement).style.top).toBe("200px");
  });

  it("hides advanced rows by default", () => {
    const { queryByTestId, getAllByTestId } = render(ContextMenu);
    openCheckpointMenu();
    const ids = getAllByTestId("context-menu-row").map((el) => el.getAttribute("data-action"));
    expect(ids).toContain(MENU_ACTION_CHECKPOINT_FORK);
    expect(ids).toContain(MENU_ACTION_CHECKPOINT_COPY_LABEL);
    expect(ids).not.toContain(MENU_ACTION_CHECKPOINT_COPY_ID); // advanced
    expect(queryByTestId("context-menu-advanced-caption")).toBeNull();
  });

  it("reveals advanced rows + caption when Shift was held", () => {
    const { getByTestId, getAllByTestId } = render(ContextMenu);
    openCheckpointMenu({ advanced: true });
    const ids = getAllByTestId("context-menu-row").map((el) => el.getAttribute("data-action"));
    expect(ids).toContain(MENU_ACTION_CHECKPOINT_COPY_ID);
    expect(getByTestId("context-menu-advanced-caption")).toHaveTextContent(
      CONTEXT_MENU_STRINGS.advancedRevealedCaption,
    );
  });

  it("clicking an enabled row fires the matching handler and closes", async () => {
    const fork = vi.fn();
    const { getAllByTestId, queryByTestId } = render(ContextMenu);
    openCheckpointMenu({ handlers: { [MENU_ACTION_CHECKPOINT_FORK]: fork } });
    const row = getAllByTestId("context-menu-row").find(
      (el) => el.getAttribute("data-action") === MENU_ACTION_CHECKPOINT_FORK,
    );
    expect(row).toBeDefined();
    await fireEvent.click(row as HTMLElement);
    expect(fork).toHaveBeenCalledOnce();
    expect(queryByTestId("context-menu")).toBeNull();
  });

  it("rows without a registered handler render disabled", () => {
    const { getAllByTestId } = render(ContextMenu);
    openCheckpointMenu({ handlers: {} });
    const rows = getAllByTestId("context-menu-row");
    for (const row of rows) {
      expect(row).toHaveAttribute("aria-disabled", "true");
    }
  });

  it("backdrop click closes the menu", async () => {
    const { getByTestId, queryByTestId } = render(ContextMenu);
    openCheckpointMenu();
    await fireEvent.click(getByTestId("context-menu-backdrop"));
    expect(queryByTestId("context-menu")).toBeNull();
  });

  it("stale target greys every action and shows the explanation", () => {
    const handlers = {
      [MENU_ACTION_CHECKPOINT_FORK]: vi.fn(),
      [MENU_ACTION_CHECKPOINT_DELETE]: vi.fn(),
    };
    const { getByTestId, getAllByTestId } = render(ContextMenu);
    openCheckpointMenu({ handlers, stale: true });
    expect(getByTestId("context-menu-stale-caption")).toHaveTextContent(
      CONTEXT_MENU_STRINGS.staleTargetMessage,
    );
    const rows = getAllByTestId("context-menu-row");
    for (const row of rows) {
      expect(row).toHaveAttribute("aria-disabled", "true");
    }
  });

  it("ArrowDown / Enter activates the highlighted row via keyboard", async () => {
    const fork = vi.fn();
    render(ContextMenu);
    openCheckpointMenu({ handlers: { [MENU_ACTION_CHECKPOINT_FORK]: fork } });

    // Highlight defaults to index 0 — Fork. Pressing Enter activates it.
    await fireEvent.keyDown(window, { key: "Enter" });
    expect(fork).toHaveBeenCalledOnce();
  });

  it("destructive action label has the destructive marker", () => {
    const { getAllByTestId } = render(ContextMenu);
    openCheckpointMenu({ handlers: { [MENU_ACTION_CHECKPOINT_DELETE]: vi.fn() } });
    const deleteRow = getAllByTestId("context-menu-row").find(
      (el) => el.getAttribute("data-action") === MENU_ACTION_CHECKPOINT_DELETE,
    );
    expect(deleteRow).toHaveAttribute("data-destructive", "true");
  });

  it("openMenu replaces an already-open menu (single-menu invariant)", () => {
    render(ContextMenu);
    openCheckpointMenu();
    openMenu({
      target: MENU_TARGET_CHECKPOINT,
      x: 50,
      y: 60,
      handlers: {},
      advancedRevealed: false,
      stale: false,
      data: null,
    });
    expect(contextMenuStore.open?.x).toBe(50);
    closeMenu();
  });
});
