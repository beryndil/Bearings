/**
 * Tests for :func:`sanitizeHtml` — covers the XSS surface item 2.1's
 * TODO flagged for 2.3 plus the chat.md-mandated ``rel`` attribute
 * on outbound anchors.
 */
import { describe, expect, it } from "vitest";

import { sanitizeHtml } from "../sanitize";

describe("sanitizeHtml — XSS rejection", () => {
  it("strips script tags", () => {
    const out = sanitizeHtml("<p>hi</p><script>alert(1)</script>");
    expect(out).toContain("<p>hi</p>");
    expect(out).not.toContain("<script");
    expect(out).not.toContain("alert");
  });

  it("strips on* event handlers", () => {
    const out = sanitizeHtml('<img src="x" onerror="alert(1)">');
    expect(out).not.toContain("onerror");
    expect(out).not.toContain("alert");
  });

  it("strips javascript: hrefs", () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">click</a>');
    expect(out).not.toContain("javascript:");
  });

  it("rejects iframes outright", () => {
    const out = sanitizeHtml('<iframe src="https://evil.example"></iframe>');
    expect(out).not.toContain("<iframe");
  });
});

describe("sanitizeHtml — markdown shapes preserved", () => {
  it("keeps standard markdown HTML (paragraphs, lists, code)", () => {
    const out = sanitizeHtml(
      "<p>x <strong>y</strong></p><ul><li>z</li></ul><pre><code>q</code></pre>",
    );
    expect(out).toContain("<strong>y</strong>");
    expect(out).toContain("<li>z</li>");
    expect(out).toContain("<code>q</code>");
  });

  it("preserves shiki-style class attributes on pre/code", () => {
    const out = sanitizeHtml('<pre class="shiki"><code class="language-python">x = 1</code></pre>');
    expect(out).toContain('class="shiki"');
    expect(out).toContain('class="language-python"');
  });
});

describe("sanitizeHtml — anchor policy", () => {
  it("forces target=_blank + rel on http(s) anchors", () => {
    const out = sanitizeHtml('<a href="https://example.com">x</a>');
    expect(out).toContain('target="_blank"');
    expect(out).toContain("noopener");
    expect(out).toContain("noreferrer");
  });

  it("does not force target=_blank on file:// anchors", () => {
    const out = sanitizeHtml('<a href="file:///etc/hosts">x</a>');
    expect(out).not.toContain('target="_blank"');
  });
});
