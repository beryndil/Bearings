<script lang="ts">
  /** Profile section — display name only for now. The local
   * `displayName` mirror seeds from the store on mount and rebinds
   * to the field's autosave; we don't subscribe reactively to
   * `preferences.displayName` because (a) the store mutates its
   * `row` mid-PATCH which would clobber an in-flight typed edit,
   * and (b) autosave debounces 400ms, so the field is the source
   * of truth between the user's keystroke and the PATCH response. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsTextField from '../SettingsTextField.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';

  let displayName = $state(preferences.displayName ?? '');

  async function save(next: string): Promise<void> {
    const trimmed = next.trim();
    await preferences.update({
      display_name: trimmed === '' ? null : next,
    });
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-profile">
  <SettingsCard>
    <SettingsTextField
      title="Display name"
      description="Replaces 'user' on your message bubbles. Up to 64 characters."
      bind:value={displayName}
      placeholder="e.g. Dave"
      maxlength={64}
      onChange={save}
    />
  </SettingsCard>
</div>
