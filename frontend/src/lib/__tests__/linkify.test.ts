/**
 * Tests for :func:`linkify` — covers the three patterns chat.md
 * §"Conversation rendering" enumerates plus edge cases (trailing
 * punctuation, traversal escape, empty input, no working dir).
 */
import { describe, expect, it } from "vitest";

import { CHAT_LINK_REL } from "../config";
import { linkify } from "../linkify";

describe("linkify — http(s) URLs", () => {
  it("turns a bare https URL into a single url segment", () => {
    const segments = linkify("see https://example.com for details");
    expect(segments).toEqual([
      { kind: "text", text: "see " },
      {
        kind: "url",
        text: "https://example.com",
        href: "https://example.com",
        rel: CHAT_LINK_REL,
      },
      { kind: "text", text: " for details" },
    ]);
  });

  it("turns a bare http URL the same way (no scheme upgrade)", () => {
    const segments = linkify("http://10.0.0.1/admin");
    expect(segments).toHaveLength(1);
    expect(segments[0]).toEqual({
      kind: "url",
      text: "http://10.0.0.1/admin",
      href: "http://10.0.0.1/admin",
      rel: CHAT_LINK_REL,
    });
  });

  it("strips trailing sentence punctuation from the anchor", () => {
    const segments = linkify("read https://example.com/foo.");
    expect(segments).toEqual([
      { kind: "text", text: "read " },
      {
        kind: "url",
        text: "https://example.com/foo",
        href: "https://example.com/foo",
        rel: CHAT_LINK_REL,
      },
      { kind: "text", text: "." },
    ]);
  });

  it("does not split on the dot inside a URL path", () => {
    const segments = linkify("https://example.com/path/to/file.html and more");
    const urlSegment = segments.find((s) => s.kind === "url");
    expect(urlSegment?.text).toBe("https://example.com/path/to/file.html");
  });
});

describe("linkify — file URLs", () => {
  it("treats file:// URLs as file segments without target=_blank cue", () => {
    const segments = linkify("open file:///etc/hosts please");
    expect(segments).toEqual([
      { kind: "text", text: "open " },
      {
        kind: "file",
        text: "file:///etc/hosts",
        href: "file:///etc/hosts",
        displayText: "file:///etc/hosts",
      },
      { kind: "text", text: " please" },
    ]);
  });
});

describe("linkify — absolute filesystem paths", () => {
  it("converts an absolute path with extension to a file:// link", () => {
    const segments = linkify("see /tmp/output.log for details");
    expect(segments).toEqual([
      { kind: "text", text: "see " },
      {
        kind: "file",
        text: "/tmp/output.log",
        href: "file:///tmp/output.log",
        displayText: "/tmp/output.log",
      },
      { kind: "text", text: " for details" },
    ]);
  });

  it("strips a trailing comma from an absolute path", () => {
    const segments = linkify("found /tmp/a.log, then /tmp/b.log");
    const fileTexts = segments.filter((s) => s.kind === "file").map((s) => s.text);
    expect(fileTexts).toEqual(["/tmp/a.log", "/tmp/b.log"]);
  });
});

describe("linkify — workspace-relative paths", () => {
  const workingDir = "/home/dev/repo";

  it("resolves a relative path under the working dir", () => {
    const segments = linkify("edit frontend/src/lib/x.svelte today", { workingDir });
    expect(segments).toEqual([
      { kind: "text", text: "edit " },
      {
        kind: "file",
        text: "frontend/src/lib/x.svelte",
        href: "file:///home/dev/repo/frontend/src/lib/x.svelte",
        displayText: "frontend/src/lib/x.svelte",
      },
      { kind: "text", text: " today" },
    ]);
  });

  it("leaves a relative path as plain text when no working dir given", () => {
    const segments = linkify("edit frontend/src/lib/x.svelte today");
    expect(segments.every((s) => s.kind === "text")).toBe(true);
  });

  it("rejects a parent-traversal escape rather than producing a broken anchor", () => {
    // ``../../../etc/passwd`` would escape the root; chat.md mandates
    // plaintext fallback.
    const segments = linkify("see ../../etc/passwd today", { workingDir: "/a/b" });
    expect(segments.every((s) => s.kind === "text")).toBe(true);
  });
});

describe("linkify — edge cases", () => {
  it("returns an empty list for empty input", () => {
    expect(linkify("")).toEqual([]);
  });

  it("coalesces adjacent text segments", () => {
    const segments = linkify("plain prose without anchors at all.");
    expect(segments).toEqual([{ kind: "text", text: "plain prose without anchors at all." }]);
  });

  it("handles two URLs in one line", () => {
    const segments = linkify("https://a.example and https://b.example");
    const urls = segments.filter((s) => s.kind === "url").map((s) => s.text);
    expect(urls).toEqual(["https://a.example", "https://b.example"]);
  });
});
