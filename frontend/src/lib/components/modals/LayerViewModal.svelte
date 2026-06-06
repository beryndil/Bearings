<script lang="ts">
  /**
   * LayerViewModal — read-only content viewer for non-file-backed
   * instruction layers (``baseline``, ``tag_memory``,
   * ``template_baseline``).
   *
   * Opened when the user clicks one of these layer cards in the
   * Instructions inspector panel.  Displays the assembled layer body
   * in a scrollable read-only textarea so the user can inspect and
   * copy the content.  A contextual note explains why the layer is
   * not editable from this panel and where to go to change it.
   *
   * Behavior anchors:
   * - ``docs/behavior/chat.md`` §"System-prompt layers contract" —
   *   layer kinds and their mutability.
   */
  import { LAYER_VIEW_MODAL_STRINGS } from "../../config";

  interface Props {
    /** Human-readable kind label shown as the modal title. */
    kindLabel: string;
    /** Layer kind identifier — used to select the contextual note. */
    kind: string;
    /** Assembled layer body text to display. */
    content: string;
    /** Optional source_path (present for project_claude_md layers shown
     *  in read-only mode, absent for baseline/tag_memory/template). */
    path?: string | null;
    onClose: () => void;
  }

  const { kindLabel, kind, content, path = null, onClose }: Props = $props();

  const contextualNote = $derived(
    kind === "tag_memory"
      ? LAYER_VIEW_MODAL_STRINGS.tagMemoryNote
      : kind === "template_baseline"
        ? LAYER_VIEW_MODAL_STRINGS.templateBaselineNote
        : LAYER_VIEW_MODAL_STRINGS.readOnlyNote,
  );

  // ---- keyboard -----------------------------------------------------------

  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  }
</script>

<div
  class="layer-view-backdrop"
  role="presentation"
  data-testid="layer-view-backdrop"
  onclick={onClose}
  onkeydown={handleKeyDown}
>
  <div
    class="layer-view-modal"
    role="dialog"
    aria-modal="true"
    aria-label={LAYER_VIEW_MODAL_STRINGS.ariaLabel}
    tabindex="-1"
    data-testid="layer-view-modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h2 class="layer-view-modal__title" data-testid="layer-view-title">{kindLabel}</h2>

    {#if path}
      <div class="layer-view-modal__path" data-testid="layer-view-path">
        <span class="layer-view-modal__path-label">Source:</span>
        <span class="layer-view-modal__path-value">{path}</span>
      </div>
    {/if}

    <!-- Content (read-only) -->
    <div class="layer-view-modal__field">
      <span class="layer-view-modal__label">
        {LAYER_VIEW_MODAL_STRINGS.contentLabel}
      </span>
      <textarea
        class="layer-view-modal__textarea"
        data-testid="layer-view-content"
        readonly
        rows={22}
        value={content}
      ></textarea>
    </div>

    <!-- Contextual note -->
    <p class="layer-view-modal__note" data-testid="layer-view-note">{contextualNote}</p>

    <!-- Actions -->
    <div class="layer-view-modal__actions">
      <button
        type="button"
        class="layer-view-modal__btn"
        data-testid="layer-view-close-btn"
        onclick={onClose}
      >
        {LAYER_VIEW_MODAL_STRINGS.closeButton}
      </button>
    </div>
  </div>
</div>

<style>
  .layer-view-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .layer-view-modal {
    background: rgb(var(--bearings-surface-1));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.5rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    width: 100%;
    max-width: 52rem;
    max-height: 90vh;
    overflow-y: auto;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .layer-view-modal__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: rgb(var(--bearings-fg-strong));
    margin: 0;
  }

  .layer-view-modal__path {
    display: flex;
    align-items: baseline;
    gap: 0.375rem;
    background: rgb(var(--bearings-surface-2));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    padding: 0.375rem 0.5rem;
  }

  .layer-view-modal__path-label {
    font-size: 0.75rem;
    font-weight: 500;
    color: rgb(var(--bearings-fg-muted));
    text-transform: uppercase;
    letter-spacing: 0.04em;
    flex-shrink: 0;
  }

  .layer-view-modal__path-value {
    font-family: monospace;
    font-size: 0.8125rem;
    color: rgb(var(--bearings-fg));
    word-break: break-all;
    overflow-wrap: break-word;
  }

  .layer-view-modal__field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .layer-view-modal__label {
    font-size: 0.75rem;
    font-weight: 500;
    color: rgb(var(--bearings-fg-muted));
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .layer-view-modal__textarea {
    width: 100%;
    background: rgb(var(--bearings-surface-2));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    padding: 0.375rem 0.5rem;
    font-family: monospace;
    font-size: 0.8125rem;
    color: rgb(var(--bearings-fg));
    outline: none;
    resize: vertical;
    box-sizing: border-box;
    cursor: default;
    user-select: text;
  }

  .layer-view-modal__note {
    font-size: 0.75rem;
    color: rgb(var(--bearings-fg-muted));
    font-style: italic;
    margin: 0;
  }

  .layer-view-modal__actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .layer-view-modal__btn {
    padding: 0.3125rem 0.875rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg));
  }

  .layer-view-modal__btn:hover {
    background: rgb(var(--bearings-surface-1));
  }
</style>
