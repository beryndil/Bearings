<script lang="ts">
  /** Defaults section — default model + default working directory.
   * Both pre-fill the corresponding fields when starting a new
   * session. Empty string saves as null (cleared); the store's
   * trim-and-coalesce server validator handles whitespace-only. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsDivider from '../SettingsDivider.svelte';
  import SettingsTextField from '../SettingsTextField.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';

  let model = $state(preferences.defaultModel);
  let workdir = $state(preferences.defaultWorkingDir);

  async function saveModel(next: string): Promise<void> {
    const trimmed = next.trim();
    await preferences.update({
      default_model: trimmed === '' ? null : next
    });
  }

  async function saveWorkdir(next: string): Promise<void> {
    const trimmed = next.trim();
    await preferences.update({
      default_working_dir: trimmed === '' ? null : next
    });
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-defaults">
  <SettingsCard>
    <SettingsTextField
      title="Default model"
      description="Pre-fills the model field when starting a new session."
      bind:value={model}
      placeholder="claude-opus-4-7"
      monospace
      onChange={saveModel}
    />
    <SettingsDivider inset />
    <SettingsTextField
      title="Default working directory"
      description="Pre-fills the working dir when starting a new session."
      bind:value={workdir}
      placeholder="/home/…"
      monospace
      onChange={saveWorkdir}
    />
  </SettingsCard>
</div>
