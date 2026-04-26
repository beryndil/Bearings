<script lang="ts">
  /** 1px hairline used between rows inside a `SettingsCard`, and as
   * the trailing rule in `SettingsSectionHeader`. Themes through the
   * existing `slate-800` token so it tints with the active theme.
   *
   * Two variants:
   *   - default: a horizontal divider that fills its parent's width.
   *   - inset:   the same line, but inset 12px from the left to read
   *              as "row separator" rather than "section break". This
   *              is what `SettingsCard`'s row spacing uses internally.
   */
  interface Props {
    /** When true, inset 12px from the left edge. Default false. */
    inset?: boolean;
  }
  let { inset = false }: Props = $props();
</script>

<hr
  class="border-0 border-t border-slate-800 {inset ? 'ml-3' : ''}"
  aria-hidden="true"
/>
