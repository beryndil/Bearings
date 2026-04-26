<script lang="ts">
  /** About section — version, build identity, project links, dev
   * credit + coffee CTA.
   *
   * Pulls from /api/version (existing endpoint, also consumed by the
   * seamless-reload watcher), which returns:
   *   - `version`: the release string, e.g. "0.20.5", from
   *     `bearings.__version__` (resolved at install time from
   *     `pyproject.toml`).
   *   - `build`: nanosecond mtime of `dist/index.html`, or null when
   *     the static bundle isn't present (dev workflow). Formatted as
   *     a localized timestamp; null falls through to "dev build".
   *
   * The dev-credit + coffee block mirrors Spyglass's About screen
   * treatment (Spyglass-Android `about/AboutScreen.kt`):
   *   - "by Beryndil" link → hardknocks.university/developer.html
   *   - prominent CTA block: small "Enjoy Bearings?" eyebrow over a
   *     larger "Buy Me a Cup of Coffee" line, primary-accent
   *     background, rounded, centered, click opens the same URL.
   */
  import SettingsCard from '../SettingsCard.svelte';
  import SettingsDivider from '../SettingsDivider.svelte';
  import SettingsLink from '../SettingsLink.svelte';
  import { fetchVersion, type VersionInfo } from '$lib/api/version';

  const COFFEE_URL = 'https://hardknocks.university/developer.html';

  let info = $state<VersionInfo | null>(null);
  let error = $state<string | null>(null);

  /** Format the `build` token (nanosecond mtime) as a local timestamp.
   * `null` (no dist directory — dev) → 'dev build'. Unparseable input
   * → 'unknown'; the API contract promises a numeric string but we
   * don't trust silently. */
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

  <!-- Coffee CTA — mirrors the prominent button block in Spyglass-
       Android's AboutScreen.kt. Stacked text on a primary-accent
       background, the whole block is clickable. -->
  <a
    href={COFFEE_URL}
    target="_blank"
    rel="noopener noreferrer"
    class="block rounded-lg bg-sky-600 hover:bg-sky-500 transition-colors
      px-5 py-3 text-center
      focus:outline-none focus:ring-2 focus:ring-sky-300/60
      focus:ring-offset-2 focus:ring-offset-slate-900"
    data-testid="settings-coffee-cta"
  >
    <span class="block text-xs text-sky-100">Enjoy Bearings?</span>
    <span class="block text-base font-semibold text-white">
      Buy Me a Cup of Coffee
    </span>
  </a>

  <p class="text-center text-xs text-slate-500">
    by
    <a
      href={COFFEE_URL}
      target="_blank"
      rel="noopener noreferrer"
      class="text-sky-400 hover:text-sky-300 hover:underline"
    >Beryndil</a>
    — Winnfield, Louisiana
  </p>

  {#if error}
    <p class="text-xs text-rose-400" role="alert">
      Could not reach /api/version: {error}
    </p>
  {/if}
</div>
