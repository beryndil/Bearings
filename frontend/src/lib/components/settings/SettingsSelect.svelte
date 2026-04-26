<script lang="ts">
  /** Native `<select>` row. Native rather than custom dropdown so
   * keyboard navigation, screen-reader behavior, and OS-level
   * accessibility (Voice Control, etc.) come for free. Visual styling
   * matches the text field input — same border, bg, focus ring.
   *
   * Autosave fires immediately on change (no debounce — discrete
   * value, not a stream of keystrokes).
   */
  import SettingsRow, { type SaveState } from './SettingsRow.svelte';

  export type SelectOption<T extends string = string> = {
    value: T;
    label: string;
  };

  interface Props<T extends string = string> {
    title: string;
    description?: string;
    value: T;
    options: SelectOption<T>[];
    id?: string;
    onChange?: (next: T) => Promise<void> | void;
  }

  let {
    title,
    description,
    value = $bindable(),
    options,
    id,
    onChange
  }: Props = $props();

  const generated = `settings-select-${Math.random().toString(36).slice(2, 9)}`;
  const inputId = $derived(id ?? generated);
  let saveState = $state<SaveState>({ kind: 'idle' });
  let savedTimer: ReturnType<typeof setTimeout> | null = null;

  async function onSelect(e: Event): Promise<void> {
    const next = (e.currentTarget as HTMLSelectElement).value;
    value = next;
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
      saveState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err)
      };
    }
  }
</script>

<SettingsRow {title} {description} controlId={inputId} state={saveState}>
  {#snippet control()}
    <select
      id={inputId}
      class="rounded bg-slate-950 border border-slate-800 px-2 py-1.5 text-sm w-56
        focus:outline-none focus:border-slate-600"
      {value}
      onchange={onSelect}
      data-testid="settings-select"
    >
      {#each options as opt (opt.value)}
        <option value={opt.value}>{opt.label}</option>
      {/each}
    </select>
  {/snippet}
</SettingsRow>
