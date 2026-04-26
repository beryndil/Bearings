<script lang="ts">
  /** Hand-rolled X glyph for close buttons. No icon dependency in
   * this repo (see `icons/SeverityShield.svelte`, `icons/TagIcon.svelte`),
   * so we keep that convention. ViewBox 0 0 16 16 to match the
   * rest of the icons folder; pass `size` to nudge density.
   */
  interface Props {
    /** Width/height in px. 14 reads naturally next to a heading at
     * the dialog densities the settings dialog uses. */
    size?: number;
    /** Hover/screen-reader label. Omit when the parent button already
     * carries an `aria-label` (the icon then becomes purely decorative
     * and gets `aria-hidden` instead). */
    title?: string;
  }

  let { size = 14, title }: Props = $props();
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 16 16"
  width={size}
  height={size}
  aria-hidden={title ? undefined : 'true'}
  role={title ? 'img' : undefined}
  aria-label={title}
  class="inline-block shrink-0"
  fill="none"
  stroke="currentColor"
  stroke-width="1.6"
  stroke-linecap="round"
>
  {#if title}
    <title>{title}</title>
  {/if}
  <path d="M3.5 3.5 L12.5 12.5" />
  <path d="M12.5 3.5 L3.5 12.5" />
</svg>
