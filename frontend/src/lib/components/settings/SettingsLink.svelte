<script lang="ts">
  /** A row that acts as a clickable link / action. Used for "Test
   * connection" inside the Authentication section, "View changelog"
   * inside About, etc. Renders the title + description as a
   * `SettingsRow`, but the entire row surface is clickable; the
   * right column shows a chevron or supplied trailing text.
   *
   * Two flavours, mutually exclusive:
   *   - `href`: renders an `<a>`. Used for external links (repo,
   *     changelog). Always opens in a new tab with `rel=noopener`.
   *   - `onClick`: renders a `<button>`. Used for in-app actions
   *     (test connection, copy token).
   */
  import SettingsRow, { type SaveState } from './SettingsRow.svelte';

  interface Props {
    title: string;
    description?: string;
    /** External URL — renders <a target=_blank>. */
    href?: string;
    /** Click handler — renders <button>. */
    onClick?: () => Promise<void> | void;
    /** Trailing text to the right of the title (e.g. "v0.20.5"). */
    trailing?: string;
    /** Disabled state for button mode. */
    disabled?: boolean;
  }

  let { title, description, href, onClick, trailing, disabled = false }: Props = $props();

  let saveState = $state<SaveState>({ kind: 'idle' });

  async function fire(): Promise<void> {
    if (!onClick || disabled) return;
    saveState = { kind: 'saving' };
    try {
      await onClick();
      saveState = { kind: 'idle' };
    } catch (err) {
      saveState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }
</script>

<SettingsRow {title} {description} state={saveState}>
  {#snippet control()}
    {#if href}
      <a
        {href}
        target="_blank"
        rel="noopener noreferrer"
        class="text-sm text-sky-400 hover:text-sky-300 hover:underline
          focus:underline focus:outline-none"
        data-testid="settings-link"
      >
        {trailing ?? 'Open ↗'}
      </a>
    {:else if onClick}
      <button
        type="button"
        class="text-sm text-sky-400 hover:text-sky-300 hover:underline
          focus:underline focus:outline-none disabled:cursor-not-allowed
          disabled:opacity-50"
        {disabled}
        onclick={fire}
        data-testid="settings-link"
      >
        {trailing ?? 'Open'}
      </button>
    {:else if trailing}
      <span class="font-mono text-sm text-slate-300">{trailing}</span>
    {/if}
  {/snippet}
</SettingsRow>
