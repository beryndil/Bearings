/**
 * Tests for the frontend constants module — locks the public API
 * surface (kind alphabet, slash-namespace separator, splitTagName)
 * against the backend mirrors documented in
 * :mod:`bearings.config.constants`.
 */
import { describe, expect, it } from "vitest";

import {
  API_BASE,
  KNOWN_SESSION_KINDS,
  KNOWN_VAULT_KINDS,
  SESSION_KIND_CHAT,
  SESSION_KIND_CHECKLIST,
  TAG_GROUP_SEPARATOR,
  VAULT_KIND_PLAN,
  VAULT_KIND_TODO,
  splitTagName,
  type SessionKind,
  type VaultKind,
} from "../config";

describe("kind alphabet", () => {
  it("exposes 'chat' and 'checklist' — matches backend KNOWN_SESSION_KINDS", () => {
    expect(SESSION_KIND_CHAT).toBe("chat");
    expect(SESSION_KIND_CHECKLIST).toBe("checklist");
    expect(KNOWN_SESSION_KINDS).toEqual([SESSION_KIND_CHAT, SESSION_KIND_CHECKLIST]);
  });

  it("SessionKind type accepts only the documented strings", () => {
    const ok: SessionKind = SESSION_KIND_CHAT;
    expect(KNOWN_SESSION_KINDS).toContain(ok);
  });
});

describe("API_BASE", () => {
  it("is the literal '/api' — vite proxies this prefix to the FastAPI backend", () => {
    expect(API_BASE).toBe("/api");
  });
});

describe("vault kind alphabet", () => {
  it("exposes 'plan' and 'todo' — matches backend KNOWN_VAULT_KINDS", () => {
    expect(VAULT_KIND_PLAN).toBe("plan");
    expect(VAULT_KIND_TODO).toBe("todo");
    expect(KNOWN_VAULT_KINDS).toEqual([VAULT_KIND_PLAN, VAULT_KIND_TODO]);
  });

  it("VaultKind type accepts only the documented strings", () => {
    const ok: VaultKind = VAULT_KIND_PLAN;
    expect(KNOWN_VAULT_KINDS).toContain(ok);
  });
});

describe("splitTagName", () => {
  it("splits a slash-namespaced tag name", () => {
    expect(splitTagName("bearings/architect")).toEqual(["bearings", "architect"]);
  });

  it("returns null group for a bare name", () => {
    expect(splitTagName("general")).toEqual([null, "general"]);
  });

  it("treats a leading-slash name as ungrouped (matches backend Tag.group)", () => {
    expect(splitTagName("/leading")).toEqual([null, "/leading"]);
  });

  it("uses the documented separator", () => {
    expect(TAG_GROUP_SEPARATOR).toBe("/");
  });
});
