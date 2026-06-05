<script lang="ts">
  /**
   * Bulk title suggestion modal for the checklist view (T2-10).
   *
   * Iterates over checklist items that have a linked chat session
   * (``chat_session_id != null``), calls
   * ``POST /api/sessions/{id}/preview_title`` for each one in sequence,
   * and applies any non-null suggestion via
   * ``PATCH /api/sessions/{id}`` (title field). The results table shows
   * each item's label, the suggested title (or an error), and whether
   * the suggestion was applied.
   *
   * Behavior anchors:
   *
   * - Calls are sequential (not parallel) to avoid hammering the LLM
   *   advisor. Progress is shown per-item as each call settles.
   * - Items without a linked session are listed as "skipped — no linked chat".
   * - A successful suggestion is applied immediately; the caller's
   *   ``onDone`` callback fires after all items are processed so the
   *   parent can refresh the session list.
   * - Backdrop-click and Esc both invoke ``onCancel`` (same as other
   *   modals in the codebase).
   */
  import { untrack } from "svelte";
  import { BULK_TITLE_SUGGEST_STRINGS } from "../../config";
  import { previewSessionTitle, patchSessionTitle } from "../../api/sessions";
  import type { ChecklistItemOut } from "../../api/checklists";

  interface Props {
    /** Flat list of checklist items — only those with chat_session_id are processed. */
    items: readonly ChecklistItemOut[];
    /** Called when all items have been processed. */
    onDone: () => void;
    /** Called when the user cancels or closes the modal. */
    onCancel: () => void;
  }

  const { items, onDone, onCancel }: Props = $props();

  // ---- result state -------------------------------------------------------

  type ItemResult =
    | { status: "pending" }
    | { status: "skipped" }
    | { status: "running" }
    | { status: "suggested"; suggested: string; applied: boolean }
    | { status: "no_suggestion" }
    | { status: "error"; message: string };

  /**
   * Per-item result map. Keyed by item id so the table renders in the
   * original order while updates land out of order on each settle.
   */
  let results = $state<Map<number, ItemResult>>(
    new Map(untrack(() => items).map((item) => [item.id, { status: "pending" }])),
  );

  let running = $state(false);
  let finished = $state(false);

  // Items that can be processed (have a linked chat session).
  const processableItems = $derived(items.filter((item) => item.chat_session_id !== null));

  // ---- run ---------------------------------------------------------------

  async function handleRun(): Promise<void> {
    if (running) return;
    running = true;
    finished = false;

    // Reset all results.
    results = new Map(
      items.map((item) => [
        item.id,
        item.chat_session_id !== null ? { status: "pending" as const } : { status: "skipped" as const },
      ]),
    );

    for (const item of processableItems) {
      const sid = item.chat_session_id as string;
      results = new Map(results).set(item.id, { status: "running" });

      try {
        const out = await previewSessionTitle(sid);
        if (out.suggested_title !== null && out.suggested_title.trim() !== "") {
          // Apply the suggestion.
          await patchSessionTitle(sid, out.suggested_title.trim());
          results = new Map(results).set(item.id, {
            status: "suggested",
            suggested: out.suggested_title.trim(),
            applied: true,
          });
        } else {
          results = new Map(results).set(item.id, { status: "no_suggestion" });
        }
      } catch (err) {
        results = new Map(results).set(item.id, {
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    }

    running = false;
    finished = true;
  }

  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCancel();
    }
  }

  // ---- derived counts ------------------------------------------------------

  const appliedCount = $derived(
    [...results.values()].filter((r) => r.status === "suggested" && r.applied).length,
  );
</script>

<div
  class="bulk-title-backdrop"
  role="presentation"
  data-testid="bulk-title-suggest-backdrop"
  onclick={onCancel}
  onkeydown={handleKeyDown}
>
  <div
    class="bulk-title-modal"
    role="dialog"
    aria-modal="true"
    aria-label={BULK_TITLE_SUGGEST_STRINGS.ariaLabel}
    tabindex="-1"
    data-testid="bulk-title-suggest-modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h2 class="bulk-title-modal__title">
      {BULK_TITLE_SUGGEST_STRINGS.title}
    </h2>
    <p class="bulk-title-modal__subtitle">
      {BULK_TITLE_SUGGEST_STRINGS.subtitle(processableItems.length)}
    </p>

    <!-- Results table -->
    <div class="bulk-title-modal__results" data-testid="bulk-title-results">
      {#each items as item (item.id)}
        {@const res = results.get(item.id) ?? { status: "pending" as const }}
        <div class="bulk-title-modal__row" data-testid="bulk-title-row" data-item-id={item.id}>
          <span class="bulk-title-modal__row-label truncate" title={item.label}>
            {item.label}
          </span>
          <span class="bulk-title-modal__row-status" data-status={res.status}>
            {#if res.status === "pending"}
              <span class="text-fg-muted">{BULK_TITLE_SUGGEST_STRINGS.statusPending}</span>
            {:else if res.status === "skipped"}
              <span class="text-fg-muted">{BULK_TITLE_SUGGEST_STRINGS.statusSkipped}</span>
            {:else if res.status === "running"}
              <span class="text-accent animate-pulse">{BULK_TITLE_SUGGEST_STRINGS.statusRunning}</span>
            {:else if res.status === "suggested"}
              <span class="text-emerald-400" title={res.suggested}>
                ✓ {res.suggested}
              </span>
            {:else if res.status === "no_suggestion"}
              <span class="text-fg-muted">{BULK_TITLE_SUGGEST_STRINGS.statusNoSuggestion}</span>
            {:else if res.status === "error"}
              <span class="text-error" title={res.message}>
                {BULK_TITLE_SUGGEST_STRINGS.statusError}
              </span>
            {/if}
          </span>
        </div>
      {/each}
    </div>

    {#if finished}
      <p class="mt-2 text-xs text-fg-muted" data-testid="bulk-title-summary">
        {BULK_TITLE_SUGGEST_STRINGS.summary(appliedCount)}
      </p>
    {/if}

    <div class="bulk-title-modal__actions">
      <button
        type="button"
        class="bulk-title-modal__btn bulk-title-modal__btn--cancel"
        data-testid="bulk-title-cancel"
        onclick={finished ? onDone : onCancel}
      >
        {finished
          ? BULK_TITLE_SUGGEST_STRINGS.doneButton
          : BULK_TITLE_SUGGEST_STRINGS.cancelButton}
      </button>
      {#if !finished}
        <button
          type="button"
          class="bulk-title-modal__btn bulk-title-modal__btn--run"
          data-testid="bulk-title-run"
          disabled={running || processableItems.length === 0}
          onclick={() => void handleRun()}
        >
          {running
            ? BULK_TITLE_SUGGEST_STRINGS.runningButton
            : BULK_TITLE_SUGGEST_STRINGS.runButton}
        </button>
      {/if}
    </div>
  </div>
</div>

<style>
  .bulk-title-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .bulk-title-modal {
    background: rgb(var(--bearings-surface-1));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.5rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    width: 100%;
    max-width: 36rem;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1.25rem;
    overflow: hidden;
  }

  .bulk-title-modal__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: rgb(var(--bearings-fg-strong));
    margin: 0;
  }

  .bulk-title-modal__subtitle {
    font-size: 0.8125rem;
    color: rgb(var(--bearings-fg-muted));
    margin: 0;
  }

  .bulk-title-modal__results {
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    padding: 0.375rem;
    background: rgb(var(--bearings-surface-2));
    max-height: 20rem;
  }

  .bulk-title-modal__row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.25rem 0.375rem;
    border-radius: 0.25rem;
    font-size: 0.8125rem;
  }

  .bulk-title-modal__row:nth-child(odd) {
    background: rgb(var(--bearings-surface-1));
  }

  .bulk-title-modal__row-label {
    flex: 0 0 40%;
    color: rgb(var(--bearings-fg));
    max-width: 40%;
  }

  .bulk-title-modal__row-status {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .bulk-title-modal__actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .bulk-title-modal__btn {
    padding: 0.3125rem 0.875rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg));
  }

  .bulk-title-modal__btn:hover:not(:disabled) {
    background: rgb(var(--bearings-surface-1));
  }

  .bulk-title-modal__btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .bulk-title-modal__btn--run {
    background: rgb(var(--bearings-accent));
    color: rgb(var(--bearings-fg-strong));
    border-color: rgb(var(--bearings-accent));
  }

  .bulk-title-modal__btn--run:hover:not(:disabled) {
    opacity: 0.85;
  }
</style>
