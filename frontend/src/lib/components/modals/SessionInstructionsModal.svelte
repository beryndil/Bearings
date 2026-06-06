<script lang="ts">
  /**
   * SessionInstructionsModal — focused editor for the
   * ``session_instructions`` instruction layer.
   *
   * Opened when the user clicks the ``session_instructions`` layer card
   * in the Instructions inspector panel.  Provides a full-screen modal
   * with a single editable textarea, saving via
   * ``PATCH /api/sessions/{id}`` with ``{session_instructions}``.
   *
   * Behavior anchors:
   * - ``docs/behavior/chat.md`` §"System-prompt layers contract" —
   *   ``session_instructions`` is the per-session override layer.
   * - Gap-cycle-10-001 — original session instructions edit surface via
   *   ``SessionEdit``; this modal is the focused replacement opened by
   *   clicking the layer card directly.
   */
  import { untrack } from "svelte";
  import { SESSION_INSTRUCTIONS_EDIT_STRINGS } from "../../config";
  import { patchSession } from "../../api/sessions";

  interface Props {
    /** Session id — target for the PATCH call. */
    sessionId: string;
    /** Current instructions content seeded from the layer body. */
    initialContent: string;
    /** Called after a successful save so the parent can re-fetch layers. */
    onSave: () => void;
    onCancel: () => void;
  }

  const { sessionId, initialContent, onSave, onCancel }: Props = $props();

  let contentValue = $state(untrack(() => initialContent));
  let saving = $state(false);
  let errorMsg = $state<string | null>(null);

  // ---- save ---------------------------------------------------------------

  async function handleSave(): Promise<void> {
    saving = true;
    errorMsg = null;
    try {
      await patchSession(sessionId, {
        session_instructions: contentValue.trim() === "" ? null : contentValue,
      });
      onSave();
    } catch (err) {
      errorMsg = `${SESSION_INSTRUCTIONS_EDIT_STRINGS.errorPrefix} ${err instanceof Error ? err.message : String(err)}`;
    } finally {
      saving = false;
    }
  }

  function handleClear(): void {
    contentValue = "";
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
  class="session-instr-backdrop"
  role="presentation"
  data-testid="session-instr-edit-backdrop"
  onclick={onCancel}
  onkeydown={handleKeyDown}
>
  <div
    class="session-instr-modal"
    role="dialog"
    aria-modal="true"
    aria-label={SESSION_INSTRUCTIONS_EDIT_STRINGS.ariaLabel}
    tabindex="-1"
    data-testid="session-instr-edit-modal"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <h2 class="session-instr-modal__title" data-testid="session-instr-edit-title">
      {SESSION_INSTRUCTIONS_EDIT_STRINGS.title}
    </h2>

    <!-- Content textarea -->
    <div class="session-instr-modal__field">
      <label for="session-instr-content-input" class="session-instr-modal__label">
        {SESSION_INSTRUCTIONS_EDIT_STRINGS.contentLabel}
      </label>
      <textarea
        id="session-instr-content-input"
        class="session-instr-modal__textarea"
        data-testid="session-instr-content-input"
        placeholder={SESSION_INSTRUCTIONS_EDIT_STRINGS.contentPlaceholder}
        bind:value={contentValue}
        disabled={saving}
        rows={22}
      ></textarea>
    </div>

    <!-- Error -->
    {#if errorMsg !== null}
      <p class="session-instr-modal__error" data-testid="session-instr-edit-error">{errorMsg}</p>
    {/if}

    <!-- Actions -->
    <div class="session-instr-modal__actions">
      <button
        type="button"
        class="session-instr-modal__btn session-instr-modal__btn--clear"
        data-testid="session-instr-clear"
        disabled={saving}
        onclick={handleClear}
      >
        {SESSION_INSTRUCTIONS_EDIT_STRINGS.clearButton}
      </button>
      <span class="flex-1"></span>
      <button
        type="button"
        class="session-instr-modal__btn session-instr-modal__btn--cancel"
        data-testid="session-instr-cancel"
        disabled={saving}
        onclick={onCancel}
      >
        {SESSION_INSTRUCTIONS_EDIT_STRINGS.cancelButton}
      </button>
      <button
        type="button"
        class="session-instr-modal__btn session-instr-modal__btn--save"
        data-testid="session-instr-save"
        disabled={saving}
        onclick={() => void handleSave()}
      >
        {saving
          ? SESSION_INSTRUCTIONS_EDIT_STRINGS.savingButton
          : SESSION_INSTRUCTIONS_EDIT_STRINGS.saveButton}
      </button>
    </div>
  </div>
</div>

<style>
  .session-instr-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .session-instr-modal {
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

  .session-instr-modal__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: rgb(var(--bearings-fg-strong));
    margin: 0;
  }

  .session-instr-modal__field {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
    flex: 1;
  }

  .session-instr-modal__label {
    font-size: 0.75rem;
    font-weight: 500;
    color: rgb(var(--bearings-fg-muted));
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .session-instr-modal__textarea {
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

  .session-instr-modal__textarea:focus {
    border-color: rgb(var(--bearings-accent));
    box-shadow: 0 0 0 1px rgb(var(--bearings-accent));
  }

  .session-instr-modal__textarea:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .session-instr-modal__error {
    font-size: 0.75rem;
    color: #f87171;
    margin: 0;
  }

  .session-instr-modal__actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding-top: 0.25rem;
  }

  .session-instr-modal__btn {
    padding: 0.3125rem 0.875rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    cursor: pointer;
    border: 1px solid rgb(var(--bearings-border));
    background: rgb(var(--bearings-surface-2));
    color: rgb(var(--bearings-fg));
  }

  .session-instr-modal__btn:hover:not(:disabled) {
    background: rgb(var(--bearings-surface-1));
  }

  .session-instr-modal__btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .session-instr-modal__btn--clear {
    font-size: 0.75rem;
    padding: 0.25rem 0.625rem;
    color: rgb(var(--bearings-fg-muted));
  }

  .session-instr-modal__btn--save {
    background: rgb(var(--bearings-accent));
    color: rgb(var(--bearings-fg-strong));
    border-color: rgb(var(--bearings-accent));
  }

  .session-instr-modal__btn--save:hover:not(:disabled) {
    opacity: 0.85;
  }
</style>
