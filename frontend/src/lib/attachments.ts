/**
 * Terminal-style `[File N]` attachment helpers shared between the
 * composer (which INSERTS tokens) and the transcript renderer (which
 * PARSES them back into chips). Kept in a single file so the token
 * shape has one definition on the frontend; the Python side mirrors
 * the same regex in `src/bearings/agent/_attachments.py` — keep the
 * two in sync when the shape changes.
 */

import type { MessageAttachment } from '$lib/api/sessions';

/** `[File 1]` — literal `[File `, one-or-more digits, literal `]`.
 * Capture group 1 is the attachment's `n`. Ordinary typed text like
 * `[File Manager]` or `[file 1]` does NOT match, so a user who names
 * something with square brackets won't trigger a spurious chip. The
 * `g` flag is required for `split` / `matchAll` callers. */
export const ATTACHMENT_TOKEN_REGEX = /\[File (\d+)\]/g;

/** Build a display-only token for insertion at the cursor. Returns
 * the string literal the composer writes into the textarea; the
 * sidecar attachments list is what actually tracks the real path. */
export function formatAttachmentToken(n: number): string {
  return `[File ${n}]`;
}

/** One segment of a parsed user-message body. `text` segments are
 * literal runs between (or around) tokens; `token` segments reference
 * an attachment by `n` and carry the resolved `MessageAttachment`
 * when one is found in the sidecar. A `token` segment whose
 * `attachment` is null means the user's text contained `[File N]`
 * literally without a matching entry — we render that as plain text
 * rather than an orphaned chip, matching the backend's substitution
 * behaviour (leave it alone). */
export type MessageBodySegment =
  | { kind: 'text'; text: string }
  | { kind: 'token'; n: number; attachment: MessageAttachment | null };

/** Split a user-message body into alternating text / token segments.
 * The transcript's user-bubble renderer walks this list and renders
 * chips for resolved tokens and plain text for everything else.
 * Order is preserved; every character of `content` appears in exactly
 * one segment. */
export function parseMessageBody(
  content: string,
  attachments: MessageAttachment[] | null | undefined
): MessageBodySegment[] {
  if (!attachments || attachments.length === 0) {
    return content ? [{ kind: 'text', text: content }] : [];
  }
  const byN = new Map<number, MessageAttachment>();
  for (const a of attachments) byN.set(a.n, a);
  const segments: MessageBodySegment[] = [];
  let lastIndex = 0;
  // Fresh regex instance each call — `ATTACHMENT_TOKEN_REGEX` carries
  // the `g` flag which persists `lastIndex` across calls on the same
  // literal. Cloning keeps this function reentrant.
  const re = new RegExp(ATTACHMENT_TOKEN_REGEX.source, 'g');
  let match: RegExpExecArray | null;
  while ((match = re.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ kind: 'text', text: content.slice(lastIndex, match.index) });
    }
    const n = Number(match[1]);
    const resolved = byN.get(n) ?? null;
    if (resolved) {
      segments.push({ kind: 'token', n, attachment: resolved });
    } else {
      // No matching attachment — treat the token as literal text so
      // the UI doesn't render a dead chip. Matches the backend's
      // "leave unknown tokens alone" substitution rule.
      segments.push({ kind: 'text', text: match[0] });
    }
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ kind: 'text', text: content.slice(lastIndex) });
  }
  return segments;
}

/** Format bytes for chip hover tooltips. Small numbers → `512 B`,
 * larger → kibibyte / mebibyte. The transcript chip shows this next
 * to the filename so the user can tell a 3 KB config from a 40 MB PDF
 * without clicking through. */
export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
