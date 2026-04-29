/**
 * Tests for the deterministic rule-evaluation helpers used by the
 * Test-against-message dialog (spec §10) — every match-type semantic
 * the spec §3 schema defines, plus the regex-validity probe the
 * row-level "invalid regex" warning reads.
 */
import { describe, expect, it } from "vitest";

import { evaluateRuleMatch, isValidRegex } from "../routingRules";
import {
  ROUTING_MATCH_TYPE_ALWAYS,
  ROUTING_MATCH_TYPE_KEYWORD,
  ROUTING_MATCH_TYPE_LENGTH_GT,
  ROUTING_MATCH_TYPE_LENGTH_LT,
  ROUTING_MATCH_TYPE_REGEX,
} from "../../config";

describe("evaluateRuleMatch — keyword (spec §3)", () => {
  it("matches a single needle case-insensitively", () => {
    const result = evaluateRuleMatch(
      ROUTING_MATCH_TYPE_KEYWORD,
      "architect",
      "Please ARCHITECT a new module.",
    );
    expect(result).toEqual({ matched: true, invalidRegex: false });
  });

  it("matches when any comma-separated needle is present", () => {
    const result = evaluateRuleMatch(
      ROUTING_MATCH_TYPE_KEYWORD,
      "rename, format, lint",
      "Run the linter please",
    );
    expect(result.matched).toBe(true);
  });

  it("misses when no needle is present", () => {
    const result = evaluateRuleMatch(
      ROUTING_MATCH_TYPE_KEYWORD,
      "architect, refactor",
      "Quick syntax question.",
    );
    expect(result).toEqual({ matched: false, invalidRegex: false });
  });

  it("misses on empty match_value (no keywords means no fire)", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_KEYWORD, "", "anything").matched).toBe(false);
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_KEYWORD, null, "anything").matched).toBe(false);
  });

  it("ignores empty entries inside a comma list", () => {
    const result = evaluateRuleMatch(
      ROUTING_MATCH_TYPE_KEYWORD,
      ",  , refactor, ,",
      "Refactor the queue",
    );
    expect(result.matched).toBe(true);
  });
});

describe("evaluateRuleMatch — regex (spec §3)", () => {
  it("matches a parseable case-insensitive pattern", () => {
    const result = evaluateRuleMatch(
      ROUTING_MATCH_TYPE_REGEX,
      "^(what|where|when) ",
      "Where is the config?",
    );
    expect(result).toEqual({ matched: true, invalidRegex: false });
  });

  it("misses when the pattern doesn't match", () => {
    const result = evaluateRuleMatch(ROUTING_MATCH_TYPE_REGEX, "^arch", "Refactor the module");
    expect(result).toEqual({ matched: false, invalidRegex: false });
  });

  it("flags invalid regex with invalidRegex=true", () => {
    const result = evaluateRuleMatch(ROUTING_MATCH_TYPE_REGEX, "[unclosed", "anything");
    expect(result).toEqual({ matched: false, invalidRegex: true });
  });

  it("treats null / empty match_value as no-match (incomplete, not invalid)", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_REGEX, null, "x")).toEqual({
      matched: false,
      invalidRegex: false,
    });
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_REGEX, "", "x")).toEqual({
      matched: false,
      invalidRegex: false,
    });
  });
});

describe("evaluateRuleMatch — length thresholds (spec §3)", () => {
  it("length_gt fires when message exceeds the threshold", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_GT, "5", "abcdef").matched).toBe(true);
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_GT, "5", "abcde").matched).toBe(false);
  });

  it("length_lt fires when message is below the threshold", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_LT, "5", "abc").matched).toBe(true);
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_LT, "5", "abcde").matched).toBe(false);
  });

  it("non-numeric thresholds fail closed (no match)", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_GT, "five", "abcdef").matched).toBe(false);
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_LENGTH_LT, null, "abc").matched).toBe(false);
  });
});

describe("evaluateRuleMatch — always (spec §3)", () => {
  it("matches unconditionally", () => {
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_ALWAYS, null, "").matched).toBe(true);
    expect(evaluateRuleMatch(ROUTING_MATCH_TYPE_ALWAYS, "ignored", "x").matched).toBe(true);
  });
});

describe("isValidRegex (spec §3 row-level warning)", () => {
  it("accepts a parseable pattern", () => {
    expect(isValidRegex("^foo$")).toBe(true);
    expect(isValidRegex("(a|b)+")).toBe(true);
  });

  it("rejects a syntactically broken pattern", () => {
    expect(isValidRegex("[unclosed")).toBe(false);
    expect(isValidRegex("(?")).toBe(false);
  });
});
