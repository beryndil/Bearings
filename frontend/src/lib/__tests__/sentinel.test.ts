/**
 * Tests for :func:`parseSentinels` — covers the six observable
 * sentinel kinds, malformed-input rejection, and the terminal-kind
 * picker. Mirrors :mod:`bearings.agent.sentinel`'s pytest coverage so
 * the two parsers stay in lockstep.
 */
import { describe, expect, it } from "vitest";

import { firstTerminalSentinel, parseSentinels } from "../sentinel";
import {
  ITEM_OUTCOME_BLOCKED,
  ITEM_OUTCOME_FAILED,
  SENTINEL_KIND_FOLLOWUP_BLOCKING,
  SENTINEL_KIND_HANDOFF,
  SENTINEL_KIND_ITEM_BLOCKED,
  SENTINEL_KIND_ITEM_DONE,
  SENTINEL_KIND_ITEM_FAILED,
} from "../config";

describe("parseSentinels — well-formed inputs", () => {
  it("returns an empty list on an empty body", () => {
    expect(parseSentinels("")).toEqual([]);
  });

  it("parses the self-closing item_done form", () => {
    const findings = parseSentinels('I am done.\n<bearings:sentinel kind="item_done" />');
    expect(findings).toHaveLength(1);
    expect(findings[0].kind).toBe(SENTINEL_KIND_ITEM_DONE);
  });

  it("parses a handoff with a multi-line plug", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="handoff"><plug>line one\nline two</plug></bearings:sentinel>',
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].kind).toBe(SENTINEL_KIND_HANDOFF);
    expect(findings[0].plug).toBe("line one\nline two");
  });

  it("parses a followup_blocking with a label", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="followup_blocking"><label>add tests</label></bearings:sentinel>',
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].kind).toBe(SENTINEL_KIND_FOLLOWUP_BLOCKING);
    expect(findings[0].label).toBe("add tests");
  });

  it("parses item_blocked with category + text", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="item_blocked">' +
        "<category>blocked</category><text>need credentials</text>" +
        "</bearings:sentinel>",
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].kind).toBe(SENTINEL_KIND_ITEM_BLOCKED);
    expect(findings[0].category).toBe(ITEM_OUTCOME_BLOCKED);
    expect(findings[0].reason).toBe("need credentials");
  });

  it("parses item_failed with reason", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="item_failed"><reason>tests broke</reason></bearings:sentinel>',
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].kind).toBe(SENTINEL_KIND_ITEM_FAILED);
    expect(findings[0].reason).toBe("tests broke");
  });

  it("returns multiple findings in document order", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="followup_nonblocking"><label>A</label></bearings:sentinel>' +
        '<bearings:sentinel kind="item_done" />',
    );
    expect(findings.map((f) => f.kind)).toEqual(["followup_nonblocking", "item_done"]);
  });
});

describe("parseSentinels — malformed inputs", () => {
  it("ignores an unknown kind attribute", () => {
    expect(parseSentinels('<bearings:sentinel kind="unknown_kind" />')).toEqual([]);
  });

  it("ignores a self-closing form for a kind that requires a payload", () => {
    // ``handoff`` is open/close only; the self-closing form is dropped.
    expect(parseSentinels('<bearings:sentinel kind="handoff" />')).toEqual([]);
  });

  it("ignores a followup with no label", () => {
    expect(
      parseSentinels('<bearings:sentinel kind="followup_blocking"></bearings:sentinel>'),
    ).toEqual([]);
  });

  it("ignores a half-emitted block (no closing tag)", () => {
    expect(parseSentinels('<bearings:sentinel kind="item_done"')).toEqual([]);
  });

  it("ignores an item_blocked with an unknown category", () => {
    expect(
      parseSentinels(
        '<bearings:sentinel kind="item_blocked"><category>bogus</category></bearings:sentinel>',
      ),
    ).toEqual([]);
  });
});

describe("firstTerminalSentinel", () => {
  it("returns null when there are no terminal kinds", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="followup_nonblocking"><label>x</label></bearings:sentinel>',
    );
    expect(firstTerminalSentinel(findings)).toBeNull();
  });

  it("returns the first terminal kind even with non-terminal kinds present", () => {
    const findings = parseSentinels(
      '<bearings:sentinel kind="followup_nonblocking"><label>x</label></bearings:sentinel>' +
        '<bearings:sentinel kind="item_failed"><reason>oops</reason></bearings:sentinel>' +
        '<bearings:sentinel kind="item_done" />',
    );
    const terminal = firstTerminalSentinel(findings);
    expect(terminal).not.toBeNull();
    expect(terminal?.kind).toBe(ITEM_OUTCOME_FAILED === "failed" ? "item_failed" : "item_failed");
  });
});
