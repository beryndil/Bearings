<script lang="ts">
  /**
   * Slice 6 of the Session Reorg plan
   * (`~/.claude/plans/sparkling-triaging-otter.md`). LLM-assisted /
   * heuristic-assisted reorg analyzer view.
   *
   * Lifecycle: caller flips `open` to true; the modal calls
   * `analyzeReorg()` with the requested mode, then renders the
   * resulting proposals as editable cards. The user can tweak title /
   * tag_ids per card, reject individual cards, then click "Approve
   * all" — at which point we issue one `/reorg/split` per approved
   * card. The server NEVER moves rows from the analyze endpoint; this
   * component is responsible for orchestrating the actual splits.
   *
   * The analyzer is read-only and re-runnable. A second click with a
   * different mode re-renders fresh proposals; nothing on the source
   * changes until the user clicks Approve.
   */
  import * as api from '$lib/api';
  import { sessions } from '$lib/stores/sessions.svelte';
  import { tags } from '$lib/stores/tags.svelte';

  type Props = {
    open: boolean;
    sessionId: string | null;
    onClose: () => void;
    /** Called after a successful approve flow with the count of new
     * sessions created. Lets the parent surface a toast and refresh
     * the sidebar. */
    onApproved: (newSessionsCreated: number) => void;
  };

  const { open, sessionId, onClose, onApproved }: Props = $props();

  // Local copy of the analyzer response — proposals get edited here
  // before commit. Per-card rejected state lives alongside so the
  // approve loop can skip cleanly.
  type EditableCard = {
    topic: string;
    rationale: string;
    confidence: number;
    message_ids: string[];
    title: string;
    description: string | null;
    tag_ids: number[];
    rejected: boolean;
    /** Per-card error from a failed split commit. Undefined on the
     * happy path. */
    error?: string;
    expanded: boolean;
  };

  let mode = $state<'heuristic' | 'llm'>('heuristic');
  let loading = $state(false);
  let error = $state<string | null>(null);
  let result = $state<api.ReorgAnalyzeResult | null>(null);
  let cards = $state<EditableCard[]>([]);
  let committing = $state(false);

  // Reset state on close so a second open starts clean.
  $effect(() => {
    if (open) return;
    result = null;
    cards = [];
    error = null;
    loading = false;
    committing = false;
  });

  async function runAnalyze(): Promise<void> {
    if (!sessionId) return;
    loading = true;
    error = null;
    try {
      const res = await api.analyzeReorg(sessionId, { mode });
      result = res;
      cards = res.proposals.map((p) => ({
        topic: p.topic,
        rationale: p.rationale,
        confidence: p.confidence,
        message_ids: [...p.message_ids],
        title: p.suggested_session.title,
        description: p.suggested_session.description ?? null,
        tag_ids: [...p.suggested_session.tag_ids],
        rejected: false,
        expanded: false
      }));
    } catch (e) {
      error = e instanceof Error ? e.message : 'Analyzer call failed';
    } finally {
      loading = false;
    }
  }

  function toggleTag(card: EditableCard, tagId: number): void {
    if (card.tag_ids.includes(tagId)) {
      card.tag_ids = card.tag_ids.filter((t) => t !== tagId);
    } else {
      card.tag_ids = [...card.tag_ids, tagId];
    }
  }

  function approveCount(): number {
    return cards.filter((c) => !c.rejected).length;
  }

  /** Locate the anchor message id immediately BEFORE this proposal's
   * first id in source-session order. `/reorg/split` takes
   * `after_message_id` (move every message strictly after) so we
   * subtract one position from the source order. Returns null when
   * the proposal starts at message 0 — which means the first segment
   * IS the source up to the first split point and shouldn't itself
   * be split off. The caller treats null as "skip this proposal but
   * don't fail." */
  function anchorBeforeProposal(card: EditableCard): string | null {
    const order = sourceMessageOrder;
    if (!card.message_ids.length || order.length === 0) return null;
    const first = card.message_ids[0];
    const idx = order.indexOf(first);
    if (idx <= 0) return null;
    return order[idx - 1];
  }

  // We need the source's message order to compute split anchors.
  // Snapshot it on analyze. The store doesn't carry message ids
  // here; the analyzer's first proposal is in source order so we can
  // reconstruct it from the proposals themselves (every message
  // appears at most once across proposals, and proposals are
  // contiguous and in order per the analyzer contract).
  const sourceMessageOrder = $derived.by(() => {
    const out: string[] = [];
    if (!result) return out;
    for (const p of result.proposals) {
      for (const id of p.message_ids) out.push(id);
    }
    return out;
  });

  async function approveAll(): Promise<void> {
    if (!sessionId || committing) return;
    committing = true;
    let created = 0;
    try {
      for (const card of cards) {
        if (card.rejected) continue;
        if (card.tag_ids.length === 0) {
          card.error = 'At least one tag required.';
          continue;
        }
        const anchor = anchorBeforeProposal(card);
        if (anchor === null) {
          // First-segment-of-the-source case: the anchor is "split
          // BEFORE the first message of this proposal." There's no
          // prior message, so we can't issue a split and still keep
          // the source's identity. We mark the card so the user can
          // reject + re-run, OR treat the source itself as this
          // segment.
          card.error = 'First segment cannot be split off the source — keep on source or reject.';
          continue;
        }
        try {
          const res = await api.reorgSplit(sessionId, {
            after_message_id: anchor,
            new_session: {
              title: card.title,
              description: card.description ?? null,
              tag_ids: card.tag_ids
            }
          });
          if (res.session) {
            created += 1;
            card.error = undefined;
            card.rejected = true; // mark "done" so the loop moves on
          }
        } catch (e) {
          card.error = e instanceof Error ? e.message : 'Split failed';
        }
      }
      // Refresh sidebar so the new sessions appear immediately.
      void sessions.refresh();
      if (created > 0) {
        onApproved(created);
      }
    } finally {
      committing = false;
    }
  }

  // Auto-run the heuristic on open so the user sees a result without
  // an extra click. LLM mode is opt-in (a click on the toggle)
  // because it costs real tokens.
  $effect(() => {
    if (!open || !sessionId || result || loading) return;
    void runAnalyze();
  });

  function pendingCommitCount(): number {
    return cards.filter((c) => !c.rejected).length;
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-4"
    role="dialog"
    aria-modal="true"
    aria-label="Analyze and reorg"
    data-testid="reorg-proposal-editor"
  >
    <div
      class="w-full max-w-3xl max-h-[85vh] overflow-hidden rounded-lg border border-slate-800
        bg-slate-900 p-5 shadow-2xl flex flex-col gap-3"
    >
      <header class="flex items-start justify-between gap-3">
        <div>
          <h2 class="text-sm font-medium text-slate-200">Analyze & reorg session</h2>
          <p class="text-xs text-slate-500 mt-1">
            The analyzer proposes how this session could be split. Edit titles / tags per card,
            then approve all to commit.
          </p>
        </div>
        <button
          type="button"
          class="text-slate-500 hover:text-slate-300 text-sm"
          aria-label="Close analyzer"
          onclick={onClose}
        >
          ✕
        </button>
      </header>

      <div class="flex items-center gap-2 text-xs">
        <span class="text-slate-500">Mode:</span>
        <button
          type="button"
          class="px-2 py-1 rounded {mode === 'heuristic'
            ? 'bg-emerald-900 text-emerald-200'
            : 'bg-slate-800 text-slate-400'} hover:text-emerald-200"
          onclick={() => {
            mode = 'heuristic';
            void runAnalyze();
          }}
          disabled={loading}
        >
          Heuristic (free)
        </button>
        <button
          type="button"
          class="px-2 py-1 rounded {mode === 'llm'
            ? 'bg-sky-900 text-sky-200'
            : 'bg-slate-800 text-slate-400'} hover:text-sky-200"
          onclick={() => {
            mode = 'llm';
            void runAnalyze();
          }}
          disabled={loading}
          title="In-process one-shot SDK call. Server falls back to heuristic when disabled in config."
        >
          LLM
        </button>
        {#if loading}
          <span class="text-slate-500 ml-auto">analyzing…</span>
        {:else if result}
          <span class="text-slate-500 ml-auto">
            {result.messages_in} messages · ran {result.mode_used}
          </span>
        {/if}
      </div>

      {#if error}
        <div class="text-xs text-rose-300 bg-rose-950/40 border border-rose-900 px-2 py-1 rounded">
          {error}
        </div>
      {/if}

      {#if result?.notes}
        <div class="text-xs text-amber-300 bg-amber-950/30 border border-amber-900 px-2 py-1 rounded">
          {result.notes}
        </div>
      {/if}

      <div class="flex-1 overflow-y-auto pr-1 flex flex-col gap-3">
        {#if !loading && result && cards.length === 0}
          <p class="text-xs text-slate-500 italic">
            Analyzer didn't find any clear topical breaks — the session looks coherent.
          </p>
        {/if}

        {#each cards as card, i (i)}
          <article
            class="rounded border bg-slate-950/60 px-3 py-2 flex flex-col gap-2
              {card.rejected ? 'border-slate-800 opacity-50' : 'border-slate-700'}"
            data-testid="reorg-proposal-card"
          >
            <header class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-[10px] uppercase tracking-wider text-slate-500">
                  {card.message_ids.length} msgs
                </span>
                <span class="text-[10px] text-slate-600">
                  conf {(card.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <button
                type="button"
                class="text-xs {card.rejected ? 'text-emerald-400' : 'text-rose-400'} hover:underline"
                onclick={() => (card.rejected = !card.rejected)}
              >
                {card.rejected ? 'Restore' : 'Reject'}
              </button>
            </header>

            <input
              type="text"
              class="rounded bg-slate-950 border border-slate-800 px-2 py-1 text-sm
                focus:outline-none focus:border-slate-600"
              bind:value={card.title}
              aria-label="Proposed session title"
              disabled={card.rejected}
            />

            <p class="text-[11px] text-slate-500 italic">{card.rationale}</p>

            {#if tags.list.length > 0}
              <div class="flex flex-wrap gap-1">
                {#each tags.list as t (t.id)}
                  <button
                    type="button"
                    class="text-[10px] font-mono px-1.5 py-0.5 rounded {card.tag_ids.includes(t.id)
                      ? 'bg-emerald-900 text-emerald-200'
                      : 'bg-slate-800 text-slate-400'} hover:text-emerald-200"
                    onclick={() => toggleTag(card, t.id)}
                    disabled={card.rejected}
                  >
                    {t.name}
                  </button>
                {/each}
              </div>
            {/if}

            <button
              type="button"
              class="text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300 self-start"
              onclick={() => (card.expanded = !card.expanded)}
            >
              {card.expanded ? '⌃ hide ids' : '⌄ show ids'}
            </button>
            {#if card.expanded}
              <ul class="text-[10px] font-mono text-slate-500 break-all pl-3 list-disc">
                {#each card.message_ids as mid (mid)}
                  <li>{mid}</li>
                {/each}
              </ul>
            {/if}

            {#if card.error}
              <p class="text-[11px] text-rose-300">{card.error}</p>
            {/if}
          </article>
        {/each}
      </div>

      <footer class="flex items-center justify-end gap-2 border-t border-slate-800 pt-3">
        <button
          type="button"
          class="text-xs px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
          onclick={onClose}
        >
          Cancel
        </button>
        <button
          type="button"
          class="text-xs px-3 py-1.5 rounded bg-emerald-900 text-emerald-200
            hover:bg-emerald-800 disabled:opacity-40 disabled:cursor-not-allowed"
          onclick={approveAll}
          disabled={committing || pendingCommitCount() === 0 || loading}
          data-testid="reorg-approve-all"
        >
          {committing ? 'Committing…' : `Approve ${approveCount()} & commit`}
        </button>
      </footer>
    </div>
  </div>
{/if}
