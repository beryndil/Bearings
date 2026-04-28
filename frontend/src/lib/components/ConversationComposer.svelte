<script lang="ts">
  /**
   * Composer + footer for the Conversation pane.
   *
   * Owns: prompt textarea (with auto-grow + draft persistence + shell-
   * style history), slash-command palette, terminal-style `[File N]`
   * attachments with chips, native + browser file pickers, paste
   * pipeline, and the in-line drop-diagnostic + upload-status surfaces.
   *
   * Drag-drop event handlers themselves bind to the outer `<section>`
   * in `Conversation.svelte` because the WHOLE pane accepts drops, but
   * the controller (`DragDropController`) is shared with this composer
   * via the `dragdrop` prop so paste, browse, and file-input flows can
   * reuse the same upload pipeline and mutate the same diagnostic +
   * uploading state.
   *
   * Lives outside `Conversation.svelte` so the parent shrinks under
   * the project's 400-line cap. The composer is one cohesive unit
   * (everything below the message list) so it ships as a single
   * subcomponent rather than a chain of smaller ones.
   */
  import { conversation } from '$lib/stores/conversation.svelte';
  import { drafts } from '$lib/stores/drafts.svelte';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { agent } from '$lib/agent.svelte';
  import {
    caretOnFirstLine,
    caretOnLastLine,
    emptyHistoryState,
    nextHistory,
    prevHistory,
    resetHistory,
    type HistoryState,
  } from '$lib/input-history';
  import * as api from '$lib/api';
  import type { MessageAttachment } from '$lib/api/sessions';
  import * as fsApi from '$lib/api/fs';
  import { ATTACHMENT_TOKEN_REGEX, formatAttachmentToken, formatBytes } from '$lib/attachments';
  import CommandMenu from './CommandMenu.svelte';
  import { contextmenu } from '$lib/actions/contextmenu';
  import type { DragDropController } from '$lib/utils/composer-dragdrop-handlers.svelte';

  /** Imperative surface exposed via `bind:this` so the parent's
   * `DragDropController` (constructed before the composer mounts)
   * can route URI / bytes / picker drops into the composer once it's
   * available. */
  export type ConversationComposerHandle = {
    attachFileAtCursor: (path: string, filename?: string, sizeBytes?: number) => void;
  };

  let {
    dragdrop,
  }: {
    dragdrop: DragDropController;
  } = $props();

  let promptText = $state('');
  let textareaEl: HTMLTextAreaElement | undefined = $state();

  // Per-session draft persistence: when the user types and navigates
  // away without sending, the text survives reloads and session
  // switches. The two effects below are split so loading on session
  // change doesn't retrigger on every keystroke. `lastLoadedSessionId`
  // also drives the pre-switch flush in `onSend` and cleanup — without
  // it we'd read the wrong session's id once selection has already
  // moved on.
  let lastLoadedSessionId = $state<string | null>(null);

  $effect(() => {
    const sid = sessions.selected?.id ?? null;
    if (sid === lastLoadedSessionId) return;
    // Commit the outgoing session's in-flight debounced write before
    // hydrating the incoming one. Otherwise the last few characters
    // typed just before the switch would be lost.
    if (lastLoadedSessionId !== null) drafts.flush(lastLoadedSessionId);
    lastLoadedSessionId = sid;
    promptText = sid === null ? '' : drafts.get(sid);
  });

  $effect(() => {
    const sid = lastLoadedSessionId;
    const text = promptText;
    if (sid === null) return;
    drafts.set(sid, text);
  });

  // Flush the pending debounced write on page hide so the tail end
  // of the user's typing survives an abrupt tab close or reload.
  // `beforeunload` covers full navigation; `pagehide` catches
  // bfcache-restored tabs and mobile suspensions the former misses.
  $effect(() => {
    if (typeof window === 'undefined') return;
    const flushNow = () => {
      const sid = lastLoadedSessionId;
      if (sid !== null) drafts.flush(sid);
    };
    window.addEventListener('beforeunload', flushNow);
    window.addEventListener('pagehide', flushNow);
    return () => {
      window.removeEventListener('beforeunload', flushNow);
      window.removeEventListener('pagehide', flushNow);
    };
  });

  // Shell-style Up/Down arrow history over prior user prompts for the
  // current session. Entries are derived from the client-side message
  // cache — no new API, and "recent history" (whatever's paginated in)
  // is an acceptable scope. Reset on session switch so walking doesn't
  // leak across sessions.
  let historyState = $state<HistoryState>(emptyHistoryState());
  const historyEntries = $derived(
    conversation.messages.filter((m) => m.role === 'user').map((m) => m.content)
  );
  $effect(() => {
    void sessions.selectedId;
    historyState = emptyHistoryState();
  });

  /** Move caret to the end of the textarea after a history swap.
   * queueMicrotask lets Svelte push the new `promptText` into the DOM
   * before we read `.value.length`, otherwise the range would target
   * the pre-update contents. */
  function setCaretToEnd(): void {
    const el = textareaEl;
    if (!el) return;
    queueMicrotask(() => {
      const end = el.value.length;
      el.selectionStart = end;
      el.selectionEnd = end;
    });
  }

  // Slash-command palette. Entries are fetched once per session
  // (keyed by id) so opening the menu doesn't restart the filesystem
  // walk every keystroke. The menu opens only when the first character
  // is `/` and there's no whitespace yet — matches the CLI, and means
  // adding args (`/fad:ship --dry`) dismisses it.
  let commandEntries = $state<api.CommandEntry[]>([]);
  let commandEntriesSessionId = $state<string | null>(null);
  let commandMenu: { handleKey: (e: KeyboardEvent) => boolean } | undefined = $state();

  const commandMenuOpen = $derived(promptText.startsWith('/') && !/\s/.test(promptText));
  const commandQuery = $derived(commandMenuOpen ? promptText.slice(1) : '');

  $effect(() => {
    const sid = sessions.selected?.id ?? null;
    if (sid === null || sid === commandEntriesSessionId) return;
    commandEntriesSessionId = sid;
    const cwd = sessions.selected?.working_dir ?? null;
    api.listCommands(cwd).then(
      (r) => {
        // Guard against session switch during the round-trip.
        if (commandEntriesSessionId === sid) commandEntries = r.entries;
      },
      () => {
        // Palette is a convenience; a failed fetch just means no menu,
        // not an error the user needs to see.
      }
    );
  });

  function onSelectCommand(slug: string): void {
    promptText = `/${slug} `;
    // Return focus to the textarea so the user can keep typing args.
    queueMicrotask(() => textareaEl?.focus());
  }

  function onCloseCommandMenu(): void {
    // Insert a space after the slash so the menu closes without
    // dropping what the user already typed.
    if (promptText.startsWith('/') && !/\s/.test(promptText)) {
      promptText = `${promptText} `;
    }
  }

  function onSend(): void {
    const text = promptText.trim();
    if (!text) return;
    // Filter the sidecar to attachments the user actually kept
    // referenced in the prompt — if they deleted `[File 2]` after
    // dropping it, we don't send its path along. The backend applies
    // the same pruning rule (`referenced_ns` in
    // `bearings/agent/_attachments.py`); we mirror it here so the
    // optimistic user bubble matches what the server will persist.
    const referenced = new Set<number>();
    const re = new RegExp(ATTACHMENT_TOKEN_REGEX.source, 'g');
    let match: RegExpExecArray | null;
    while ((match = re.exec(text)) !== null) referenced.add(Number(match[1]));
    const activeAttachments = composerAttachments.filter((a) => referenced.has(a.n));
    if (!agent.send(text, activeAttachments)) return;
    // Clear the persisted draft before resetting `promptText` so the
    // debounced writer in the save effect doesn't race the clear and
    // re-persist an empty string (harmless but pointless I/O).
    const sid = lastLoadedSessionId;
    if (sid !== null) drafts.clear(sid);
    promptText = '';
    composerAttachments = [];
    nextAttachmentN = 1;
    // A successful send is an implicit "leave history mode" — the
    // next Up should stash the (empty) draft and walk back through
    // the newly-extended history.
    historyState = emptyHistoryState();
  }

  function onKeydown(e: KeyboardEvent): void {
    // The command menu claims arrow/Enter/Tab/Escape while open so the
    // user can navigate without leaving the textarea. It returns false
    // for other keys so normal typing still flows through.
    if (commandMenu?.handleKey(e)) return;
    // Shell-style history on Up/Down. Guards mirror readline: no
    // modifiers (so Shift-select and Ctrl-shortcuts are untouched),
    // no IME composition, caret must be at the first/last visual
    // line with no active selection (so multi-line editing still
    // works the obvious way).
    if (
      (e.key === 'ArrowUp' || e.key === 'ArrowDown') &&
      !e.shiftKey &&
      !e.ctrlKey &&
      !e.altKey &&
      !e.metaKey &&
      !e.isComposing
    ) {
      const el = textareaEl;
      if (el) {
        const start = el.selectionStart ?? 0;
        const end = el.selectionEnd ?? 0;
        if (e.key === 'ArrowUp' && caretOnFirstLine(promptText, start, end)) {
          const step = prevHistory(historyState, historyEntries, promptText);
          if (step.changed) {
            e.preventDefault();
            historyState = step.state;
            promptText = step.text;
            setCaretToEnd();
            return;
          }
        } else if (e.key === 'ArrowDown' && caretOnLastLine(promptText, start, end)) {
          const step = nextHistory(historyState, historyEntries);
          if (step.changed) {
            e.preventDefault();
            historyState = step.state;
            promptText = step.text;
            setCaretToEnd();
            return;
          }
        }
      }
    }
    // Enter sends; Shift+Enter falls through so the textarea inserts
    // a newline. Skip while the user is mid-IME composition.
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      onSend();
    }
  }

  /** Called on textarea `input`. If the user edits the text after
   * walking into history, exit history mode so the next Up treats
   * the edited text as the new baseline and stashes it. Programmatic
   * updates (history swap, slash-insert, paste) shouldn't trigger
   * the reset — those set `promptText` directly without firing
   * `input`, or are handled elsewhere. */
  function onInput(): void {
    historyState = resetHistory(historyState);
  }

  // Prompt textarea auto-grow. Starts at a single row and stretches
  // as the user types until the content height hits PROMPT_MAX_PX;
  // past that, `overflow-y: auto` takes over so the rest scrolls
  // inside a fixed-height box. Recomputed on every value change —
  // cheap because `scrollHeight` is O(1) for a textarea.
  const PROMPT_MAX_PX = 240;

  function autosizeTextarea(): void {
    const el = textareaEl;
    if (!el) return;
    // Reset first so the measurement isn't capped by the previous
    // height. The `auto` pass lets scrollHeight report the content's
    // natural height even when it would shrink.
    el.style.height = 'auto';
    const next = Math.min(el.scrollHeight, PROMPT_MAX_PX);
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > PROMPT_MAX_PX ? 'auto' : 'hidden';
  }

  // Runs on every promptText change (including programmatic updates
  // from drop / upload / slash-command insertion). `queueMicrotask`
  // defers until Svelte has pushed the new value into the DOM.
  $effect(() => {
    void promptText;
    queueMicrotask(autosizeTextarea);
  });

  /** Insert a literal string at the cursor, with whitespace padding so
   * the insertion doesn't glue onto surrounding text. Used by both the
   * path-shaped fallback (`insertPathAtCursor`) and the terminal-style
   * attachment flow (`attachFileAtCursor`). Moves the caret to just
   * after the inserted text so typing continues naturally. */
  function insertAtCursor(literal: string): void {
    const el = textareaEl;
    if (!el) {
      promptText = promptText ? `${promptText} ${literal}` : literal;
      return;
    }
    const start = el.selectionStart ?? promptText.length;
    const end = el.selectionEnd ?? promptText.length;
    const before = promptText.slice(0, start);
    const after = promptText.slice(end);
    const leftPad = before && !/\s$/.test(before) ? ' ' : '';
    const rightPad = after && !/^\s/.test(after) ? ' ' : '';
    const insertion = `${leftPad}${literal}${rightPad}`;
    promptText = before + insertion + after;
    queueMicrotask(() => {
      if (!textareaEl) return;
      const pos = before.length + insertion.length;
      textareaEl.setSelectionRange(pos, pos);
      textareaEl.focus();
    });
  }

  /** Composer sidecar for terminal-style `[File N]` attachments. The
   * textarea carries only the token literals — the real path + display
   * metadata live here until send, where we forward both to the agent
   * so the SDK sees the path and the DB keeps the tokenised content.
   *
   * `nextAttachmentN` is monotonically increasing across the life of a
   * single compose-and-send. Deleting a token from the text does NOT
   * renumber the remaining ones; the send-time prune filters orphans
   * by referenced-N instead. This matches the terminal Claude Code
   * behaviour where `[File 1]` stays `[File 1]` even after edits. */
  let composerAttachments = $state<MessageAttachment[]>([]);
  let nextAttachmentN = $state(1);

  /** Attach a file to the composer: push a sidecar entry with a fresh
   * `n` and insert the matching `[File N]` token at the cursor.
   *
   * All three drop paths (URI, bytes-upload, native-picker) funnel
   * through here. When the caller doesn't know `filename` or
   * `sizeBytes` (URI / picker don't include them), we derive the
   * filename from the path's basename and default size to 0; the
   * chip renderer falls back to showing just the name in that case.
   *
   * Exported so the parent's `DragDropController` (constructed before
   * this component mounts) can dispatch into the composer once it's
   * available. */
  export function attachFileAtCursor(path: string, filename?: string, sizeBytes?: number): void {
    const n = nextAttachmentN;
    nextAttachmentN += 1;
    const baseName = filename ?? path.split('/').filter(Boolean).pop() ?? 'file';
    composerAttachments = [
      ...composerAttachments,
      { n, path, filename: baseName, size_bytes: sizeBytes ?? 0 },
    ];
    insertAtCursor(formatAttachmentToken(n));
  }

  /** Remove a composer attachment: drop the sidecar row AND strip
   * every `[File N]` occurrence from the textarea. Called from the
   * chip strip's `×` button and from the right-click → Remove action.
   * We don't renumber the surviving attachments — keeping `n` stable
   * matches the terminal Claude Code behaviour, and the send-time
   * prune already filters orphans so stray sidecar rows never leak to
   * the server. */
  function removeAttachment(n: number): void {
    composerAttachments = composerAttachments.filter((a) => a.n !== n);
    promptText = promptText.split(formatAttachmentToken(n)).join('');
  }

  /** Active sidecar chips — filter to attachments whose token is
   * actually still present in the text, so the composer chip strip
   * matches what the user can see above it. Kept as a derived value
   * so deletes update the strip without needing a manual sync on
   * every keystroke. */
  const activeComposerAttachments = $derived.by(() => {
    if (composerAttachments.length === 0) return [] as MessageAttachment[];
    const referenced = new Set<number>();
    const re = new RegExp(ATTACHMENT_TOKEN_REGEX.source, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(promptText)) !== null) referenced.add(Number(m[1]));
    return composerAttachments.filter((a) => referenced.has(a.n));
  });

  /** Browser-native file picker — a second affordance that doesn't
   * depend on the server's zenity/kdialog bridge OR the compositor's
   * drag-and-drop bridge. Works identically in every Chromium and
   * Firefox build, Wayland or X11. Complements the zenity button,
   * which is still useful because it honors `working_dir`. */
  let fileInputEl: HTMLInputElement | null = $state(null);

  function onBrowseClick(): void {
    fileInputEl?.click();
  }

  async function onFileInputChange(e: Event): Promise<void> {
    const target = e.currentTarget as HTMLInputElement;
    if (!target.files || target.files.length === 0) return;
    await dragdrop.uploadDroppedFiles(target.files);
    // Reset so picking the SAME file twice in a row re-fires `change`.
    // Without this the input's value is sticky and a repeat selection
    // is silently ignored.
    target.value = '';
  }

  // Upload button → native picker via `POST /api/fs/pick` (zenity on
  // GTK, kdialog on KDE). Bearings runs on the user's own machine, so
  // popping a dialog on their desktop is fair game and gives us the
  // absolute path directly — no sandboxing, no upload, no custom modal
  // to maintain. Multi-select: zenity supports it; paths come back
  // NUL-delimited and we inject them in order at the cursor.
  let picking = $state(false);

  async function onPickFile(): Promise<void> {
    if (picking) return;
    picking = true;
    try {
      const start = sessions.selected?.working_dir ?? null;
      const result = await fsApi.pickFile({
        start,
        multiple: true,
        title: 'Attach a file to the prompt',
      });
      if (result.cancelled) return;
      for (const p of result.paths) attachFileAtCursor(p);
    } catch (e) {
      conversation.error = e instanceof Error ? e.message : String(e);
    } finally {
      picking = false;
    }
  }

  // Phase 14 — `attachment.remove` action dispatches this event so the
  // composer chip's right-click menu can drop the chip without owning
  // a reference to `removeAttachment`. Phase 15 — `message.regenerate`
  // dispatches `bearings:composer-prefill` after navigating to the new
  // session; we seed the textarea so the user can re-run the boundary
  // user prompt against a fresh sdk_session_id.
  $effect(() => {
    function onAttachmentRemove(e: Event) {
      const detail = (e as CustomEvent<{ n: number }>).detail;
      if (typeof detail?.n === 'number') removeAttachment(detail.n);
    }
    function onComposerPrefill(e: Event) {
      const detail = (e as CustomEvent<{ sessionId: string; text: string }>).detail;
      if (!detail) return;
      // Only seed if we're rendering the destination session — a stale
      // dispatch into the wrong tab would clobber an unrelated draft.
      if (detail.sessionId !== sessions.selectedId) return;
      promptText = detail.text;
      queueMicrotask(() => textareaEl?.focus());
    }
    window.addEventListener('bearings:attachment-remove', onAttachmentRemove);
    window.addEventListener('bearings:composer-prefill', onComposerPrefill);
    return () => {
      window.removeEventListener('bearings:attachment-remove', onAttachmentRemove);
      window.removeEventListener('bearings:composer-prefill', onComposerPrefill);
    };
  });

  /** Forward the controller's paste handler — bound to the textarea
   * so a Ctrl+V with a file in the clipboard funnels into the same
   * upload pipeline the drop path uses. */
  function onPaste(e: ClipboardEvent): void {
    dragdrop.onPaste(e);
  }
</script>

{#if dragdrop.dropDiagnostic}
  <div
    class="flex items-start gap-2 border-t border-amber-900/50 bg-amber-950/40 px-4 py-2"
    data-testid="drop-diagnostic"
  >
    <pre
      class="flex-1 whitespace-pre-wrap font-mono text-[11px] text-amber-200">{dragdrop.dropDiagnostic}</pre>
    <button
      type="button"
      class="text-xs text-amber-400 hover:text-amber-200"
      aria-label="Dismiss drop diagnostic"
      onclick={() => (dragdrop.dropDiagnostic = null)}
    >
      ✕
    </button>
  </div>
{/if}

<form
  class="relative flex flex-col gap-2 border-t border-slate-800 px-4 py-3"
  onsubmit={(e) => {
    e.preventDefault();
    onSend();
  }}
>
  <CommandMenu
    bind:this={commandMenu}
    entries={commandEntries}
    query={commandQuery}
    open={commandMenuOpen}
    onSelect={onSelectCommand}
    onClose={onCloseCommandMenu}
  />
  <div class="flex items-end gap-2">
    <textarea
      class="flex-1 resize-none rounded border border-slate-800 bg-slate-950 px-3 py-2
        text-sm focus:border-slate-600 focus:outline-none disabled:opacity-50"
      rows="1"
      placeholder={sessions.selectedId
        ? 'Send a prompt (Enter · Shift+Enter for newline · / for commands · Ctrl+V to paste files)'
        : 'Select a session first'}
      bind:value={promptText}
      bind:this={textareaEl}
      onkeydown={onKeydown}
      oninput={onInput}
      onpaste={onPaste}
      disabled={!sessions.selectedId || agent.state !== 'open'}
    ></textarea>
    <button
      type="submit"
      class="rounded bg-emerald-600 px-3 py-2 text-sm hover:bg-emerald-500
        disabled:cursor-not-allowed disabled:opacity-50"
      disabled={!sessions.selectedId || agent.state !== 'open' || !promptText.trim()}
    >
      Send
    </button>
  </div>
  {#if activeComposerAttachments.length > 0}
    <div class="flex flex-wrap gap-1.5" data-testid="composer-attachments">
      {#each activeComposerAttachments as att (att.n)}
        <span
          class="inline-flex items-center gap-1.5 rounded border border-slate-700
            bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300"
          title={`${att.path}${att.size_bytes ? ' · ' + formatBytes(att.size_bytes) : ''}`}
          use:contextmenu={{
            target: {
              type: 'attachment',
              n: att.n,
              path: att.path,
              filename: att.filename,
              size_bytes: att.size_bytes,
              sessionId: sessions.selectedId,
              messageId: null,
            },
          }}
        >
          <span class="text-slate-500">[File {att.n}]</span>
          <span class="max-w-[220px] truncate">{att.filename}</span>
          {#if att.size_bytes}
            <span class="text-slate-500">·</span>
            <span class="text-slate-500">{formatBytes(att.size_bytes)}</span>
          {/if}
          <button
            type="button"
            class="ml-0.5 text-slate-500 hover:text-slate-200"
            aria-label={`Remove [File ${att.n}]`}
            onclick={() => removeAttachment(att.n)}
          >
            ✕
          </button>
        </span>
      {/each}
    </div>
  {/if}
  <div class="flex items-center gap-2">
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded border border-slate-800
        bg-slate-900 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-600
        hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
      onclick={onPickFile}
      disabled={!sessions.selectedId || picking}
      title="Attach a file path via native dialog (honors session working dir)"
      data-testid="attach-file"
    >
      <span aria-hidden="true">📎</span>
      <span>{picking ? 'Picking…' : 'Attach file'}</span>
    </button>
    <button
      type="button"
      class="inline-flex items-center gap-1.5 rounded border border-slate-800
        bg-slate-900 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-600
        hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
      onclick={onBrowseClick}
      disabled={!sessions.selectedId || dragdrop.uploading}
      title="Browse via the browser's file picker (no compositor deps)"
      data-testid="browse-file"
    >
      <span aria-hidden="true">📁</span>
      <span>{dragdrop.uploading ? 'Uploading…' : 'Browse'}</span>
    </button>
    <input
      type="file"
      multiple
      bind:this={fileInputEl}
      onchange={onFileInputChange}
      class="hidden"
      data-testid="file-input"
    />
    <span class="text-[10px] text-slate-500"> or drag · Ctrl+V to paste files </span>
  </div>
</form>
