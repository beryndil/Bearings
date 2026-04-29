<script lang="ts">
  /**
   * Single sidebar session row, extracted from `SessionList.svelte`
   * (§FileSize). Pure presentational — every interactive callback
   * dispatches to the parent so the parent retains ownership of the
   * "only one row in confirm/rename mode at a time" invariants.
   *
   * Markup is unchanged from the parent's pre-extraction snippet.
   */
  import { billing } from '$lib/stores/billing.svelte';
  import { contextmenu } from '$lib/actions/contextmenu';
  import type { ContextTarget } from '$lib/context-menu/types';
  import type { Session } from '$lib/api';
  import SeverityShield from '$lib/components/icons/SeverityShield.svelte';
  import TagIcon from '$lib/components/icons/TagIcon.svelte';
  import { costClass, formatTimestamp, medallionData } from './sessionListHelpers.js';
  import type { Tag } from '$lib/api';

  type Indicator = 'red' | 'orange' | 'green' | null;

  interface Props {
    session: Session;
    selected: boolean;
    bulkSelected: boolean;
    indicator: Indicator;
    confirming: boolean;
    renaming: boolean;
    renameDraft: string;
    allTags: readonly Tag[];
    contextTarget: ContextTarget;
    onSelect: (id: string, e: MouseEvent) => void;
    onDelete: (e: MouseEvent, id: string) => void;
    onStartRename: (
      e: MouseEvent,
      session: { id: string; title: string | null; model: string }
    ) => void;
    onCommitRename: () => void | Promise<void>;
    onCancelRename: () => void;
    onRenameDraftChange: (draft: string) => void;
  }

  const {
    session,
    selected,
    bulkSelected,
    indicator,
    confirming,
    renaming,
    renameDraft,
    allTags,
    contextTarget,
    onSelect,
    onDelete,
    onStartRename,
    onCommitRename,
    onCancelRename,
    onRenameDraftChange,
  }: Props = $props();

  let medals = $derived(medallionData(session, allTags));

  function handleRenameKey(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      void onCommitRename();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancelRename();
    }
  }
</script>

<li
  class="group flex items-stretch gap-1 rounded hover:bg-slate-800 {selected
    ? 'bg-slate-800'
    : ''} {bulkSelected ? 'bg-slate-800/80 ring-1 ring-emerald-500/60' : ''}"
  use:contextmenu={{ target: contextTarget }}
  data-multi-selected={bulkSelected ? 'true' : 'false'}
>
  <button
    type="button"
    class="min-w-0 flex-1 rounded-l px-2 py-1 text-left"
    onclick={(e) => onSelect(session.id, e)}
    ondblclick={(e) => onStartRename(e, session)}
  >
    {#if renaming}
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        class="w-full rounded border border-slate-700 bg-slate-950 px-1
          py-0.5 text-xs focus:border-emerald-600 focus:outline-none"
        value={renameDraft}
        oninput={(e) => onRenameDraftChange((e.currentTarget as HTMLInputElement).value)}
        onkeydown={handleRenameKey}
        onblur={() => void onCommitRename()}
        onclick={(e) => e.stopPropagation()}
        autofocus
        placeholder="Session title"
      />
    {:else}
      <!-- Three-row grid: col 1 reserves space for the activity
           indicator so rows 2–3 indent cleanly under the title.
           Row 1: [indicator | title … severity shield].
           Row 2: [—        | general tag icons + working_dir].
           Row 3: [—        | updated_at … cost].
           Col 1 is 1.25rem (20 px) so a 10 px dot has enough
           whitespace on either side to read as a deliberate
           indicator rather than a stray pixel. Sized up from
           0.75rem × 6 px after the original pill was visually
           swallowed by the selected-row slate highlight. -->
      <div class="grid grid-cols-[1.25rem_1fr] gap-x-1 text-xs" title="Double-click to rename">
        <!-- Row 1, Col 1: activity indicator slot. Width is always
             reserved so titles align whether or not an indicator is
             showing. Two states share the same ping geometry — only
             the color differs — so the animation rhythm reads
             identically for "working" and "look at this now"; color
             carries the meaning. -->
        <div class="col-start-1 row-start-1 flex items-center justify-center">
          {#if indicator === 'red'}
            <!-- Red flashing: needs attention now. Covers both
                 "runner parked on approval/AskUserQuestion" (live
                 axis from sessions.awaiting) and "last turn errored"
                 (latched server-side on error_pending). Clears only
                 when the real problem resolves — user submits the
                 pending answer, or a subsequent turn completes
                 without crashing. -->
            <span
              class="relative inline-flex h-2.5 w-2.5 shrink-0"
              aria-label="Needs attention now"
              title="Needs attention — agent is waiting on you, or the last turn errored"
              data-testid="indicator-red"
            >
              <span
                class="absolute inline-flex h-full w-full animate-ping
                  rounded-full bg-red-500 opacity-60"
              ></span>
              <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-600"></span>
            </span>
          {:else if indicator === 'orange'}
            <!-- Yellow flashing: agent is actively working a turn
                 and not parked on a user decision. The indicator-state
                 name (`'orange'`) is kept as the data-layer key so
                 store/API/test contracts don't churn; only the rendered
                 hue moved to yellow to widen the gap from the red
                 "needs attention" state. -->

            <span
              class="relative inline-flex h-2.5 w-2.5 shrink-0"
              aria-label="Agent is working"
              title="Agent is working — you can switch away and come back"
              data-testid="indicator-orange"
            >
              <span
                class="absolute inline-flex h-full w-full animate-ping
                  rounded-full bg-yellow-300 opacity-60"
              ></span>
              <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-yellow-400"></span>
            </span>
          {:else if indicator === 'green'}
            <!-- Green solid: turn finished while the user was
                 elsewhere, output waiting to be read. Solid, not
                 flashing — it's a passive "new here" signal, not a
                 call to action like red. Cleared when the user
                 focuses the row (markViewed bumps last_viewed_at). -->
            <span
              class="relative inline-flex h-2.5 w-2.5 shrink-0"
              aria-label="Finished — new output waiting"
              title="Finished — new output waiting to be viewed"
              data-testid="indicator-green"
            >
              <span class="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
            </span>
          {/if}
        </div>

        <!-- Row 1, Col 2: title with severity shield pinned to the
             right edge. The checklist marker stays inline with the
             title so ☑ still reads as a type badge. -->
        <div class="col-start-2 row-start-1 flex min-w-0 items-center gap-1">
          {#if session.kind === 'checklist'}
            <span
              class="shrink-0 text-slate-500"
              aria-label="Checklist session"
              title="Checklist session">☑</span
            >
          {/if}
          <span class="min-w-0 flex-1 truncate">
            {session.title ?? session.model}
          </span>
          <SeverityShield
            color={medals.severity?.color ?? null}
            title={medals.severity?.name ?? 'No severity'}
            size={11}
          />
        </div>

        <!-- Row 2, Col 2: general-group tag icons ("what project are
             we on") followed by the working_dir path. -->
        <div
          class="col-start-2 row-start-2 flex min-w-0 items-center gap-1"
          data-testid="medallion-row"
        >
          {#each medals.general as tag (tag.id)}
            <TagIcon color={tag.color} title={tag.name} size={11} />
          {/each}
          <span class="min-w-0 truncate font-mono text-[10px] text-slate-500">
            {session.working_dir}
          </span>
        </div>

        <!-- Row 3, Col 2: timestamp + optional cost. -->
        <div
          class="col-start-2 row-start-3 flex items-baseline justify-between
            gap-2 text-[10px]"
        >
          <span class="text-slate-600">
            {formatTimestamp(session.updated_at)}
          </span>
          {#if !billing.showTokens && session.total_cost_usd > 0}
            <span class="font-mono {costClass(session)}">
              ${session.total_cost_usd.toFixed(4)}
            </span>
          {/if}
        </div>
      </div>
    {/if}
  </button>
  <button
    type="button"
    class="px-1.5 text-[11px] transition {confirming
      ? 'font-medium text-rose-400'
      : 'text-slate-500 opacity-0 hover:text-rose-400 group-hover:opacity-100'}"
    aria-label={confirming ? 'Confirm delete session' : 'Delete session'}
    onclick={(e) => onDelete(e, session.id)}
  >
    {confirming ? 'Confirm?' : '✕'}
  </button>
</li>
