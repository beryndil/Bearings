<script lang="ts">
  /**
   * One tool-call drawer row — header (name + elapsed + status pip)
   * plus the streaming output area.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/chat.md`` §"What a message turn looks like" —
   *   the tool-work drawer enumerates one row per tool call.
   * - ``docs/behavior/tool-output-streaming.md`` §"When output begins
   *   streaming" — output streams in as it arrives; the row never
   *   blocks behind a spinner; the elapsed-time readout is the live
   *   signal.
   * - §"Very-long-output truncation rules" — past the soft cap the
   *   middle is folded inside an inline expander; the head/tail
   *   bookends remain interactive. (The store applies the soft cap on
   *   ``output``; the row exposes ``rawLength`` so the user sees the
   *   elided count.) M-6.
   * - §"ANSI passthrough" — ANSI color escape sequences in Bash tool
   *   output are converted to HTML color spans via ``ansi-to-html``
   *   and sanitized with DOMPurify. M-5.
   * - §"Partial-output behavior on tool failure" — a failed call
   *   keeps the partial output visible and appends an error block.
   * - §"Long-tool keepalive" — keepalive ticks update
   *   ``liveElapsedMs``; the readout uses it during in-flight, then
   *   freezes on ``durationMs`` once ``done``.
   * - ``docs/behavior/context-menus.md`` §"Tool call" — right-click
   *   opens ``MENU_TARGET_TOOL_CALL`` with copy-name / copy-input /
   *   copy-output / copy-id handlers (G5).
   */
  import {
    CHAT_TOOL_OUTPUT_HEAD_CHARS,
    CHAT_TOOL_OUTPUT_TAIL_CHARS,
    CONVERSATION_STRINGS,
    MENU_ACTION_TOOL_CALL_COPY_ID,
    MENU_ACTION_TOOL_CALL_COPY_INPUT,
    MENU_ACTION_TOOL_CALL_COPY_NAME,
    MENU_ACTION_TOOL_CALL_COPY_OUTPUT,
    MENU_ACTION_TOOL_CALL_DEBUG,
    MENU_ACTION_TOOL_CALL_EDIT_INPUT,
    MENU_ACTION_TOOL_CALL_RETRY,
    MENU_TARGET_TOOL_CALL,
  } from "../../config";
  import { contextMenu } from "../../actions/contextMenu";
  import { sendPrompt } from "../../api/prompt";
  import { ansiToHtml } from "../../ansi";
  import { linkifyToHtml } from "../../linkify";
  import { sanitizeHtml } from "../../sanitize";
  import CollapsibleBody from "../common/CollapsibleBody.svelte";
  import type { ToolCallView } from "../../stores/conversation.svelte";

  interface Props {
    call: ToolCallView;
    /**
     * Absolute working directory of the active session, forwarded from
     * ``Conversation.svelte`` via ``MessageTurn.svelte``. When provided,
     * workspace-relative paths in the tool output (e.g.
     * ``src/bearings/agent/runner.py``) resolve against this root and
     * render as clickable ``data-link-kind="file"`` anchors.  When
     * ``null`` only absolute paths and explicit URLs become anchors.
     *
     * Per ``docs/behavior/tool-output-streaming.md``
     * §"Clickable file paths and URLs in output" (gap-cycle-06-004).
     */
    workingDir?: string | null;
    /**
     * The session this tool call belongs to. Forwarded from
     * ``MessageTurn.svelte`` → ``ToolOutput.svelte`` to enable the
     * T1-07 retry action (``POST /api/sessions/{id}/prompt``). When
     * absent, retry is disabled.
     */
    sessionId?: string | null;
  }

  const { call, workingDir = null, sessionId = null }: Props = $props();

  // ---- T1-07 debug drawer + edit input state ----------------------------------

  /** True when the raw JSON debug drawer is expanded. */
  let debugOpen = $state(false);
  /** True when the inline edit-input textarea is open. */
  let editInputOpen = $state(false);
  let editInputDraft = $state("");

  /**
   * M-6: whether the middle fold is expanded by the user.  Starts
   * ``false``; toggled by the "Show full output" button.  Resets to
   * ``false`` when the tool call changes (reactive via ``$derived``).
   */
  let foldExpanded = $state(false);

  function openEditInput(): void {
    editInputDraft = prettyJson(call.inputJson);
    editInputOpen = true;
  }

  function cancelEditInput(): void {
    editInputOpen = false;
  }

  async function submitEditInput(): Promise<void> {
    if (sessionId === null || editInputDraft.trim().length === 0) return;
    // Validate the edited JSON before sending.
    try {
      JSON.parse(editInputDraft);
    } catch {
      return; // invalid JSON — don't send
    }
    editInputOpen = false;
    await sendPrompt(
      sessionId,
      `Retry ${call.name} with this input:\n\`\`\`json\n${editInputDraft}\n\`\`\``,
    );
  }

  // ---- context-menu handlers -------------------------------------------------

  const menuHandlers = $derived({
    /** Copy the tool name (e.g. ``Bash``, ``Read``) to the clipboard. */
    [MENU_ACTION_TOOL_CALL_COPY_NAME]: () => {
      void navigator.clipboard.writeText(call.name);
    },

    /** Copy the raw tool-input JSON to the clipboard. */
    [MENU_ACTION_TOOL_CALL_COPY_INPUT]: () => {
      void navigator.clipboard.writeText(call.inputJson);
    },

    /**
     * Copy the streamed / truncated output text to the clipboard.
     * Disabled with tooltip while the tool is still running —
     * matches ``docs/behavior/context-menus.md`` §"Disabled entries".
     *
     * When the output is folded, copies head + tail (the full persisted
     * portion); the hidden middle is not available in the store.
     */
    [MENU_ACTION_TOOL_CALL_COPY_OUTPUT]: call.done
      ? () => {
          const text = call.isFolded ? call.outputHead + call.output : call.output;
          void navigator.clipboard.writeText(text);
        }
      : { disabledReason: "No output yet — the tool is still running" },

    /** Copy the tool-call ID.  Advanced action. */
    [MENU_ACTION_TOOL_CALL_COPY_ID]: () => {
      void navigator.clipboard.writeText(call.id);
    },

    /**
     * T1-07 — retry: POST a prompt to the session asking the agent to
     * re-invoke the tool with the same input. Disabled when no sessionId.
     */
    [MENU_ACTION_TOOL_CALL_RETRY]:
      sessionId !== null
        ? () => {
            void sendPrompt(
              sessionId,
              `Please retry the ${call.name} tool call with the same input: \`\`\`json\n${call.inputJson}\n\`\`\``,
            ).catch((err: unknown) => {
              console.error("Retry tool call failed:", err);
            });
          }
        : { disabledReason: "No session context — retry unavailable" },

    /**
     * T1-07 — edit input: open the inline edit textarea with the current
     * input JSON pre-filled. Disabled when no sessionId.
     */
    [MENU_ACTION_TOOL_CALL_EDIT_INPUT]:
      sessionId !== null
        ? () => openEditInput()
        : { disabledReason: "No session context — edit input unavailable" },

    /**
     * T1-07 — debug: toggle the raw JSON debug drawer below the output.
     */
    [MENU_ACTION_TOOL_CALL_DEBUG]: () => {
      debugOpen = !debugOpen;
    },
  });

  // ---- live elapsed clock ---------------------------------------------------
  //
  // While the tool is in flight we need the elapsed counter to tick every
  // second even when the backend's ``tool_progress`` keepalive only arrives
  // every TOOL_PROGRESS_INTERVAL_S (2 s).  A local ``setInterval`` advances
  // ``nowMs`` once per second while ``!call.done``; the effect cleans up the
  // interval automatically when the call completes or the component unmounts.
  // ``liveElapsedMs`` (from the last ``tool_progress`` frame) floors the
  // local computation, which prevents a briefly-throttled setInterval (e.g.
  // backgrounded tab) from showing a value smaller than the server's
  // authoritative tick once the tab regains focus.

  let nowMs = $state(Date.now());

  $effect(() => {
    if (call.done) return;
    const id = setInterval(() => {
      nowMs = Date.now();
    }, 1000);
    return () => {
      clearInterval(id);
    };
  });

  const elapsedMs = $derived(
    call.done && call.durationMs !== null
      ? call.durationMs
      : Math.max(nowMs - call.startedAt, call.liveElapsedMs),
  );
  const elapsedLabel = $derived(formatElapsed(elapsedMs));

  /**
   * Number of characters elided in the hard-cap truncation (past the
   * persistence cap, not the soft-cap fold).  Zero for normal outputs.
   * Rendered as a "[truncated — more bytes elided]" annotation.
   *
   * Note: when the middle fold is active, ``call.output`` is the tail
   * portion only (``TAIL_CHARS``), so the visible count compares against
   * HEAD + TAIL rather than just output.length.
   */
  const hardCapElidedCount = $derived(
    call.isFolded
      ? Math.max(
          0,
          call.rawLength - CHAT_TOOL_OUTPUT_HEAD_CHARS - CHAT_TOOL_OUTPUT_TAIL_CHARS,
        )
      : Math.max(0, call.rawLength - call.output.length),
  );

  /**
   * Characters hidden by the middle fold (between head and tail).
   * Zero when not folded or when the user has expanded the fold.
   */
  const middleFoldCount = $derived(
    call.isFolded && !foldExpanded
      ? Math.max(
          0,
          call.rawLength - CHAT_TOOL_OUTPUT_HEAD_CHARS - CHAT_TOOL_OUTPUT_TAIL_CHARS,
        )
      : 0,
  );

  const statusLabel = $derived(
    call.done
      ? call.ok === false
        ? CONVERSATION_STRINGS.toolStatusError
        : CONVERSATION_STRINGS.toolStatusOk
      : CONVERSATION_STRINGS.toolStatusRunning,
  );

  function formatElapsed(ms: number): string {
    if (ms < 1000) {
      return `00:00`;
    }
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${pad2(min)}:${pad2(sec)}`;
  }

  function pad2(n: number): string {
    return n < 10 ? `0${n}` : String(n);
  }

  /**
   * Return ``raw`` pretty-printed with 2-space indent, or ``raw`` verbatim
   * if it is not valid JSON (defensive fall-back per gap-cycle-16-002).
   *
   * ``JSON.stringify(JSON.parse(raw), null, 2)`` mirrors v17's
   * ``inputPretty: JSON.stringify(parsedInput, null, 2)`` from the v17
   * reducer.  Compact-by-nature payloads (e.g. ``{}``) stringify back to
   * a single line, matching the v17 behaviour exactly.
   */
  function prettyJson(raw: string): string {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2) as string;
    } catch {
      return raw;
    }
  }

  /**
   * Pretty-printed version of ``call.inputJson``, computed once (Svelte
   * ``$derived`` only re-runs when the source dependency changes, and
   * ``call.inputJson`` is set once at ``tool_call_start`` / hydration and
   * never mutated thereafter).  Streaming ``tool_output_delta`` events do
   * not re-trigger the parse+stringify — per gap-cycle-16-002
   * acceptance criterion (2b).
   */
  const inputPretty = $derived(prettyJson(call.inputJson));

  /**
   * Render a raw tool-output text segment to safe HTML.
   *
   * M-5 pipeline: if the text contains ANSI color escape sequences,
   * ``ansiToHtml`` converts them to ``<span style="color:…">`` elements
   * (with ``escapeXML: true`` for XSS safety) and the result is passed
   * to DOMPurify.  For text without ANSI sequences the existing
   * ``linkifyToHtml → sanitizeHtml`` pipeline applies (clickable paths/URLs).
   *
   * The two pipelines are mutually exclusive in v1: ANSI-colored output
   * does not receive path/URL linkification, and vice-versa.
   */
  function renderSegment(text: string): string {
    const ansiHtml = ansiToHtml(text);
    if (ansiHtml !== null) {
      return sanitizeHtml(ansiHtml);
    }
    return sanitizeHtml(
      linkifyToHtml(text, { workingDir: workingDir ?? undefined }),
    );
  }
</script>

<details
  class="tool-output mb-2 rounded border border-border bg-surface-0"
  data-testid="tool-output"
  use:contextMenu={{
    target: MENU_TARGET_TOOL_CALL,
    handlers: menuHandlers,
    data: { toolCallId: call.id },
  }}
>
  <summary
    class="flex cursor-pointer items-center gap-2 px-2 py-1.5 font-mono text-xs"
    data-testid="tool-output-summary"
  >
    <span class="text-fg-muted">$</span>
    <span class="font-medium text-fg-strong" data-testid="tool-output-name">{call.name}</span>
    <span
      class="ml-auto inline-flex items-center gap-1.5 font-mono text-fg-muted"
      data-testid="tool-output-elapsed"
    >
      <span
        class="inline-block h-1.5 w-1.5 rounded-full"
        class:bg-accent={call.done && call.ok === true}
        class:bg-red-400={call.done && call.ok === false}
        class:bg-fg-muted={!call.done}
        data-testid="tool-output-status-pip"
        aria-label={statusLabel}
      ></span>
      {elapsedLabel}
    </span>
  </summary>
  <div
    class="tool-output__body border-t border-border px-2 py-2 text-xs"
    data-testid="tool-output-body"
  >
    <CollapsibleBody>
      <pre
        class="whitespace-pre-wrap break-words font-mono text-fg-muted"
        data-testid="tool-output-input">{inputPretty}</pre>
    </CollapsibleBody>
    {#if call.output.length === 0 && !call.done}
      <p class="mt-2 text-fg-muted" data-testid="tool-output-empty">
        {CONVERSATION_STRINGS.toolStatusRunning}…
      </p>
    {:else if call.isFolded && !foldExpanded}
      <!--
        M-6: two-tier middle-fold — head + fold banner + tail.
        The head is rendered first, then the interactive fold banner,
        then the tail.  Both bookends are individually wrapped in a
        CollapsibleBody so very long heads/tails don't dominate the viewport.
      -->
      <!-- eslint-disable svelte/no-at-html-tags -->
      <CollapsibleBody class="mt-2">
        <pre
          class="whitespace-pre-wrap break-words font-mono text-fg"
          data-testid="tool-output-head">{@html renderSegment(call.outputHead)}</pre>
      </CollapsibleBody>
      <div
        class="my-1 flex items-center gap-1 font-mono text-fg-muted"
        data-testid="tool-output-fold-banner"
        aria-label={CONVERSATION_STRINGS.toolOutputFoldBanner(middleFoldCount)}
      >
        <span class="italic"
          >{CONVERSATION_STRINGS.toolOutputFoldBanner(middleFoldCount)}</span
        ><button
          type="button"
          class="rounded bg-surface-2 px-1.5 py-0.5 text-xs text-fg-strong hover:bg-surface-3 focus:outline-none focus:ring-1 focus:ring-accent/60"
          onclick={() => {
            foldExpanded = true;
          }}
          data-testid="tool-output-show-full">{CONVERSATION_STRINGS.toolOutputShowFull}</button
        >
      </div>
      <CollapsibleBody>
        <pre
          class="whitespace-pre-wrap break-words font-mono text-fg"
          data-testid="tool-output-tail">{@html renderSegment(call.output)}</pre>
      </CollapsibleBody>
      <!-- eslint-enable svelte/no-at-html-tags -->
    {:else}
      <!--
        Normal path (not folded, or fold expanded).  When the fold has been
        expanded, render head + tail concatenated so the full persisted
        content is visible without the fold UI.
      -->
      <!-- eslint-disable svelte/no-at-html-tags -->
      <CollapsibleBody class="mt-2">
        <pre
          class="whitespace-pre-wrap break-words font-mono text-fg"
          data-testid="tool-output-stream">{@html renderSegment(
            call.isFolded ? call.outputHead + call.output : call.output,
          )}</pre>
      </CollapsibleBody>
      <!-- eslint-enable svelte/no-at-html-tags -->
    {/if}
    {#if hardCapElidedCount > 0}
      <p class="mt-1 italic text-fg-muted" data-testid="tool-output-truncated">
        {CONVERSATION_STRINGS.truncationLabel} ({hardCapElidedCount} chars elided)
      </p>
    {/if}
    {#if call.done && call.ok === false && call.errorMessage !== null}
      <p
        class="mt-2 rounded border border-red-500 px-2 py-1 text-red-400"
        data-testid="tool-output-error"
      >
        Error: {call.errorMessage}
      </p>
    {/if}
    {#if debugOpen}
      <!-- T1-07 debug drawer — raw input + output JSON -->
      <div
        class="mt-2 rounded border border-border bg-surface-2 p-2 font-mono text-xs"
        data-testid="tool-output-debug-drawer"
      >
        <p class="mb-1 text-fg-muted">Raw input JSON:</p>
        <pre class="whitespace-pre-wrap break-words text-fg">{call.inputJson}</pre>
        {#if call.done}
          <p class="mb-1 mt-2 text-fg-muted">Raw output:</p>
          <pre class="whitespace-pre-wrap break-words text-fg"
            >{call.isFolded ? call.outputHead + call.output : call.output}</pre>
        {/if}
      </div>
    {/if}
    {#if editInputOpen}
      <!-- T1-07 edit input textarea -->
      <div class="mt-2 flex flex-col gap-1" data-testid="tool-output-edit-input">
        <textarea
          class="w-full rounded border border-accent/60 bg-surface-1 p-2 font-mono text-xs text-fg-strong focus:outline-none focus:ring-1 focus:ring-accent/60"
          rows="6"
          bind:value={editInputDraft}
          data-testid="tool-output-edit-input-textarea"
        ></textarea>
        <div class="flex justify-end gap-2">
          <button
            type="button"
            class="rounded px-2 py-0.5 text-xs text-fg-muted hover:bg-surface-2 hover:text-fg-strong"
            onclick={cancelEditInput}
            data-testid="tool-output-edit-input-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded bg-accent/20 px-2 py-0.5 text-xs text-fg-strong hover:bg-accent/30 disabled:opacity-50"
            onclick={() => void submitEditInput()}
            disabled={sessionId === null}
            data-testid="tool-output-edit-input-submit"
          >
            Retry with edited input
          </button>
        </div>
      </div>
    {/if}
  </div>
</details>
