<script lang="ts">
  /**
   * Paired-chat breadcrumb chip — small indicator on the conversation
   * header per ``docs/behavior/paired-chats.md`` §"What 'paired' means
   * observably" point 2 ("From the chat side. The conversation header
   * shows a breadcrumb chip: <parent checklist title> › <item label>").
   *
   * The chip is purely presentational. Click handlers are delivered as
   * callback props so the parent (Conversation header) can wire
   * navigation: clicking the parent-title segment selects the parent
   * checklist; clicking the item-label segment scrolls the parent
   * checklist pane to the corresponding item.
   *
   * Behavior under one-side-closed (paired-chats.md §"Behavior under
   * one-side-closed"): when the parent has been deleted, the chip
   * renders the literal string "(checklist deleted)" and the click
   * handlers are inert.
   */
  import { CONVERSATION_STRINGS } from "../../config";

  interface Props {
    /** Parent checklist title; ``null`` when the parent has been deleted. */
    parentTitle: string | null;
    /** Leaf item label inside the parent checklist; same null shape. */
    itemLabel: string | null;
    /** Click handler for the parent-title segment. */
    onSelectParent?: () => void;
    /** Click handler for the item-label segment. */
    onScrollToItem?: () => void;
  }

  const { parentTitle, itemLabel, onSelectParent, onScrollToItem }: Props = $props();

  const isDeleted = $derived(parentTitle === null && itemLabel === null);
</script>

<span
  class="paired-chat-indicator inline-flex items-center gap-1 rounded bg-surface-2 px-2 py-0.5 text-xs text-fg-muted"
  aria-label={CONVERSATION_STRINGS.pairedChatBreadcrumbAriaLabel}
  data-testid="paired-chat-indicator"
  data-deleted={isDeleted ? "true" : "false"}
>
  <span aria-hidden="true">{CONVERSATION_STRINGS.pairedChatBreadcrumbPrefix}</span>
  {#if isDeleted}
    <span data-testid="paired-chat-deleted">{CONVERSATION_STRINGS.pairedChatBreadcrumbDeleted}</span
    >
  {:else}
    <button
      type="button"
      class="paired-chat-indicator__segment hover:underline"
      data-testid="paired-chat-parent"
      onclick={onSelectParent}
      disabled={onSelectParent === undefined}
    >
      {parentTitle}
    </button>
    <span aria-hidden="true">›</span>
    <button
      type="button"
      class="paired-chat-indicator__segment hover:underline"
      data-testid="paired-chat-item"
      onclick={onScrollToItem}
      disabled={onScrollToItem === undefined}
    >
      {itemLabel}
    </button>
  {/if}
</span>

<style>
  /*
   * The two segments inside the chip render as buttons (so keyboard
   * Tab/Enter activates them) without inheriting the page's default
   * button chrome — Tailwind's text utilities color them, this rule
   * just removes the platform default border.
   */
  .paired-chat-indicator__segment {
    background: transparent;
    border: none;
    padding: 0;
    color: inherit;
    cursor: pointer;
  }
  .paired-chat-indicator__segment[disabled] {
    cursor: default;
  }
</style>
