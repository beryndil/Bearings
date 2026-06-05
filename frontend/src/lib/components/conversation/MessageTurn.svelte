<script lang="ts">
  /**
   * One user/assistant turn — user bubble, optional tool-work
   * drawer, assistant bubble, routing badge, error block.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/chat.md`` §"What a message turn looks like" —
   *   the per-row anatomy: user bubble, tool drawer, assistant
   *   bubble, routing badge.
   * - ``docs/behavior/chat.md`` §"Conversation rendering" — markdown
   *   bodies render via CommonMark + GFM; the rendered HTML flows
   *   through :func:`sanitizeHtml` before insertion.
   * - ``docs/behavior/tool-output-streaming.md`` §"When output
   *   begins streaming" — the drawer above the assistant bubble
   *   expands per row.
   * - ``docs/behavior/chat.md`` §"Error states" — assistant bubble
   *   closes with a red error block when the agent emits an
   *   error event mid-turn.
   * - ``docs/behavior/context-menus.md`` §"Message bubble" — nine
   *   context-menu actions wired via ``use:contextMenu`` (G3).
   *
   * The component is presentational: receives a ``MessageTurnView``
   * and renders it. The reducer produces these views; the parent
   * Conversation component iterates the list.
   */
  import {
    CONTEXT_MENU_STRINGS,
    CONVERSATION_STRINGS,
    MENU_ACTION_MESSAGE_COPY_AS_MARKDOWN,
    MENU_ACTION_MESSAGE_COPY_CODE,
    MENU_ACTION_MESSAGE_COPY_CONTENT,
    MENU_ACTION_MESSAGE_COPY_ID,
    MENU_ACTION_MESSAGE_COPY_JSON,
    MENU_ACTION_MESSAGE_DELETE,
    MENU_ACTION_MESSAGE_EDIT,
    MENU_ACTION_MESSAGE_FORK_FROM_HERE,
    MENU_ACTION_MESSAGE_HIDE_FROM_CONTEXT,
    MENU_ACTION_MESSAGE_JUMP_TO_TURN,
    MENU_ACTION_MESSAGE_MOVE_TO_SESSION,
    MENU_ACTION_MESSAGE_MULTI_SELECT_COPY,
    MENU_ACTION_MESSAGE_MULTI_SELECT_DELETE,
    MENU_ACTION_MESSAGE_MULTI_SELECT_HIDE,
    MENU_ACTION_MESSAGE_MULTI_SELECT_PIN,
    MENU_ACTION_MESSAGE_PIN,
    MENU_ACTION_MESSAGE_REGENERATE,
    MENU_ACTION_MESSAGE_REGENERATE_IN_PLACE,
    MENU_ACTION_MESSAGE_SPLIT_HERE,
    MENU_TARGET_MESSAGE,
    MENU_TARGET_MESSAGE_MULTI_SELECT,
  } from "../../config";
  import { regenerateFromMessage, spawnFromReply } from "../../api/sessions";
  import { goto } from "$app/navigation";
  import { contextMenu } from "../../actions/contextMenu";
  import { markdownContextMenu } from "../../actions/markdownContextMenu";
  import { createCheckpoint, forkCheckpoint } from "../../api/checkpoints";
  import {
    deleteMessage,
    patchMessageContent,
    patchMessageHidden,
    patchMessagePinned,
  } from "../../api/messages";
  import { regenerateSession } from "../../api/sessions";
  import { linkifyToHtml } from "../../linkify";
  import { renderMarkdown } from "../../render";
  import { sanitizeHtml } from "../../sanitize";
  import { bumpCheckpointRefresh } from "../../stores/checkpointBus.svelte";
  import { conversationStore, type MessageTurnView } from "../../stores/conversation.svelte";
  import {
    clearMessageSelection,
    messageMultiSelectionStore,
    toggleMessageId,
  } from "../../stores/messageMultiSelectionStore.svelte";
  import { reorgStore } from "../../stores/reorg.svelte";
  import { scrollBehavior } from "../../utils/motion";
  import CollapsibleBody from "../common/CollapsibleBody.svelte";
  import ConfirmDialog from "../sidebar/ConfirmDialog.svelte";
  import RoutingBadge from "./RoutingBadge.svelte";
  import ReplyActionPreview from "./ReplyActionPreview.svelte";
  import SentAttachmentChips from "./SentAttachmentChips.svelte";
  import ToolOutput from "./ToolOutput.svelte";

  interface Props {
    turn: MessageTurnView;
    sessionId?: string | null;
    onAskForMoreDetail?: () => void;
    /**
     * ``true`` when this assistant turn is the last one in the
     * conversation list. When ``true`` the "Regenerate from this message…"
     * context-menu entry is suppressed — the top-level "Regenerate"
     * covers that case. Only meaningful for ``role="assistant"`` turns;
     * ignored on user turns.
     *
     * Per ``docs/behavior/chat.md`` §"Regenerate from here"
     * (gap-cycle-03-006).
     */
    isLastAssistantTurn?: boolean;
    /**
     * Number of turns in the conversation list that come after this turn.
     * Used to compute the discard-count shown in the confirmation dialog.
     * Includes the current turn's subsequent turns only, not the current
     * turn itself (the clicked assistant turn is also discarded, so the
     * dialog shows ``turnsAfterCount + 1`` total).
     */
    turnsAfterCount?: number;
    /**
     * ``true`` when the current session is paired to a checklist item.
     * When ``true`` the **＋ SPAWN** pill is suppressed — paired chats
     * are "work chat" surfaces; spawning a new reply-thread from inside
     * a paired chat is not part of the paired-chats behavior spec
     * (gap-cycle-03-007).
     */
    isPaired?: boolean;
    /**
     * Absolute working directory of the active session.  Forwarded to
     * each ``ToolOutput`` row so workspace-relative paths in tool output
     * (e.g. ``src/bearings/agent/runner.py``) become clickable
     * ``data-link-kind="file"`` anchors.  Plumbed from
     * ``Conversation.svelte`` via the sessions store.
     *
     * Per ``docs/behavior/tool-output-streaming.md``
     * §"Clickable file paths and URLs in output" (gap-cycle-06-004).
     */
    workingDir?: string | null;
  }

  const {
    turn,
    sessionId,
    onAskForMoreDetail,
    isLastAssistantTurn = false,
    turnsAfterCount = 0,
    isPaired = false,
    workingDir = null,
  }: Props = $props();

  /**
   * True when this turn's ``id`` is no longer present in
   * ``conversationStore.turns`` — meaning it was removed (e.g. via a
   * paired-chats reorg or a WS-driven deletion) between the user
   * pressing the mouse button and the ``contextmenu`` event firing.
   * Passed to ``use:contextMenu`` so the menu opens with every action
   * greyed and the stale-target caption per
   * ``docs/behavior/context-menus.md`` §"Failure modes".
   */
  const isTurnStale = $derived(!conversationStore.turns.some((t) => t.id === turn.id));

  function handleAskForMoreDetail(): void {
    onAskForMoreDetail?.();
  }

  async function handleRegenerate(): Promise<void> {
    if (sessionId === null || sessionId === undefined) return;
    try {
      await regenerateSession(sessionId);
      // Toast feedback handled by the API consumer or parent component
    } catch (err) {
      console.error("Regenerate failed:", err);
    }
  }

  async function handleRegenerateFrom(): Promise<void> {
    if (sessionId === null || sessionId === undefined) return;
    try {
      await regenerateFromMessage(sessionId, turn.id);
    } catch (err) {
      console.error("Regenerate from here failed:", err);
    }
  }

  /**
   * Spawn a new paired chat seeded with a blockquote of this assistant
   * message, then navigate to the new chat (gap-cycle-03-007).  The call
   * is idempotent — a second click returns the already-spawned session
   * and navigates to it without creating a duplicate.
   */
  async function handleSpawn(): Promise<void> {
    if (sessionId === null || sessionId === undefined) return;
    try {
      const result = await spawnFromReply(sessionId, turn.id);
      await goto(`/sessions/${encodeURIComponent(result.chat_session_id)}`);
    } catch (err) {
      console.error("Spawn from reply failed:", err);
    }
  }

  // ---- context-menu action state -----------------------------------------

  let showDeleteConfirm = $state(false);
  /**
   * Controls the "discard N messages?" confirmation dialog for
   * "Regenerate from this message…" (gap-cycle-03-006).
   */
  let showRegenerateFromConfirm = $state(false);

  // ---- T1-05 inline edit state -------------------------------------------

  /** True when the inline edit textarea is open. User-role messages only. */
  let editActive = $state(false);
  /** Current value of the edit textarea — initialised to turn.body on open. */
  let editDraft = $state("");
  let editSaving = $state(false);
  let editError = $state<string | null>(null);

  function openEdit(): void {
    editDraft = turn.body;
    editError = null;
    editActive = true;
  }

  function cancelEdit(): void {
    editActive = false;
    editError = null;
  }

  async function saveEdit(): Promise<void> {
    if (editDraft.trim().length === 0) return;
    editSaving = true;
    editError = null;
    try {
      await patchMessageContent(turn.id, editDraft);
      editActive = false;
    } catch (err) {
      editError = err instanceof Error ? err.message : "Save failed.";
    } finally {
      editSaving = false;
    }
  }

  // ---- T2-12 message multi-select ----------------------------------------

  /**
   * True when this message is part of the current multi-selection.
   * The context menu target switches to MENU_TARGET_MESSAGE_MULTI_SELECT
   * when any messages are selected.
   */
  const isSelected = $derived(messageMultiSelectionStore.ids.has(turn.id));
  const hasSelection = $derived(messageMultiSelectionStore.ids.size > 0);

  function handleClick(event: MouseEvent): void {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      toggleMessageId(turn.id);
    } else if (hasSelection && !event.shiftKey) {
      // Plain click clears the selection when one exists (unless Shift is
      // being used for text selection).
      clearMessageSelection();
    }
  }

  /**
   * Helpers for extracting code blocks and JSON from the message body (T2-11).
   */
  function extractCodeBlocks(body: string): string {
    const blocks: string[] = [];
    const re = /```(?:[^\n]*)?\n([\s\S]*?)```/g;
    let match: RegExpExecArray | null;
    while ((match = re.exec(body)) !== null) {
      blocks.push(match[1]);
    }
    return blocks.join("\n---\n");
  }

  function extractJson(body: string): string {
    const pieces: string[] = [];
    // Inline fenced JSON blocks first.
    const fenceRe = /```(?:json)?\n([\s\S]*?)```/gi;
    let m: RegExpExecArray | null;
    while ((m = fenceRe.exec(body)) !== null) {
      const candidate = m[1].trim();
      try {
        JSON.parse(candidate);
        pieces.push(candidate);
      } catch {
        // not valid JSON — skip
      }
    }
    // Bare JSON objects/arrays (heuristic: starts with { or [).
    const bareRe = /([{[][^]*?[}\]])/g;
    while ((m = bareRe.exec(body)) !== null) {
      const candidate = m[1].trim();
      try {
        JSON.parse(candidate);
        if (!pieces.includes(candidate)) pieces.push(candidate);
      } catch {
        // not valid JSON — skip
      }
    }
    return pieces.join("\n---\n");
  }

  // ---- context-menu handlers ---------------------------------------------

  const menuHandlers = $derived({
    /** Scroll the element into view. */
    [MENU_ACTION_MESSAGE_JUMP_TO_TURN]: () => {
      const el = document.querySelector(`[data-turn-id="${CSS.escape(turn.id)}"]`);
      el?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
    },

    /** Copy the plain-text message body to the clipboard. */
    [MENU_ACTION_MESSAGE_COPY_CONTENT]: () => {
      void navigator.clipboard.writeText(turn.body);
    },

    /**
     * Copy the message as Markdown with role + timestamp header.
     * Advanced action — Shift+right-click only.
     */
    [MENU_ACTION_MESSAGE_COPY_AS_MARKDOWN]: () => {
      const header = `**${turn.role}** (${turn.createdAt})\n\n`;
      void navigator.clipboard.writeText(header + turn.body);
    },

    /** Copy the message ID. Advanced action. */
    [MENU_ACTION_MESSAGE_COPY_ID]: () => {
      void navigator.clipboard.writeText(turn.id);
    },

    /**
     * T2-11 — copy all fenced code blocks as plain text (concatenated
     * with ``---`` separators). Enabled only when the body contains at
     * least one code block.
     */
    [MENU_ACTION_MESSAGE_COPY_CODE]: () => {
      const extracted = extractCodeBlocks(turn.body);
      if (extracted.length > 0) void navigator.clipboard.writeText(extracted);
    },

    /**
     * T2-11 — copy all valid JSON objects/arrays found in the message
     * body (fenced blocks + bare JSON heuristic). No-op when none found.
     */
    [MENU_ACTION_MESSAGE_COPY_JSON]: () => {
      const extracted = extractJson(turn.body);
      if (extracted.length > 0) void navigator.clipboard.writeText(extracted);
    },

    /**
     * T1-05 — inline edit (user-role messages only). Disabled via
     * ``disabledReason`` for assistant/system roles.
     */
    ...(turn.role === "user"
      ? { [MENU_ACTION_MESSAGE_EDIT]: () => openEdit() }
      : {
          [MENU_ACTION_MESSAGE_EDIT]: {
            disabledReason: "Only user messages can be edited",
          },
        }),

    /** Pin the message bubble to the conversation header. */
    [MENU_ACTION_MESSAGE_PIN]: () => {
      void patchMessagePinned(turn.id, true).catch((err) => {
        console.error("Pin message failed:", err);
      });
    },

    /**
     * Hide the message from the context window so it is excluded from
     * the next prompt. Advanced action.
     */
    [MENU_ACTION_MESSAGE_HIDE_FROM_CONTEXT]: () => {
      void patchMessageHidden(turn.id, true).catch((err) => {
        console.error("Hide message failed:", err);
      });
    },

    /**
     * Move the message to another session — opens the ReorgPicker in
     * "move" mode (gap-cycle-01-013).
     */
    [MENU_ACTION_MESSAGE_MOVE_TO_SESSION]: () => {
      if (sessionId === null || sessionId === undefined) return;
      reorgStore.openPicker({
        mode: "move",
        messageId: turn.id,
        sourceSessionId: sessionId,
        seq: turn.seq,
      });
    },

    /**
     * Split the conversation at this message — opens the ReorgPicker in
     * "split" mode (gap-cycle-01-013).  The picker lets the user choose
     * a destination; all messages at or after this ``seq`` are moved.
     */
    [MENU_ACTION_MESSAGE_SPLIT_HERE]: () => {
      if (sessionId === null || sessionId === undefined) return;
      reorgStore.openPicker({
        mode: "split",
        messageId: turn.id,
        sourceSessionId: sessionId,
        seq: turn.seq,
      });
    },

    /**
     * Fork a new session from this message onward (G6) — create a
     * checkpoint here, then immediately fork it. Navigates to the new
     * session on success. Per ``docs/behavior/context-menus.md``
     * §"Message bubble" + §"Checkpoint (gutter chip)".
     */
    [MENU_ACTION_MESSAGE_FORK_FROM_HERE]: () => {
      if (sessionId === null || sessionId === undefined) return;
      void (async () => {
        try {
          const cp = await createCheckpoint({ sessionId, messageId: turn.id });
          bumpCheckpointRefresh();
          const result = await forkCheckpoint(cp.id);
          await goto(`/sessions/${encodeURIComponent(result.new_session_id)}`);
        } catch (err) {
          console.error("fork-from-here failed:", err);
        }
      })();
    },

    // "Regenerate from this message…" — fires the /regenerate_from/{id}
    // endpoint which truncates and re-queues. Only active on non-last
    // assistant turns; on the last assistant turn the existing plain
    // "Regenerate" action covers the same need without truncation.
    // Per docs/behavior/chat.md §"Regenerate from here" (gap-cycle-03-006).
    ...(turn.role === "assistant" && !isLastAssistantTurn
      ? {
          [MENU_ACTION_MESSAGE_REGENERATE]: () => {
            showRegenerateFromConfirm = true;
          },
        }
      : {}),

    // "Regenerate (rewrite in place)" — replays the latest user message
    // via the plain /regenerate endpoint (no truncation).
    [MENU_ACTION_MESSAGE_REGENERATE_IN_PLACE]: () => void handleRegenerate(),

    /** Show the delete confirmation dialog. Advanced + destructive action. */
    [MENU_ACTION_MESSAGE_DELETE]: {
      handler: () => {
        showDeleteConfirm = true;
      },
      skipMenuConfirm: true,
    },
  });

  async function handleDeleteConfirm(): Promise<void> {
    showDeleteConfirm = false;
    try {
      await deleteMessage(turn.id);
    } catch (err) {
      console.error("Delete message failed:", err);
    }
  }

  // ---- T2-12 multi-select context menu handlers --------------------------

  const multiSelectMenuHandlers = $derived({
    [MENU_ACTION_MESSAGE_MULTI_SELECT_COPY]: () => {
      const ids = [...messageMultiSelectionStore.ids];
      const turns = conversationStore.turns.filter((t) => ids.includes(t.id));
      const text = turns.map((t) => `**${t.role}**: ${t.body}`).join("\n\n---\n\n");
      void navigator.clipboard.writeText(text);
    },
    [MENU_ACTION_MESSAGE_MULTI_SELECT_PIN]: () => {
      for (const id of messageMultiSelectionStore.ids) {
        void patchMessagePinned(id, true).catch((err) => {
          console.error("Pin message failed:", err);
        });
      }
      clearMessageSelection();
    },
    [MENU_ACTION_MESSAGE_MULTI_SELECT_HIDE]: () => {
      for (const id of messageMultiSelectionStore.ids) {
        void patchMessageHidden(id, true).catch((err) => {
          console.error("Hide message failed:", err);
        });
      }
      clearMessageSelection();
    },
    [MENU_ACTION_MESSAGE_MULTI_SELECT_DELETE]: {
      handler: async () => {
        const ids = [...messageMultiSelectionStore.ids];
        clearMessageSelection();
        for (const id of ids) {
          await deleteMessage(id).catch((err) => {
            console.error("Delete message failed:", err);
          });
        }
      },
      skipMenuConfirm: false,
    },
  });

  // ---- tool-work drawer jump ---------------------------------------------

  /**
   * Bound to the tool-work ``<details>`` element so the ⤴ TOOLS jump
   * button can open the drawer and scroll it into view.
   *
   * Per ``docs/behavior/tool-output-streaming.md`` §"Scroll-anchor
   * behavior" bullet 5 and ``docs/behavior/chat.md`` §"What a message
   * turn looks like" line 38 (gap-cycle-06-002).
   */
  let toolWorkEl = $state<HTMLDetailsElement | null>(null);

  /** Opens the tool-work drawer and scrolls it into view (no-op when already open). */
  function handleJumpToTools(): void {
    if (toolWorkEl === null) return;
    toolWorkEl.open = true;
    toolWorkEl.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
  }

  // Body rendering pipeline — marked → DOMPurify. The pipeline runs
  // asynchronously because :func:`renderMarkdown` returns a promise;
  // we cache the resolved HTML on the turn view via a derived
  // ``$state`` so a re-render of the same body doesn't re-parse.
  let bodyHtml = $state<string>("");

  $effect(() => {
    const body = turn.body;
    if (body.length === 0) {
      bodyHtml = "";
      return;
    }
    let cancelled = false;
    void (async () => {
      const html = await renderMarkdown(body);
      if (cancelled) return;
      bodyHtml = sanitizeHtml(html);
    })();
    return () => {
      cancelled = true;
    };
  });
</script>

{#if showRegenerateFromConfirm}
  <ConfirmDialog
    message="Discard {turnsAfterCount + 1} message{turnsAfterCount + 1 === 1
      ? ''
      : 's'} and regenerate from here?"
    confirmLabel="Regenerate"
    onConfirm={() => {
      showRegenerateFromConfirm = false;
      void handleRegenerateFrom();
    }}
    onCancel={() => {
      showRegenerateFromConfirm = false;
    }}
  />
{/if}

{#if showDeleteConfirm}
  <ConfirmDialog
    message="Delete this message? This cannot be undone."
    confirmLabel="Delete"
    onConfirm={() => void handleDeleteConfirm()}
    onCancel={() => {
      showDeleteConfirm = false;
    }}
  />
{/if}

<div
  class="message-turn flex flex-col gap-2 px-4 py-4{isSelected
    ? ' ring-1 ring-accent/40 rounded'
    : ''}"
  data-testid="message-turn"
  data-turn-id={turn.id}
  data-role={turn.role}
  role="button"
  tabindex="0"
  onclick={handleClick}
  onkeydown={(e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggleMessageId(turn.id);
    }
  }}
  use:contextMenu={{
    target: hasSelection ? MENU_TARGET_MESSAGE_MULTI_SELECT : MENU_TARGET_MESSAGE,
    handlers: hasSelection ? multiSelectMenuHandlers : menuHandlers,
    data: { messageId: turn.id, sessionId },
    stale: isTurnStale,
  }}
>
  {#if turn.role === "user"}
    <div class="flex flex-col items-end gap-1">
      {#if turn.resumed}
        <span
          class="text-xs text-fg-muted"
          data-testid="message-turn-resumed"
          title="This prompt was re-queued and replayed to the runner after a restart"
        >
          {CONVERSATION_STRINGS.turnResumedLabel}
        </span>
      {/if}
      {#if editActive}
        <!-- T1-05 inline edit overlay -->
        <div class="flex w-full flex-col gap-1" data-testid="message-turn-edit">
          <textarea
            class="w-full rounded border border-accent/60 bg-surface-1 p-2 text-sm text-fg-strong focus:outline-none focus:ring-1 focus:ring-accent/60"
            rows="4"
            bind:value={editDraft}
            disabled={editSaving}
            data-testid="message-turn-edit-textarea"
          ></textarea>
          {#if editError !== null}
            <p class="text-xs text-red-400" data-testid="message-turn-edit-error">{editError}</p>
          {/if}
          <div class="flex justify-end gap-2">
            <button
              type="button"
              class="rounded px-2 py-0.5 text-xs text-fg-muted hover:bg-surface-2 hover:text-fg-strong"
              onclick={cancelEdit}
              disabled={editSaving}
              data-testid="message-turn-edit-cancel"
            >
              {CONTEXT_MENU_STRINGS.destructiveCancelLabel}
            </button>
            <button
              type="button"
              class="rounded bg-accent/20 px-2 py-0.5 text-xs text-fg-strong hover:bg-accent/30 disabled:opacity-50"
              onclick={() => void saveEdit()}
              disabled={editSaving || editDraft.trim().length === 0}
              data-testid="message-turn-edit-save"
            >
              {editSaving ? CONTEXT_MENU_STRINGS.confirmPendingLabel : "Save"}
            </button>
          </div>
        </div>
      {:else}
        <div
          class="user-bubble self-end rounded px-3 py-2 text-sm text-fg-strong"
          data-testid="message-turn-user-body"
        >
          <!-- User bubbles get linkifier-anchored URLs / paths but no
               Markdown reflow (chat.md notes user bubbles render as
               Markdown — applying the same renderMarkdown pipeline as
               assistant bubbles is a TODO once the linkifier integrates
               with the marked tokeniser). The HTML output of
               ``linkifyToHtml`` is escaped per-segment; we still pass it
               through ``sanitizeHtml`` for defense in depth. -->
          <!-- eslint-disable-next-line svelte/no-at-html-tags -->
          {@html sanitizeHtml(linkifyToHtml(turn.body))}
          <!-- Attachment chips at the bottom of the user bubble —
               gap-cycle-01-015 / docs/behavior/chat.md §"What a message
               turn looks like". Renders nothing when the array is empty. -->
          <SentAttachmentChips attachments={turn.attachments} />
        </div>
      {/if}
    </div>
  {:else}
    {#if turn.toolCalls.length > 0}
      <details
        class="rounded border border-border"
        data-testid="tool-work-drawer"
        open
        bind:this={toolWorkEl}
      >
        <summary class="cursor-pointer px-2 py-1 text-xs text-fg-muted">
          {CONVERSATION_STRINGS.toolDrawerLabel} ({turn.toolCalls.length})
        </summary>
        <div class="px-2 py-1">
          {#each turn.toolCalls as call (call.id)}
            <ToolOutput {call} {workingDir} {sessionId} />
          {/each}
        </div>
      </details>
    {/if}
    <div
      class="group relative rounded bg-surface-1 px-3 py-2 text-sm"
      data-testid="message-turn-assistant"
    >
      {#if turn.thinking.length > 0}
        <details
          class="mb-2 rounded border border-border bg-surface-2"
          data-testid="message-turn-thinking"
        >
          <summary class="cursor-pointer px-2 py-1 text-xs text-fg-muted">Thinking</summary>
          <pre class="whitespace-pre-wrap px-2 py-1 text-xs text-fg-muted">{turn.thinking}</pre>
        </details>
      {/if}
      {#if bodyHtml.length > 0}
        <CollapsibleBody>
          <div
            class="message-turn__body"
            data-testid="message-turn-body"
            use:markdownContextMenu={{ sessionId: sessionId ?? undefined }}
          >
            <!-- eslint-disable-next-line svelte/no-at-html-tags -->
            {@html bodyHtml}
          </div>
        </CollapsibleBody>
      {:else if turn.body.length > 0}
        <CollapsibleBody>
          <p class="text-fg-muted" data-testid="message-turn-body-fallback">{turn.body}</p>
        </CollapsibleBody>
      {/if}
      <div class="mt-2 flex items-center justify-end gap-2">
        {#if turn.toolCalls.length > 0 && turn.complete}
          <button
            type="button"
            class="opacity-0 transition-opacity group-hover:opacity-100 rounded px-1.5 py-0.5 text-xs text-fg-muted hover:text-fg-strong hover:bg-surface-2"
            title={CONVERSATION_STRINGS.toolDrawerJumpLabel}
            aria-label={CONVERSATION_STRINGS.toolDrawerJumpLabel}
            onclick={handleJumpToTools}
            data-testid="message-turn-jump-to-tools"
          >
            {CONVERSATION_STRINGS.toolDrawerJumpLabel}
          </button>
        {/if}
        {#if !isPaired}
          <button
            type="button"
            class="opacity-0 transition-opacity group-hover:opacity-100 rounded px-1.5 py-0.5 text-xs text-fg-muted hover:text-fg-strong hover:bg-surface-2"
            title={CONVERSATION_STRINGS.spawnPillAriaLabel}
            aria-label={CONVERSATION_STRINGS.spawnPillAriaLabel}
            onclick={() => void handleSpawn()}
            data-testid="message-turn-spawn-pill"
          >
            {CONVERSATION_STRINGS.spawnPillLabel}
          </button>
        {/if}
        <button
          type="button"
          class="opacity-0 transition-opacity group-hover:opacity-100"
          title={CONVERSATION_STRINGS.askForMoreDetailLabel}
          onclick={handleAskForMoreDetail}
          data-testid="message-turn-ask-for-detail"
        >
          <svg
            class="h-4 w-4 text-fg-muted hover:text-fg-strong"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </button>
        {#if turn.routing !== null}
          <RoutingBadge routing={turn.routing} />
        {/if}
      </div>
      {#if turn.error !== null}
        <p
          class="mt-2 rounded border border-red-500 px-2 py-1 text-xs text-red-400"
          data-testid="message-turn-error"
        >
          {CONVERSATION_STRINGS.errorBubbleLabel}: {turn.error}
        </p>
      {/if}
      {#if turn.stopped}
        <!-- feature-2-004: [stopped] annotation on interrupted turns.
             Per docs/behavior/chat.md §"Stopping or interrupting a turn". -->
        <span
          class="mt-2 inline-block rounded border border-amber-500/60 px-1.5 py-0.5 text-xs text-amber-400"
          data-testid="message-turn-stopped"
          title="This turn was interrupted by the user"
        >
          {CONVERSATION_STRINGS.stoppedAnnotationLabel}
        </span>
      {/if}
    </div>
    <!--
      Reply-action strip (T1-09) — rendered below the assistant bubble for
      complete turns with a non-empty body. Hidden on incomplete or empty
      turns so the strip doesn't appear mid-stream.
    -->
    {#if turn.complete && turn.body.length > 0 && sessionId !== null && sessionId !== undefined}
      <ReplyActionPreview {sessionId} messageBody={turn.body} />
    {/if}
  {/if}
</div>

<style>
  /* User bubble — soft brand-tinted surface to visually distinguish from
     assistant bubbles, matching v0.17.x's right-aligned user prompt style. */
  .user-bubble {
    background-color: rgb(var(--bearings-accent) / 0.14);
  }
</style>
