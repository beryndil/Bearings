<script lang="ts">
  import type { ReorgAudit } from '$lib/api';
  import { formatAbsolute } from '$lib/utils/datetime';

  // Slice 5 of the Session Reorg plan
  // (`~/.claude/plans/sparkling-triaging-otter.md`). Inline divider
  // rendered in the source conversation to mark "at this point N
  // messages moved/split/merged to another session." Persistent: the
  // backend keeps the row past the 30s undo window so Dave has a
  // trail of his triage decisions.
  //
  // When `target_session_id` is null the target has been deleted
  // since the op ran (FK is `ON DELETE SET NULL`); we fall back to
  // the snapshotted title and skip the jump-to link.

  type Props = {
    audit: ReorgAudit;
    /** Fired when the user clicks the target title. The parent wires
     * this to `sessions.select(targetId)` so the conversation switches
     * over. Skipped entirely when the target is gone. */
    onJumpTo?: (targetId: string) => void;
  };

  const { audit, onJumpTo }: Props = $props();

  const verb = $derived(
    audit.op === 'move' ? 'Moved' : audit.op === 'split' ? 'Split off' : 'Merged'
  );

  const targetLabel = $derived(audit.target_title_snapshot ?? '(untitled)');

  /** Audit-row stamp uses the centralized `formatAbsolute` so locale
   * and timezone overrides flow through (§32). Empty-string fallback
   * gives the row a deterministic shape if the wire timestamp is
   * malformed. */
  const stamp = $derived(formatAbsolute(audit.created_at) || audit.created_at);

  function onClickTarget() {
    if (!audit.target_session_id || !onJumpTo) return;
    onJumpTo(audit.target_session_id);
  }
</script>

<div
  class="flex items-center gap-3 px-2 py-1.5 text-[11px] text-slate-500"
  role="note"
  aria-label="Reorg audit"
  data-testid="reorg-audit-divider"
  data-audit-id={audit.id}
  data-audit-op={audit.op}
>
  <div class="flex-1 border-t border-dashed border-slate-800"></div>
  <span class="whitespace-nowrap">
    {verb}
    {audit.message_count}
    message{audit.message_count === 1 ? '' : 's'}
    to
    {#if audit.target_session_id}
      <button
        type="button"
        class="text-emerald-400 underline decoration-dotted underline-offset-2 hover:text-emerald-300"
        onclick={onClickTarget}
        data-testid="reorg-audit-jump"
      >
        "{targetLabel}"
      </button>
    {:else}
      <span class="italic text-slate-400" data-testid="reorg-audit-deleted-target">
        "{targetLabel}" (deleted session)
      </span>
    {/if}
    · <span class="font-mono">{stamp}</span>
  </span>
  <div class="flex-1 border-t border-dashed border-slate-800"></div>
</div>
