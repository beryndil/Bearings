<script lang="ts">
  /**
   * Checkpoint compare modal -- opened by ``checkpoint.compare`` context-menu
   * action on a gutter chip (T1-08 parity gap).
   *
   * Shows every message added to the session *after* the checkpoint's anchor
   * message, i.e. the delta since the checkpoint was created.  Each entry
   * shows the role badge and a content preview.
   *
   * Behavior anchor: ``docs/behavior/context-menus.md``
   * §"Checkpoint (gutter chip)" -- ``checkpoint.compare`` is listed under the
   * view section.
   *
   * Props:
   *   checkpointId   -- id of the checkpoint being compared.
   *   checkpointLabel -- user-visible label (shown in the modal title).
   *   onClose        -- called when the user dismisses the modal.
   *
   * The component fetches the compare result on mount.
   */
  import { onMount } from "svelte";
  import { compareCheckpoint, type CheckpointCompareResult } from "../../api/checkpoints";
  import { CHECKPOINT_GUTTER_STRINGS } from "../../config";

  interface Props {
    /** ID of the checkpoint to compare against. */
    checkpointId: string;
    /** User-visible label shown in the modal title. */
    checkpointLabel: string;
    /** Called when the user dismisses the modal. */
    onClose: () => void;
  }

  const { checkpointId, checkpointLabel, onClose }: Props = $props();

  let loading = $state(true);
  let error = $state<string | null>(null);
  let result = $state<CheckpointCompareResult | null>(null);

  onMount(() => {
    void (async () => {
      try {
        result = await compareCheckpoint(checkpointId);
      } catch (err) {
        error = err instanceof Error ? err.message : String(err);
      } finally {
        loading = false;
      }
    })();
  });

  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  }

  /** Truncate long message content for the preview rows. */
  function previewContent(content: string, maxLen = 300): string {
    if (content.length <= maxLen) return content;
    return content.slice(0, maxLen) + "…";
  }

  /** Human-readable sub-header count string. */
  function countLabel(n: number): string {
    if (n === 1) return CHECKPOINT_GUTTER_STRINGS.compareModalCountSingular;
    return CHECKPOINT_GUTTER_STRINGS.compareModalCountPlural(n);
  }
</script>

<div
  class="cpc-backdrop"
  role="presentation"
  data-testid="checkpoint-compare-backdrop"
  onclick={onClose}
  onkeydown={handleKeyDown}
>
  <div
    class="cpc-modal"
    role="dialog"
    aria-modal="true"
    aria-label="{CHECKPOINT_GUTTER_STRINGS.compareModalTitlePrefix} {checkpointLabel}"
    tabindex="-1"
    data-testid="checkpoint-compare-modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <header class="cpc-modal__header">
      <h2 class="cpc-modal__title" data-testid="checkpoint-compare-title">
        {CHECKPOINT_GUTTER_STRINGS.compareModalTitlePrefix}
        <span class="cpc-modal__label">"{checkpointLabel}"</span>
      </h2>
      {#if result !== null && !loading}
        <p class="cpc-modal__subtitle" data-testid="checkpoint-compare-count">
          {#if result.delta_message_count === 0}
            {CHECKPOINT_GUTTER_STRINGS.compareModalEmpty}
          {:else}
            {countLabel(result.delta_message_count)}
          {/if}
        </p>
      {/if}
    </header>

    <div class="cpc-modal__body" data-testid="checkpoint-compare-body">
      {#if loading}
        <p class="cpc-modal__status">Loading…</p>
      {:else if error !== null}
        <p class="cpc-modal__error" role="alert" data-testid="checkpoint-compare-error">
          {error}
        </p>
      {:else if result !== null && result.delta_message_count === 0}
        <p class="cpc-modal__empty" data-testid="checkpoint-compare-empty">
          {CHECKPOINT_GUTTER_STRINGS.compareModalEmpty}
        </p>
      {:else if result !== null}
        <ul class="cpc-modal__list" data-testid="checkpoint-compare-list">
          {#each result.delta_messages as msg (msg.id)}
            <li
              class="cpc-modal__item"
              class:cpc-modal__item--user={msg.role === "user"}
              class:cpc-modal__item--assistant={msg.role === "assistant"}
              data-testid="checkpoint-compare-message"
              data-role={msg.role}
            >
              <span
                class="cpc-modal__role-badge"
                class:cpc-modal__role-badge--user={msg.role === "user"}
                class:cpc-modal__role-badge--assistant={msg.role === "assistant"}
                aria-label={msg.role}
              >
                {msg.role}
              </span>
              <span class="cpc-modal__content">{previewContent(msg.content)}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <footer class="cpc-modal__footer">
      <button
        type="button"
        class="cpc-modal__close-btn"
        data-testid="checkpoint-compare-close"
        onclick={onClose}
      >
        {CHECKPOINT_GUTTER_STRINGS.compareModalClose}
      </button>
    </footer>
  </div>
</div>

<style>
  .cpc-backdrop {
    position: fixed;
    inset: 0;
    background-color: rgba(0, 0, 0, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 900;
  }

  .cpc-modal {
    background: var(--color-surface-1);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    display: flex;
    flex-direction: column;
    min-width: 360px;
    max-width: 560px;
    width: 100%;
    max-height: 75vh;
    overflow: hidden;
  }

  .cpc-modal__header {
    padding: 16px 20px 12px;
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
  }

  .cpc-modal__title {
    margin: 0 0 4px;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--color-fg-strong);
  }

  .cpc-modal__label {
    font-style: italic;
  }

  .cpc-modal__subtitle {
    margin: 0;
    font-size: 0.8rem;
    color: var(--color-fg-muted);
  }

  .cpc-modal__body {
    flex: 1;
    overflow-y: auto;
    padding: 12px 0;
  }

  .cpc-modal__status,
  .cpc-modal__empty {
    padding: 12px 20px;
    font-size: 0.875rem;
    color: var(--color-fg-muted);
    margin: 0;
  }

  .cpc-modal__error {
    padding: 12px 20px;
    font-size: 0.875rem;
    color: var(--color-fg-danger, #dc2626);
    margin: 0;
  }

  .cpc-modal__list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .cpc-modal__item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 20px;
    border-bottom: 1px solid var(--color-border);
    background: var(--color-surface-1);
  }

  .cpc-modal__item:last-child {
    border-bottom: none;
  }

  .cpc-modal__item--user {
    background: var(--color-surface-2, var(--color-surface-1));
  }

  .cpc-modal__role-badge {
    flex-shrink: 0;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 2px 6px;
    border-radius: 3px;
    margin-top: 1px;
  }

  .cpc-modal__role-badge--user {
    background: var(--color-accent-muted, rgba(99, 102, 241, 0.15));
    color: var(--color-accent, #6366f1);
  }

  .cpc-modal__role-badge--assistant {
    background: var(--color-fg-muted-bg, rgba(107, 114, 128, 0.12));
    color: var(--color-fg-muted);
  }

  .cpc-modal__content {
    font-size: 0.85rem;
    color: var(--color-fg);
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    flex: 1;
  }

  .cpc-modal__footer {
    padding: 12px 20px;
    border-top: 1px solid var(--color-border);
    display: flex;
    justify-content: flex-end;
    flex-shrink: 0;
  }

  .cpc-modal__close-btn {
    padding: 6px 16px;
    border-radius: 5px;
    border: 1px solid var(--color-border);
    background: var(--color-surface-2, var(--color-surface-1));
    color: var(--color-fg);
    font-size: 0.875rem;
    cursor: pointer;
    transition: background 0.1s;
  }

  .cpc-modal__close-btn:hover {
    background: var(--color-surface-hover, var(--color-border));
  }
</style>
