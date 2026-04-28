<script lang="ts">
  import type { TokenTotals } from '$lib/api';

  /**
   * Compact token readout for subscription-mode users. Shown in the
   * conversation header in place of the dollar figure — Max/Pro
   * subscribers pay a flat rate, so tokens are the honest quota proxy
   * we can actually expose (Anthropic's Max-plan quota percentages
   * are not available via any public API).
   *
   * Render:
   *   `123.4k in · 45.6k out · 1.2M cache`
   *
   * `in` = fresh input tokens (cache miss). `out` = output tokens.
   * `cache` = cache_read + cache_creation combined, because the UI
   * mostly wants "how much cached context is riding along" rather
   * than the read-vs-create split.
   */

  type Props = {
    /** Null while the first fetch is in flight — component renders
     * a placeholder so header height doesn't jump when the totals
     * arrive a moment later. */
    totals: TokenTotals | null;
    /** Compact mode drops the suffix labels ("in", "out", "cache")
     * so three numbers fit in a session-card row. Header uses the
     * full form. */
    compact?: boolean;
  };

  let { totals, compact = false }: Props = $props();

  /** Render as k/M with one decimal when under 100k/M, zero above.
   * Matches the convention people expect for token counts: 12.3k,
   * 456k, 1.2M, 34M. Zero renders as plain "0". */
  function formatTokens(n: number): string {
    if (!Number.isFinite(n) || n < 0) return '—';
    if (n === 0) return '0';
    if (n < 1_000) return String(n);
    if (n < 1_000_000) {
      const k = n / 1_000;
      return `${k < 100 ? k.toFixed(1) : Math.round(k)}k`;
    }
    const m = n / 1_000_000;
    return `${m < 100 ? m.toFixed(1) : Math.round(m)}M`;
  }

  const cacheTotal = $derived(
    (totals?.cache_read_tokens ?? 0) + (totals?.cache_creation_tokens ?? 0)
  );
</script>

{#if totals === null}
  <span class="font-mono text-slate-600" aria-label="Loading token totals">—</span>
{:else if compact}
  <span
    class="font-mono text-slate-500"
    title="Fresh input · output · cached (read + created) tokens"
    aria-label="Token usage summary"
  >
    {formatTokens(totals.input_tokens)}/{formatTokens(totals.output_tokens)}/{formatTokens(
      cacheTotal
    )}
  </span>
{:else}
  <span
    class="font-mono text-slate-400"
    title={`input ${totals.input_tokens.toLocaleString()} · output ${totals.output_tokens.toLocaleString()} · ` +
      `cache read ${totals.cache_read_tokens.toLocaleString()} · ` +
      `cache create ${totals.cache_creation_tokens.toLocaleString()}`}
    aria-label="Token usage summary"
  >
    {formatTokens(totals.input_tokens)} in · {formatTokens(totals.output_tokens)} out · {formatTokens(
      cacheTotal
    )} cache
  </span>
{/if}
