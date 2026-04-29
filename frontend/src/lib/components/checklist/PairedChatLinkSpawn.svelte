<script lang="ts">
  /**
   * PairedChatLinkSpawn — the per-leaf affordance row for spawning a
   * fresh paired chat or linking an existing chat session.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/paired-chats.md`` §"Spawning a new pair" — the
   *   **💬 Work on this** button creates a chat that inherits the
   *   checklist's working dir / model / tags; second click is
   *   idempotent (returns the existing pair).
   * - ``docs/behavior/paired-chats.md`` §"Linking to an existing
   *   chat" — the **Link existing chat…** action opens a picker; the
   *   picker lists open chat-kind sessions (the gate is enforced at
   *   the boundary by the link route).
   * - ``docs/behavior/paired-chats.md`` §"Detaching" — when the leaf
   *   is paired the component shows **Continue working** + the chat
   *   title link plus a unlink action.
   * - ``docs/behavior/checklists.md`` §"Item ↔ chat-session linking"
   *   — leaves only; parents render no affordance.
   *
   * Layer rules: the component takes the open-sessions list as a prop
   * (the parent owns the fetch) so the link-existing picker doesn't
   * trigger a second sessions refresh. The two write helpers
   * (``spawnPairedChat`` / ``linkChat``) are also injected so unit
   * tests don't need to monkey-patch the api modules.
   */
  import { CHECKLIST_STRINGS, PAIRED_CHAT_SPAWNED_BY_USER } from "../../config";
  import type { ChecklistItemOut } from "../../api/checklists";
  import {
    linkChecklistItemChat as linkChatDefault,
    unlinkChecklistItemChat as unlinkChatDefault,
  } from "../../api/checklists";
  import { spawnPairedChat as spawnPairedChatDefault } from "../../api/paired_chats";
  import type { SessionOut } from "../../api/sessions";

  interface Props {
    item: ChecklistItemOut;
    /** ``true`` when the row is a leaf (no children). Affordance hidden otherwise. */
    isLeaf: boolean;
    /**
     * Open chat-kind sessions for the link-existing picker. Empty list
     * disables the picker's confirm button per behavior doc.
     */
    availableChats?: readonly SessionOut[];
    /** Called after a successful spawn / link so the parent re-fetches. */
    onChange?: () => void;
    /** Test-injectable spawn helper. */
    spawnPairedChat?: typeof spawnPairedChatDefault;
    /** Test-injectable link helper. */
    linkChat?: typeof linkChatDefault;
    /** Test-injectable unlink helper. */
    unlinkChat?: typeof unlinkChatDefault;
    /** Called when the user clicks the chat title to focus the paired chat. */
    onSelectChat?: (chatSessionId: string) => void;
  }

  const {
    item,
    isLeaf,
    availableChats = [],
    onChange = () => {},
    spawnPairedChat = spawnPairedChatDefault,
    linkChat = linkChatDefault,
    unlinkChat = unlinkChatDefault,
    onSelectChat = () => {},
  }: Props = $props();

  let busy = $state(false);
  let error = $state<string | null>(null);
  let pickerOpen = $state(false);
  let pickerChoice = $state<string>("");

  async function handleSpawn(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      const result = await spawnPairedChat(item.id, { spawned_by: PAIRED_CHAT_SPAWNED_BY_USER });
      onChange();
      onSelectChat(result.chat_session_id);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : CHECKLIST_STRINGS.pairedChatSpawnFailed;
    } finally {
      busy = false;
    }
  }

  async function handleLink(): Promise<void> {
    if (busy || pickerChoice === "") return;
    busy = true;
    error = null;
    try {
      await linkChat(item.id, {
        chat_session_id: pickerChoice,
        spawned_by: PAIRED_CHAT_SPAWNED_BY_USER,
      });
      pickerOpen = false;
      pickerChoice = "";
      onChange();
      onSelectChat(item.id.toString()); // signal a refresh; the row will re-render with the new id
    } catch (caught) {
      error = caught instanceof Error ? caught.message : CHECKLIST_STRINGS.pairedChatLinkFailed;
    } finally {
      busy = false;
    }
  }

  async function handleUnlink(): Promise<void> {
    if (busy) return;
    busy = true;
    error = null;
    try {
      await unlinkChat(item.id);
      onChange();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : CHECKLIST_STRINGS.pairedChatLinkFailed;
    } finally {
      busy = false;
    }
  }
</script>

{#if isLeaf}
  <div class="paired-chat flex flex-row items-center gap-2 text-xs" data-testid="paired-chat">
    {#if item.chat_session_id !== null}
      <button
        type="button"
        class="paired-chat__continue rounded bg-surface-2 px-2 py-1"
        data-testid="paired-chat-continue"
        aria-label={CHECKLIST_STRINGS.pairedChatContinueAriaLabel}
        disabled={busy}
        onclick={() => onSelectChat(item.chat_session_id ?? "")}
      >
        {CHECKLIST_STRINGS.pairedChatContinueLabel}
      </button>
      <button
        type="button"
        class="paired-chat__unlink text-fg-muted hover:text-fg"
        data-testid="paired-chat-unlink"
        disabled={busy}
        onclick={handleUnlink}
      >
        {CHECKLIST_STRINGS.pairedChatUnlinkLabel}
      </button>
    {:else}
      <button
        type="button"
        class="paired-chat__spawn rounded bg-surface-2 px-2 py-1"
        data-testid="paired-chat-spawn"
        aria-label={CHECKLIST_STRINGS.pairedChatWorkOnThisAriaLabel}
        disabled={busy}
        onclick={handleSpawn}
      >
        {CHECKLIST_STRINGS.pairedChatWorkOnThisLabel}
      </button>
      <button
        type="button"
        class="paired-chat__link text-fg-muted hover:text-fg"
        data-testid="paired-chat-link"
        disabled={busy}
        onclick={() => {
          pickerOpen = !pickerOpen;
        }}
      >
        {CHECKLIST_STRINGS.pairedChatLinkExistingLabel}
      </button>
    {/if}
    {#if error !== null}
      <span class="paired-chat__error text-red-400" data-testid="paired-chat-error">{error}</span>
    {/if}
  </div>

  {#if pickerOpen}
    <div
      class="paired-chat-picker mt-2 rounded border border-border bg-surface-1 p-2 text-xs"
      data-testid="paired-chat-picker"
      role="dialog"
      aria-label={CHECKLIST_STRINGS.pairedChatLinkChooseLabel}
    >
      <p class="text-fg-muted">{CHECKLIST_STRINGS.pairedChatLinkChooseLabel}</p>
      {#if availableChats.length === 0}
        <p class="text-fg-muted" data-testid="paired-chat-picker-empty">
          {CHECKLIST_STRINGS.pairedChatLinkEmptyLabel}
        </p>
      {:else}
        <select
          class="paired-chat-picker__select w-full rounded bg-surface-2 px-2 py-1"
          data-testid="paired-chat-picker-select"
          bind:value={pickerChoice}
        >
          <option value="">—</option>
          {#each availableChats as chat (chat.id)}
            <option value={chat.id}>{chat.title}</option>
          {/each}
        </select>
      {/if}
      <div class="mt-2 flex flex-row gap-2">
        <button
          type="button"
          class="paired-chat-picker__confirm rounded bg-surface-2 px-2 py-1"
          data-testid="paired-chat-picker-confirm"
          disabled={pickerChoice === "" || busy}
          onclick={handleLink}
        >
          {CHECKLIST_STRINGS.pairedChatLinkConfirmLabel}
        </button>
        <button
          type="button"
          class="paired-chat-picker__cancel rounded text-fg-muted"
          data-testid="paired-chat-picker-cancel"
          onclick={() => {
            pickerOpen = false;
            pickerChoice = "";
          }}
        >
          {CHECKLIST_STRINGS.pairedChatLinkCancelLabel}
        </button>
      </div>
    </div>
  {/if}
{/if}
