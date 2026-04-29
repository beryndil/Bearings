/**
 * Inspector store tests — pin the boot defaults, the imperative API,
 * and the unknown-id ignore behaviour.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_INSPECTOR_TAB,
  INSPECTOR_TAB_AGENT,
  INSPECTOR_TAB_CONTEXT,
  INSPECTOR_TAB_INSTRUCTIONS,
  type InspectorTabId,
} from "../../config";
import {
  _resetForTests,
  inspectorStore,
  setActiveSession,
  setInspectorTab,
} from "../inspector.svelte";

beforeEach(() => {
  _resetForTests();
});

describe("inspectorStore — boot defaults", () => {
  it("starts on the documented default tab", () => {
    expect(inspectorStore.activeTabId).toBe(DEFAULT_INSPECTOR_TAB);
    // Pin the default's identity so a future ``DEFAULT_INSPECTOR_TAB``
    // re-aliasing is caught here rather than as a UI regression.
    expect(DEFAULT_INSPECTOR_TAB).toBe(INSPECTOR_TAB_AGENT);
  });

  it("starts with no active session", () => {
    expect(inspectorStore.activeSessionId).toBeNull();
  });
});

describe("setInspectorTab", () => {
  it("switches the active tab to a known id", () => {
    setInspectorTab(INSPECTOR_TAB_CONTEXT);
    expect(inspectorStore.activeTabId).toBe(INSPECTOR_TAB_CONTEXT);
    setInspectorTab(INSPECTOR_TAB_INSTRUCTIONS);
    expect(inspectorStore.activeTabId).toBe(INSPECTOR_TAB_INSTRUCTIONS);
  });

  it("ignores ids outside the documented alphabet", () => {
    setInspectorTab(INSPECTOR_TAB_CONTEXT);
    // Cast through ``unknown`` rather than ``any`` — the cast is the
    // explicit defense-in-depth check for a stale persisted id.
    setInspectorTab("not-a-tab" as unknown as InspectorTabId);
    expect(inspectorStore.activeTabId).toBe(INSPECTOR_TAB_CONTEXT);
  });
});

describe("setActiveSession", () => {
  it("records the supplied session id", () => {
    setActiveSession("ses_a");
    expect(inspectorStore.activeSessionId).toBe("ses_a");
  });

  it("clears the active session when called with null", () => {
    setActiveSession("ses_a");
    setActiveSession(null);
    expect(inspectorStore.activeSessionId).toBeNull();
  });
});

describe("_resetForTests", () => {
  it("restores both fields to their boot defaults", () => {
    setInspectorTab(INSPECTOR_TAB_INSTRUCTIONS);
    setActiveSession("ses_a");
    _resetForTests();
    expect(inspectorStore.activeTabId).toBe(DEFAULT_INSPECTOR_TAB);
    expect(inspectorStore.activeSessionId).toBeNull();
  });
});
