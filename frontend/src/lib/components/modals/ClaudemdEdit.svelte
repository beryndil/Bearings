<script lang="ts">
  /**
   * ClaudemdEdit modal — edit a filesystem-sourced CLAUDE.md layer file
   * in-place from the Instructions inspector panel.
   *
   * Behavior anchors:
   *
   * - Opened by ``InspectorInstructions`` when the user clicks "Edit…" on
   *   a ``project_claude_md`` layer row.
   * - Calls ``PUT /api/sessions/{id}/system_prompt/layer`` with the
   *   session id + absolute file path + new content.
   * - The backend validates the path against the session's current
   *   assembled layers so only files already in the system prompt can be
   *   written.
   * - On save success: calls ``onSave()`` so the parent re-fetches layers.
   * - Cancel / Esc / backdrop click: calls ``onCancel()`` with no write.
   */
  import { CLAUDEMD_EDIT_STRINGS } from "../../config";
  import { putSessionLayerContent } from "../../api/sessions";

  interface Props {
    /** Session id — used as the write-endpoint scope guard. */
    sessionId: string;
    /** Absolute path of the CLAUDE.md file being edited. */
    path: string;
    /** Current file content seeded from the assembled layer body. */
    initialContent: string;
    /** Called after a successful write so the parent can re-fetch layers. */
    onSave: () => void;
    onCancel: () => void;
  }

  const { sessionId, path, initialContent, onSave, onCancel }: Props = $props();

  let contentValue = $state(initialContent);
  let saving = $state(false);
  let errorMsg = $state<string | null>(null);
  let copyLabel = $state(CLAUDEMD_EDIT_STRINGS.copyPathButton);

  // ---- copy path ----------------------------------------------------------

  function copyPath(): void {
    void navigator.clipboard.writeText(path).then(() => {
      copyLabel = CLAUDEMD_EDIT_STRINGS.copyPathDone;
      setTimeout(() => {
        copyLabel = CLAUDEMD_EDIT_STRINGS.copyPathButton;
      }, 1500);
    });
  }

  // ---- save ---------------------------------------------------------------

  async function handleSave(): Promise<void> {
    saving = true;
    errorMsg = null;
    try {
      await putSessionLayerContent(sessionId, path, contentValue);
      onSave();
    } catch (err) {
      errorMsg = `${CLAUDEMD_EDIT_STRINGS.errorPrefix} ${err instanceof Error ? err.message : String(err)}`;
    } finally {
      saving = false;
    }
  }

  // ---- keyboard -----------------------------------------------------------

  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.stopPropagation();
      onCancel();
    }
  }
</script>

<div
  class="claudemd-edit-backdrop"
  role="presentation"
  data-testid="claudemd-edit-backdrop"
  onclick={onCancel}
  onkeydown={handleKeyDown}
>
  <div
    class="claudemd-edit-modal"
    role="dialog"
    aria-modal="true"
    aria-label={CLAUDEMD_EDIT_STRINGS.ariaLabel}
    tabindex="-1"
    data-testid="claudemd-edit-modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h2 class="claudemd-edit-modal__title" data-testid="claudemd-edit-title">
      {CLAUDEMD_EDIT_STRINGS.title}
    </h2>

    <!-- File path (read-only display with copy button) -->
    <div class="claudemd-edit-modal__field">
      <span class="claudemd-edit-modal__label">
        {CLAUDEMD_EDIT_STRINGS.pathLabel}
      </span>
      <div class="claudemd-edit-modal__path-row">
        <span
          class="claudemd-edit-modal__path"
          title={path}
          data-testid="claudemd-edit-path"
        >{path}</span>
        <button
          type="button"
          class="claudemd-edit-modal__btn claudemd-edit-modal__btn--copy"
          data-testid="claudemd-edit-copy-path"
          onclick={copyPath}
        >
          {copyLabel}
        </button>
      </div>
    </div>

    <!-- Content textarea -->
    <div class="claudemd-edit-modal__field">
      <label for="claudemd-edit-content-input" class="claudemd-edit-modal__label">
        {CLAUDEMD_EDIT_STRINGS.contentLabel}
      </label>
      <textarea
        id="claudemd-edit-content-input"
        class="claudemd-edit-modal__textarea"
        data-testid="claudemd-edit-content-input"
        bind:value={contentValue}
        disabled={saving}
        rows={20}
      ></textarea>
    </div>

    <!-- Error -->
    {#if errorMsg !== null}
      <p class="claudemd-edit-modal__error" data-testid="claudemd-edit-error">{errorMsg}</p>
    {/if}

    <!-- Actions -->
    <div class="claudemd-edit-modal__actions">
      <button
        type="button"
        class="claudemd-edit-modal__btn claudemd-edit-modal__btn--cancel"
        data-testid="claudemd-edit-cancel"
        disabled={saving}
        onclick={onCancel}
      >
        {CLAUDEMD_EDIT_STRINGS.cancelButton}
      </button>
      <button
        type="button"
        class="claudemd-edit-modal__btn claudemd-edit-modal__btn--save"
        data-testid="claudemd-edit-save"
        disabled={saving}
        onclick={() => void handleSave()}
      >
        {saving ? CLAUDEMD_EDIT_STRINGS.savingButton : CLAUDEMD_EDIT_STRINGS.saveButton}
      </button>
    </div>
  </div>
</div>

<style>
  .claudemd-edit-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .claudemd-edit-modal {
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

  .claudemd-edit-modal__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: rgb(var(--bearings-fg-strong));
    margin: 0;
  }

  .claudemd-edit-modal__field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .claudemd-edit-modal__label {
    font-size: 0.75rem;
    font-weight: 500;
    color: rgb(var(--bearings-fg-muted));
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .claudemd-edit-modal__path-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: rgb(var(--bearings-surface-2));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    padding: 0.375rem 0.5rem;
  }

  .claudemd-edit-modal__path {
    flex: 1;
    min-width: 0;
    overflow-wrap: break-word;
    word-break: break-all;
    font-family: monospace;
    font-size: 0.8125rem;
    color: rgb(var(--bearings-fg));
    user-select: all;
  }

  .claudemd-edit-modal__textarea {
    width: 100%;
    background: rgb(var(--bearings-surface-2));
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.25rem;
    padding: 0.375rem 0.5rem;
    font-family: monospace;
    font-size: 0.8125rem;
    color: rgb(var(--bearings-fg-strong));
    outline: none;
    resize: vertical;
    box-sizing: border-box;
  }

  .claudemd-edit-modal__textarea:focus {
    border-color: rgb(var(--bearings-accent));
    box-shadow: 0 0 0 1px rgb(var(--bearings-accent));
  }

  .claudemd-edit-modal__textarea:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .claudemd-edit-modal__error {
    font-size: 0.75rem;
    color: #f87171;
    margin: 0;
  }

  .claudemd-edit-modal__actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .claudemd-edit-modal__btn {
    padding: 0.3125rem 0.875rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg));
  }

  .claudemd-edit-modal__btn:hover:not(:disabled) {
    background: rgb(var(--bearings-surface-1));
  }

  .claudemd-edit-modal__btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .claudemd-edit-modal__btn--copy {
    flex-shrink: 0;
    padding: 0.1875rem 0.5rem;
    font-size: 0.75rem;
  }

  .claudemd-edit-modal__btn--save {
    background: rgb(var(--bearings-accent));
    color: rgb(var(--bearings-fg-strong));
    border-color: rgb(var(--bearings-accent));
  }

  .claudemd-edit-modal__btn--save:hover:not(:disabled) {
    opacity: 0.85;
  }
</style>
