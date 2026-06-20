<script lang="ts">
  /**
   * TemplateSaveDialog — modal for naming a session before saving it as a
   * template (N-7; ``session.save_as_template``).
   *
   * Replaces the ``window.prompt()`` call in :class:`SessionRow` with a
   * styled dialog consistent with the ChangeModel modal.  The parent is
   * responsible for showing/hiding: render the dialog inside an ``{#if}``
   * block and pass ``onCancel`` to close it.
   */
  import { onMount, untrack } from "svelte";
  import { TEMPLATE_SAVE_DIALOG_STRINGS } from "../../config";

  interface Props {
    /** Pre-filled name — typically the session title. */
    initialName: string;
    /** Called with the trimmed name when the user clicks Save. */
    onSave: (name: string) => void;
    /** Called when the user cancels or clicks the backdrop. */
    onCancel: () => void;
    /** Inline error to show below the input (null = no error). */
    errorMessage?: string | null;
  }

  const { initialName, onSave, onCancel, errorMessage = null }: Props = $props();

  // untrack() captures the prop at mount time — this is a modal that is
  // seeded once from the session title and then the user edits freely.
  let name = $state(untrack(() => initialName));

  let inputEl = $state<HTMLInputElement | null>(null);

  onMount(() => {
    inputEl?.focus();
  });
  let localError = $state<string | null>(null);

  function handleSave(): void {
    const trimmed = name.trim();
    if (trimmed === "") {
      localError = TEMPLATE_SAVE_DIALOG_STRINGS.emptyNameError;
      return;
    }
    localError = null;
    onSave(trimmed);
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      onCancel();
    } else if (event.key === "Enter") {
      handleSave();
    }
  }

  const displayError = $derived(localError ?? errorMessage ?? null);
</script>

<!-- Backdrop -->
<div
  class="fixed inset-0 z-200 flex items-center justify-center bg-black/50 p-4"
  role="presentation"
  onclick={onCancel}
  onkeydown={() => {}}
>
  <!-- Dialog card — stop propagation so clicks inside don't close -->
  <div
    class="w-full max-w-xs rounded border border-border bg-surface-1 p-4 shadow-xl"
    role="dialog"
    aria-modal="true"
    aria-label={TEMPLATE_SAVE_DIALOG_STRINGS.ariaLabel}
    tabindex="-1"
    data-testid="template-save-dialog"
    onclick={(e) => e.stopPropagation()}
    onkeydown={handleKeydown}
  >
    <h3 class="mb-3 text-sm font-semibold text-fg-strong">
      {TEMPLATE_SAVE_DIALOG_STRINGS.title}
    </h3>

    <label class="mb-1 block text-xs text-fg-muted" for="template-save-name">
      {TEMPLATE_SAVE_DIALOG_STRINGS.nameLabel}
    </label>
    <input
      id="template-save-name"
      type="text"
      class="w-full rounded border border-border bg-surface-2 px-3 py-2 text-sm text-fg focus:border-accent focus:outline-none"
      placeholder={TEMPLATE_SAVE_DIALOG_STRINGS.namePlaceholder}
      bind:value={name}
      bind:this={inputEl}
      data-testid="template-save-dialog-input"
    />

    {#if displayError !== null}
      <p class="mt-1 text-xs text-error" data-testid="template-save-dialog-error">
        {displayError}
      </p>
    {/if}

    <div class="mt-3 flex justify-end gap-2">
      <button
        type="button"
        class="rounded border border-border bg-surface-2 px-3 py-1 text-xs text-fg hover:bg-surface-1"
        data-testid="template-save-dialog-cancel"
        onclick={onCancel}
      >
        {TEMPLATE_SAVE_DIALOG_STRINGS.cancelLabel}
      </button>
      <button
        type="button"
        class="rounded border border-accent bg-accent px-3 py-1 text-xs text-fg-strong hover:opacity-90"
        data-testid="template-save-dialog-save"
        onclick={handleSave}
      >
        {TEMPLATE_SAVE_DIALOG_STRINGS.saveLabel}
      </button>
    </div>
  </div>
</div>
