<script lang="ts">
  /** Notifications section — single toggle for completion notifications.
   *
   * Carve-out preserved from the original Settings.svelte: when the
   * user flips the toggle ON, we request browser permission *first*,
   * BEFORE the PATCH. If the user denies, we throw — the toggle
   * primitive's rollback path then visibly reverts the flip and
   * surfaces the error, which is exactly what we want UX-wise.
   *
   * `permission` state is refreshed in two places: on mount (so a
   * user who flipped the system permission outside the dialog sees
   * it on next open), and after every requestPermission call. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsToggle from '../SettingsToggle.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';
  import { notifyPermission, notifySupported, requestNotifyPermission } from '$lib/utils/notify';

  let enabled = $state(preferences.notifyOnComplete);
  let permission = $state(notifyPermission());

  const supported = $derived(notifySupported());
  const blocked = $derived(permission === 'denied');

  async function save(next: boolean): Promise<void> {
    if (next) {
      // Ask the browser the moment the user opts in, not at some
      // separate Save click. Gives them a chance to flip the prompt
      // while the dialog is still open — and makes "I enabled it
      // but nothing fires" a single UX step to debug.
      permission = await requestNotifyPermission();
      if (permission !== 'granted') {
        throw new Error('Notifications are blocked in browser settings.');
      }
    }
    await preferences.update({ notify_on_complete: next });
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-notifications">
  <SettingsCard>
    <SettingsToggle
      title="Notify when Claude finishes replying"
      description="Fires a tray notification for each completed agent turn — only while this tab is hidden or unfocused."
      bind:checked={enabled}
      disabled={!supported || blocked}
      onChange={save}
    >
      {#snippet footnote()}
        {#if !supported}
          Your browser does not support desktop notifications.
        {:else if blocked}
          Blocked in browser settings — re-allow notifications for this site, then re-toggle.
        {/if}
      {/snippet}
    </SettingsToggle>
  </SettingsCard>
</div>
