<script lang="ts">
  /** The header that sits above a group of `SettingsCard`s in a
   * section pane. Matches Spyglass's `SectionHeader`: uppercase label
   * (small, primary-tinted), optional leading icon, trailing rule
   * that takes the remaining width.
   *
   * Used at most once per pane — settings panes that need multiple
   * groupings should use multiple `SettingsCard`s with `title=` props
   * instead, reserving this primitive for the top-level "this is
   * what this section is" banner.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    /** Section label. Rendered uppercase by CSS. */
    label: string;
    /** Optional leading icon, supplied as a snippet so the caller
     * controls colors/sizing without a brittle `iconComponent` prop. */
    icon?: Snippet;
    /** Optional id for screen-reader association via aria-labelledby. */
    id?: string;
  }

  let { label, icon, id }: Props = $props();
</script>

<header class="flex items-center gap-2 px-1">
  {#if icon}
    <span class="text-sky-400 shrink-0">{@render icon()}</span>
  {/if}
  <h2
    {id}
    class="text-[11px] font-semibold uppercase tracking-wider text-sky-400"
  >
    {label}
  </h2>
  <span
    class="flex-1 border-t border-slate-800 ml-2"
    aria-hidden="true"
  ></span>
</header>
