/**
 * Per-target action-list tests for the context-menu registry. These
 * checks pin the spec contract: the action ids inside each per-target
 * array match ``docs/behavior/context-menus.md`` §"Per-target action
 * lists" verbatim, and every action id has a matching label entry in
 * :data:`CONTEXT_MENU_STRINGS.actionLabels`.
 *
 * Phase 14 / 15 / 16 surfaces have dedicated coverage in
 * :file:`phases.test.ts`.
 */
import { describe, expect, it } from "vitest";

import {
  CONTEXT_MENU_STRINGS,
  KNOWN_MENU_TARGETS,
  MENU_ACTION_MESSAGE_DELETE,
  MENU_ACTION_MULTI_SELECT_DELETE,
  MENU_ACTION_MULTI_SELECT_TAG,
  MENU_ACTION_MULTI_SELECT_UNTAG,
  MENU_ACTION_SESSION_COPY_ID,
  MENU_ACTION_SESSION_COPY_TITLE,
  MENU_ACTION_SESSION_DELETE,
  MENU_ACTION_SESSION_RENAME,
  MENU_ACTION_TAG_DELETE,
  MENU_SECTION_DESTRUCTIVE,
  MENU_SECTION_ORGANIZE,
  MENU_TARGET_MESSAGE,
  MENU_TARGET_MULTI_SELECT,
  MENU_TARGET_SESSION,
  MENU_TARGET_TAG,
} from "../../config";
import { actionsForTarget, MENU_ACTIONS_BY_TARGET } from "../registry";

describe("MENU_ACTIONS_BY_TARGET", () => {
  it("has an entry for every target in the alphabet", () => {
    for (const target of KNOWN_MENU_TARGETS) {
      expect(MENU_ACTIONS_BY_TARGET[target], target).toBeDefined();
      expect(actionsForTarget(target).length).toBeGreaterThan(0);
    }
  });

  it("every action id has a matching label entry", () => {
    const labels = CONTEXT_MENU_STRINGS.actionLabels as Record<string, string>;
    for (const target of KNOWN_MENU_TARGETS) {
      for (const action of actionsForTarget(target)) {
        expect(labels[action.id], action.id).toBeDefined();
      }
    }
  });
});

describe("session target", () => {
  it("contains the rename + copy + delete actions per the doc", () => {
    const ids = actionsForTarget(MENU_TARGET_SESSION).map((a) => a.id);
    expect(ids).toContain(MENU_ACTION_SESSION_RENAME);
    expect(ids).toContain(MENU_ACTION_SESSION_COPY_TITLE);
    expect(ids).toContain(MENU_ACTION_SESSION_DELETE);
  });

  it("marks Copy session ID as advanced (Shift-revealed)", () => {
    const action = actionsForTarget(MENU_TARGET_SESSION).find(
      (a) => a.id === MENU_ACTION_SESSION_COPY_ID,
    );
    expect(action?.advanced).toBe(true);
  });

  it("marks Delete session as destructive", () => {
    const action = actionsForTarget(MENU_TARGET_SESSION).find(
      (a) => a.id === MENU_ACTION_SESSION_DELETE,
    );
    expect(action?.section).toBe(MENU_SECTION_DESTRUCTIVE);
    expect(action?.destructive).toBe(true);
  });
});

describe("message target", () => {
  it("marks Delete message as both advanced and destructive", () => {
    const action = actionsForTarget(MENU_TARGET_MESSAGE).find(
      (a) => a.id === MENU_ACTION_MESSAGE_DELETE,
    );
    expect(action?.advanced).toBe(true);
    expect(action?.destructive).toBe(true);
  });
});

describe("tag target", () => {
  it("marks Delete tag as advanced + destructive", () => {
    const action = actionsForTarget(MENU_TARGET_TAG).find((a) => a.id === MENU_ACTION_TAG_DELETE);
    expect(action?.advanced).toBe(true);
    expect(action?.destructive).toBe(true);
  });
});

describe("multi_select target", () => {
  it("Add tag and Remove tag have submenu markers", () => {
    const list = actionsForTarget(MENU_TARGET_MULTI_SELECT);
    expect(list.find((a) => a.id === MENU_ACTION_MULTI_SELECT_TAG)?.submenu).toBe(true);
    expect(list.find((a) => a.id === MENU_ACTION_MULTI_SELECT_UNTAG)?.submenu).toBe(true);
  });

  it("Untag is hidden behind Shift-reveal (advanced)", () => {
    const action = actionsForTarget(MENU_TARGET_MULTI_SELECT).find(
      (a) => a.id === MENU_ACTION_MULTI_SELECT_UNTAG,
    );
    expect(action?.advanced).toBe(true);
  });

  it("Add tag lives in the organize section", () => {
    const action = actionsForTarget(MENU_TARGET_MULTI_SELECT).find(
      (a) => a.id === MENU_ACTION_MULTI_SELECT_TAG,
    );
    expect(action?.section).toBe(MENU_SECTION_ORGANIZE);
  });

  it("Delete sessions is destructive", () => {
    const action = actionsForTarget(MENU_TARGET_MULTI_SELECT).find(
      (a) => a.id === MENU_ACTION_MULTI_SELECT_DELETE,
    );
    expect(action?.destructive).toBe(true);
  });
});
