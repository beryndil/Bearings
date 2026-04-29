<script lang="ts">
  /**
   * One sidebar row — title, kind indicator, attached tag chips,
   * status indicators (pinned / closed / error).
   *
   * Behavior anchors:
   *
   * - ``docs/behavior/chat.md`` §"opens an existing chat" — selecting
   *   the row reconnects the conversation pane (the click handler
   *   surfaces the id; the parent decides what to do with it).
   * - §"creates a chat" — clicking a tag chip on a session row toggles
   *   that tag in the global filter set (the "finder-click" behavior).
   * - §"Error states" — the red flashing pip is the
   *   ``error_pending`` indicator; the row class also reflects the
   *   ``closed_at`` state (closed rows render in the muted/closed
   *   style).
   *
   * The component is presentational: props in, events out via
   * callback props. The parent (``SessionList.svelte``) wires the
   * click handlers to the stores. Keeping the presentation pure
   * makes the row testable in isolation against synthetic data.
   */
  import { SESSION_KIND_CHAT, SIDEBAR_STRINGS } from "../../config";
  import type { SessionOut } from "../../api/sessions";
  import type { TagOut } from "../../api/tags";

  interface Props {
    session: SessionOut;
    /** Tags attached to this session (cached in the sessions store). */
    tags: readonly TagOut[];
    /** Tag ids currently in the filter set — used to mark active chips. */
    selectedTagIds: ReadonlySet<number>;
    /** Selected-row highlight (the conversation pane is pointing at this row). */
    isSelected: boolean;
    /** Row click — typically "open this session in the conversation pane". */
    onSelect: (sessionId: string) => void;
    /** Tag-chip click — finder-click integration; toggles tag in filter set. */
    onToggleTag: (tagId: number) => void;
  }

  const { session, tags, selectedTagIds, isSelected, onSelect, onToggleTag }: Props = $props();

  const isClosed = $derived(session.closed_at !== null);

  const kindLabel = $derived(
    SIDEBAR_STRINGS.kindIndicatorAriaLabels[
      session.kind as keyof typeof SIDEBAR_STRINGS.kindIndicatorAriaLabels
    ] ?? session.kind,
  );
</script>

<button
  type="button"
  class="session-row group flex w-full flex-col gap-1 border-b border-border px-3 py-2 text-left transition-colors hover:bg-surface-2"
  class:session-row--selected={isSelected}
  class:bg-surface-2={isSelected}
  class:opacity-70={isClosed}
  data-testid="session-row"
  data-session-id={session.id}
  aria-current={isSelected ? "true" : undefined}
  onclick={() => onSelect(session.id)}
>
  <span class="flex items-center gap-2">
    <span
      class="inline-block h-2 w-2 rounded-full"
      class:bg-accent={session.kind === SESSION_KIND_CHAT}
      class:bg-fg-muted={session.kind !== SESSION_KIND_CHAT}
      aria-label={kindLabel}
      data-testid="session-kind-indicator"
    ></span>
    <span class="flex-1 truncate text-sm text-fg-strong" data-testid="session-title">
      {session.title}
    </span>
    {#if session.pinned}
      <span
        class="text-xs text-accent"
        aria-label={SIDEBAR_STRINGS.pinnedIndicatorAriaLabel}
        data-testid="session-pinned-indicator"
      >
        ★
      </span>
    {/if}
    {#if session.error_pending}
      <span
        class="text-xs text-red-400"
        aria-label={SIDEBAR_STRINGS.errorPendingIndicatorAriaLabel}
        data-testid="session-error-indicator"
      >
        !
      </span>
    {/if}
    {#if isClosed}
      <span
        class="text-xs text-fg-muted"
        aria-label={SIDEBAR_STRINGS.closedIndicatorAriaLabel}
        data-testid="session-closed-indicator"
      >
        ◌
      </span>
    {/if}
  </span>

  {#if tags.length > 0}
    <span class="flex flex-wrap gap-1" data-testid="session-row-tags">
      {#each tags as tag (tag.id)}
        <!--
          Nested <button> inside the row <button> is invalid HTML — Svelte
          will warn. We render the chip as a span with role="button" + a
          stopPropagation handler so the chip click doesn't also fire the
          row click. (The composer-row pattern in chat.md drives the same
          tradeoff for the clickable chip on the conversation header.)
        -->
        <span
          role="button"
          tabindex="0"
          class="rounded px-1.5 py-0.5 text-xs"
          class:bg-accent={selectedTagIds.has(tag.id)}
          class:text-fg-strong={selectedTagIds.has(tag.id)}
          class:bg-surface-2={!selectedTagIds.has(tag.id)}
          class:text-fg-muted={!selectedTagIds.has(tag.id)}
          aria-pressed={selectedTagIds.has(tag.id)}
          data-testid="session-tag-chip"
          data-tag-id={tag.id}
          onclick={(event) => {
            event.stopPropagation();
            onToggleTag(tag.id);
          }}
          onkeydown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              event.stopPropagation();
              onToggleTag(tag.id);
            }
          }}
        >
          {tag.name}
        </span>
      {/each}
    </span>
  {/if}
</button>

<style>
  /*
   * Selected-row accent — Tailwind handles bg + text via utility
   * classes; this rule supplies the inset focus ring the keyboard-nav
   * `j`/`k` selection (item 2.9) will rely on. Theme-aware via the
   * --bearings-accent CSS variable.
   */
  .session-row--selected {
    box-shadow: inset 2px 0 0 0 rgb(var(--bearings-accent));
  }
</style>
