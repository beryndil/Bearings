<script lang="ts">
  /** The canonical row layout: title (left col, small/strong), optional
   * description below the title (left col, muted), control on the
   * right. Used by every settings primitive — `SettingsToggle`,
   * `SettingsTextField`, `SettingsSelect`, `SettingsLink`,
   * `SettingsDangerButton` all consume this for layout.
   *
   * Save state surfaces as a small badge to the right of the control
   * area: a spinner during `saving`, a check on `saved` (auto-fades),
   * an error pill with retry hover-text on `error`. Per-row state
   * mirrors the autosave model (Spyglass parity); the dialog footer
   * also surfaces overall status, but per-row is what the user
   * actually looks at when they flip a toggle.
   *
   * Layout uses CSS grid so very long descriptions wrap under the
   * title without pushing the control off-axis; the right column
   * stays a fixed minimum width so all controls in a card line up.
   */
  import type { Snippet } from 'svelte';

  export type SaveState =
    | { kind: 'idle' }
    | { kind: 'saving' }
    | { kind: 'saved' }
    | { kind: 'error'; message: string };

  interface Props {
    /** Row title. Short, sentence-case. */
    title: string;
    /** Optional secondary description, muted. Inline help for the
     * row — no tooltips per Spyglass convention. */
    description?: string;
    /** Optional id to wire up `for=` on a contained label. The
     * primitives that need it (TextField, Select, Toggle) accept a
     * matching prop and forward it to their inner control. */
    controlId?: string;
    /** Save state for this row. Idle by default. */
    state?: SaveState;
    /** Control snippet — the actual input/toggle/etc. Rendered in
     * the right column. */
    control: Snippet;
    /** Optional extra block below the title/description (left col).
     * Useful for permission-state explanations on the notify row. */
    footnote?: Snippet;
  }

  let {
    title,
    description,
    controlId,
    state = { kind: 'idle' },
    control,
    footnote
  }: Props = $props();
</script>

<div
  class="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 items-start px-4 py-3"
  data-testid="settings-row"
>
  <div class="min-w-0 flex flex-col gap-0.5">
    {#if controlId}
      <label
        for={controlId}
        class="text-sm font-medium text-slate-200 cursor-pointer w-fit"
      >
        {title}
      </label>
    {:else}
      <span class="text-sm font-medium text-slate-200">{title}</span>
    {/if}
    {#if description}
      <span class="text-xs text-slate-400 leading-snug">{description}</span>
    {/if}
    {#if footnote}
      <div class="text-xs text-slate-500 leading-snug pt-1">
        {@render footnote()}
      </div>
    {/if}
  </div>

  <div class="flex items-center gap-2 shrink-0">
    {@render control()}
    {#if state.kind === 'saving'}
      <span
        class="text-[11px] text-slate-500 italic"
        role="status"
        aria-live="polite"
      >
        Saving…
      </span>
    {:else if state.kind === 'saved'}
      <span
        class="text-[11px] text-emerald-400"
        role="status"
        aria-live="polite"
      >
        Saved
      </span>
    {:else if state.kind === 'error'}
      <span
        class="text-[11px] text-rose-400"
        role="alert"
        title={state.message}
      >
        Error
      </span>
    {/if}
  </div>
</div>
