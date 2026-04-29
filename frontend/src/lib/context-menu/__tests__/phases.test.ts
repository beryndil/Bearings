/**
 * Phases 14 / 15 / 16 surfaces — the action ids the per-target lists
 * must expose. The master checklist for item 2.9 explicitly asks for
 * "per-context tests for the phases 14-16 actions
 * (context-menus.md enumerates which actions belong to which target)".
 *
 * Phase 14 — Checkpoint (gutter chip).
 * Phase 15 — Attachment (composer / transcript chip).
 * Phase 16 — Pending operation (row inside the floating card).
 */
import { describe, expect, it } from "vitest";

import {
  MENU_ACTION_ATTACHMENT_COPY_FILENAME,
  MENU_ACTION_ATTACHMENT_COPY_PATH,
  MENU_ACTION_ATTACHMENT_OPEN_IN_EDITOR,
  MENU_ACTION_ATTACHMENT_OPEN_IN_FILE_EXPLORER,
  MENU_ACTION_ATTACHMENT_REMOVE,
  MENU_ACTION_CHECKPOINT_COPY_ID,
  MENU_ACTION_CHECKPOINT_COPY_LABEL,
  MENU_ACTION_CHECKPOINT_DELETE,
  MENU_ACTION_CHECKPOINT_FORK,
  MENU_ACTION_PENDING_OPERATION_COPY_COMMAND,
  MENU_ACTION_PENDING_OPERATION_COPY_NAME,
  MENU_ACTION_PENDING_OPERATION_DISMISS,
  MENU_ACTION_PENDING_OPERATION_OPEN_IN_EDITOR,
  MENU_ACTION_PENDING_OPERATION_RESOLVE,
  MENU_SECTION_COPY,
  MENU_SECTION_DESTRUCTIVE,
  MENU_SECTION_PRIMARY,
  MENU_SECTION_VIEW,
  MENU_TARGET_ATTACHMENT,
  MENU_TARGET_CHECKPOINT,
  MENU_TARGET_PENDING_OPERATION,
} from "../../config";
import { actionsForTarget } from "../registry";

describe("Phase 14 — Checkpoint", () => {
  const list = actionsForTarget(MENU_TARGET_CHECKPOINT);

  it("exposes Fork from here as the primary action", () => {
    const action = list.find((a) => a.id === MENU_ACTION_CHECKPOINT_FORK);
    expect(action?.section).toBe(MENU_SECTION_PRIMARY);
  });

  it("Copy label is in the copy section", () => {
    const action = list.find((a) => a.id === MENU_ACTION_CHECKPOINT_COPY_LABEL);
    expect(action?.section).toBe(MENU_SECTION_COPY);
  });

  it("Copy checkpoint ID is advanced", () => {
    const action = list.find((a) => a.id === MENU_ACTION_CHECKPOINT_COPY_ID);
    expect(action?.advanced).toBe(true);
  });

  it("Delete checkpoint is destructive", () => {
    const action = list.find((a) => a.id === MENU_ACTION_CHECKPOINT_DELETE);
    expect(action?.destructive).toBe(true);
    expect(action?.section).toBe(MENU_SECTION_DESTRUCTIVE);
  });

  it("contains exactly the four phase-14 actions", () => {
    expect(list.map((a) => a.id).sort()).toEqual(
      [
        MENU_ACTION_CHECKPOINT_FORK,
        MENU_ACTION_CHECKPOINT_COPY_LABEL,
        MENU_ACTION_CHECKPOINT_COPY_ID,
        MENU_ACTION_CHECKPOINT_DELETE,
      ].sort(),
    );
  });
});

describe("Phase 15 — Attachment", () => {
  const list = actionsForTarget(MENU_TARGET_ATTACHMENT);

  it("exposes copy path / copy filename in the copy section", () => {
    expect(list.find((a) => a.id === MENU_ACTION_ATTACHMENT_COPY_PATH)?.section).toBe(
      MENU_SECTION_COPY,
    );
    expect(list.find((a) => a.id === MENU_ACTION_ATTACHMENT_COPY_FILENAME)?.section).toBe(
      MENU_SECTION_COPY,
    );
  });

  it("Open in editor is in the view section", () => {
    expect(list.find((a) => a.id === MENU_ACTION_ATTACHMENT_OPEN_IN_EDITOR)?.section).toBe(
      MENU_SECTION_VIEW,
    );
  });

  it("Reveal in file explorer is advanced", () => {
    expect(list.find((a) => a.id === MENU_ACTION_ATTACHMENT_OPEN_IN_FILE_EXPLORER)?.advanced).toBe(
      true,
    );
  });

  it("Remove from message is destructive", () => {
    const action = list.find((a) => a.id === MENU_ACTION_ATTACHMENT_REMOVE);
    expect(action?.destructive).toBe(true);
    expect(action?.section).toBe(MENU_SECTION_DESTRUCTIVE);
  });

  it("contains exactly the five phase-15 actions", () => {
    expect(list.map((a) => a.id).sort()).toEqual(
      [
        MENU_ACTION_ATTACHMENT_COPY_PATH,
        MENU_ACTION_ATTACHMENT_COPY_FILENAME,
        MENU_ACTION_ATTACHMENT_OPEN_IN_EDITOR,
        MENU_ACTION_ATTACHMENT_OPEN_IN_FILE_EXPLORER,
        MENU_ACTION_ATTACHMENT_REMOVE,
      ].sort(),
    );
  });
});

describe("Phase 16 — Pending operation", () => {
  const list = actionsForTarget(MENU_TARGET_PENDING_OPERATION);

  it("Mark resolved is the primary action", () => {
    expect(list.find((a) => a.id === MENU_ACTION_PENDING_OPERATION_RESOLVE)?.section).toBe(
      MENU_SECTION_PRIMARY,
    );
  });

  it("Dismiss is destructive", () => {
    const action = list.find((a) => a.id === MENU_ACTION_PENDING_OPERATION_DISMISS);
    expect(action?.destructive).toBe(true);
    expect(action?.section).toBe(MENU_SECTION_DESTRUCTIVE);
  });

  it("Copy command is advanced", () => {
    expect(list.find((a) => a.id === MENU_ACTION_PENDING_OPERATION_COPY_COMMAND)?.advanced).toBe(
      true,
    );
  });

  it("Open directory in editor is advanced + view", () => {
    const action = list.find((a) => a.id === MENU_ACTION_PENDING_OPERATION_OPEN_IN_EDITOR);
    expect(action?.advanced).toBe(true);
    expect(action?.section).toBe(MENU_SECTION_VIEW);
  });

  it("contains exactly the five phase-16 actions", () => {
    expect(list.map((a) => a.id).sort()).toEqual(
      [
        MENU_ACTION_PENDING_OPERATION_RESOLVE,
        MENU_ACTION_PENDING_OPERATION_DISMISS,
        MENU_ACTION_PENDING_OPERATION_COPY_NAME,
        MENU_ACTION_PENDING_OPERATION_COPY_COMMAND,
        MENU_ACTION_PENDING_OPERATION_OPEN_IN_EDITOR,
      ].sort(),
    );
  });
});
