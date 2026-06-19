<script lang="ts">
  /**
   * Reply-action action strip for a completed assistant message (T1-09).
   *
   * Renders a row of transformation buttons (Summarize, Reformat, etc.)
   * fetched from ``GET /api/reply_actions/catalog``. Clicking one calls
   * ``POST /api/sessions/{id}/reply_actions`` and displays the result
   * in an inline preview panel that closes when dismissed.
   *
   * Behavior anchors:
   *
   * - Catalog is fetched once on mount (cached while the component is
   *   mounted; re-fetched on re-mount). A fetch failure degrades
   *   gracefully — the strip is hidden rather than showing an error.
   * - The preview panel renders below the action buttons with the
   *   transformed content rendered as plain text. A "Copy" button writes
   *   the content to the clipboard; "Close" dismisses the panel.
   * - Only one action runs at a time; the strip is disabled while a call
   *   is in flight.
   * - The component is only rendered on complete assistant turns with a
   *   non-empty body; the parent ``MessageTurn`` guards on those.
   */
  import { onMount } from "svelte";
  import { getReplyActionCatalog, applyReplyAction } from "../../api/reply_actions";
  import type { ActionDescriptor, ApplyActionOut } from "../../api/reply_actions";
  import { REPLY_ACTION_STRINGS } from "../../config";

  interface Props {
    /** Session that owns the message — used to scope the apply endpoint. */
    sessionId: string;
    /** Raw body text of the assistant turn being acted on. */
    messageBody: string;
  }

  const { sessionId, messageBody }: Props = $props();

  let catalog = $state<ActionDescriptor[]>([]);
  let applying = $state(false);
  let activeActionId = $state<string | null>(null);
  let result = $state<ApplyActionOut | null>(null);
  let applyError = $state<string | null>(null);

  onMount(() => {
    void getReplyActionCatalog().then((entries) => {
      catalog = entries;
    });
  });

  async function handleApply(action: ActionDescriptor): Promise<void> {
    if (applying || messageBody.trim().length === 0) return;
    applying = true;
    activeActionId = action.id;
    applyError = null;
    result = null;
    try {
      result = await applyReplyAction(sessionId, {
        source_content: messageBody,
        transformation_id: action.id,
      });
    } catch (err) {
      applyError = err instanceof Error ? err.message : String(err);
    } finally {
      applying = false;
    }
  }

  function handleCopy(): void {
    if (result === null) return;
    void navigator.clipboard.writeText(result.content);
  }

  function handleClose(): void {
    result = null;
    applyError = null;
    activeActionId = null;
  }
</script>

{#if catalog.length > 0}
  <div class="reply-action-strip mt-2" data-testid="reply-action-strip">
    <div class="flex flex-wrap items-center gap-1">
      <span class="text-xs text-fg-muted">{REPLY_ACTION_STRINGS.stripLabel}</span>
      {#each catalog as action (action.id)}
        <button
          type="button"
          class="reply-action-strip__btn"
          class:reply-action-strip__btn--active={activeActionId === action.id && applying}
          data-testid="reply-action-btn"
          data-action-id={action.id}
          disabled={applying}
          title={action.description}
          onclick={() => void handleApply(action)}
        >
          {applying && activeActionId === action.id
            ? REPLY_ACTION_STRINGS.applyingLabel
            : action.label}
        </button>
      {/each}
    </div>

    {#if applyError !== null}
      <p class="mt-1 text-xs text-error" data-testid="reply-action-error">
        {REPLY_ACTION_STRINGS.errorPrefix}{applyError}
      </p>
    {/if}

    {#if result !== null}
      <div
        class="reply-action-strip__preview"
        data-testid="reply-action-preview"
        aria-label={REPLY_ACTION_STRINGS.previewAriaLabel}
      >
        <p class="reply-action-strip__preview-body">{result.content}</p>
        <div class="reply-action-strip__preview-actions">
          <button
            type="button"
            class="reply-action-strip__preview-btn"
            data-testid="reply-action-copy"
            onclick={handleCopy}
          >
            {REPLY_ACTION_STRINGS.copyLabel}
          </button>
          <button
            type="button"
            class="reply-action-strip__preview-btn"
            data-testid="reply-action-close"
            onclick={handleClose}
          >
            {REPLY_ACTION_STRINGS.closeLabel}
          </button>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .reply-action-strip__btn {
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg-muted));
    transition:
      background 0.1s,
      color 0.1s;
  }

  .reply-action-strip__btn:hover:not(:disabled) {
    background: rgb(var(--bearings-surface-1));
    color: rgb(var(--bearings-fg-strong));
  }

  .reply-action-strip__btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .reply-action-strip__btn--active {
    border-color: rgb(var(--bearings-accent));
    color: rgb(var(--bearings-accent));
  }

  .reply-action-strip__preview {
    margin-top: 0.5rem;
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    background: rgb(var(--bearings-surface-2));
    padding: 0.5rem 0.75rem;
    font-size: 0.8125rem;
  }

  .reply-action-strip__preview-body {
    color: rgb(var(--bearings-fg));
    white-space: pre-wrap;
    margin: 0 0 0.5rem 0;
    line-height: 1.5;
  }

  .reply-action-strip__preview-actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }

  .reply-action-strip__preview-btn {
    padding: 0.125rem 0.625rem;
    border-radius: 0.25rem;
    font-size: 0.75rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-1));
    color: rgb(var(--bearings-fg));
  }

  .reply-action-strip__preview-btn:hover {
    background: rgb(var(--bearings-surface-2));
  }
</style>
