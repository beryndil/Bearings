<script lang="ts">
  /** Real toggle widget (not a raw checkbox) for boolean preferences.
   * Built on top of a hidden `<input type="checkbox">` so the form
   * semantics, focus behavior, and `bind:checked` parity all stay
   * native — the visual track/knob is a pure CSS shell wrapping the
   * input.
   *
   * Wraps `SettingsRow` so every toggle in the dialog has identical
   * title/description/control geometry. Pass `onChange` for the
   * autosave hook: it fires *after* the local `checked` state has
   * already flipped, returns a promise, and the row surfaces the
   * resolved state (idle → saving → saved/error) automatically.
   *
   * Carve-outs the autosave model has to support and this primitive
   * already supports:
   *   - permission gates: `onChange` can throw, in which case the row
   *     enters error state AND the local `checked` is reverted before
   *     re-throwing so consumers can show a footnote explaining why.
   *   - notify-permission immediate-prompt UX: same path. The notify
   *     section's `onChange` calls `Notification.requestPermission()`
   *     and throws if denied; this primitive handles the rest.
   */
  import SettingsRow, { type SaveState } from './SettingsRow.svelte';
  import type { Snippet } from 'svelte';

  interface Props {
    title: string;
    description?: string;
    /** Bound boolean. Two-way: flips immediately on click; consumers
     * who need to veto persistence should throw from `onChange`
     * which auto-reverts. */
    checked: boolean;
    /** Forwarded to inner input.disabled. */
    disabled?: boolean;
    /** Stable id for label-control association. Generated if absent. */
    id?: string;
    /** Optional async hook fired after the value flips. Throw to
     * roll back the flip and surface an error state. */
    onChange?: (next: boolean) => Promise<void> | void;
    /** Optional footnote rendered below the description (e.g.
     * permission-state explanations). */
    footnote?: Snippet;
  }

  let {
    title,
    description,
    checked = $bindable(),
    disabled = false,
    id,
    onChange,
    footnote
  }: Props = $props();

  // Random-ish id when caller didn't supply one — `generated` is
  // initialised once at module instantiation; `$derived` keeps the
  // reactive contract with `id` so a prop change propagates.
  const generated = `settings-toggle-${Math.random().toString(36).slice(2, 9)}`;
  const inputId = $derived(id ?? generated);
  let saveState = $state<SaveState>({ kind: 'idle' });
  let savedTimer: ReturnType<typeof setTimeout> | null = null;

  async function flip(next: boolean): Promise<void> {
    const previous = checked;
    checked = next;
    if (!onChange) return;
    saveState = { kind: 'saving' };
    try {
      await onChange(next);
      saveState = { kind: 'saved' };
      if (savedTimer) clearTimeout(savedTimer);
      savedTimer = setTimeout(() => {
        saveState = { kind: 'idle' };
      }, 1500);
    } catch (err) {
      checked = previous;
      saveState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err)
      };
    }
  }
</script>

<SettingsRow {title} {description} controlId={inputId} state={saveState} {footnote}>
  {#snippet control()}
    <button
      type="button"
      class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors
        focus:outline-none focus:ring-2 focus:ring-sky-500/60 focus:ring-offset-1
        focus:ring-offset-slate-900
        {checked ? 'bg-emerald-600' : 'bg-slate-700'}
        {disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}"
      role="switch"
      aria-checked={checked}
      aria-label={title}
      {disabled}
      onclick={() => {
        if (disabled) return;
        void flip(!checked);
      }}
      data-testid="settings-toggle"
    >
      <span
        class="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
          {checked ? 'translate-x-5' : 'translate-x-1'}"
      ></span>
    </button>
    <input
      id={inputId}
      type="checkbox"
      class="sr-only"
      {checked}
      {disabled}
      onchange={(e) => {
        if (disabled) return;
        void flip((e.currentTarget as HTMLInputElement).checked);
      }}
      tabindex="-1"
      aria-hidden="true"
    />
  {/snippet}
</SettingsRow>
