<script lang="ts">
  /**
   * Settings page — Appearance section per
   * ``docs/behavior/themes.md`` §"Theme picker UI". Renders the theme
   * picker and (in future items) the display-timezone selector +
   * other Appearance controls.
   *
   * Reachable via the ``/settings`` route. The center column of
   * ``+layout.svelte`` renders this page when no session is selected
   * (i.e. the ``children`` snippet branch).
   */
  import { THEME_STRINGS } from "$lib/config";
  import ThemePicker from "$lib/themes/ThemePicker.svelte";
</script>

<section class="settings-page p-4" data-testid="settings-page" aria-label="Settings">
  <h1 class="mb-4 text-lg font-semibold text-fg-strong">{THEME_STRINGS.appearanceHeading}</h1>
  <ThemePicker />
</section>
