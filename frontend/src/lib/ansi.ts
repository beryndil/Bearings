/**
 * ANSI-to-HTML converter for tool output rendering.
 *
 * Behavior anchor:
 * ``docs/behavior/tool-output-streaming.md`` §"Clickable file paths and
 * URLs in output" — "ANSI escape sequences are stripped by the HTML
 * sanitizer before rendering". M-5 fixes this: escape sequences must
 * render as colored text rather than being stripped.
 *
 * Implementation notes:
 *
 * - Uses ``ansi-to-html`` with ``escapeXML: true`` so text portions are
 *   HTML-escaped (XSS-safe) before the span wrapper is applied.
 * - The DOMPurify config in ``sanitize.ts`` already allows ``<span>``
 *   elements and the ``style`` attribute, so the span tags emitted by
 *   the converter survive sanitization without modifications to the
 *   allowlist.
 * - When the text contains no ANSI escape sequences, ``ansiToHtml``
 *   returns ``null`` so callers can fast-path to the existing
 *   ``linkifyToHtml`` → ``sanitizeHtml`` pipeline (which provides
 *   clickable file paths and URLs).  The two pipelines are mutually
 *   exclusive: linkification is skipped for ANSI-colored output to
 *   avoid double-encoding, a known v1.0 limitation.
 * - ``newline: false`` keeps newlines as ``\n``; the CSS
 *   ``whitespace-pre-wrap`` on the ``<pre>`` container handles
 *   rendering without converting them to ``<br/>``.
 */
import Convert from "ansi-to-html";

/**
 * Matches any CSI (``ESC [``) color/attribute sequence.
 * ```` is the ESC character (U+001B) — written as a Unicode escape
 * to satisfy the ``no-control-regex`` lint rule.
 */
// eslint-disable-next-line no-control-regex
const ANSI_SEQUENCE_RE = /\x1b\[[0-9;]*m/u;

const converter = new Convert({
  escapeXML: true,
  newline: false,
  // Use terminal-neutral defaults; bright variants produced by color
  // codes 9-14 are already specified in ansi-to-html's default palette.
  fg: "#d4d4d4",
  bg: "transparent",
});

/**
 * Convert ANSI escape sequences in ``text`` to HTML ``<span>`` elements
 * carrying inline ``style="color:…"`` attributes.  Text portions are
 * HTML-escaped.  Returns ``null`` when ``text`` contains no ANSI
 * sequences so callers can take the cheaper linkify fast-path.
 *
 * The return value **must** be passed through :func:`sanitize.sanitizeHtml`
 * before DOM insertion — the converter does not apply DOMPurify itself.
 */
export function ansiToHtml(text: string): string | null {
  if (!ANSI_SEQUENCE_RE.test(text)) {
    return null;
  }
  return converter.toHtml(text);
}
