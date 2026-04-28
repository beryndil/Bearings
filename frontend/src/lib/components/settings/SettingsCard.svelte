<script lang="ts">
  /** Surface container for a logical group of settings rows. Matches
   * Spyglass's `ResultCard` role: rounded, bordered, padded, with
   * children stacked vertically. Consumers compose
   * `<SettingsRow/>` plus `<SettingsDivider/>` between rows.
   *
   * Border + bg use the existing themed slate tokens, so the card
   * automatically re-tints when `data-theme` flips.
   *
   * Optional `title` prop renders an inline header inside the card,
   * useful for sub-groupings inside a section that don't deserve a
   * full `SettingsSectionHeader`.
   */
  import type { Snippet } from 'svelte';

  interface Props {
    /** Optional inline header text. */
    title?: string;
    /** Optional id for screen-reader association via aria-labelledby. */
    titleId?: string;
    children: Snippet;
  }

  let { title, titleId, children }: Props = $props();
</script>

<section
  class="flex flex-col rounded-lg border border-slate-800
    bg-slate-900/60 shadow-sm"
  aria-labelledby={titleId}
>
  {#if title}
    <h3
      id={titleId}
      class="px-4 pb-2 pt-3 text-xs font-medium uppercase tracking-wide text-slate-400"
    >
      {title}
    </h3>
  {/if}
  {@render children()}
</section>
