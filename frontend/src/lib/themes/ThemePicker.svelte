<script lang="ts">
  /**
   * Theme picker — the dropdown that lives in Settings → Appearance per
   * ``docs/behavior/themes.md`` §"Theme picker UI".
   *
   * The picker has no Save / Apply button; selecting an option commits
   * the change immediately (no debounce, single click) per the doc.
   * Mutation goes through :func:`setTheme`, which applies + persists +
   * updates the store in one shot.
   */
  import { KNOWN_THEMES, THEME_STRINGS, type ThemeId } from "../config";
  import { setTheme, themeStore } from "./store.svelte";

  function handleChange(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement;
    const next = target.value as ThemeId;
    if (KNOWN_THEMES.includes(next)) {
      setTheme(next);
    }
  }
</script>

<div class="theme-picker" data-testid="theme-picker">
  <label class="theme-picker__label" for="theme-picker-select">
    {THEME_STRINGS.pickerLabel}
  </label>
  <select
    id="theme-picker-select"
    class="theme-picker__select bg-surface-1 text-fg-strong"
    aria-label={THEME_STRINGS.pickerAriaLabel}
    data-testid="theme-picker-select"
    value={themeStore.theme}
    onchange={handleChange}
  >
    {#each KNOWN_THEMES as theme (theme)}
      <option value={theme}>{THEME_STRINGS.themeLabels[theme]}</option>
    {/each}
  </select>
  <p class="theme-picker__caption text-fg-muted" data-testid="theme-picker-caption">
    {THEME_STRINGS.pickerCaption}
  </p>
</div>

<style>
  .theme-picker {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-width: 28rem;
  }
  .theme-picker__label {
    font-size: 0.875rem;
    font-weight: 600;
  }
  .theme-picker__select {
    border: 1px solid rgb(var(--bearings-border));
    border-radius: 0.375rem;
    padding: 0.375rem 0.5rem;
    font: inherit;
  }
  .theme-picker__caption {
    font-size: 0.75rem;
  }
</style>
