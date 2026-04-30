<script lang="ts">
  /**
   * Claude logomark — the actual Anthropic burst, fetched from
   * `claude.ai`'s static asset bundle and stored at
   * `frontend/static/claude-logomark.svg`. Served at `/claude-logomark.svg`
   * by SvelteKit's static adapter; the FastAPI mount point passes
   * static files through unchanged.
   *
   * Used in `MessageTurn` to identify assistant rows. Single-asset
   * `<img>` rather than inline SVG so the file caches at the network
   * layer and the component stays trivial.
   *
   * Colour is fixed to Anthropic's brand copper (`#D97757`) by the
   * source SVG's `fill` attribute. If the design ever needs a tinted
   * variant, swap the asset for an inline `<svg>` whose path inherits
   * `currentColor` — out of scope for v1.
   *
   * Size defaults to 36px to match the user-avatar height in the
   * message header. Bump for hero / overlay use.
   */
  interface Props {
    /** Square width/height in px. */
    size?: number;
    /** Extra classes for spacing / sizing from the caller. */
    class?: string;
    /** Accessible label. Omit for a decorative role. */
    label?: string;
  }

  let { size = 36, class: klass = '', label }: Props = $props();
</script>

<img
  src="/claude-logomark.svg"
  alt={label ?? ''}
  width={size}
  height={size}
  class="claude-mark {klass}"
  aria-hidden={label ? undefined : 'true'}
  data-testid="claude-mark"
/>

<style>
  .claude-mark {
    display: inline-block;
    vertical-align: middle;
    flex-shrink: 0;
  }
</style>
