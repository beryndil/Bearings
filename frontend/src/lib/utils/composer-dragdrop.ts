/**
 * Pure helpers for the Conversation composer's drag-drop handling.
 *
 * Lives outside `Conversation.svelte` so the component file shrinks
 * back under the project's 400-line cap and the parsing logic gets a
 * proper unit-test surface (`composer-dragdrop.test.ts`). The
 * handlers themselves (`onDrop`, `onDragEnter`, etc.) stay in the
 * component because they mutate component state (`dragging`,
 * `dropDiagnostic`, the textarea cursor) — but every chunk of pure
 * "given a DragEvent / DataTransfer, what paths does the OS expose?"
 * logic moves here.
 *
 * Linux file managers (Dolphin, Nautilus, Thunar, the KDE
 * dolphin-from-Hyprland combo Dave uses) expose dragged files as
 * `text/uri-list` with absolute `file://` URIs. Chromium on Linux is
 * inconsistent about which formats are populated — Nautilus/Thunar
 * usually set `text/uri-list`, Dolphin sometimes sets only
 * `text/plain` with a `file://` URI, and some Wayland setups strip
 * URIs entirely for security. `extractPaths` tries every format and
 * dedupes.
 */

/** True iff the dataTransfer advertises File entries. Used by the
 * dragenter handler to decide whether to flip the drop overlay on.
 * Note: Chrome on Wayland exposes an empty `types` list during
 * `dragover` (types only arrive reliably on `dragenter` / `drop`),
 * so callers must NOT gate `dragover.preventDefault()` on this. */
export function hasFiles(e: DragEvent): boolean {
  return e.dataTransfer?.types.includes('Files') ?? false;
}

/** Parse a `text/uri-list` payload (RFC 2483) into absolute local
 * paths. Lines starting with `#` are comments, blanks are
 * separators, anything not `file://` is skipped — we deliberately
 * never inject http(s) URLs at the cursor.
 *
 * Localhost / empty hostname is the only accepted authority; a
 * remote-host file URI gets dropped rather than silently ingested
 * as a local path. */
export function parseUriList(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (!line.startsWith('file://')) continue;
    try {
      const url = new URL(line);
      if (url.hostname && url.hostname !== 'localhost') continue;
      out.push(decodeURIComponent(url.pathname));
    } catch {
      // Malformed URI — skip rather than inject garbage.
    }
  }
  return out;
}

/** Pull candidate absolute paths out of every DataTransfer format
 * the browser/OS combo might expose. Returns the deduped path list
 * plus a parallel `formats` array of "fmt=raw[:200]" debug strings —
 * the caller surfaces those in the drop-diagnostic banner when no
 * paths come back, so future compositor/browser regressions are
 * identifiable from the user's screenshot.
 *
 * Tries `text/uri-list`, `text/x-moz-url`,
 * `application/x-kde4-urilist`, and `text/plain` in order. The
 * raw-path fallback (lines that start with `/` and contain no
 * spaces) catches plain-text drags from KDE / xdg / shells where
 * the absolute path is dropped without a `file://` prefix. */
export function extractPaths(dt: DataTransfer): { paths: string[]; formats: string[] } {
  const formats: string[] = [];
  const paths = new Set<string>();
  const tryFormat = (fmt: string) => {
    const raw = dt.getData(fmt);
    if (!raw) return;
    formats.push(`${fmt}=${raw.slice(0, 200)}`);
    for (const p of parseUriList(raw)) paths.add(p);
    // Raw-path fallback: some sources (KDE, xdg, plain-text drags)
    // put the absolute path directly, no file:// prefix.
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (trimmed.startsWith('/') && !trimmed.includes(' ')) paths.add(trimmed);
    }
  };
  tryFormat('text/uri-list');
  tryFormat('text/x-moz-url');
  tryFormat('application/x-kde4-urilist');
  tryFormat('text/plain');
  return { paths: [...paths], formats };
}
