/**
 * Tests for the ANSI-to-HTML converter (M-5).
 *
 * Behavior anchor:
 * ``docs/behavior/tool-output-streaming.md`` §"ANSI passthrough" —
 * ANSI color escape sequences in bash tool output must render as colored
 * text rather than being stripped by DOMPurify.
 */
import { describe, expect, it } from "vitest";

import { ansiToHtml } from "../ansi";
import { sanitizeHtml } from "../sanitize";

describe("ansiToHtml", () => {
  it("returns null for text with no ANSI sequences (fast-path)", () => {
    expect(ansiToHtml("hello world")).toBeNull();
    expect(ansiToHtml("")).toBeNull();
    expect(ansiToHtml("line1\nline2\n")).toBeNull();
  });

  it("returns a string (not null) when ANSI sequences are present", () => {
    const result = ansiToHtml("\x1b[31mred\x1b[0m");
    expect(result).not.toBeNull();
    expect(typeof result).toBe("string");
  });

  it("converts a foreground color sequence to a span with inline style", () => {
    const result = ansiToHtml("\x1b[31mred text\x1b[0m");
    expect(result).not.toBeNull();
    // Should contain a span with color styling
    expect(result).toContain("<span");
    expect(result).toContain("color:");
    expect(result).toContain("red text");
    // Reset should close the span
    expect(result).toContain("</span>");
  });

  it("HTML-escapes text portions (XSS safety with escapeXML: true)", () => {
    // A malicious payload mixed with ANSI — the text portion must be escaped.
    const result = ansiToHtml("\x1b[32m<script>alert(1)</script>\x1b[0m");
    expect(result).not.toBeNull();
    // The < and > must be escaped
    expect(result).not.toContain("<script>");
    expect(result).toContain("&lt;script&gt;");
  });

  it("preserves plain text between color spans", () => {
    const result = ansiToHtml("\x1b[32mgreen\x1b[0m normal \x1b[31mred\x1b[0m");
    expect(result).not.toBeNull();
    expect(result).toContain("green");
    expect(result).toContain("normal");
    expect(result).toContain("red");
  });

  it("does not introduce <br> for newlines (newline: false)", () => {
    const result = ansiToHtml("\x1b[33mline1\nline2\x1b[0m");
    expect(result).not.toBeNull();
    expect(result).not.toContain("<br");
    expect(result).toContain("\n");
  });

  it("survives DOMPurify sanitization — span and style preserved", () => {
    const ansiHtml = ansiToHtml("\x1b[34mblue\x1b[0m");
    expect(ansiHtml).not.toBeNull();
    const safe = sanitizeHtml(ansiHtml!);
    // After DOMPurify the span with color should still be present
    expect(safe).toContain("<span");
    expect(safe).toContain("color:");
    expect(safe).toContain("blue");
  });

  it("sanitizeHtml strips script injection even if somehow present", () => {
    // Verify DOMPurify defense-in-depth: even if ansiToHtml produced a
    // script tag (it won't with escapeXML: true, but belt-and-suspenders).
    const malicious = '<span style="color:red"><script>alert(1)</script>hi</span>';
    const safe = sanitizeHtml(malicious);
    expect(safe).not.toContain("<script>");
    expect(safe).toContain("hi");
  });

  it("handles bold / reset sequences", () => {
    // ESC[1m is bold, ESC[0m is reset
    const result = ansiToHtml("\x1b[1mbold\x1b[0m normal");
    expect(result).not.toBeNull();
    expect(result).toContain("bold");
    expect(result).toContain("normal");
  });

  it("handles 256-color sequences", () => {
    // ESC[38;5;196m is 256-color red foreground
    const result = ansiToHtml("\x1b[38;5;196mred256\x1b[0m");
    expect(result).not.toBeNull();
    expect(result).toContain("red256");
    expect(result).toContain("color:");
  });
});
