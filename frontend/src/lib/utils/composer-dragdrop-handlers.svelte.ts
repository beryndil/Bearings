/**
 * Drag-drop + paste handler controller for the Conversation pane.
 *
 * Owns: `dragging` overlay flag, `uploading` flag for the bytes-
 * upload fallback, `dropDiagnostic` banner text, and the section
 * element ref used to scope document-level swallow listeners. The
 * pure parsing of `DragEvent` payloads still lives in
 * `composer-dragdrop.ts` (`extractPaths` / `hasFiles` / `parseUriList`)
 * — this module is the stateful glue around those pure helpers plus
 * the upload pipeline.
 *
 * Lives outside `Conversation.svelte` so the parent shrinks under
 * the project's 400-line cap. Used as a per-Conversation instance
 * because drop state is tab-local: each pane has its own overlay,
 * own upload-in-flight indicator, and own diagnostic banner.
 *
 * Chrome-on-Wayland workarounds preserved:
 *   - `onDragOver` calls `preventDefault()` UNCONDITIONALLY (Chrome
 *     exposes an empty `types` list during dragover, so a
 *     `hasFiles`-gated branch falls through and Chrome refuses to
 *     dispatch `drop`).
 *   - The bytes-upload fallback in `uploadDroppedFiles` covers the
 *     case where Chrome strips both `text/uri-list` and `text/plain`
 *     even when the File objects are fully readable.
 *   - The document-level swallow listener only fires OUTSIDE the
 *     section (double-preventDefault at both document + section level
 *     was observed to confuse Chrome's drop-target chain during the
 *     v0.10.0 DnD shakeout).
 */

import * as uploadsApi from '$lib/api/uploads';
import { extractPaths, hasFiles } from '$lib/utils/composer-dragdrop';

export type DropOps = {
  /** Insert the resolved path as a `[File N]` token in the composer.
   * Carries optional filename + sizeBytes for the chip display when
   * known (URI / picker paths don't include them; bytes-upload does). */
  attachFileAtCursor: (path: string, filename?: string, sizeBytes?: number) => void;
  /** Bind the section element to the controller so the document-level
   * swallow effect knows what counts as "inside." */
  getSectionEl: () => HTMLElement | null;
};

export class DragDropController {
  /** True while a drag carrying files is hovering the section. Drives
   * the dashed-border overlay. */
  dragging = $state(false);

  /** True while bytes are streaming up via `/api/uploads`. Drives the
   * "Uploading dropped file…" overlay (different visual from
   * `dragging` so the user can tell drop succeeded). */
  uploading = $state(false);

  /** Live byte counters for the in-flight upload, or null when nothing
   * is uploading. `loaded` is bytes posted so far; `total` is the full
   * batch size, or null if the browser couldn't compute one (chunked
   * encoding, redirects). Drives the determinate progress bar in the
   * upload overlay; absent / null `total` falls back to a marquee.
   *
   * For multi-file batches the counters are CUMULATIVE across the
   * whole request — XHR exposes one progress stream per HTTP request,
   * not per multipart part, and the UX wants one bar per drop anyway. */
  uploadProgress = $state<{ loaded: number; total: number | null } | null>(null);

  /** Filename label for the upload overlay. Single-file drops show the
   * actual filename; multi-file batches show "N files". Kept separate
   * from `uploadProgress` so the overlay can render the label even
   * before the first `progress` event arrives. */
  uploadLabel = $state<string | null>(null);

  /** Soft-error banner — shown above the composer when a drop landed
   * but didn't yield anything actionable, or when an upload rejected.
   * Lives outside `conversation.error` because that store only renders
   * at the tail of the message list (invisible when scrolled up or
   * when the session has no messages). */
  dropDiagnostic = $state<string | null>(null);

  constructor(private ops: DropOps) {}

  onDragEnter(e: DragEvent): void {
    if (hasFiles(e)) this.dragging = true;
  }

  onDragOver(e: DragEvent): void {
    // preventDefault UNCONDITIONALLY whenever a drag is in flight.
    // Chrome on Wayland exposes an EMPTY `types` list during dragover
    // (types only arrive reliably on dragenter/drop), so gating this
    // on hasFiles(e) would fall through without preventDefault and
    // Chrome would then refuse to dispatch `drop` to this target —
    // verified live against the server access log during the v0.10.0
    // DnD shakeout. Firefox accepts unconditional preventDefault
    // fine; Chrome (on supported compositors) needs it.
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'link';
  }

  onDragLeave(e: DragEvent): void {
    // Only clear when leaving the section entirely, not when crossing
    // into a child element.
    const related = e.relatedTarget as Node | null;
    if (!related || !(e.currentTarget as Node).contains(related)) {
      this.dragging = false;
    }
  }

  onDrop(e: DragEvent): void {
    e.preventDefault();
    this.dragging = false;
    if (!e.dataTransfer) return;
    const { paths, formats } = extractPaths(e.dataTransfer);
    if (paths.length > 0) {
      // Happy path — the OS handed us URIs, no upload needed. Preserves
      // the original "all it has to do is give you the link" behavior
      // from file managers that still expose text/uri-list. URIs don't
      // carry size; the chip falls back to showing just the basename.
      this.dropDiagnostic = null;
      for (const p of paths) this.ops.attachFileAtCursor(p);
      return;
    }
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      // Fallback: the browser stripped path metadata (Chrome/Wayland
      // tab-sandboxing) but the File objects are still readable. Stream
      // the bytes through `/api/uploads` and inject the server path.
      // Kick off async without awaiting — the DragEvent handler returns
      // synchronously and the upload progresses in the background.
      void this.uploadDroppedFiles(files);
      return;
    }
    // Nothing to work with — neither URIs nor File objects. Keep the
    // diagnostic banner so the failure mode stays visible; it's the
    // instrumentation that'll tell us about future compositor/browser
    // regressions.
    const typesInfo = `types=[${(e.dataTransfer.types ?? []).join(', ')}]`;
    this.dropDiagnostic =
      'Drop received, but the browser exposed neither a path nor file bytes. ' +
      `${typesInfo} ` +
      (formats.length ? formats.join(' | ') : '(no text formats exposed)') +
      ' — use the Attach-file button instead.';
  }

  /** Paste handler — Chrome-on-Wayland compatible alternative to the
   * broken drop-dispatch path. Clipboard uses a different Wayland
   * protocol than DnD and works reliably when drag-and-drop silently
   * fails on Hyprland/Chromium. Workflow: copy a file in the file
   * manager (Dolphin, Nautilus) → focus the textarea → Ctrl+V. The
   * clipboard exposes File objects with readable bytes, so we feed
   * them straight into the same `/api/uploads` pipeline the drop path
   * uses.
   *
   * Only preventDefault when files are present — a paste of plain text
   * (the common case) must still land in the textarea normally. */
  onPaste(e: ClipboardEvent): void {
    const files = e.clipboardData?.files;
    if (!files || files.length === 0) return;
    e.preventDefault();
    void this.uploadDroppedFiles(files);
  }

  /** Bytes-upload fallback path for drops that exposed no filesystem
   * path. Chrome on Wayland strips `text/uri-list` and `text/plain`
   * even when the File objects are fully readable — so we read the
   * bytes via FormData, POST them to `/api/uploads/batch` (or
   * `/api/uploads` for a single file), and inject the resulting
   * absolute paths at the cursor in send order.
   *
   * Order semantics: for N>1 files we send a single multipart batch —
   * the server returns the `uploads` array in the same order as the
   * request, and we walk that array to call `attachFileAtCursor` once
   * per file. One round-trip instead of N keeps localhost-latency-
   * sensitive flows snappy and gives the UI a single progress arc.
   * Single-file drops keep using the single-file endpoint so the
   * legacy `/api/uploads` shape stays in active use (smaller diff for
   * the common case, easier debugging when something regresses).
   *
   * Public so the file-input `change` handler can reuse the pipeline
   * for Browse-button uploads. */
  async uploadDroppedFiles(files: FileList): Promise<void> {
    if (this.uploading) return;
    const list = Array.from(files);
    if (list.length === 0) return;
    this.uploading = true;
    this.uploadLabel = list.length === 1 ? list[0].name : `${list.length} files`;
    this.uploadProgress = { loaded: 0, total: null };
    try {
      const onProgress = (p: { loaded: number; total: number | null }): void => {
        this.uploadProgress = p;
      };
      try {
        if (list.length === 1) {
          const result = await uploadsApi.uploadFile(list[0], onProgress);
          this.ops.attachFileAtCursor(result.path, result.filename, result.size_bytes);
        } else {
          const batch = await uploadsApi.uploadFiles(list, onProgress);
          for (const result of batch.uploads) {
            this.ops.attachFileAtCursor(result.path, result.filename, result.size_bytes);
          }
        }
        this.dropDiagnostic = null;
      } catch (e) {
        // Surface the specific reason (413 over-size, 415 blocked
        // extension, 500 disk full) so the user can act. Keying the
        // label off the drop label rather than the individual file is
        // honest — the batch endpoint is fail-fast, so we don't know
        // *which* file in a batch tripped the reject without parsing
        // the server's detail string.
        const msg = e instanceof Error ? e.message : String(e);
        const target = list.length === 1 ? `"${list[0].name}"` : `${list.length} files`;
        this.dropDiagnostic = `Upload failed for ${target}: ${msg}`;
      }
    } finally {
      this.uploading = false;
      this.uploadProgress = null;
      this.uploadLabel = null;
    }
  }

  /** Document-level dragover/drop default-suppression. Without this
   * the browser's default handler navigates the tab to `file://…`
   * whenever the user misses the section (or, on some compositors,
   * always). Returns the cleanup function so callers can wire it into
   * a `$effect` teardown.
   *
   * Scoping note: only suppress when the event target is OUTSIDE the
   * section. Inside-section events go through the section's own
   * `ondragover` / `ondrop`; suppressing at the document level too was
   * plausibly the reason Chrome+Wayland stopped delivering drop events
   * to our handlers on some DOM trees (the double-preventDefault
   * confused the drop-target chain). SessionList.svelte — the working
   * reference in this same codebase — has NO document-level listeners
   * and its drop zone works reliably. Matching that pattern. */
  installSwallow(): () => void {
    const swallow = (e: DragEvent) => {
      const sectionEl = this.ops.getSectionEl();
      const inside =
        !!sectionEl && e.target instanceof Node && sectionEl.contains(e.target);
      if (!inside) e.preventDefault();
    };
    document.addEventListener('dragover', swallow);
    document.addEventListener('drop', swallow);
    return () => {
      document.removeEventListener('dragover', swallow);
      document.removeEventListener('drop', swallow);
    };
  }
}
