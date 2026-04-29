/**
 * Tests for the Esc cascade — priority-ordered overlay dismissal +
 * lowest-priority input-blur.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ESC_PRIORITY_COMMAND_PALETTE,
  ESC_PRIORITY_CONTEXT_MENU,
  ESC_PRIORITY_OVERLAY,
  ESC_PRIORITY_PENDING_OPS_CARD,
  _resetForTests,
  registerEscEntry,
  runEscCascade,
} from "../escCascade";

beforeEach(() => {
  _resetForTests();
  document.body.innerHTML = "";
});

afterEach(() => {
  _resetForTests();
});

describe("runEscCascade", () => {
  it("returns 'noop' when no overlay is open and no input is focused", () => {
    expect(runEscCascade()).toBe("noop");
  });

  it("dismisses the highest-priority open overlay first", () => {
    const closeMenu = vi.fn();
    const closePalette = vi.fn();
    const closeOverlay = vi.fn();
    registerEscEntry({ priority: ESC_PRIORITY_OVERLAY, isOpen: () => true, close: closeOverlay });
    registerEscEntry({
      priority: ESC_PRIORITY_COMMAND_PALETTE,
      isOpen: () => true,
      close: closePalette,
    });
    registerEscEntry({
      priority: ESC_PRIORITY_CONTEXT_MENU,
      isOpen: () => true,
      close: closeMenu,
    });

    expect(runEscCascade()).toBe(ESC_PRIORITY_CONTEXT_MENU);
    expect(closeMenu).toHaveBeenCalledOnce();
    expect(closePalette).not.toHaveBeenCalled();
    expect(closeOverlay).not.toHaveBeenCalled();
  });

  it("falls through to the next priority when the higher overlay is closed", () => {
    const closePalette = vi.fn();
    registerEscEntry({
      priority: ESC_PRIORITY_CONTEXT_MENU,
      isOpen: () => false,
      close: () => {},
    });
    registerEscEntry({
      priority: ESC_PRIORITY_COMMAND_PALETTE,
      isOpen: () => true,
      close: closePalette,
    });
    registerEscEntry({
      priority: ESC_PRIORITY_PENDING_OPS_CARD,
      isOpen: () => true,
      close: () => {},
    });

    expect(runEscCascade()).toBe(ESC_PRIORITY_COMMAND_PALETTE);
    expect(closePalette).toHaveBeenCalledOnce();
  });

  it("blurs a focused input when no overlays are open", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    expect(document.activeElement).toBe(input);

    expect(runEscCascade()).toBe("blur");
    expect(document.activeElement).not.toBe(input);
  });

  it("respects unregister cleanup", () => {
    const close = vi.fn();
    const unregister = registerEscEntry({
      priority: ESC_PRIORITY_OVERLAY,
      isOpen: () => true,
      close,
    });
    unregister();
    expect(runEscCascade()).toBe("noop");
    expect(close).not.toHaveBeenCalled();
  });
});
