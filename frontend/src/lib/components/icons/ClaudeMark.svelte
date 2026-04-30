<script lang="ts">
  /**
   * Claude logomark — the four-pointed sparkle Anthropic uses for
   * Claude's brand. Used in `MessageTurn` to identify assistant
   * messages so the role row carries an icon next to the text label
   * (matching the user row's avatar / initials circle).
   *
   * Geometry: a four-pointed star with the bottom-right point
   * extended longer than the others, which is the silhouette of the
   * Anthropic mark. Drawn from a single path so the fill colour can
   * be swapped without re-exporting the asset. Colour defaults to
   * Anthropic's brand copper (`#cc785c`) but is overridable via the
   * `color` prop or the surrounding `currentColor` chain — pass
   * `color="currentColor"` to inherit the text colour, e.g. when the
   * mark sits inside a muted-slate header.
   *
   * Size defaults to 14px to slot inline with the existing 10-pt
   * uppercase `tracking-wider` role labels in the message header.
   * Bump for overlay / hero uses.
   */
  interface Props {
    /** Square width/height in px. */
    size?: number;
    /** Fill colour. Defaults to Anthropic's brand copper. Pass
     * `currentColor` to inherit from the surrounding text colour. */
    color?: string;
    /** Extra classes for spacing / sizing from the caller. */
    class?: string;
    /** Accessible label. Omit for a decorative role. */
    label?: string;
  }

  let { size = 14, color = '#cc785c', class: klass = '', label }: Props = $props();
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 100 100"
  width={size}
  height={size}
  class="claude-mark {klass}"
  role={label ? 'img' : undefined}
  aria-label={label}
  aria-hidden={label ? undefined : 'true'}
  data-testid="claude-mark"
>
  {#if label}
    <title>{label}</title>
  {/if}
  <!-- Four-pointed sparkle. The bottom-right point is intentionally
       longer; that asymmetry is what reads as the Anthropic mark
       rather than a generic four-pointed star. Single path so a
       colour swap is one attribute. -->
  <path
    d="M50 5
       L57 43
       L95 50
       L57 57
       L50 95
       L43 57
       L5 50
       L43 43
       Z"
    fill={color}
  />
</svg>

<style>
  .claude-mark {
    display: inline-block;
    vertical-align: middle;
    flex-shrink: 0;
  }
</style>
