<script lang="ts">
  /** Appearance section — theme picker (server-synced via the
   * `preferences` store) plus a timezone override (local-only,
   * per-device, via `displaySettings`). Theme selection autosaves
   * immediately (no debounce, single click); the preferences store's
   * `apply()` flips `<html data-theme>` and the `<meta theme-color>`
   * tag synchronously on success, so the visual change lands in the
   * same tick as the network success rather than after a re-render.
   *
   * Timezone is intentionally local-only (localStorage). A laptop in
   * CT, a desktop in UTC, and a phone abroad each want their own
   * display tz — server-syncing it would require a migration + DTO
   * + endpoint and would fight the user's mental model. If
   * cross-device sync becomes desirable later, the migration 0026
   * preferences row is where it would land and the localStorage
   * value can be promoted cleanly. The locale picker is deferred
   * for the same reason; helpers accept locale already, so a
   * follow-up PR can surface it without touching the helpers. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsDivider from '../SettingsDivider.svelte';
  import SettingsSelect from '../SettingsSelect.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';
  import { displaySettings } from '$lib/stores/display-settings.svelte';

  let theme = $state(preferences.theme ?? 'midnight-glass');

  // 'auto' sentinel = follow browser default (`null` in the store);
  // SettingsSelect can't bind to `null` so the UI translates back
  // and forth on read/write.
  const AUTO_TZ = 'auto';
  let timezone = $state<string>(displaySettings.timezone ?? AUTO_TZ);

  const themeOptions = [
    { value: 'midnight-glass', label: 'Midnight Glass (warm-navy, glass panels)' },
    { value: 'default', label: 'Default (Tailwind classic dark)' },
    { value: 'paper-light', label: 'Paper Light (cream, flat)' }
  ];

  /** Curated IANA zones. Covers Dave (CT), the most common US zones,
   * UTC for ops/audit work, the major European hubs, and the two
   * Asian zones a Bearings user is most likely to need. Custom-zone
   * text input is deferred — `Pacific/Marquesas` users can edit
   * localStorage `bearings:display:timezone` directly until a
   * follow-up adds a freeform field. */
  const timezoneOptions = [
    { value: AUTO_TZ, label: 'Auto (browser default)' },
    { value: 'UTC', label: 'UTC' },
    { value: 'America/New_York', label: 'New York (Eastern)' },
    { value: 'America/Chicago', label: 'Chicago (Central)' },
    { value: 'America/Denver', label: 'Denver (Mountain)' },
    { value: 'America/Los_Angeles', label: 'Los Angeles (Pacific)' },
    { value: 'Europe/London', label: 'London' },
    { value: 'Europe/Paris', label: 'Paris / Berlin' },
    { value: 'Asia/Tokyo', label: 'Tokyo' },
    { value: 'Asia/Shanghai', label: 'Shanghai' }
  ];

  async function saveTheme(next: string): Promise<void> {
    await preferences.update({ theme: next });
  }

  function saveTimezone(next: string): void {
    displaySettings.setTimezone(next === AUTO_TZ ? null : next);
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-appearance">
  <SettingsCard>
    <SettingsSelect
      title="Theme"
      description="Saved per device. Applies immediately."
      bind:value={theme}
      options={themeOptions}
      onChange={saveTheme}
    />
    <SettingsDivider inset />
    <SettingsSelect
      title="Timezone"
      description="Display timezone for timestamps in this UI. Saved per device — the server keeps every timestamp in UTC."
      bind:value={timezone}
      options={timezoneOptions}
      onChange={saveTimezone}
    />
  </SettingsCard>
</div>
