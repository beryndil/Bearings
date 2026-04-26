<script lang="ts">
  /** Appearance section — theme picker only for now. Theme selection
   * autosaves immediately (no debounce, single click); the store's
   * `apply()` flips `<html data-theme>` and the `<meta theme-color>`
   * tag synchronously on success, so the visual change lands in the
   * same tick as the network success rather than after a re-render. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsSelect from '../SettingsSelect.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';

  let theme = $state(preferences.theme ?? 'midnight-glass');

  const options = [
    { value: 'midnight-glass', label: 'Midnight Glass (warm-navy, glass panels)' },
    { value: 'default', label: 'Default (Tailwind classic dark)' },
    { value: 'paper-light', label: 'Paper Light (cream, flat)' }
  ];

  async function save(next: string): Promise<void> {
    await preferences.update({ theme: next });
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-appearance">
  <SettingsCard>
    <SettingsSelect
      title="Theme"
      description="Saved per device. Applies immediately."
      bind:value={theme}
      {options}
      onChange={save}
    />
  </SettingsCard>
</div>
