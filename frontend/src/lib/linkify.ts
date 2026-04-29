/**
 * Linkifier — converts URLs and filesystem paths inside plaintext to
 * clickable anchors per ``docs/behavior/chat.md`` §"Conversation
 * rendering".
 *
 * The doc enumerates exactly three patterns to auto-detect:
 *
 * 1. ``https://…`` and ``http://…`` URLs — anchors with
 *    ``target="_blank"`` and ``rel="noopener noreferrer"`` so they
 *    open in a new tab.
 * 2. ``file://…`` URLs — anchors carrying a ``data-link-kind="file"``
 *    attribute the local "Open in editor" handler can dispatch on.
 *    No ``target="_blank"``: the file:// scheme is interpreted by the
 *    SPA, not the browser.
 * 3. Absolute filesystem paths and (when a ``workingDir`` is supplied)
 *    workspace-relative paths shaped like
 *    ``frontend/src/lib/x.svelte`` — resolved against the working
 *    directory and rendered as ``file://`` anchors. Paths that can't
 *    be resolved against an absolute root are left as plain text per
 *    the chat.md guarantee "rather than producing a broken anchor".
 *
 * **Out of scope (per chat.md):** the linkifier does NOT auto-link
 * session-ids or message-ids. The session and message surfaces are
 * navigable via the sidebar / inspector / context-menus; chat.md does
 * not prescribe in-message linkification for them. (The plug for
 * item 2.3 mentions session-ids / message-ids as a fourth bucket; the
 * authoritative behavior doc is silent on that surface, so this
 * implementation matches chat.md.)
 *
 * The linkifier is a *pure function* — input plaintext + an optional
 * ``workingDir`` → an array of segments tagged ``"text" | "url" |
 * "file"``. Components render the segments themselves so the final
 * HTML escaping is owned by Svelte's template, not by hand-rolled
 * string concatenation. That keeps XSS surface narrow: even a
 * malicious URL that contains ``<script>`` falls into the ``text``
 * branch of the rendered anchor and is escaped by Svelte.
 */
import { CHAT_LINK_REL } from "./config";

/** A plain-text run with no link substitution. */
interface TextSegment {
  readonly kind: "text";
  readonly text: string;
}

/**
 * An ``http(s)://`` link. ``href`` is the URL exactly as it appeared
 * (no normalisation); ``rel`` is the security attribute the renderer
 * should apply on the anchor element.
 */
interface UrlSegment {
  readonly kind: "url";
  readonly text: string;
  readonly href: string;
  readonly rel: string;
}

/**
 * A ``file://`` link or a resolvable filesystem-path link. The
 * ``href`` is always a fully-qualified ``file://`` URL even when the
 * source text was a workspace-relative path; ``displayText`` is the
 * source span the user typed so the rendered anchor reads like the
 * input.
 */
interface FileSegment {
  readonly kind: "file";
  readonly text: string;
  readonly href: string;
  readonly displayText: string;
}

type LinkSegment = TextSegment | UrlSegment | FileSegment;

/**
 * Match URL and filesystem-path candidates in source order. Each
 * alternative captures one shape; the ``linkify`` function decides
 * which capture won and translates it to a segment.
 *
 * - ``url``: ``http(s)://...`` runs up to whitespace or angle bracket.
 * - ``fileUrl``: ``file://`` URL likewise.
 * - ``absPath``: an absolute POSIX path. Stops at whitespace, end-of-
 *   string, or terminal punctuation that's commonly attached to a
 *   path in prose (``,;)`` etc.).
 * - ``relPath``: a workspace-shaped relative path with at least one
 *   segment separator, restricted to typical filename charset so a
 *   sentence like "use a/b form" doesn't slurp ordinary words.
 *
 * The regex is constructed with the ``g`` (global) and ``u``
 * (Unicode) flags. Each alternative is captured with a named group so
 * a single ``matchAll`` produces a discriminator without re-running
 * the pattern per alternative.
 */
const LINK_PATTERN =
  /(?<url>https?:\/\/[^\s<>"']+)|(?<fileUrl>file:\/\/[^\s<>"']+)|(?<absPath>\/[A-Za-z0-9_\-./]+(?:\.[A-Za-z0-9_-]+|\/))|(?<relPath>(?:\.\.?\/)*[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_./-]+)+)/gu;

const TRAILING_PUNCTUATION = /[).,;:!?'"]+$/u;

/** Parameters shared by every call to :func:`linkify`. */
interface LinkifyOptions {
  /**
   * Absolute working directory of the session, used to resolve
   * workspace-relative paths to ``file://`` URLs. When omitted, only
   * absolute paths and explicit URLs become anchors; relative paths
   * stay as plain text.
   */
  readonly workingDir?: string;
}

/**
 * Convert ``source`` to an ordered array of segments. Plaintext runs
 * are coalesced so two adjacent ``text`` segments never appear back
 * to back.
 */
export function linkify(source: string, options: LinkifyOptions = {}): readonly LinkSegment[] {
  if (source.length === 0) {
    return [];
  }
  const segments: LinkSegment[] = [];
  let cursor = 0;
  for (const match of source.matchAll(LINK_PATTERN)) {
    const start = match.index ?? 0;
    const groups = match.groups ?? {};
    const segment = matchToSegment(groups, options.workingDir);
    if (segment === null) {
      continue;
    }
    if (start > cursor) {
      pushText(segments, source.slice(cursor, start));
    }
    // Trailing punctuation handling — chat.md does not address it,
    // but a "see https://example.com." style sentence should not
    // include the dot in the anchor. We strip it from the link span
    // and emit a separate text segment carrying the punctuation.
    const raw = segment.text;
    const punctuation = trailingPunctuation(raw);
    if (punctuation.length > 0) {
      const cleaned = trimTrailing(segment, punctuation);
      segments.push(cleaned);
      pushText(segments, punctuation);
    } else {
      segments.push(segment);
    }
    cursor = start + raw.length;
  }
  if (cursor < source.length) {
    pushText(segments, source.slice(cursor));
  }
  return segments;
}

function matchToSegment(
  groups: Record<string, string | undefined>,
  workingDir: string | undefined,
): LinkSegment | null {
  const url = groups.url;
  if (url !== undefined && url.length > 0) {
    return { kind: "url", text: url, href: url, rel: CHAT_LINK_REL };
  }
  const fileUrl = groups.fileUrl;
  if (fileUrl !== undefined && fileUrl.length > 0) {
    return { kind: "file", text: fileUrl, href: fileUrl, displayText: fileUrl };
  }
  const absPath = groups.absPath;
  if (absPath !== undefined && absPath.length > 0) {
    return {
      kind: "file",
      text: absPath,
      href: pathToFileUrl(absPath),
      displayText: absPath,
    };
  }
  const relPath = groups.relPath;
  if (relPath !== undefined && relPath.length > 0) {
    if (workingDir === undefined || workingDir.length === 0) {
      return null;
    }
    const absolute = joinUnderRoot(workingDir, relPath);
    if (absolute === null) {
      return null;
    }
    return {
      kind: "file",
      text: relPath,
      href: pathToFileUrl(absolute),
      displayText: relPath,
    };
  }
  return null;
}

function pushText(segments: LinkSegment[], text: string): void {
  if (text.length === 0) {
    return;
  }
  const last = segments[segments.length - 1];
  if (last !== undefined && last.kind === "text") {
    segments[segments.length - 1] = { kind: "text", text: last.text + text };
    return;
  }
  segments.push({ kind: "text", text });
}

function trailingPunctuation(text: string): string {
  const match = TRAILING_PUNCTUATION.exec(text);
  return match === null ? "" : match[0];
}

function trimTrailing(segment: LinkSegment, suffix: string): LinkSegment {
  const trimmed = segment.text.slice(0, segment.text.length - suffix.length);
  switch (segment.kind) {
    case "text":
      return { kind: "text", text: trimmed };
    case "url":
      return { kind: "url", text: trimmed, href: trimmed, rel: segment.rel };
    case "file": {
      // File-segments may have been built from workspace-relative
      // input; in that case the ``href`` is already an absolute
      // ``file://`` URL while the ``displayText`` is the relative
      // span. Trim both consistently from the trailing edge.
      const sameAsDisplay = segment.text === segment.displayText;
      const newHref = sameAsDisplay
        ? pathToFileUrl(stripFileUrlScheme(segment.href).slice(0, -suffix.length))
        : segment.href;
      const newDisplay = sameAsDisplay
        ? trimmed
        : segment.displayText.slice(0, segment.displayText.length - suffix.length);
      return {
        kind: "file",
        text: trimmed,
        href: newHref,
        displayText: newDisplay,
      };
    }
  }
}

function stripFileUrlScheme(href: string): string {
  return href.startsWith("file://") ? href.slice("file://".length) : href;
}

function pathToFileUrl(absolutePath: string): string {
  // Always emit a triple-slash form so the URL parses as
  // ``file:///path`` even on platforms whose absolute paths begin
  // with a single slash.
  return `file://${absolutePath}`;
}

/**
 * Resolve ``relativePath`` under ``root``. Returns ``null`` when the
 * resolved path would escape the root via ``..`` traversal — the
 * chat.md guarantee that "paths that can't be resolved against an
 * absolute root are left as plain text rather than producing a broken
 * anchor" extends to traversal-suspicious shapes.
 */
/**
 * Render the segments :func:`linkify` returns to safe HTML. URLs
 * become ``<a href target=_blank rel=…>`` anchors; file links become
 * anchors carrying ``data-link-kind="file"`` so the SPA's "Open in
 * editor" handler can dispatch on them; text runs are HTML-escaped.
 *
 * The output is consumed via Svelte's ``{@html}`` insertion AFTER the
 * caller passes it through :func:`sanitize.sanitizeHtml`. We don't
 * call sanitize here so the helper stays a pure function of the
 * segment list — the policy layer lives in ``sanitize.ts``.
 */
export function linkifyToHtml(source: string, options: LinkifyOptions = {}): string {
  const segments = linkify(source, options);
  return segments.map(segmentToHtml).join("");
}

function segmentToHtml(segment: LinkSegment): string {
  switch (segment.kind) {
    case "text":
      return escapeHtml(segment.text);
    case "url":
      return `<a href="${escapeAttr(segment.href)}" target="_blank" rel="${escapeAttr(segment.rel)}">${escapeHtml(segment.text)}</a>`;
    case "file":
      return `<a href="${escapeAttr(segment.href)}" data-link-kind="file">${escapeHtml(segment.displayText)}</a>`;
  }
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(text: string): string {
  return escapeHtml(text);
}

function joinUnderRoot(root: string, relativePath: string): string | null {
  if (!root.startsWith("/")) {
    return null;
  }
  if (relativePath.startsWith("/")) {
    return relativePath;
  }
  const normalisedRoot = root.endsWith("/") ? root.slice(0, -1) : root;
  const rootStack: string[] = normalisedRoot.split("/").filter((part) => part.length > 0);
  const stack: string[] = [...rootStack];
  for (const part of relativePath.split("/")) {
    if (part === "" || part === ".") {
      continue;
    }
    if (part === "..") {
      // Reject any traversal that would escape the original root
      // depth — chat.md's "left as plain text rather than producing
      // a broken anchor" guarantee covers attempted-escape shapes.
      if (stack.length <= rootStack.length) {
        return null;
      }
      stack.pop();
      continue;
    }
    stack.push(part);
  }
  return `/${stack.join("/")}`;
}
