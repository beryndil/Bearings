<script lang="ts">
  /** Profile section — display name + avatar. The local `displayName`
   * mirror seeds from the store on mount and rebinds to the field's
   * autosave; we don't subscribe reactively to `preferences.displayName`
   * because (a) the store mutates its `row` mid-PATCH which would
   * clobber an in-flight typed edit, and (b) autosave debounces 400ms,
   * so the field is the source of truth between the user's keystroke
   * and the PATCH response.
   *
   * Avatar: file picker → `preferences.uploadAvatar(file)`. The store
   * applies the response so `avatarUrl` updates the moment the upload
   * lands and the sidebar's `UserIdentityBlock` rerenders. The Clear
   * button calls `preferences.clearAvatar()` (idempotent server-side).
   * Per-row state mirrors the SettingsRow autosave pattern — saving /
   * saved / error pills surface in the row's right column. */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsRow, { type SaveState } from '../SettingsRow.svelte';
  import SettingsTextField from '../SettingsTextField.svelte';
  import { preferences } from '$lib/stores/preferences.svelte';

  let displayName = $state(preferences.displayName ?? '');
  let avatarState = $state<SaveState>({ kind: 'idle' });
  let fileInput: HTMLInputElement | undefined = $state();
  let avatarUrl = $derived(preferences.avatarUrl);

  // Mirrors the backend `_ALLOWED_MIME` allowlist. A mismatch here is
  // a UX papercut at worst (browser file picker shows different
  // options than the server accepts) — the server still validates.
  const ACCEPT_MIME = 'image/png,image/jpeg,image/webp';

  async function save(next: string): Promise<void> {
    const trimmed = next.trim();
    await preferences.update({
      display_name: trimmed === '' ? null : next,
    });
  }

  async function onFilePicked(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    avatarState = { kind: 'saving' };
    try {
      await preferences.uploadAvatar(file);
      avatarState = { kind: 'saved' };
    } catch (err) {
      avatarState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err),
      };
    } finally {
      // Reset the input so re-selecting the same file still fires
      // `change` (browsers suppress duplicate selections otherwise).
      if (input) input.value = '';
    }
  }

  async function onClearAvatar(): Promise<void> {
    avatarState = { kind: 'saving' };
    try {
      await preferences.clearAvatar();
      avatarState = { kind: 'saved' };
    } catch (err) {
      avatarState = {
        kind: 'error',
        message: err instanceof Error ? err.message : String(err),
      };
    }
  }
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-profile">
  <SettingsCard>
    <SettingsRow
      title="Avatar"
      description="PNG, JPEG, or WebP. Square crop, scaled to 512×512. 5 MiB max."
      state={avatarState}
    >
      {#snippet control()}
        <div class="flex items-center gap-3">
          {#if avatarUrl}
            <img
              src={avatarUrl}
              alt=""
              class="h-12 w-12 rounded-full object-cover ring-1 ring-slate-700"
              aria-hidden="true"
            />
          {:else}
            <span
              class="flex h-12 w-12 items-center justify-center rounded-full
                bg-slate-800 text-xs text-slate-500 ring-1 ring-slate-700"
              aria-hidden="true"
            >
              none
            </span>
          {/if}
          <input
            bind:this={fileInput}
            type="file"
            accept={ACCEPT_MIME}
            class="hidden"
            onchange={onFilePicked}
            data-testid="avatar-file-input"
          />
          <button
            type="button"
            class="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs
              font-medium text-slate-200 hover:border-slate-600 hover:bg-slate-700
              focus:outline-none focus:ring-2 focus:ring-sky-500"
            onclick={() => fileInput?.click()}
          >
            {avatarUrl ? 'Replace' : 'Upload'}
          </button>
          {#if avatarUrl}
            <button
              type="button"
              class="rounded-md border border-slate-800 px-3 py-1.5 text-xs font-medium
                text-slate-400 hover:border-rose-700 hover:text-rose-300
                focus:outline-none focus:ring-2 focus:ring-rose-500"
              onclick={onClearAvatar}
              data-testid="avatar-clear-button"
            >
              Clear
            </button>
          {/if}
        </div>
      {/snippet}
    </SettingsRow>
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
