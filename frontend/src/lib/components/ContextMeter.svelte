<script lang="ts">
  import type { ContextUsageState } from '$lib/stores/conversation.svelte';

  /**
   * Compact context-window pressure indicator shown in the conversation
   * header. Sourced from `ClaudeSDKClient.get_context_usage()` emitted
   * as a `context_usage` WS event after every completed turn and seeded
   * from the session row's cached columns (migration 0013) on first
   * paint.
   *
   * Intent: tell Dave at a glance when a session is approaching
   * auto-compact or hard-cap so he can checkpoint / fork / delegate to
   * a sub-agent *before* the detail loss he hit today. The bands are
   * chosen to give him runway, not surprise him:
   *
   *   < 50%  — slate  (ignore: plenty of room)
   *   50-74% — amber  (start watching; any big research turn will push past)
   *   75-89% — orange (compact imminent; decide now — fork or checkpoint)
   *   ≥ 90%  — red    (compact has almost certainly fired or is about to)
   *
   * Auto-compact-disabled sessions bump one band earlier so the user
   * sees "decide now" territory at 50% instead of 75% — without the
   * compaction safety net, the cliff is closer.
   */

  type Props = {
    /** Null while no context snapshot has been captured for this
     * session yet (new session, or pre-migration-0013 session that
     * hasn't completed a turn since the upgrade). */
    context: ContextUsageState | null;
  };

  let { context }: Props = $props();

  /** One-decimal k/M formatter matching TokenMeter's convention. */
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

  /** Resolve the threshold band for a given percentage + auto-compact
   * flag. Returns a Tailwind class set (text + background) for the
   * pill. Shifted one band earlier when auto-compact is off because
   * there's no safety net catching an overflow. */
  function bandClass(pct: number, autoCompact: boolean): string {
    const [yellow, orange, red] = autoCompact ? [50, 75, 90] : [40, 60, 80];
    if (pct >= red) return 'text-red-100 bg-red-900/60';
    if (pct >= orange) return 'text-orange-100 bg-orange-900/60';
    if (pct >= yellow) return 'text-amber-100 bg-amber-900/60';
    return 'text-slate-400 bg-slate-800/60';
  }

  const pill = $derived(
    context
      ? {
          class: bandClass(context.percentage, context.isAutoCompactEnabled),
          label: `${Math.round(context.percentage)}%`,
          title:
            `Context: ${formatTokens(context.totalTokens)} / ` +
            `${formatTokens(context.maxTokens)} tokens ` +
            `(${context.percentage.toFixed(1)}%). ` +
            `Auto-compact ${context.isAutoCompactEnabled ? 'on' : 'off'}.`
        }
      : null
  );
</script>

{#if pill}
  <span
    class="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[10px] {pill.class}"
    title={pill.title}
    aria-label={pill.title}
  >
    ctx {pill.label}
  </span>
{/if}
