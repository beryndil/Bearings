<script lang="ts">
  /**
   * ChecklistChat — embedded conversation pane for the active item's
   * paired chat.
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/paired-chats.md`` §"What 'paired' means
   *   observably" — clicking a paired-leaf's chat title selects the
   *   paired chat; the conversation header shows a breadcrumb back
   *   to the parent item.
   * - ``docs/behavior/paired-chats.md`` §"Cross-cuts with the
   *   autonomous driver" — every leg the driver spawns is a paired
   *   chat; the breadcrumb on each leg's chat points to the same
   *   item; the driver's *visit-existing* mode reuses an item's
   *   already-paired chat for the first leg.
   * - ``docs/behavior/checklists.md`` §"Sentinels" — the agent's
   *   assistant turn carries the structured sentinels the driver
   *   acts on; this pane summarises the parsed sentinels of the
   *   latest assistant turn for the user (the SentinelEvent surface
   *   on each item shows the *aggregated* state; the chat-side
   *   summary shows the *latest turn*).
   *
   * The component reuses :class:`Conversation` for the actual
   * transcript + WS subscription per item 2.3's pattern. The
   * sentinel-summary surface reads the conversation store's latest
   * assistant turn and runs :func:`parseSentinels` against the body.
   */
  import { CHECKLIST_STRINGS } from "../../config";
  import {
    conversationStore as conversationStoreDefault,
    type MessageTurnView,
  } from "../../stores/conversation.svelte";
  import { parseSentinels, type SentinelFinding } from "../../sentinel";
  import Conversation from "../conversation/Conversation.svelte";

  interface Props {
    /** Paired-chat session id; ``null`` when the active item is unpaired. */
    chatSessionId: string | null;
    /** Item label rendered in the breadcrumb. ``null`` hides the breadcrumb. */
    itemLabel?: string | null;
    /** Test-injectable conversation store (for the sentinel-summary read). */
    conversationStore?: typeof conversationStoreDefault;
  }

  const {
    chatSessionId,
    itemLabel = null,
    conversationStore = conversationStoreDefault,
  }: Props = $props();

  // Latest assistant turn — sentinel-summary input. ``null`` when the
  // store is empty or the latest turn is a user turn (the agent's
  // sentinels live in assistant text).
  const latestAssistantTurn = $derived<MessageTurnView | null>(
    findLatestAssistantTurn(conversationStore.turns),
  );

  const sentinels = $derived<SentinelFinding[]>(
    latestAssistantTurn === null ? [] : parseSentinels(latestAssistantTurn.body),
  );

  function findLatestAssistantTurn(turns: readonly MessageTurnView[]): MessageTurnView | null {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      if (turns[i].role === "assistant") return turns[i];
    }
    return null;
  }
</script>

<section
  class="checklist-chat flex h-full flex-col"
  data-testid="checklist-chat"
  aria-label={CHECKLIST_STRINGS.checklistChatAriaLabel}
>
  {#if chatSessionId === null}
    <p class="m-3 text-sm text-fg-muted" data-testid="checklist-chat-empty">
      {CHECKLIST_STRINGS.checklistChatNoSelection}
    </p>
  {:else}
    {#if itemLabel !== null}
      <header
        class="checklist-chat__breadcrumb border-b border-border px-3 py-1 text-xs text-fg-muted"
        data-testid="checklist-chat-breadcrumb"
      >
        {CHECKLIST_STRINGS.checklistChatBreadcrumbPrefix}: <span class="text-fg">{itemLabel}</span>
      </header>
    {/if}

    <div class="checklist-chat__conversation flex-1 overflow-hidden">
      <Conversation sessionId={chatSessionId} />
    </div>

    <aside
      class="checklist-chat__sentinels border-t border-border p-2 text-xs"
      data-testid="checklist-chat-sentinels"
    >
      <h4 class="font-semibold text-fg-muted">{CHECKLIST_STRINGS.checklistChatSentinelHeading}</h4>
      {#if sentinels.length === 0}
        <p class="text-fg-muted" data-testid="checklist-chat-sentinels-empty">
          {CHECKLIST_STRINGS.checklistChatSentinelEmpty}
        </p>
      {:else}
        <ul class="flex flex-row flex-wrap gap-1" data-testid="checklist-chat-sentinels-list">
          {#each sentinels as finding, idx (idx)}
            <li
              class="checklist-chat__sentinel-chip rounded bg-surface-2 px-2 py-0.5"
              data-testid="checklist-chat-sentinel-chip"
              data-sentinel-kind={finding.kind}
            >
              {CHECKLIST_STRINGS.sentinelKindLabels[
                finding.kind as keyof typeof CHECKLIST_STRINGS.sentinelKindLabels
              ] ?? finding.kind}
            </li>
          {/each}
        </ul>
      {/if}
    </aside>
  {/if}
</section>
