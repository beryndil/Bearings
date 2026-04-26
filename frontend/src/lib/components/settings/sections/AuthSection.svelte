<script lang="ts">
  /** Authentication section — auth token only.
   *
   * Carve-out preserved from the original Settings.svelte: the token
   * is intentionally client-side. The server can't authorize itself
   * on its own stored token, so the bearer that gates `/api/preferences`
   * has to live in localStorage. `prefs.save()` writes it; a non-empty
   * value while auth status is `required` or `invalid` also feeds
   * the auth store so the auth-gate retries on the new token without
   * a reload.
   *
   * No PATCH to /api/preferences from here — the autosave path is the
   * client store, not the server. The primitive still surfaces a
   * per-row 'Saved' indicator for the localStorage write. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsTextField from '../SettingsTextField.svelte';
  import { prefs } from '$lib/stores/prefs.svelte';
  import { auth } from '$lib/stores/auth.svelte';

  let token = $state(prefs.authToken);

  function save(next: string): void {
    prefs.save({ authToken: next });
    const trimmed = next.trim();
    if (trimmed && (auth.status === 'required' || auth.status === 'invalid')) {
      auth.saveToken(trimmed);
    }
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-auth">
  <SettingsCard>
    <SettingsTextField
      title="Auth token"
      description="Stays in localStorage on this device only. Used when the server requires it."
      bind:value={token}
      password
      monospace
      placeholder="leave empty if the server has auth disabled"
      onChange={save}
    />
  </SettingsCard>
</div>
