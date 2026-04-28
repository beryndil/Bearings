<script lang="ts">
  /** Single-line text input row. Wraps `SettingsRow`, takes the full
   * remaining width on the right column, debounces autosave by 400ms
   * so a string of keystrokes results in one PATCH. Throw from
   * `onChange` to surface an error state.
   *
   * `monospace` flips the font to mono — used for paths, model
   * identifiers, and the auth token where character ambiguity
   * matters. `password` flips to `type="password"` for masking.
   *
   * `maxlength` is enforced both as the HTML attribute (browser-side
   * truncation) and as the source for an inline char counter once
   * the input crosses ~80% of the cap. The counter prevents the
   * "I typed 70 chars and the server said 64" surprise.
   *
   * `validate(value)` runs synchronously on every change; truthy
   * return string surfaces as a red helper line and suppresses the
   * autosave call. Falsy return clears the error and triggers the
   * debounced save.
   */
  import SettingsRow, { type SaveState } from './SettingsRow.svelte';

  interface Props {
    title: string;
    description?: string;
    value: string;
    placeholder?: string;
    monospace?: boolean;
    password?: boolean;
    maxlength?: number;
    id?: string;
    /** Synchronous validator. Return error message to block save. */
    validate?: (value: string) => string | null;
    /** Async autosave hook. Debounced 400ms. Throw to error-state. */
    onChange?: (next: string) => Promise<void> | void;
  }

  let {
    title,
    description,
    value = $bindable(),
    placeholder,
    monospace = false,
    password = false,
    maxlength,
    id,
    validate,
    onChange,
  }: Props = $props();

  const generated = `settings-text-${Math.random().toString(36).slice(2, 9)}`;
  const inputId = $derived(id ?? generated);
  let saveState = $state<SaveState>({ kind: 'idle' });
  let validationError = $state<string | null>(null);
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let savedTimer: ReturnType<typeof setTimeout> | null = null;

  const showCounter = $derived(
    maxlength !== undefined && value.length >= Math.floor(maxlength * 0.8)
  );

  function onInput(e: Event): void {
    const next = (e.currentTarget as HTMLInputElement).value;
    value = next;
    if (validate) {
      const err = validate(next);
      validationError = err;
      if (err) {
        if (debounceTimer) clearTimeout(debounceTimer);
        saveState = { kind: 'idle' };
        return;
      }
    }
    if (!onChange) return;
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      void runSave(next);
    }, 400);
  }

  async function runSave(next: string): Promise<void> {
    saveState = { kind: 'saving' };
    try {
      await onChange?.(next);
      saveState = { kind: 'saved' };
      if (savedTimer) clearTimeout(savedTimer);
      savedTimer = setTimeout(() => {
        saveState = { kind: 'idle' };
      }, 1500);
    } catch (err) {
      saveState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }

  const inputType = $derived(password ? 'password' : 'text');
</script>

<SettingsRow {title} {description} controlId={inputId} state={saveState}>
  {#snippet control()}
    <div class="flex flex-col items-end gap-1">
      <input
        id={inputId}
        type={inputType}
        class="w-56 rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-sm
          focus:border-slate-600 focus:outline-none
          {monospace ? 'font-mono' : ''}
          {validationError ? 'border-rose-700' : ''}"
        {placeholder}
        {maxlength}
        autocomplete={password ? 'off' : undefined}
        {value}
        oninput={onInput}
        data-testid="settings-text-input"
      />
      {#if validationError}
        <span class="text-[11px] leading-snug text-rose-400" role="alert">
          {validationError}
        </span>
      {:else if showCounter}
        <span class="text-[11px] tabular-nums text-slate-500">
          {value.length}/{maxlength}
        </span>
      {/if}
    </div>
  {/snippet}
</SettingsRow>
