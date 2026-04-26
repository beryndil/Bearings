<script lang="ts">
  /** About section — version, build identity, project links.
   *
   * Pulls from /api/version (existing endpoint, also consumed by the
   * seamless-reload watcher), which returns:
   *   - `version`: the release string, e.g. "0.20.5", from
   *     `bearings.__version__` (resolved at install time from
   *     `pyproject.toml`).
   *   - `build`: nanosecond mtime of `dist/index.html`, or null when
   *     the static bundle isn't present (dev workflow). We format the
   *     mtime as a localized timestamp; `null` falls through to a
   *     "dev build" label.
   *
   * Commit hash isn't exposed by the API yet — it would require either
   * shelling out to git at server start (unreliable when installed as
   * a wheel) or build-time injection. Tracked as a follow-up; not v1.
   */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsDivider from '../SettingsDivider.svelte';
  import SettingsLink from '../SettingsLink.svelte';
  import { fetchVersion, type VersionInfo } from '$lib/api/version';

  let info = $state<VersionInfo | null>(null);
  let error = $state<string | null>(null);

  /** Format the `build` token (nanosecond mtime) as a local timestamp.
   * Returns "dev build" when build is null (no dist directory — the
   * developer is running the API without having built the frontend
   * yet). Returns "unknown" if the value can't be parsed; the API
   * promises a numeric string but we don't trust silently. */
  function formatBuild(build: string | null): string {
    if (build === null) return 'dev build';
    const ns = Number(build);
    if (!Number.isFinite(ns) || ns <= 0) return 'unknown';
    const ms = Math.floor(ns / 1_000_000);
    return new Date(ms).toLocaleString();
  }

  $effect(() => {
    fetchVersion()
      .then((v) => {
        info = v;
      })
      .catch((err: unknown) => {
        error = err instanceof Error ? err.message : String(err);
      });
  });
</script>

<div class="flex flex-col gap-4" data-testid="settings-section-about">
  <SettingsCard>
    <SettingsLink
      title="Version"
      description="Bearings package version, resolved from pyproject.toml at install."
      trailing={info ? `v${info.version}` : error ? 'unavailable' : '…'}
    />
    <SettingsDivider inset />
    <SettingsLink
      title="Build"
      description="Identifies the running frontend bundle. Bumps on every npm run build."
      trailing={info ? formatBuild(info.build) : error ? 'unavailable' : '…'}
    />
    <SettingsDivider inset />
    <SettingsLink
      title="Repository"
      description="Source, issues, and releases on GitHub."
      href="https://github.com/Beryndil/Bearings"
      trailing="Beryndil/Bearings ↗"
    />
  </SettingsCard>

  {#if error}
    <p class="text-xs text-rose-400" role="alert">
      Could not reach /api/version: {error}
    </p>
  {/if}
</div>
